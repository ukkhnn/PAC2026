"""목록 보충은 원본 불변·알려진 누락에만 허용한다."""
from pathlib import Path
import tempfile
import unittest
from contextweld_dashboard.preservation import prepare_weld_copy
from contextweld.recognition import sha256
from contextweld.weld_pipeline import run_pipeline
from recapture_support import make_bundle
ROOT=Path(__file__).resolve().parents[1]

class PreservationTests(unittest.TestCase):
    def test_known_historical_omissions_are_repaired_in_copy_only(self):
        source=ROOT/'output/weld-pipeline-20261010/marking-delivery-02'
        if not source.exists(): self.skipTest('historical local evidence unavailable')
        before=sha256(source/'checksums.json')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            report=prepare_weld_copy(source,root/'copy',root/'report.json')
            self.assertEqual(len(report['added_entries']),2)
            self.assertTrue(report['verification']['verified'])
        self.assertEqual(sha256(source/'checksums.json'),before)

    def test_unknown_extra_file_is_not_silently_rehashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); source=make_bundle(root/'source')
            bundle=run_pipeline(repo=ROOT,output=root/'resumed',source=source,source_kind='recapture',
                data_root=ROOT/'data/raw/demo-bootstrap-v1',index_path=ROOT/'output/document-rag/server-v1/index.json')
            (bundle/'unexpected.txt').write_text('unregistered')
            with self.assertRaisesRegex(ValueError,'추가 파일'):
                prepare_weld_copy(bundle,root/'copy',root/'report.json')
            self.assertFalse((root/'copy').exists())
