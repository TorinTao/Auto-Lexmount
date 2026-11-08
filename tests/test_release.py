import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from autolex.common import WorkflowError, read_json, write_json
from autolex.release import prepare_release, release, recover_publication

PROFILE={'authors':'Fixture author','contact_email':'fixture@example.com','context_id':'fixture-context'}


class Browser:
    published=0;submitted=0;share_fail=False;submit_fail=False;bad_url=False;capture_fail=False
    def __init__(self,profile):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def prepare_upload(self,archive,title):self.title=title
    def capture(self,path):
        if type(self).capture_fail and path.name=='04-receipt.png':raise OSError('capture failed')
    def publish(self):
        type(self).published+=1
        return {'url':'https://example.com/agent' if type(self).bad_url else 'https://yours.lexmount.cn/artifact-site/s/fixture-product'}
    def share_and_verify(self,*args):
        if type(self).share_fail:raise WorkflowError('sharing unavailable')
        return {'passcode':'TEST12','access':'passcode','guest_verified':True}
    def fill_contest(self,fields):type(self).fields=fields
    def submit_contest(self):
        type(self).submitted+=1
        if type(self).submit_fail:raise TimeoutError()
        return {'id':'fixture-receipt','title':type(self).fields['workTitle']}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'generated-work';self.root.mkdir()
        self.check=patch('autolex.release.preflight');self.check.start();self.addCleanup(self.check.stop)
        for name,data in {'spec.json':{'selected':{'title':'Generated CSV guide','description':'Choose a data format','source_urls':['https://example.com/csv']}},
            'output.json':{'items':[{'points':[{'id':'point'}]}],'conclusions':[{'text':'conclusion'}]},
            'state.json':{'model_calls':3},'quality.json':{'version':2,'passed':True},'manifest.json':{},'input.json':{},'tests.json':{},'review.json':{}}.items():write_json(self.root/name,data)
        (self.root/'main.py').write_text('print("generated product")')
        (self.root/'index.html').write_text('<main><h1>Generated CSV guide</h1></main>')
        (self.root/'.env').write_text('PRIVATE_FIXTURE_SECRET')
        Browser.published=Browser.submitted=0
        Browser.share_fail=Browser.submit_fail=Browser.bad_url=Browser.capture_fail=False

    def run_release(self,**kw):return release(self.root,PROFILE,backend=Browser,**kw)

    def test_preparation_is_only_this_work_and_no_remote_write(self):
        result=self.run_release()
        self.assertEqual(result['status'],'prepared');self.assertEqual(Browser.published,0)
        with zipfile.ZipFile(self.root/'release/site.zip') as z:
            self.assertEqual(set(z.namelist()),{'index.html','materials.html'})
            text=''.join(z.read(n).decode() for n in z.namelist())
            self.assertIn('Generated CSV guide',text);self.assertIn('generated product',text)
            self.assertNotIn('PRIVATE_FIXTURE_SECRET',text);self.assertNotIn(PROFILE['contact_email'],text)
        first=hashlib.sha256((self.root/'release/site.zip').read_bytes()).hexdigest()
        self.run_release()
        self.assertEqual(first,hashlib.sha256((self.root/'release/site.zip').read_bytes()).hexdigest())

    def test_submit_uses_generated_title_and_own_published_url(self):
        result=self.run_release(send=True)
        self.assertEqual(result['status'],'submitted')
        self.assertEqual(Browser.fields['workTitle'],'Generated CSV guide')
        self.assertEqual(Browser.fields['evidenceLink'],result['url'])
        self.assertEqual(read_json(self.root/'submission-state.json')['receipt']['id'],'fixture-receipt')
        self.run_release(send=True)
        self.assertEqual((Browser.published,Browser.submitted),(1,1))

    def test_sharing_retry_reuses_already_published_work(self):
        Browser.share_fail=True
        with self.assertRaises(WorkflowError):self.run_release(send=True)
        self.assertEqual(read_json(self.root/'release-state.json')['status'],'published')
        Browser.share_fail=False;self.run_release(send=True)
        self.assertEqual(Browser.published,1)

    def test_unknown_submission_is_not_retried(self):
        Browser.submit_fail=True
        with self.assertRaisesRegex(WorkflowError,'unknown'):self.run_release(send=True)
        self.assertEqual(read_json(self.root/'release-state.json')['status'],'unknown')
        with self.assertRaisesRegex(WorkflowError,'uncertain'):self.run_release(send=True)
        self.assertEqual(Browser.submitted,1)

    def test_wrong_publisher_domain_never_reaches_submission(self):
        Browser.bad_url=True
        with self.assertRaisesRegex(WorkflowError,'canonical'):self.run_release(send=True)
        self.assertEqual(Browser.submitted,0)

    def test_revision_cannot_duplicate_same_task(self):
        import shutil
        self.run_release(send=True)
        other=self.root.parent/'revision';other.mkdir()
        for p in self.root.iterdir():
            if p.is_file() and p.name not in {'release-state.json','submission-state.json','.lock'}:shutil.copyfile(p,other/p.name)
        with self.assertRaisesRegex(WorkflowError,'already has a release'):
            release(other,PROFILE,send=True,backend=Browser)
        self.assertEqual(Browser.submitted,1)

    def test_receipt_is_saved_even_when_final_screenshot_fails(self):
        Browser.capture_fail=True
        self.assertEqual(self.run_release(send=True)['status'],'submitted')

    def test_old_quality_gate_cannot_be_released(self):
        write_json(self.root/'quality.json',{'passed':True,'version':1})
        with self.assertRaisesRegex(WorkflowError,'current evidence checks'):self.run_release(send=True)
        self.assertEqual(Browser.published,0)

    def test_invalid_profile_stops_before_browser(self):
        with self.assertRaisesRegex(WorkflowError,'contact_email'):release(self.root,{'authors':'fixture'},send=True,backend=Browser)
        self.assertEqual(Browser.published,0)

    def test_changed_manifest_cannot_reuse_publication(self):
        Browser.share_fail=True
        with self.assertRaises(WorkflowError):self.run_release(send=True)
        write_json(self.root/'manifest.json',{'changed':True})
        with self.assertRaisesRegex(WorkflowError,'Published work changed'):self.run_release(send=True)
        self.assertEqual(Browser.published,1)

    def test_recovery_verifies_existing_url_without_upload(self):
        draft=prepare_release(self.root,PROFILE)
        write_json(self.root/'release-state.json',{'status':'unknown','phase':'publish','source_manifest_sha256':draft['source_manifest_sha256']})
        result=recover_publication(self.root,PROFILE,'https://yours.lexmount.cn/artifact-site/s/known-work',backend=Browser)
        self.assertEqual(result['status'],'published');self.assertEqual(Browser.published,0)
        self.run_release(send=True)
        self.assertEqual(Browser.published,0);self.assertEqual(Browser.submitted,1)

    def test_publication_recovery_cannot_resend_uncertain_submission(self):
        write_json(self.root/'release-state.json',{'status':'unknown','phase':'submit'})
        with self.assertRaisesRegex(WorkflowError,'uncertain publication'):
            recover_publication(self.root,PROFILE,'https://yours.lexmount.cn/artifact-site/s/known-work',backend=Browser)
        self.assertEqual(Browser.submitted,0)

    def test_resume_preserves_the_bundle_already_published(self):
        Browser.share_fail=True
        with self.assertRaises(WorkflowError):self.run_release(send=True)
        before=(self.root/'release/site.zip').read_bytes()
        # Operational counters may change; a resume still uses the uploaded bytes.
        write_json(self.root/'state.json',{'model_calls':20})
        prepare_release(self.root,PROFILE)
        self.assertEqual((self.root/'release/site.zip').read_bytes(),before)
        (self.root/'release/site.zip').write_bytes(b'tampered')
        with self.assertRaisesRegex(WorkflowError,'archive changed'):self.run_release(send=True)


if __name__=='__main__':unittest.main()
