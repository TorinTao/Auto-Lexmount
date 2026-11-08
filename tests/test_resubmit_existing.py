import io
import unittest
import zipfile
from scripts.resubmit_existing import validate_target,matching_archive,check_resume
from autolex.common import WorkflowError

class ExistingUpdateTests(unittest.TestCase):
    def test_target_requires_exact_known_domain_and_receipt(self):
        target={'title':'Work','url':'https://yours.lexmount.cn/artifact-site/s/abc','receipt':'11111111-2222-3333-4444-555555555555'}
        self.assertEqual(validate_target(target),'abc')
        for changes in [{'url':'https://evil.example/s/abc'},{'receipt':'missing'},{'title':''}]:
            with self.assertRaises(WorkflowError):validate_target({**target,**changes})

    def test_export_must_match_every_prepared_byte(self):
        def zipped(files):
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:
                for k,v in files.items():z.writestr(k,v)
            return b.getvalue()
        original=zipped({'index.html':'report','materials.html':'source'})
        matching_archive(original,original)
        for altered in [zipped({'index.html':'report'}),zipped({'index.html':'changed','materials.html':'source'})]:
            with self.assertRaises(WorkflowError):matching_archive(altered,original)

    def test_unknown_operations_cannot_be_repeated(self):
        for status in ['updating_materials','saving_entry','unknown_materials','unknown_entry']:
            with self.assertRaises(WorkflowError):check_resume({'status':status,'archive_sha256':'same'},'same')
        for status in ['materials_updated','guest_verified','entry_saved','complete']:
            check_resume({'status':status,'archive_sha256':'same'},'same')
        with self.assertRaises(WorkflowError):check_resume({'status':'prepared','archive_sha256':'old'},'new')

if __name__=='__main__':unittest.main()
