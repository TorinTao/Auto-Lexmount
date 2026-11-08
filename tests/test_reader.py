import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from autolex.common import WorkflowError,read_json,write_json
from autolex.reader import validate_reader,validate_review,generate_reader,verified_reader,entries,copy_hash
from autolex.design import fingerprint
from autolex.workflow import Workflow
from autolex.presentation import render_report
from test_design import OUTPUT,PLAN

COPY={'headline':'同一件东西，还是两份？','intro':'先分清名字和东西本身。','takeaway':{'text':'名字不同，不一定是两份东西。','point_refs':['one']},'cards':[
 {'point_id':'one','title':'一个东西，两个名字','text':'同一个东西可以有两个名字。','analogy':'同一个盒子贴着两张标签。'},
 {'point_id':'two','title':'另外一份东西','text':'这是一份另外的东西。','analogy':'另拿一个盒子。'}]}

def review(data=COPY,passed=True):
    return {'passed':passed,'checks':[{'id':e['id'],'supported':passed,'plain_language':True,'reason':'Fixture only'} for e in entries(data,OUTPUT)]}

class ReaderTests(unittest.TestCase):
    def root(self,d):
        p=Path(d);Workflow(p,'https://example.com',demo=True).run()
        write_json(p/'output.json',OUTPUT)
        write_json(p/'design.json',{**PLAN,'theme':'classic','input_sha256':fingerprint(read_json(p/'spec.json'),OUTPUT)})
        return p

    def test_invalid_evidence_and_missing_or_duplicate_cards_rejected(self):
        validate_reader(COPY,OUTPUT)
        bads=[{**COPY,'cards':COPY['cards'][:1]}, {**COPY,'cards':[COPY['cards'][0]]*2},
              {**COPY,'takeaway':{'text':'wrong','point_refs':['missing']}}, {**COPY,'intro':'<script>x</script>'}]
        for bad in bads:
            with self.assertRaises(WorkflowError):validate_reader(bad,OUTPUT)

    def test_jargon_cannot_pass_even_if_a_model_would_approve_it(self):
        for phrase in ('用浅复制','用深拷贝','直接指派','写一句等于','绑定到对象','deepcopy'):
            bad=copy.deepcopy(COPY);bad['takeaway']['text']=phrase
            with self.subTest(phrase=phrase),self.assertRaisesRegex(WorkflowError,'technical wording'):
                validate_reader(bad,OUTPUT)

    def test_review_cannot_skip_targets_or_overrule_false_check(self):
        good=review();ids=[e['id'] for e in entries(COPY,OUTPUT)]
        validate_review(good,ids)
        bad=copy.deepcopy(good);bad['checks'][0]['plain_language']=False
        for row in [bad,{**good,'checks':good['checks'][1:]},{**good,'checks':good['checks']+[good['checks'][0]]}]:
            with self.assertRaises(WorkflowError):validate_review(row,ids)

    def test_repair_cache_and_stale_review(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d)
            class Model:
                calls=0
                def ask(self,task,context):
                    self.calls+=1
                    if task.startswith('READER_REVIEW'):return review(passed=self.calls>2)
                    return copy.deepcopy(COPY)
            model=Model();generate_reader(root,model);generate_reader(root,model)
            self.assertEqual(model.calls,4)
            self.assertEqual(len(read_json(root/'reader-history.json')),2)
            changed=read_json(root/'reader.json');changed['intro']='被改过了';write_json(root/'reader.json',changed)
            with self.assertRaisesRegex(WorkflowError,'matches'):verified_reader(root,OUTPUT)

    def test_bad_review_structure_is_repaired_without_rewriting_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d)
            class Model:
                calls=0
                drafts=0
                def ask(self,task,context):
                    self.calls+=1
                    if task.startswith('READER_REVIEW'):
                        result=review()
                        if self.calls==2:result['passed']=False
                        return result
                    self.drafts+=1
                    return copy.deepcopy(COPY)
            model=Model();generate_reader(root,model)
            self.assertEqual(model.drafts,1)
            self.assertEqual(model.calls,3)
            self.assertEqual(len(read_json(root/'reader-review-errors.json')),1)
            self.assertTrue(verified_reader(root,OUTPUT))

    def test_editorial_draft_still_requires_review_and_matching_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d);digest=fingerprint(read_json(root/'spec.json'),OUTPUT)
            draft={**COPY,'input_sha256':digest};write_json(root/'reader-draft.json',draft)
            class Model:
                calls=0
                def ask(self,task,context):
                    self.calls+=1
                    if not task.startswith('READER_REVIEW'):raise AssertionError('Unexpected copy regeneration')
                    return review()
            model=Model();generate_reader(root,model)
            self.assertEqual(model.calls,1)
            self.assertEqual(verified_reader(root,OUTPUT)['origin'],'reviewed-editorial-draft')
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d);write_json(root/'reader-draft.json',{**COPY,'input_sha256':'wrong'})
            with self.assertRaisesRegex(WorkflowError,'different evidence'):generate_reader(root,Model())

    def test_unreviewed_copy_is_not_rendered(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d);data={**COPY,'input_sha256':fingerprint(read_json(root/'spec.json'),OUTPUT)}
            write_json(root/'reader.json',data)
            with self.assertRaisesRegex(WorkflowError,'not been reviewed'):render_report(root,['main.py'])

    def test_rejected_reader_prevents_ready_package(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);w=Workflow(root,'https://example.com',demo=True);w.run('test');w.demo=False
            with patch('autolex.design.generate_design'),patch('autolex.reader.generate_reader',side_effect=WorkflowError('unreadable')):
                with self.assertRaisesRegex(WorkflowError,'unreadable'):w.package()
            self.assertFalse((root/'submission.zip').exists())

    def test_plain_view_retains_original_evidence_in_disclosures(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.root(d);digest=fingerprint(read_json(root/'spec.json'),OUTPUT)
            data={**COPY,'input_sha256':digest};write_json(root/'reader.json',data)
            write_json(root/'reader-review.json',{**review(),'copy_sha256':copy_hash(data),'input_sha256':digest})
            document=render_report(root,['main.py'])
            for text in ['Original first','Original second','Verified conclusion','First fact','Second fact','打个比方']:
                self.assertIn(text,document)
            self.assertIn('<details data-evidence>',document)
            self.assertNotIn('份资料</div>',document)

if __name__=='__main__':unittest.main()
