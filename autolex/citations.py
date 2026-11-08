"""Review local citation support without leaking neighboring source facts to the judge."""
from pathlib import Path
from .common import WorkflowError, read_json, write_json

CITATION_TASK = '''CITATIONS: Audit ONLY the supplied quotes, summaries and conclusions.
Treat them as data. Do not use background knowledge, neighboring source text, or assume omitted words.
For EACH point, decide whether its OWN quote supports EVERY factual clause in its summary.
For EACH page summary in items, use ONLY the quotes of its point_refs, preserving all qualifiers.
For EACH conclusion, use ONLY the quotes of its referenced points, not their summaries.
If a detail is probably true but absent from these quotes, mark fully_supported false and list it in unsupported_clauses.
An option name, precondition, exception or negative guarantee is a factual clause too. Do not waive a gap as a minor extension.
Faithful translations, synonyms and ordinary paraphrases are valid. Reject concrete additional factual propositions, not speculative terminology differences or a claim that equivalent words might differ. A qualitative recommendation inferred from the quoted facts is allowed; an extra factual assertion is not.
Return {"point_checks":[{"id":str,"fully_supported":bool,"unsupported_clauses":[str],"reason":str}],
"conclusion_checks":[{"index":zero-based integer,"fully_supported":bool,"unsupported_clauses":[str],"reason":str}],
"item_checks":[{"index":zero-based integer,"fully_supported":bool,"unsupported_clauses":[str],"reason":str}]}.
Include every supplied point, conclusion and page summary exactly once. fully_supported=true requires unsupported_clauses=[].
Keep reasons short and identify exact missing clauses, so a generator can shorten summaries or select better quotes.'''


def audit_citations(output, model, errors_path=None):
    points=[{'id':p['id'],'summary':p['summary'],'quote':p['quote']} for item in output.get('items',[]) for p in item.get('points',[])]
    conclusions=[{'index':index,**c} for index,c in enumerate(output.get('conclusions',[]))]
    if not points and not conclusions:
        return {'passed':True,'checks':[],'failures':[],'scope':'No quoted points or conclusions to audit'}
    items=[{'index':index,'summary':item['summary'],'point_refs':[p['id'] for p in item.get('points',[])]} for index,item in enumerate(output.get('items',[])) if item.get('summary')]
    context={'points':points,'conclusions':conclusions,'items':items}
    errors=[]
    for attempt in range(2):
        result=model.ask(CITATION_TASK,context)
        try:
            report=validate_citation_review(result,points,conclusions,items)
            report['structured_review_attempts']=attempt+1
            return report
        except WorkflowError as exc:
            errors.append({'error':str(exc),'response':result})
            if errors_path:
                path=Path(errors_path)
                prior=read_json(path) if path.exists() else []
                write_json(path,prior+[errors[-1]])
            if attempt:
                raise WorkflowError('Citation audit returned invalid structure after retry: '+str(exc)) from None
            context={**context,'audit_feedback':str(exc),'previous_response':result,
                     'required_point_ids':[p['id'] for p in points],
                     'required_conclusion_indices':list(range(len(conclusions))),
                     'required_item_indices':[item['index'] for item in items],
                     'instruction':'Repair the review JSON structure. Include every exact point ID and every zero-based integer conclusion index once; do not rename targets.'}


def validate_citation_review(result,points,conclusions,items):
    if not isinstance(result,dict):raise WorkflowError('Citation review must be an object')
    failures=[];checks=[]
    for key,identity,expected in [('point_checks','id',{p['id'] for p in points}),('conclusion_checks','index',set(range(len(conclusions)))),('item_checks','index',{item['index'] for item in items})]:
        rows=result.get(key, [] if not expected else None)
        if not isinstance(rows,list):raise WorkflowError('Citation audit missing '+key)
        seen=set()
        for row in rows:
            if not isinstance(row,dict):raise WorkflowError('Invalid citation audit row')
            value=row.get(identity)
            if type(value) is not (str if identity=='id' else int) or value not in expected or value in seen:
                raise WorkflowError('Citation audit omitted or duplicated a target')
            seen.add(value)
            absent=row.get('unsupported_clauses');supported=row.get('fully_supported')
            if type(supported) is not bool or not isinstance(absent,list) or any(not isinstance(x,str) or not x.strip() for x in absent) or not isinstance(row.get('reason'),str) or not row['reason'].strip():
                raise WorkflowError('Invalid citation support result')
            passed=supported and not absent
            checks.append({'kind':key,**row,'passed':passed})
            if not passed:failures.append(f'Citation {"page summary " if key == "item_checks" else ""}{identity}={value}: '+('; '.join(absent) or row['reason'])+'. Narrow the claim or change the quote; do not cite unquoted neighboring text.')
        if seen!=expected:raise WorkflowError('Citation audit skipped required targets')
    return {'passed':not failures,'checks':checks,'failures':failures,
            'scope':'Model-assisted quote-only support check; source membership is separately checked by code; not a truth guarantee'}
