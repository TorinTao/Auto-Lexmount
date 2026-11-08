"""Revisit verified works without rewriting their facts or overwriting their versions."""
import hashlib
import json
import sys
import shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import WorkflowError, now, read_json, write_json
from autolex.config import load_environment
from autolex.workflow import Workflow


def prepare(parent, child):
    state=read_json(parent/'state.json')
    if state.get('status')!='ready' or state.get('demo'):raise WorkflowError('Expected a ready live parent')
    if child.exists():raise WorkflowError('Revision directory already exists')
    manifest=read_json(parent/'manifest.json')
    if hashlib.sha256((parent/'manifest.json').read_bytes()).hexdigest()!=state['hashes']['manifest.json']:
        raise WorkflowError('Parent manifest changed')
    for name,digest in manifest.items():
        p=parent/name
        if p.parent!=parent or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise WorkflowError('Parent artifact changed: '+name)
    child.mkdir()
    skip={'design.json','design-error.json','index.html','submission.md','submission.json','model-events.json','visual-review.json','visual-history.json','visual-theme.json','visual-evidence.zip'}
    hashes={}
    for name in manifest:
        if name not in skip:
            shutil.copyfile(parent/name,child/name);hashes[name]=manifest[name]
    # Inherit validated execution/semantic results explicitly; no regeneration is claimed.
    write_json(child/'state.json',{'url':state['url'],'demo':False,'created_at':now(),
      'completed':['rules','ideas','build','test'],'status':'paused','stage':'package',
      'hashes':hashes,'brief':state.get('brief',''),'revision':state.get('revision'),
      'model_calls':state['model_calls'],'visual_enabled':True,
      'visual_parent':parent.name,'inherited_model_calls':state['model_calls'],
      'reused_validation':'Original source, program, output and validation records are hash-identical; this revision reruns visual packaging only.'})
    return {'parent':parent.name,'run':child.name,'parent_manifest_sha256':state['hashes']['manifest.json'],
      'unchanged':hashes,'before_html_sha256':hashlib.sha256((parent/'index.html').read_bytes()).hexdigest()}


def main():
    load_environment('.env');lab=Path('runs/visual-retrospective');lab.mkdir(exist_ok=True)
    selected=read_json('runs/batch7-lab/final-runs.json');records=[]
    for key,choice in selected.items():
        parent=Path('runs')/choice['run'];child=Path('runs')/('visual-revisit-'+key)
        info_path=lab/(key+'.json')
        if info_path.exists():
            records.append(read_json(info_path));continue
        print('START',key,flush=True)
        record=prepare(parent,child)
        write_json(info_path,record)
        try:
            result=Workflow(child,read_json(parent/'state.json')['url']).run()
            visual=read_json(child/'visual-review.json')
            record.update(status=result['status'],visual_calls=result['model_calls']-result['inherited_model_calls'],
                          visual_rounds=visual['attempts'],issues=visual['last']['review']['issues'],
                          html_changed=record['before_html_sha256']!=hashlib.sha256((child/'index.html').read_bytes()).hexdigest())
        except Exception as exc:
            record.update(status='blocked',error=str(exc) if isinstance(exc,WorkflowError) else type(exc).__name__)
        write_json(info_path,record);records.append(record)
        write_json(lab/'summary.json',{'records':records,'scope':'Seven prior final works, visual-only child revisions, no publication.'})
        print('DONE',key,record['status'],record.get('visual_rounds'),flush=True)
    return 0 if all(r.get('status')=='ready' for r in records) else 1

if __name__=='__main__':raise SystemExit(main())
