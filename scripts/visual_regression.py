"""Real screenshot/model regression with an explicitly degraded local fixture."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.clients import Model
from autolex.common import write_json
from autolex.config import load_environment
from autolex.visual import visual_gate
load_environment('.env')
kind=sys.argv[1] if len(sys.argv)>1 else 'fixture'
root=Path('runs/visual-release-lab')/kind;root.mkdir(parents=True,exist_ok=True)
source=Path('runs/b7-touchup-collections/index.html').read_text()
# Deliberately tiny body text tests failure detection and actual repair, not production quality.
fault='body{font-size:8px}' if kind=='fixture' else '.points{grid-template-columns:repeat(12,minmax(0,1fr))}'
source=source.replace('</head>','<style>'+fault+'</style></head>')
model=Model(max_calls=8);events=[]
model.observer=lambda event:(events.append(event),write_json(root/'model-events.json',events))
result=visual_gate(root,model,source)
(root/'index.html').write_text(result)
history=json.loads((root/'visual-history.json').read_text())
assert len(history)>=2 and not history[0]['passed'] and history[-1]['passed']
write_json(root/'result.json',{'passed':True,'deliberately_degraded_fixture':True,'model_calls':model.calls,'rounds':len(history),'scope':'Real screenshots and real DeepSeek review/repair; tiny text fault injected only in this separate test fixture.'})
print(json.dumps({'passed':True,'rounds':len(history),'model_calls':model.calls}),flush=True)
