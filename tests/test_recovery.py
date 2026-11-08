import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from autolex.clients import Model
from autolex.common import WorkflowError, read_json, write_json
from autolex.demo import DemoFetch, DemoModel, CODE
from autolex.workflow import Workflow


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_hard_exit_reserves_model_call_before_network(self):
        script='''import os,sys
from autolex.clients import Model
from autolex.demo import DemoFetch
from autolex.workflow import Workflow
import autolex.clients
# Simulate an abrupt process death after the request would have been issued.
autolex.clients.post_json=lambda *a,**kw:os._exit(77)
Workflow(sys.argv[1],"https://example.com",fetcher=DemoFetch(),model=Model(max_calls=1)).run()
'''
        env={**os.environ,'MODEL_API_KEY':'fixture-only','MODEL_NAME':'fixture'}
        result=subprocess.run([sys.executable,'-c',script,str(self.root)],env=env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,77)
        self.assertEqual(read_json(self.root/'state.json')['model_calls'],1)
        with patch.dict(os.environ,env),patch('autolex.clients.post_json') as post:
            with self.assertRaisesRegex(WorkflowError,'budget exhausted'):
                Workflow(self.root,'https://example.com',fetcher=DemoFetch(),model=Model(max_calls=1)).run()
            post.assert_not_called()

    def test_recovery_reuses_latest_repair_and_only_current_feedback(self):
        root=self.root
        class RecordingModel(DemoModel):
            contexts=[]
            def ask(self,task,context):
                if task.startswith('CODE'):
                    self.contexts.append(context)
                return super().ask(task,context)
        w=Workflow(root,'https://example.com',demo=False,fetcher=DemoFetch(),model=RecordingModel(),repairs=0,
                   executor=lambda *a,**k:{'returncode':1,'log':'new failure','timeout':False})
        w.run('build')
        latest=CODE+'\n# latest repair, retained across resume\n'
        w.save_candidate(latest)
        write_json(root/'tests.json',{'passed':False,'attempts':[{'failures':['old resolved problem']},{'failures':['current problem']}]})
        with self.assertRaises(WorkflowError):w.run('test')
        ctx=w.model.contexts[-1]
        self.assertEqual(ctx['code'],latest)
        self.assertEqual(ctx['failures'],['current problem'])
        self.assertTrue((root/'test-history.json').exists())

    def test_old_error_is_cleared_before_retrying_stage(self):
        root=self.root
        class InspectingFetch(DemoFetch):
            def fetch(self,url):
                self_state=read_json(root/'state.json')
                assert self_state.get('error') is None
                return super().fetch(url)
        write_json(root/'state.json',{'url':'https://example.com','demo':True,'completed':[],'hashes':{},'model_calls':0,'error':'old problem'})
        Workflow(root,'https://example.com',demo=True,fetcher=InspectingFetch()).run('rules')

    def test_rule_retry_receives_last_failure_after_restart(self):
        write_json(self.root/'rule-errors.json', [{'error':'Copy original semicolon', 'response':{}}])
        class RecordingModel(DemoModel):
            def ask(model,task,context):
                self.assertEqual(context['failure'],'Copy original semicolon')
                return super().ask(task,context)
        Workflow(self.root,'https://example.com',demo=True,model=RecordingModel()).run('rules')

    def test_repeated_network_failure_does_not_duplicate_test_history(self):
        w=Workflow(self.root,'https://example.com',demo=False,fetcher=DemoFetch(),model=DemoModel())
        w.run('build')
        write_json(self.root/'tests.json',{'passed':False,'attempts':[{'failures':['repair me']}]})
        with patch.object(w,'generate_code',side_effect=WorkflowError('network down')):
            for _ in range(2):
                with self.assertRaisesRegex(WorkflowError,'network down'):w.run('test')
        self.assertEqual(len(read_json(self.root/'test-history.json')),1)

    def test_candidate_checksum_detects_accidental_edit(self):
        w=Workflow(self.root,'https://example.com',demo=True)
        w.save_candidate(CODE)
        d=read_json(self.root/'candidate.json');d['code']+='\n# changed'
        write_json(self.root/'candidate.json',d)
        with self.assertRaisesRegex(WorkflowError,'checkpoint changed'):w.latest_candidate(CODE)


if __name__=='__main__':unittest.main()
