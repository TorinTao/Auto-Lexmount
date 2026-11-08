import tempfile
import unittest
from pathlib import Path
from autolex.common import read_json, write_json, WorkflowError
from autolex.workflow import Workflow
from scripts.revisit_visuals import prepare

class VisualRevisitTests(unittest.TestCase):
    def parent(self, root):
        parent=root/'parent';Workflow(parent,'https://example.com',demo=True).run()
        state=read_json(parent/'state.json');state['demo']=False;write_json(parent/'state.json',state)
        (parent/'submission-state.json').write_text('{"status":"submitted"}')
        (parent/'release-state.json').write_text('{"status":"submitted"}')
        return parent

    def test_child_reuses_content_but_not_receipt_or_completed_visual_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent=self.parent(root);before={p.name:p.read_bytes() for p in parent.iterdir() if p.is_file()}
            child=root/'child';record=prepare(parent,child)
            state=read_json(child/'state.json')
            self.assertEqual(state['visual_parent'],'parent')
            from autolex.server import Dashboard
            self.assertEqual(Dashboard(root).detail('child')['summary']['parent'],'parent')
            self.assertEqual(state['completed'],['rules','ideas','build','test'])
            self.assertTrue(state['visual_enabled'])
            for name in ['main.py','output.json','input.json','tests.json']:
                self.assertEqual((child/name).read_bytes(),before[name])
            self.assertFalse((child/'release-state.json').exists())
            self.assertFalse((child/'submission-state.json').exists())
            self.assertFalse((child/'index.html').exists())
            self.assertTrue(record['parent_manifest_sha256'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in parent.iterdir() if p.is_file()})

    def test_changed_parent_or_existing_child_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent=self.parent(root);child=root/'child'
            child.mkdir()
            with self.assertRaisesRegex(WorkflowError,'already exists'):prepare(parent,child)
            child.rmdir();(parent/'output.json').write_text('{}')
            with self.assertRaisesRegex(WorkflowError,'changed'):prepare(parent,child)
            self.assertFalse(child.exists())

if __name__=='__main__':unittest.main()
