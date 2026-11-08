"""Prepare visual updates only for works with existing submission receipts."""
import hashlib
import sys
import shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json,WorkflowError
from autolex.config import load_environment
from autolex.workflow import Workflow
from autolex.visual import DEFAULTS
from autolex.runner import execute,validate_output
from autolex.release import prepare_release
from scripts.revisit_visuals import prepare


def main():
    load_environment('.env');root=Path.cwd();lab=root/'runs/resubmission-lab';lab.mkdir(exist_ok=True)
    records=read_json(root/'runs/polish-20261108/publications.json')
    copy=read_json(root/'runs/agent-copy-visual/release-state.json')
    records.append({'run':'agent-copy-visual','title':copy['title'],'url':copy['url'],'passcode':copy['passcode'],'receipt':copy['receipt']['id']})
    ready=[];profile=read_json(root/'.release-profile.json')
    for record in records:
        parent=root/'runs'/record['run'];child=root/'runs'/('resubmit-'+record['run'])
        prior=read_json(parent/'submission-state.json')
        if prior['status']!='submitted' or prior['receipt']['id']!=record['receipt']:raise WorkflowError('Original submission not verified')
        target=lab/(record['run']+'.json')
        if target.exists():raise WorkflowError('Preparation already attempted; inspect existing record')
        print('PREPARE',record['run'],flush=True)
        provenance=prepare(parent,child)
        write_json(child/'visual-theme.json',{**DEFAULTS,'code_wrap':1,'size_nowrap':1})
        state=Workflow(child,read_json(parent/'state.json')['url']).run()
        for name in ['main.py','input.json','output.json','tests.json','review.json','quality.json']:
            if (parent/name).read_bytes()!=(child/name).read_bytes():raise WorkflowError('Content changed during visual revision')
        work=lab/'rerun'/record['run']/'work';work.mkdir(parents=True)
        for name in ['main.py','input.json']:shutil.copyfile(child/name,work/name)
        rerun=execute(work)
        if rerun['returncode']!=0 or rerun['timeout'] or validate_output(work,read_json(child/'input.json')) or read_json(work/'output.json')!=read_json(child/'output.json'):
            raise WorkflowError('Fresh execution did not reproduce the original output')
        draft=prepare_release(child,profile)
        record.update(revision=child.name,archive=str((child/'release/site.zip').relative_to(root)),archive_sha256=draft['archive_sha256'],
                      source_manifest_sha256=draft['source_manifest_sha256'],visual_calls=state['model_calls']-state['inherited_model_calls'],
                      visual_passed=read_json(child/'visual-review.json')['passed'],docker_rerun_matches=True,
                      original_manifest=provenance['parent_manifest_sha256'])
        write_json(target,record);ready.append(record);write_json(lab/'prepared.json',ready)
        print('READY',record['run'],flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
