"""Use quote-only review feedback to revise all seven works through the real workflow."""
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'runs/batch7-lab'
def run(args):subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
while subprocess.run(['systemctl','--user','is-active','--quiet','autolex-batch7-replay']).returncode==0:time.sleep(5)
summary=json.loads((LAB/'improved/summary.json').read_text())
if len(summary['records'])!=7:raise SystemExit('Incomplete improved round')
ready=[str(ROOT/'runs'/r['run']) for r in summary['records'] if r['status']=='ready']
run(['scripts/citation_audit.py',*ready,'--out',str(LAB/'citation-audit-improved')])
feedback={}
for record in summary['records']:
    path=LAB/'citation-audit-improved'/(record['run']+'.json')
    issues=json.loads(path.read_text())['failures'] if path.exists() else []
    tests=ROOT/'runs'/record['run']/'tests.json'
    if record['status']!='ready' and tests.exists():issues+=list(dict.fromkeys(failure for attempt in json.loads(tests.read_text())['attempts'] for failure in attempt['failures']))
    feedback[record['case']]='not_mentioned 只保留任务要求但该页确实未提到的主题，删除无关或原文明说不支持某行为却误列为未提及的条目。保持原始 brief 的全部主题、数量和来源；保留已经通过的输入扰动保护。逐条修复下列独立复核问题，不用相邻原文替引用辩护。必要时重新分配要点，删除次要内容，为必须覆盖的主题保留引用和名额。不要只缩短引用却保留超出引用的摘要。每条结论的事实都必须由它引用的摘录直接支撑。\n'+'\n'.join(issues)
(LAB/'refinement-feedback.json').write_text(json.dumps(feedback,ensure_ascii=False,indent=2))
run(['scripts/benchmark.py','--round','refined','--resume-existing','--reuse-evidence','--engine','runs/batch7-lab/engine-refined','--parent-round','improved','--feedback',str(LAB/'refinement-feedback.json')])
summary=json.loads((LAB/'refined/summary.json').read_text())
ready=[str(ROOT/'runs'/r['run']) for r in summary['records'] if r['status']=='ready']
run(['scripts/adversarial_audit.py',*ready,'--out',str(LAB/'audit-refined')])
print('REFINEMENT AND AUDIT FINISHED',flush=True)
