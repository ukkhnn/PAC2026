"""통합 전달 검증기를 관리자에서 호출하고 실패를 숨기지 않는지 검사한다."""
import json
from pathlib import Path
import tempfile
import unittest
from contextweld_dashboard.integrity import inspect
from contextweld.weld_pipeline import run_pipeline
from recapture_support import make_bundle
ROOT=Path(__file__).resolve().parents[1]

class WeldIntegrityTests(unittest.TestCase):
    def test_resumed_bundle_verified_then_extra_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            source=make_bundle(root/'source')
            output=run_pipeline(repo=ROOT,output=root/'resumed',source=source,source_kind='recapture',
                data_root=ROOT/'data/raw/demo-bootstrap-v1',index_path=ROOT/'output/document-rag/server-v1/index.json')
            result=inspect(output)
            self.assertEqual(result['state'],'verified',result['message'])
            self.assertFalse(any(c['state']=='fail' for c in result['checks']))
            (output/'extra.txt').write_text('not registered')
            result=inspect(output)
            self.assertEqual(result['state'],'failed')
            self.assertIn('미등재',result['message'])

    def test_preserved_shipyard_original_is_supported(self):
        source=ROOT/'output/weld-pipeline-20261010/shipyard-connected-01'
        if not source.exists(): self.skipTest('local historical evidence unavailable')
        result=inspect(source)
        self.assertEqual(result['state'],'verified',result['message'])
        self.assertIn('verify_pipeline',result['verifier'])
