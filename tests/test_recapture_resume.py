"""재촬영 결과 재사용→문서 검증→양 제조사 loopback 전달의 종단 검사."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from contextweld.recognition import sha256
from contextweld.weld_pipeline import run_pipeline, verify_pipeline
from recapture_support import make_bundle

ROOT = Path(__file__).resolve().parents[1]

class RecaptureResumeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def run_bundle(self, bundle, repo=ROOT, name='resumed'):
        return run_pipeline(repo=repo, output=self.root/name, source=bundle,
                            source_kind='recapture', data_root=ROOT/'data/raw/demo-bootstrap-v1',
                            index_path=ROOT/'output/document-rag/server-v1/index.json')

    def test_b_resume_delivers_both_and_preserves_fixture_provenance(self):
        source = make_bundle(self.root/'source')
        before = {str(p): sha256(p) for p in source.rglob('*') if p.is_file()}
        output = self.run_bundle(source)
        manifest = json.loads((output/'manifest.json').read_text())
        self.assertEqual(manifest['run_outcome'], 'succeeded',
                         (output/'results/error.json').read_text() if (output/'results/error.json').exists() else '')
        self.assertEqual(manifest['delivery_status'], 'received')
        self.assertEqual(manifest['new_model_calls'], 0)
        self.assertEqual(manifest['source_kind'], 'test_fixture')
        self.assertEqual(set(verify_pipeline(output)['receipts']), {'hyundai','doosan'})
        self.assertEqual(before, {str(p): sha256(p) for p in source.rglob('*') if p.is_file()})
        for vendor in ('hyundai','doosan'):
            command = json.loads((output/f'commands/{vendor}-request.json').read_text())
            self.assertEqual(command['marking_binding']['frame_id'], 'frame-B')
            self.assertEqual(command['common_spec']['target']['source_kind'], 'test_fixture')
            self.assertFalse(command['execution_authorized'])

    def test_unresolved_wrong_identity_and_failure_never_send(self):
        for i, kwargs in enumerate([{'states':['retry','retry']}, {'part':'OTHER'}, {'fail':True}]):
            with self.subTest(kwargs=kwargs), patch('contextweld.weld_pipeline.send_command') as send:
                output = self.run_bundle(make_bundle(self.root/str(i), **kwargs), name=f'blocked-{i}')
                manifest = json.loads((output/'manifest.json').read_text())
                self.assertEqual(manifest['delivery_status'], 'blocked')
                send.assert_not_called()

    def test_document_conflict_still_blocks_after_visual_continue(self):
        repo = self.root/'repo'
        shutil.copytree(ROOT/'configs', repo/'configs')
        shutil.copytree(ROOT/'data/knowledge', repo/'data/knowledge')
        path = repo/'configs/shipyard_pipeline/drawing.json'
        drawing = json.loads(path.read_text())
        drawing['process'] = 'GTAW'
        path.write_text(json.dumps(drawing))
        with patch('contextweld.weld_pipeline.send_command') as send:
            output = self.run_bundle(make_bundle(self.root/'source'), repo=repo)
            self.assertEqual(json.loads((output/'manifest.json').read_text())['delivery_status'], 'blocked')
            send.assert_not_called()

    def test_output_cannot_be_inside_source(self):
        source = make_bundle(self.root/'source')
        with self.assertRaises(ValueError):
            run_pipeline(repo=ROOT, output=source/'child', source=source, source_kind='recapture',
                         data_root=self.root, index_path=self.root/'unused')
