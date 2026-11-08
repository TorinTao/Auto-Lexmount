"""Apply screenshot-derived presentation feedback, then require fresh visual acceptance."""
import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import WorkflowError,read_json,write_json
from autolex.config import load_environment
from autolex.visual import REPAIR,LIMITS,DEFAULTS,validate_theme
from autolex.workflow import Workflow
from scripts.revisit_visuals import prepare


def main():
    load_environment('.env');lab=Path('runs/visual-retrospective');records=[]
    for key in read_json('runs/batch7-lab/final-runs.json'):
        parent=Path('runs')/('visual-revisit-'+key);child=Path('runs')/('visual-final-'+key)
        record_path=lab/('final-'+key+'.json')
        if record_path.exists():raise WorkflowError('Polish already attempted; inspect its saved result')
        record=prepare(parent,child);write_json(record_path,record)
        print('START',key,flush=True)
        w=Workflow(child,read_json(parent/'state.json')['url'])
        state=read_json(child/'state.json');w.model.calls=state['model_calls']
        w.model.observer=lambda event:w.record_model_event(state,child/'state.json',event)
        try:
            review=read_json(parent/'visual-review.json')
            prior_theme=read_json(parent/'visual-theme.json') if (parent/'visual-theme.json').exists() else DEFAULTS
            suggestion=w.model.ask(REPAIR,{'review':review['last']['review'],'browser':review['last']['browser']['checks'],
                'current_theme':{**DEFAULTS,**prior_theme},'limits':LIMITS,
                'instruction':'This is a requested polish pass. Resolve actionable minor code readability and file-size wrapping feedback too. Keep all evidence text and code unchanged. Use code_wrap=1 when long source lines are hard to read; size_nowrap=1 when byte units split.'})
            theme=validate_theme(suggestion.get('theme'));write_json(child/'visual-theme.json',theme)
            record['suggestion']=suggestion;write_json(record_path,record)
            result=w.run();visual=read_json(child/'visual-review.json')
            record.update(status=result['status'],visual_calls=result['model_calls']-result['inherited_model_calls'],
                          visual_rounds=visual['attempts'],issues=visual['last']['review']['issues'],
                          theme=read_json(child/'visual-theme.json'),
                          html_changed=record['before_html_sha256']!=hashlib.sha256((child/'index.html').read_bytes()).hexdigest())
        except Exception as exc:
            record.update(status='blocked',error=str(exc) if isinstance(exc,WorkflowError) else type(exc).__name__)
        write_json(record_path,record);records.append(record)
        write_json(lab/'final-summary.json',{'records':records,'scope':'Visual-only revisions based on actual prior screenshot feedback; no publication.'})
        print('DONE',key,record['status'],record.get('theme'),record.get('error'),flush=True)
    return 0 if all(r.get('status')=='ready' for r in records) else 1

if __name__=='__main__':raise SystemExit(main())
