"""시각 continue만으로 문서·대상을 추정하지 않는지 확인한다."""
import json
from pathlib import Path
import tempfile
import unittest
from contextweld.recapture_binding import recapture_binding
from contextweld.recognition import sha256
from recapture_support import make_bundle

ROOT = Path(__file__).resolve().parents[1]

class RecaptureBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.orders = json.loads((ROOT/'configs/document_demo/work_orders.json').read_text())
        self.drawing = json.loads((ROOT/'configs/shipyard_pipeline/drawing.json').read_text())

    def test_final_b_links_without_changing_source(self):
        bundle = make_bundle(self.root)
        before = {str(p): sha256(p) for p in bundle.rglob('*') if p.is_file()}
        binding = recapture_binding(bundle, self.orders, self.drawing)
        self.assertEqual(binding['frame_id'], 'frame-B')
        self.assertEqual(binding['part_id'], 'BISB30N-15')
        self.assertEqual(binding['joint_id'], 'JOINT-DEMO-01')
        self.assertEqual(binding['source_kind'], 'test_fixture')
        self.assertEqual(before, {str(p): sha256(p) for p in bundle.rglob('*') if p.is_file()})

    def test_a_can_continue_without_using_b(self):
        binding = recapture_binding(make_bundle(self.root, ['observed']), self.orders, self.drawing)
        self.assertEqual(binding['frame_id'], 'frame-A')

    def test_unresolved_and_failure_cannot_resume(self):
        for i, kwargs in enumerate([{'states':['retry','retry']}, {'fail':True}]):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                recapture_binding(make_bundle(self.root/str(i), **kwargs), self.orders, self.drawing)

    def test_wrong_or_unrelated_identity_cannot_resume(self):
        for i, kwargs in enumerate([{'part':'OTHER'}, {'joint':'J99'}, {'duplicate':True}, {'detached_joint':True}]):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                recapture_binding(make_bundle(self.root/str(i), **kwargs), self.orders, self.drawing)
