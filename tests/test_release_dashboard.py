import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from autolex.common import WorkflowError,write_json
from autolex.server import Dashboard


class ReleaseDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.app=Dashboard(self.root)
        p=self.root/'work';p.mkdir()
        write_json(p/'state.json',{'demo':False,'status':'ready','completed':['package']})
        self.profile=self.root/'profile.json'
        write_json(self.profile,{'authors':'fixture','contact_email':'fixture@example.com','context_id':'fixture'})

    def test_dashboard_release_uses_server_profile_and_current_run(self):
        with patch.dict('os.environ',{'AUTOLEX_RELEASE_PROFILE':str(self.profile)}),patch('autolex.release.prepare_release') as prepare,patch('autolex.release.release') as release:
            result=self.app.launch_release('work')
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(result['id'],'work')
            self.assertEqual(prepare.call_args.args[0],self.root/'work')
            self.assertEqual(release.call_args.args[0],self.root/'work')
            self.assertTrue(release.call_args.kwargs['send'])
            self.assertEqual(release.call_args.args[1]['authors'],'fixture')

    def test_demo_is_rejected_before_thread_or_publication(self):
        write_json(self.root/'work/state.json',{'demo':True,'status':'ready','completed':['package']})
        with patch.dict('os.environ',{'AUTOLEX_RELEASE_PROFILE':str(self.profile)}),patch('autolex.release.release') as release:
            with self.assertRaisesRegex(WorkflowError,'completed live'):self.app.launch_release('work')
            release.assert_not_called()

    def test_missing_profile_is_actionable(self):
        with patch.dict('os.environ',{'AUTOLEX_RELEASE_PROFILE':''}):
            with self.assertRaisesRegex(WorkflowError,'AUTOLEX_RELEASE_PROFILE'):self.app.launch_release('work')

    def test_automatic_release_runs_only_after_workflow_finishes(self):
        events=[]
        class Workflow:
            def __init__(self,*args,**kwargs):pass
            def run(self,until):events.append('workflow:'+until)
        app=Dashboard(self.root,workflow=Workflow)
        with patch.dict('os.environ',{'AUTOLEX_RELEASE_PROFILE':str(self.profile)}),patch('autolex.server.configuration',return_value={'configured':True}),patch('autolex.release.release',side_effect=lambda *a,**kw:events.append('release')):
            result=app.launch({'url':'https://example.com','mode':'live','auto_release':True})
            for _ in range(100):
                if not app.active:break
                time.sleep(.01)
            self.assertEqual(events,['workflow:package','release'])
            self.assertTrue(app.detail(result['id'])['state']['auto_release'])

    def test_demo_cannot_enable_automatic_submission(self):
        with patch.dict('os.environ',{'AUTOLEX_RELEASE_PROFILE':str(self.profile)}):
            with self.assertRaisesRegex(WorkflowError,'自动投稿需要真实'):
                self.app.launch({'url':'https://example.com','mode':'demo','auto_release':True})

    def test_failed_generation_never_reaches_automatic_submission(self):
        class FailedWorkflow:
            def __init__(self,*args,**kwargs):pass
            def run(self,until):raise WorkflowError('Tests did not pass')
        app=Dashboard(self.root,workflow=FailedWorkflow)
        with patch('autolex.release.release') as release:
            app._work('work','https://example.com',False,3,'package',auto_release=True)
            release.assert_not_called()
            self.assertEqual(app.errors['work'],'Tests did not pass')


if __name__=='__main__':unittest.main()
