"""Measure bounded real workflows and independently check the original task brief.

Telemetry lives outside immutable run directories. This harness never publishes.
"""
import argparse
from datetime import datetime, timezone
import functools
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urldefrag


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',default='examples/batch7.json')
    parser.add_argument('--lab',default='runs/batch7-lab')
    parser.add_argument('--round',required=True)
    parser.add_argument('--engine',help='Frozen directory containing an autolex package')
    parser.add_argument('--reuse-evidence',action='store_true')
    parser.add_argument('--only',nargs='+')
    parser.add_argument('--resume-existing',action='store_true',help='Explicitly resume an interrupted run while retaining counts and telemetry')
    parser.add_argument('--parent-round',help='Revise a prior round without replacing its artifacts')
    parser.add_argument('--feedback',help='JSON mapping case IDs to concrete reviewer feedback')
    args=parser.parse_args()
    sys.path.insert(0,str(Path(args.engine or Path(__file__).resolve().parents[1]).resolve()))
    from autolex.clients import Model,LexmountFetch
    from autolex.config import load_environment
    from autolex.common import WorkflowError,read_json,write_json,now
    from autolex.workflow import Workflow,STAGES
    from autolex.runner import execute
    load_environment('.env')
    lab=Path(args.lab);lab.mkdir(parents=True,exist_ok=True)
    measure=lab/args.round;measure.mkdir(exist_ok=True)
    cache=lab/'evidence-cache';cache.mkdir(exist_ok=True)
    cases=read_json(args.cases);records=[]
    if args.only:cases=[case for case in cases if case['id'] in args.only]
    engine=Path(sys.modules['autolex.workflow'].__file__).parent
    fingerprint={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in engine.glob('*.py')}
    write_json(measure/'engine.json',{'files':fingerprint,'path':str(engine),'started_at':now(),'reused_evidence':args.reuse_evidence})
    for case in cases:
        name=f'b7-{args.round}-{case["id"]}';root=Path('runs')/name
        resumed=(root/'state.json').exists()
        if resumed:
            old=measure/(case['id']+'.json')
            if old.exists():records.append(read_json(old));continue
            if not args.resume_existing:
                raise WorkflowError('Run already exists without benchmark record; inspect before resuming: '+name)
        previous=read_json(measure/(case['id']+'-telemetry.json')) if resumed and (measure/(case['id']+'-telemetry.json')).exists() else {}
        calls=previous.get('model',[]);fetches=previous.get('fetch',[]);executions=previous.get('execution',[]);stages=previous.get('stages',[])
        def snapshot():write_json(measure/(case['id']+'-telemetry.json'),{'model':calls,'fetch':fetches,'execution':executions,'stages':stages})
        class TimedModel(Model):
            def ask(self,task,context,**kwargs):
                start=time.perf_counter();ok=False;before=self.calls
                try:
                    value=super().ask(task,context,**kwargs);ok=True;return value
                finally:
                    calls.append({'operation':task.split(':',1)[0],'seconds':time.perf_counter()-start,'calls_before':before,'calls_after':self.calls,'ok':ok});snapshot()
        class TimedFetch(LexmountFetch):
            def fetch(self,url):
                start=time.perf_counter();key=hashlib.sha256(url.encode()).hexdigest();cached=args.reuse_evidence and (cache/(key+'.json')).exists();ok=False
                try:
                    result=read_json(cache/(key+'.json')) if cached else super().fetch(url)
                    if not cached:write_json(cache/(key+'.json'),result)
                    ok=True;return result
                finally:
                    fetches.append({'url':url,'seconds':time.perf_counter()-start,'cached':cached,'ok':ok});snapshot()
        def timed_execute(project,**kwargs):
            start=time.perf_counter();result=execute(project,**kwargs)
            executions.append({'project':str(project),'seconds':time.perf_counter()-start,'returncode':result['returncode'],'timeout':result.get('timeout',False)});snapshot()
            return result
        revision=None
        if args.parent_round:
            parent=Path('runs')/f'b7-{args.parent_round}-{case["id"]}'
            feedback=read_json(args.feedback) if args.feedback else {}
            previous_code=(parent/'main.py').read_text()
            if (parent/'candidate.json').exists():
                candidate=read_json(parent/'candidate.json')
                if hashlib.sha256(candidate['code'].encode()).hexdigest()!=candidate.get('sha256'):
                    raise WorkflowError('Changed parent candidate checkpoint')
                previous_code=candidate['code']
            revision={'parent':parent.name,'selected':read_json(parent/'spec.json')['selected'],
                      'previous_code':previous_code,
                      'feedback':feedback.get(case['id'],'Preserve the original brief and fix unsupported citation clauses.')}
        workflow=Workflow(root,'https://browser.lexmount.cn/events/real-task-challenge',brief=case['brief'],model=TimedModel(),fetcher=TimedFetch(),executor=timed_execute,revision=revision)
        for stage in STAGES:
            method=getattr(workflow,stage)
            def timed_stage(method=method,stage=stage):
                start=time.perf_counter();ok=False
                try:value=method();ok=True;return value
                finally:stages.append({'stage':stage,'seconds':time.perf_counter()-start,'ok':ok});snapshot()
            setattr(workflow,stage,timed_stage)
        start=time.perf_counter();error=None
        print('START',name,flush=True)
        try:state=workflow.run()
        except Exception as exc:
            error=str(exc) if isinstance(exc,WorkflowError) else type(exc).__name__
            state=read_json(root/'state.json') if (root/'state.json').exists() else {'status':'blocked'}
        elapsed=time.perf_counter()-start
        if resumed:elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(state['created_at'])).total_seconds()
        original_checks=[]
        if (root/'output.json').exists():
            output=read_json(root/'output.json');points=sum(len(i.get('points',[])) for i in output.get('items',[]));conclusions=len(output.get('conclusions',[]))
            for kind,value in [('points',points),('conclusions',conclusions)]:
                low,high=case[kind];original_checks.append({'criterion':kind,'expected':[low,high],'actual':value,'passed':low<=value<=high})
            allowed={urldefrag(url.rstrip('。，.;'))[0] for url in re.findall(r'https?://[^\s]+',case['brief'])}
            actual={i.get('url') for i in output.get('items',[])}
            original_checks.append({'criterion':'brief_source_allowlist','expected':sorted(allowed),'actual':sorted(actual),'passed':bool(actual) and actual==allowed})
        history=read_json(root/'tests.json') if (root/'tests.json').exists() else {}
        events=read_json(root/'model-events.json') if (root/'model-events.json').exists() else []
        tokens=sum(e.get('usage',{}).get('total_tokens',0) for e in events)
        record={'resumed':resumed,'timing_note':'Includes interruption downtime; incomplete request latency/tokens may be unavailable' if resumed else None,'case':case['id'],'run':name,'status':state.get('status'),'error':error,'seconds':elapsed,'model_calls':state.get('model_calls',0),'tokens_reported':tokens,'attempts':len(history.get('attempts',[])),'original_brief_checks':original_checks,'original_brief_passed':bool(original_checks) and all(x['passed'] for x in original_checks),'facets_for_review':case['facets'],'telemetry':str(measure/(case['id']+'-telemetry.json'))}
        records.append(record);write_json(measure/(case['id']+'.json'),record)
        write_json(measure/'summary.json',{'records':records,'ready':sum(r['status']=='ready' for r in records),'original_brief_passed':sum(r['original_brief_passed'] for r in records),'model_calls':sum(r['model_calls'] for r in records),'total_seconds':sum(r['seconds'] for r in records),'note':'Sequential small-sample experiments; model samples and remote latency vary. Evidence-cache time is reported separately. No publication.'})
        print('DONE',name,record['status'],'calls',record['model_calls'],'seconds',round(elapsed,1),'brief',record['original_brief_passed'],flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
