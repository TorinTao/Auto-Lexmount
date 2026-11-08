"""Small real-model regression probes; these are not a factual accuracy benchmark."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autolex.clients import Model
from autolex.citations import audit_citations
from autolex.common import write_json,WorkflowError
from autolex.config import load_environment

def main():
    load_environment('.env');model=Model(max_calls=8);records=[]
    cases=[
      ('faithful_translation',True,'consider each line as a new flex container. Any space distribution will happen across each line, without reference to the previous or subsequent lines.','每一行应视为新的 flex 容器；空间在各行内分配，与前后行无关。'),
      ('unsupported_revalidation',False,'the response can be stored only in a private cache','响应只能保存在私有缓存，并且每次复用前必须重新验证。'),
      ('default_is_not_always',False,'get() will, like normal dictionaries, return None as a default rather than using default_factory','get() 在任何情况下都返回 None，不论键是否存在或是否给定默认实参。')]
    for name,expected,quote,summary in cases:
        before=model.calls;start=time.perf_counter()
        try:
            review=audit_citations({'items':[{'points':[{'id':'point','summary':summary,'quote':quote}]}],'conclusions':[]},model)
            record={'name':name,'expected_supported':expected,'actual_supported':review['passed'],'passed':review['passed']==expected,'review':review}
        except WorkflowError as exc:record={'name':name,'passed':False,'error':str(exc)}
        record.update(calls=model.calls-before,seconds=time.perf_counter()-start);records.append(record)
    report={'passed':all(r['passed'] for r in records),'checks':records,'model_calls':model.calls,'scope':'Three bounded live model probes; stochastic and insufficient to estimate general semantic accuracy.'}
    write_json('runs/batch7-lab/citation-regression.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
