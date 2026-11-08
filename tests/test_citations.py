import copy
import unittest
from autolex.citations import audit_citations
from autolex.common import WorkflowError

class CitationTests(unittest.TestCase):
    def setUp(self):
        self.output={'items':[{'points':[{'id':'p','summary':'The response is never stored.', 'quote':'must be validated'}]}], 'conclusions':[{'text':'Never store it.', 'point_refs':['p']}]}
        self.response={'point_checks':[{'id':'p','fully_supported':False,'unsupported_clauses':['never stored'],'reason':'validation does not forbid storing'}], 'conclusion_checks':[{'index':0,'fully_supported':False,'unsupported_clauses':['Never store'],'reason':'not supported'}]}
    def model(self,response):
        class Model:
            def ask(inner,task,context):
                self.assertTrue({'points','conclusions'} <= set(context))
                self.assertNotIn('main_text',str(context))
                return response
        return Model()
    def test_true_fact_outside_quote_still_fails(self):
        report=audit_citations(self.output,self.model(self.response))
        self.assertFalse(report['passed']);self.assertEqual(len(report['failures']),2)
    def test_positive_flag_cannot_override_listed_unsupported_clauses(self):
        response=copy.deepcopy(self.response)
        for rows in response.values():rows[0]['fully_supported']=True
        self.assertFalse(audit_citations(self.output,self.model(response))['passed'])
    def test_incomplete_duplicate_or_unknown_audit_is_rejected(self):
        for rows in [[],self.response['point_checks']*2,[{**self.response['point_checks'][0],'id':'wrong'}]]:
            with self.subTest(rows=rows),self.assertRaises(WorkflowError):
                audit_citations(self.output,self.model({**self.response,'point_checks':rows}))
    def test_malformed_review_retries_once_and_preserves_diagnostics(self):
        import tempfile
        from pathlib import Path
        from autolex.common import read_json
        response=copy.deepcopy(self.response)
        for rows in response.values():rows[0].update(fully_supported=True,unsupported_clauses=[],reason='supported')
        class Model:
            calls=0
            def ask(inner,task,context):
                inner.calls+=1
                return {'point_checks':[],'conclusion_checks':[]} if inner.calls==1 else response
        with tempfile.TemporaryDirectory() as folder:
            model=Model();path=Path(folder)/'errors.json'
            report=audit_citations(self.output,model,path)
            self.assertTrue(report['passed']);self.assertEqual(model.calls,2)
            self.assertEqual(len(read_json(path)),1)
            self.assertEqual(report['structured_review_attempts'],2)

    def test_page_summary_is_not_a_loophole_around_point_checks(self):
        output=copy.deepcopy(self.output);output['items'][0]['summary']='An unquoted guarantee'
        response=copy.deepcopy(self.response)
        for rows in response.values():rows[0].update(fully_supported=True,unsupported_clauses=[],reason='supported')
        response['item_checks']=[{'index':0,'fully_supported':False,'unsupported_clauses':['An unquoted guarantee'],'reason':'not in point quotes'}]
        report=audit_citations(output,self.model(response))
        self.assertFalse(report['passed'])
        self.assertIn('page summary',report['failures'][0])

    def test_complete_support_passes(self):
        response=copy.deepcopy(self.response)
        for rows in response.values():rows[0].update(fully_supported=True,unsupported_clauses=[],reason='supported')
        self.assertTrue(audit_citations(self.output,self.model(response))['passed'])

class CitationWorkflowTests(unittest.TestCase):
    def test_failed_quote_support_blocks_package_before_expensive_perturbations(self):
        import tempfile
        from pathlib import Path
        from autolex.workflow import Workflow
        from autolex.demo import DemoFetch, DemoModel
        from autolex.common import read_json, write_json
        calls=[]
        class Model(DemoModel):
            def ask(self, task, context):
                if task.startswith('CITATIONS'):
                    self.calls += 1
                    return {'point_checks':[{'id':'p','fully_supported':False,'unsupported_clauses':['all sites'],'reason':'The quote names one provider only'}], 'conclusion_checks':[], 'item_checks':[{'index':0,'fully_supported':False,'unsupported_clauses':['All sites'],'reason':'not quoted'}]}
                return super().ask(task,context)
        def executor(project, **kwargs):
            calls.append(project)
            write_json(project/'output.json', {'items':[{'url':'https://example.com','title':'Fixture','summary':'All sites', 'points':[{'id':'p','summary':'Use all sites','quote':'Use Lexmount cloud.'}]}]})
            return {'returncode':0,'log':'fixture','timeout':False}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(WorkflowError):
                Workflow(root,'https://example.com',fetcher=DemoFetch(),model=Model(),executor=executor,repairs=0).run()
            self.assertEqual(len(calls),1)
            self.assertFalse((root/'submission.zip').exists())
            self.assertFalse(read_json(root/'citations.json')['passed'])
            self.assertIn('Citation id=p',read_json(root/'tests.json')['attempts'][0]['failures'][0])

if __name__=='__main__':unittest.main()
