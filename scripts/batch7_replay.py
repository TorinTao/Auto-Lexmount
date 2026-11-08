"""Continue the controlled seven-case experiment after its frozen baseline finishes."""
import subprocess
import sys
import time
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'runs/batch7-lab'
def run(args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)

def ready(round_name):
    return [str(ROOT/'runs'/r['run']) for r in json.loads((LAB/round_name/'summary.json').read_text())['records'] if r['status']=='ready']

while subprocess.run(['systemctl','--user','is-active','--quiet','autolex-batch7-baseline']).returncode == 0:
    time.sleep(5)
records=json.loads((LAB/'baseline/summary.json').read_text())['records']
if len(records)!=7:raise SystemExit('Incomplete baseline; inspect before continuing')
run(['scripts/adversarial_audit.py',*ready('baseline'),'--out',str(LAB/'audit-baseline')])
run(['scripts/benchmark.py','--round','improved','--reuse-evidence','--engine','runs/batch7-lab/engine-improved'])
run(['scripts/adversarial_audit.py',*ready('improved'),'--out',str(LAB/'audit-improved')])
print('REPLAY AND AUDITS FINISHED',flush=True)
