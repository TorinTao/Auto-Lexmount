import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from autolex.clients import Model
from autolex.common import WorkflowError, read_json
from autolex.visual import DEFAULTS, styled, validate_theme, validate_review, visual_gate


class VisualTests(unittest.TestCase):
    def test_theme_cannot_hide_content_or_inject_css(self):
        for change in [{'display':'none'}, {'font_size':'16px;display:none'}, {'font_size':1}, {'point_columns':1.5}, {'code_wrap':0.5}, {'size_nowrap':True}]:
            with self.assertRaises(WorkflowError):validate_theme({**DEFAULTS,**change})
        page=styled('<html><head></head><body>Evidence</body></html>',DEFAULTS)
        self.assertIn('Evidence',page)
        self.assertIn('font-size:17px',page)

    def test_old_themes_remain_valid_and_wrapping_preserves_source(self):
        from autolex.visual import BASE_KEYS
        old={k:v for k,v in DEFAULTS.items() if k in BASE_KEYS}
        self.assertEqual(validate_theme(old),old)
        source='<head></head><pre>if True:\n    print("proof")</pre>'
        rendered=styled(source,{**DEFAULTS,'code_wrap':1,'size_nowrap':1})
        self.assertIn('<pre>if True:\n    print("proof")</pre>',rendered)
        self.assertIn('white-space:pre-wrap',rendered)
        self.assertIn('td:last-child{white-space:nowrap',rendered)

    def test_missing_and_contradictory_review_rejected(self):
        good={'passed':True,'observations':[{'image':'a.png','observation':'Readable'}],'issues':[]}
        self.assertEqual(validate_review(good,['a.png']),good)
        for bad in [{**good,'observations':[]},{**good,'passed':False},{**good,'observations':good['observations']*2},
                    {**good,'issues':[{'severity':'blocking','image':'a.png','problem':'clip','fix':'wrap'}]}]:
            with self.assertRaises(WorkflowError):validate_review(bad,['a.png'])

    def test_image_payload_and_json_retry_retain_images(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png';p.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            calls=[]
            def post(url,payload,*args,**kwargs):
                calls.append(payload)
                return {'choices':[{'message':{'content':'bad' if len(calls)==1 else '{"ok":true}'}}]}
            with patch.dict(os.environ,{'MODEL_API_KEY':'test','MODEL_NAME':'test'}),patch('autolex.clients.post_json',side_effect=post):
                model=Model(max_calls=2);self.assertTrue(model.ask('check',{},images=[p])['ok'])
            self.assertEqual(model.calls,2)
            for payload in calls:
                block=payload['messages'][1]['content'][1]
                self.assertEqual(base64.b64decode(block['image_url']['url'].split(',')[1]),p.read_bytes())

    def test_browser_failure_cannot_be_overruled_and_repair_is_rechecked(self):
        with tempfile.TemporaryDirectory() as d:
            captures=[]
            def capture(html,directory):
                captures.append(html);directory.mkdir(parents=True)
                image=directory/'a.png';image.write_bytes(b'png')
                return {'screenshots':[str(image)],'checks':[{'passed':len(captures)>1}],'passed':len(captures)>1}
            class Judge:
                def ask(self,task,context,**kwargs):
                    if task.startswith('VISUAL_REPAIR'):return {'theme':DEFAULTS}
                    return {'passed':True,'observations':[{'image':'a.png','observation':'Readable'}],'issues':[]}
            final=visual_gate(d,Judge(),'<head></head><body>Evidence</body>',capture_fn=capture)
            report=read_json(Path(d)/'visual-review.json')
            self.assertTrue(report['passed']);self.assertEqual(report['attempts'],2)
            self.assertNotEqual(captures[0],captures[1]);self.assertIn('Evidence',final)
            self.assertFalse(read_json(Path(d)/'visual-history.json')[0]['passed'])

    def test_repair_limit_blocks_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as d:
            def capture(html,directory):
                directory.mkdir(parents=True);p=directory/'a.png';p.write_bytes(b'png')
                return {'screenshots':[str(p)],'checks':[],'passed':True}
            class Judge:
                def ask(self,*args,**kwargs):
                    return {'passed':False,'observations':[{'image':'a.png','observation':'Clipped'}],
                            'issues':[{'severity':'blocking','image':'a.png','problem':'Clipped','fix':'Wrap'}]}
            with self.assertRaisesRegex(WorkflowError,'limit reached'):
                visual_gate(d,Judge(),'<head></head>',capture_fn=capture,repairs=0)
            self.assertFalse(read_json(Path(d)/'visual-review.json')['passed'])

    def test_failed_visual_gate_prevents_packaging(self):
        from autolex.workflow import Workflow
        with tempfile.TemporaryDirectory() as d:
            w=Workflow(d,'https://example.com',demo=True)
            w.run('test');w.visual_enabled=True
            with patch('autolex.visual.visual_gate',side_effect=WorkflowError('visual blocked')):
                with self.assertRaisesRegex(WorkflowError,'visual blocked'):w.package()
            self.assertFalse((Path(d)/'manifest.json').exists())
            self.assertFalse((Path(d)/'submission.zip').exists())

    def test_visual_calls_share_the_existing_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png';p.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            model=Model(max_calls=1);model.calls=1
            with patch('autolex.clients.post_json') as request:
                with self.assertRaisesRegex(WorkflowError,'budget exhausted'):model.ask('check',{},images=[p])
                request.assert_not_called()

if __name__=='__main__':unittest.main()
