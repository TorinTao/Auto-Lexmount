"""Model-authored presentation plans; evidence and executable HTML remain trusted."""
import hashlib
import json
from .common import WorkflowError, read_json, write_json

THEMES = ('blueprint', 'editorial', 'fieldnotes')
TASK = '''DESIGN: You are the editorial designer of a small Chinese reference website.
Create a distinctive, beginner-friendly presentation plan from the supplied verified output.
This is a reader's guide, not an engineering execution report. Start with a concrete question.
Return JSON only: {"theme":"blueprint"|"editorial"|"fieldnotes", "kicker":str,
"headline":str, "intro":str, "reason":str,
"chapters":[{"point_id":existing point ID,"label":str}]}.
blueprint = cobalt technical atlas, giant sans-serif question, numbered index and dark diagram panel;
editorial = warm paper and vermilion, serif editorial headline, wide numbered reading rows;
fieldnotes = forest green field guide, notebook rules, compact checklist and annotated tabs.
Choose based on the subject, not randomly. Each must have a recognizable visual concept.
Write Chinese: kicker <=18 chars, headline <=28 chars, intro <=90 chars, reason <=180 chars,
chapter label <=16 chars. Headline should be an inviting question instead of copying the technical title.
Intro describes what readers can look up, not new factual advice or claims. Labels are short topic names.
Include EVERY supplied point ID exactly once, in a deliberate beginner-friendly reading order.
Never change quotes, factual summaries, conclusions or URLs. No HTML, CSS, scripts, new data,
prize claims, invented examples or functionality. Empty chapters is valid only when no points exist.
If supplied schema_error, correct the plan. feedback is a user's visual preference, not source evidence.'''


def fingerprint(spec, output):
    return hashlib.sha256(json.dumps({'spec':spec,'output':output},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def validate_plan(plan, output):
    if not isinstance(plan,dict) or plan.get('theme') not in THEMES:
        raise WorkflowError('Design must select a supported visual concept')
    for key,limit in [('kicker',18),('headline',28),('intro',90),('reason',180)]:
        value=plan.get(key)
        if not isinstance(value,str) or not value.strip() or len(value)>limit or any(c in value for c in '<>'):
            raise WorkflowError('Invalid design text: '+key)
    rows=plan.get('chapters');expected=[p['id'] for item in output['items'] for p in item.get('points',[])]
    if not isinstance(rows,list):raise WorkflowError('Missing design reading order')
    seen=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('point_id'),str):raise WorkflowError('Invalid design point ID')
        label=row.get('label')
        if not isinstance(label,str) or not 1<=len(label)<=16 or any(c in label for c in '<>'):raise WorkflowError('Invalid design chapter label')
        seen.append(row['point_id'])
    if len(seen)!=len(expected) or set(seen)!=set(expected):raise WorkflowError('Design must preserve every evidence point exactly once')
    return {k:plan[k] for k in ('theme','kicker','headline','intro','reason','chapters')}


def generate_design(root, model, *, feedback=''):
    spec=read_json(root/'spec.json');output=read_json(root/'output.json');digest=fingerprint(spec,output)
    path=root/'design.json'
    if path.exists():
        saved=read_json(path)
        if saved.get('input_sha256')!=digest or saved.get('feedback','')!=feedback:
            raise WorkflowError('Design inputs changed; create a new revision')
        validate_plan(saved,output)
        return saved
    context={'selected':spec['selected'],'output':output,'feedback':feedback}
    for attempt in range(2):
        result=model.ask(TASK,context)
        try:plan=validate_plan(result,output);break
        except WorkflowError as error:
            write_json(root/'design-error.json',{'response':result,'error':str(error)})
            if attempt:raise
            context['schema_error']=str(error)
    plan.update(version=1,input_sha256=digest,feedback=feedback,generated_by='model')
    write_json(path,plan)
    return plan


def fallback_design(spec, output):
    # Offline fixtures/legacy direct rendering remain deterministic and make no AI claim.
    return {'theme':'editorial','kicker':'一份可以查证的小指南','headline':spec['selected']['title'],
            'intro':'先看看关键区别，再顺着原文找到依据。','reason':'Deterministic fallback',
            'chapters':[{'point_id':p['id'],'label':'阅读要点 '+str(n+1)} for n,p in enumerate(p for i in output['items'] for p in i.get('points',[]))]}
