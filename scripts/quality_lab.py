"""Run bounded, separately versioned experiments and feed actual failures into revisions."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import WorkflowError, read_json, write_json
from autolex.config import load_environment
from autolex.workflow import Workflow


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',default='examples/quality-lab.json')
    parser.add_argument('--rounds',type=int,choices=range(1,4),default=2)
    parser.add_argument('--prefix',default='experiment')
    parser.add_argument('--runs',default='runs')
    parser.add_argument('--visual-feedback',help='UTF-8 findings from actual screenshot inspection')
    args=parser.parse_args()
    if not args.prefix.replace('-','').replace('_','').isalnum():
        parser.error('prefix must contain letters, numbers, underscores or hyphens')
    load_environment('.env')
    cases=read_json(args.cases)
    records=[]
    root=Path(args.runs)
    for case in cases:
        if not case['id'].replace('-','').isalnum():
            parser.error('case id is invalid')
        previous=None
        for version in range(1,args.rounds+1):
            name=f'{args.prefix}-{case["id"]}-v{version}'
            directory=root/name
            revision=None
            if previous and (previous/'spec.json').exists():
                feedback={'prior_status':read_json(previous/'state.json')['status']}
                for artifact in ('tests.json','quality.json','review.json'):
                    if (previous/artifact).exists():feedback[artifact]=read_json(previous/artifact)
                if args.visual_feedback:feedback['visual_findings']=Path(args.visual_feedback).read_text()[:6000]
                revision={'parent':previous.name,'selected':read_json(previous/'spec.json')['selected'],
                          'previous_code':(previous/'main.py').read_text() if (previous/'main.py').exists() else '',
                          'feedback':json.dumps(feedback,ensure_ascii=False)}
            # Resume uses its saved brief/feedback, keeping the experiment immutable.
            exists=(directory/'state.json').exists()
            try:
                state=Workflow(directory,'https://browser.lexmount.cn/events/real-task-challenge',
                               brief=None if exists else case['brief'],revision=None if exists else revision).run()
            except (WorkflowError,OSError,ValueError) as error:
                state=read_json(directory/'state.json') if (directory/'state.json').exists() else {'status':'blocked'}
                print(name,type(error).__name__,flush=True)
            records.append({'run':name,'status':state['status'],'model_calls':state.get('model_calls',0),'error':state.get('error')})
            print(name,state['status'],flush=True)
            previous=directory
            write_json(root/(args.prefix+'-summary.json'),{'runs':records,'note':'Independent model samples; no claim of statistically proven improvement. Inspect screenshots separately.'})
    return 0 if all(r['status']=='ready' for r in records) else 1


if __name__=='__main__':sys.exit(main())
