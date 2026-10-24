"""외부 해시를 다시 기록해도 재촬영 계보·대상 바꿔치기를 거절한다."""
import json
from pathlib import Path
import tempfile
import unittest
from contextweld.recognition import sha256
from contextweld.weld_pipeline import run_pipeline, verify_pipeline
from recapture_support import make_bundle
ROOT = Path(__file__).resolve().parents[1]

class RecaptureIntegrityTests(unittest.TestCase):
    def test_rehashed_binding_and_provenance_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            source=make_bundle(root/'source')
            output=run_pipeline(repo=ROOT,output=root/'resumed',source=source,source_kind='recapture',
                                data_root=ROOT/'data/raw/demo-bootstrap-v1',index_path=ROOT/'output/document-rag/server-v1/index.json')
            verify_pipeline(output)
            for ref, key, value, message in [
                ('results/marking-binding.json','frame_id','frame-A','재계산'),
                ('manifest.json','source_kind','actual_model','출처'),
                ('manifest.json','manufacturers',[],'제조사'),
                ('manifest.json','resume_mode',None,'방식')]:
                with self.subTest(key=key):
                    path=output/ref; original=path.read_bytes()
                    data=json.loads(original); data[key]=value; path.write_text(json.dumps(data))
                    sums=json.loads((output/'checksums.json').read_text()); sums[ref]=sha256(path)
                    (output/'checksums.json').write_text(json.dumps(sums))
                    with self.assertRaisesRegex(ValueError,message): verify_pipeline(output)
                    path.write_bytes(original); sums[ref]=sha256(path)
                    (output/'checksums.json').write_text(json.dumps(sums))
