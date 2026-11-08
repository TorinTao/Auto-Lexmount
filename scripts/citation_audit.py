"""Audit saved works with a quote-only DeepSeek review, preserving original run state."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.clients import Model
from autolex.citations import audit_citations
from autolex.common import read_json,write_json,WorkflowError
from autolex.config import load_environment

def main():
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+');p.add_argument('--out',required=True);args=p.parse_args();load_environment('.env')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for name in args.runs:
        root=Path(name);dest=out/(root.name+'.json')
        if dest.exists():continue
        state=read_json(root/'state.json')
        if state.get('status')!='ready' or state.get('demo'):raise WorkflowError('Audit requires completed live work')
        for name,digest in state.get('hashes',{}).items():
            path=root/name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise WorkflowError('Changed artifact '+name)
        model=Model();events=[];model.observer=events.append;start=time.perf_counter()
        report=audit_citations(read_json(root/'output.json'),model)
        report.update(run=root.name,model_calls=model.calls,seconds=time.perf_counter()-start,events=events)
        write_json(dest,report)
        print(root.name,'passed',report['passed'],'issues',len(report['failures']),flush=True)

if __name__=='__main__':main()
