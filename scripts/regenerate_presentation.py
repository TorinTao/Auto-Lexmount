"""Create an immutable, model-designed revision of one existing generated work."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json, write_json
from autolex.config import load_environment
from autolex.workflow import Workflow
from autolex.release import prepare_release
from scripts.revisit_visuals import prepare


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parent',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();load_environment('.env')
    parent=Path(args.parent);child=Path(args.out)
    if not child.exists():
        info=prepare(parent,child);write_json(child/'presentation-parent.json',info)
    else:
        info=read_json(child/'presentation-parent.json')
        if info['parent']!=parent.name:raise ValueError('Different parent')
    result=Workflow(child,read_json(parent/'state.json')['url']).run()
    draft=prepare_release(child,read_json('.release-profile.json'))
    print(json.dumps({'status':result['status'],'run':child.name,'new_model_calls':result['model_calls']-result['inherited_model_calls'],
      'theme':read_json(child/'design.json')['theme'],'archive_sha256':draft['archive_sha256'],
      'scope':'Model regenerated presentation from hash-identical verified work; not new research or code execution.'},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
