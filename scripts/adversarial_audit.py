"""Independent metamorphic checks, beyond the workflow's own acceptance review."""
import argparse
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import re
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.common import read_json,write_json,WorkflowError
from autolex.runner import execute,validate_output
from autolex.quality import evidence_refusal


def canonical(output):
    data=copy.deepcopy(output)
    data['items'].sort(key=lambda item:item['url'])
    for item in data['items']:
        for point in item.get('points',[]):point['quote']=' '.join(point['quote'].split())
    return data


def audit(root,dest):
    root=Path(root).resolve();dest=Path(dest).resolve()
    if dest==root or root in dest.parents:raise WorkflowError('Audit must be outside original artifacts')
    state=read_json(root/'state.json')
    if state.get('status')!='ready' or state.get('demo'):raise WorkflowError('Audit requires a completed live run')
    for name,digest in state.get('hashes',{}).items():
        p=root/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise WorkflowError('Changed original artifact: '+name)
    if dest.exists():raise WorkflowError('Audit output already exists; preserve previous results')
    dest.mkdir(parents=True)
    evidence=read_json(root/'input.json');expected=read_json(root/'output.json');code=(root/'main.py').read_text()
    whitespace=copy.deepcopy(evidence)
    for page in whitespace['pages']:page['result']['main_text']=re.sub(r'\s+','\n \t',page['result']['main_text'])
    variants=[('equivalent_whitespace',whitespace,True)]
    for index in range(len(evidence['pages'])):
        missing=copy.deepcopy(evidence);missing['pages'].pop(index)
        variants.append((f'missing_source_{index+1}',missing,False))
        empty=copy.deepcopy(evidence);empty['pages'][index]['result']['main_text']=''
        variants.append((f'empty_source_{index+1}',empty,False))
    duplicate=copy.deepcopy(evidence)
    duplicate['pages'].append(copy.deepcopy(duplicate['pages'][0]))
    variants.append(('duplicate_source',duplicate,False))
    checks=[]
    for name,data,positive in variants:
        work=dest/name/'project';work.mkdir(parents=True)
        (work/'main.py').write_text(code);write_json(work/'input.json',data)
        start=time.perf_counter();result=execute(work);duration=time.perf_counter()-start
        failures=validate_output(work,data)
        if positive:
            passed=result['returncode']==0 and not failures and canonical(read_json(work/'output.json'))==canonical(expected)
            requirement='Whitespace-only source formatting must preserve content, ignoring quote whitespace.'
        else:
            passed=evidence_refusal(result,work)
            requirement='A required source that is missing, duplicated or empty must be explicitly refused; an accidental crash is not a valid refusal.'
        checks.append({'name':name,'passed':bool(passed),'requirement':requirement,'seconds':duration,**result,'failures':failures if not passed else []})
    report={'run':root.name,'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'Executable input perturbations only; source support and visual quality require separate review.'}
    write_json(dest/'audit.json',report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+');p.add_argument('--out',required=True);p.add_argument('--workers',type=int,choices=[1,2,3],default=3);args=p.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        futures=[pool.submit(audit,root,Path(args.out)/Path(root).name) for root in args.runs]
        for future in futures:
            result=future.result()
            print(result['run'],[(c['name'],c['passed']) for c in result['checks']],flush=True)


if __name__=='__main__':main()
