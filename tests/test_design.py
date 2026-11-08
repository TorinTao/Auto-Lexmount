import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from autolex.common import WorkflowError,read_json,write_json
from autolex.design import validate_plan,generate_design,fingerprint
from autolex.workflow import Workflow
from autolex.presentation import render_report

OUTPUT={'items':[{'title':'Source','url':'https://example.com','summary':'Summary','points':[
    {'id':'one','summary':'First fact','quote':'Original first','url':'https://example.com'},
    {'id':'two','summary':'Second fact','quote':'Original second','url':'https://example.com'}]}],
    'conclusions':[{'text':'Verified conclusion','point_refs':['one','two']}]}
PLAN={'theme':'blueprint','kicker':'知识图鉴','headline':'到底该怎么选？','intro':'看看两种选择有什么区别。','reason':'技术概念适合图鉴。',
      'chapters':[{'point_id':'two','label':'第二点'},{'point_id':'one','label':'第一点'}]}

class DesignTests(unittest.TestCase):
    def test_plan_rejects_lost_or_invented_evidence_and_markup(self):
        validate_plan(PLAN,OUTPUT)
        for changed in [{'chapters':PLAN['chapters'][:1]}, {'chapters':[PLAN['chapters'][0]]*2},
                        {'chapters':[{'point_id':'fake','label':'fake'},PLAN['chapters'][1]]},
                        {'theme':'url(secret)'},{'headline':'<script>alert(1)</script>'},{'intro':'x'*91}]:
            with self.subTest(changed=changed),self.assertRaises(WorkflowError):validate_plan({**PLAN,**changed},OUTPUT)

    def root(self,d):
        root=Path(d);Workflow(root,'https://example.com',demo=True).run()
        write_json(root/'output.json',OUTPUT)
        return root

    def test_retry_cache_and_changed_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d)
            class Model:
                calls=0
                def ask(self,task,context):
                    self.calls+=1
                    return {**PLAN,'chapters':[]} if self.calls==1 else PLAN
            model=Model();generate_design(root,model);generate_design(root,model)
            self.assertEqual(model.calls,2)
            self.assertTrue((root/'design-error.json').exists())
            changed=copy.deepcopy(OUTPUT);changed['items'][0]['summary']='Changed';write_json(root/'output.json',changed)
            with self.assertRaisesRegex(WorkflowError,'inputs changed'):generate_design(root,model)

    def test_render_retains_facts_code_and_escapes_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d);output=copy.deepcopy(OUTPUT)
            output['items'][0]['points'][0]['summary']='<img src=x onerror=alert(1)>'
            write_json(root/'output.json',output)
            write_json(root/'design.json',{**PLAN,'input_sha256':fingerprint(read_json(root/'spec.json'),output)})
            document=render_report(root,['main.py','design.json'])
            for text in ['Original first','Original second','Verified conclusion','design.json','&lt;img']:self.assertIn(text,document)
            self.assertNotIn('<img',document)
            self.assertLess(document.index('第二点'),document.index('第一点'))

    def test_invalid_design_blocks_package(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);w=Workflow(root,'https://example.com',demo=True);w.run('test');w.demo=False
            with patch('autolex.design.generate_design',side_effect=WorkflowError('bad design')):
                with self.assertRaisesRegex(WorkflowError,'bad design'):w.package()
            self.assertFalse((root/'submission.zip').exists())

if __name__=='__main__':unittest.main()
