import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from autolex.release_browser import publication_url, ReleaseBrowser


class PublicationResponseTests(unittest.TestCase):
    def test_direct_and_async_completed_responses(self):
        for data in [{'slug':'work-1','editToken':'must-not-be-returned'},{'status':'completed','result':{'slug':'work-1'}}]:
            self.assertEqual(publication_url(data),'https://yours.lexmount.cn/artifact-site/s/work-1')

    def test_queued_upload_and_invalid_paths_are_not_success(self):
        for data in [{'status':'queued','result':{'slug':'not-ready'}},{'slug':'../../agent'},None,{'error':'failed'},{'status':'completed','result':None}]:
            self.assertIsNone(publication_url(data))

    def test_archive_completion_is_polled_for_this_upload_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=ReleaseBrowser({});b.proof=Path(tmp)
            callbacks={}
            response=SimpleNamespace(status=202,url='https://yours.lexmount.cn/artifact-site/api/uploads/ver_ours/commit?async=1',json=lambda:{'versionId':'ver_ours','status':'queued'})
            page=Mock()
            page.on.side_effect=lambda event,cb:callbacks.update({event:cb})
            page.get_by_role.return_value.click.side_effect=lambda:callbacks['response'](response)
            b.page=page
            get=Mock(return_value=SimpleNamespace(status=200,json=lambda:{'status':'completed','result':{'slug':'our-generated-work'}}))
            b.context=SimpleNamespace(request=SimpleNamespace(get=get))
            self.assertEqual(b.publish()['url'],'https://yours.lexmount.cn/artifact-site/s/our-generated-work')
            self.assertEqual(get.call_args.args[0],'https://yours.lexmount.cn/artifact-site/api/uploads/ver_ours')
            self.assertTrue((b.proof/'upload-operation.json').exists())


if __name__=='__main__':unittest.main()
