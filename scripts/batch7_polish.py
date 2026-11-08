"""Apply targeted final feedback, retaining all previous experiment rounds."""
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'runs/batch7-lab'
def read(p):return json.loads(p.read_text())
def run(args):subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
while subprocess.run(['systemctl','--user','is-active','--quiet','autolex-batch7-refine']).returncode==0:time.sleep(5)
summary=read(LAB/'refined/summary.json')
if len(summary['records'])!=7:raise SystemExit('Incomplete refinement; inspect first')
review=read(LAB/'reviewer-refined.json')['cases'];selected=[];feedback={}
for record in summary['records']:
    case=record['case'];notes=review.get(case,{})
    if record['status']=='ready' and not notes.get('needs_revision'):continue
    selected.append(case)
    issues=list(notes.get('revision_feedback',notes.get('findings',[])))
    tests=ROOT/'runs'/record['run']/'tests.json'
    if record['status']!='ready' and tests.exists():issues+=read(tests)['attempts'][-1]['failures']
    feedback[case]='以原始 brief 为完整验收契约，保留已通过的输入保护逻辑。特别注意缺失键、默认参数等限定条件，不能把默认行为泛化为无条件行为。\n'+'\n'.join(issues)
(LAB/'polish-feedback.json').write_text(json.dumps(feedback,ensure_ascii=False,indent=2))
if selected:
    run(['scripts/benchmark.py','--round','polished','--reuse-evidence','--engine','runs/batch7-lab/engine-polished','--parent-round','refined','--feedback',str(LAB/'polish-feedback.json'),'--only',*selected])
    works=read(LAB/'polished/summary.json')['records']
    ready=[str(ROOT/'runs'/r['run']) for r in works if r['status']=='ready']
    if ready:run(['scripts/adversarial_audit.py',*ready,'--out',str(LAB/'audit-polished')])
selection={r['case']:{'run':f'b7-polished-{r["case"]}' if r['case'] in selected else r['run'],'audit_round':'polished' if r['case'] in selected else 'refined'} for r in summary['records']}
(LAB/'final-runs.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2))
print('FINAL SELECTION WRITTEN',flush=True)
