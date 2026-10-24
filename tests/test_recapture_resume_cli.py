"""저장 결과 재개는 모델 초기화 없이 CLI로도 동작해야 한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from recapture_support import make_bundle

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/run/run_weld_pipeline.py'

class ResumeCliTests(unittest.TestCase):
    def test_stored_source_requires_no_model_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = make_bundle(root/'source')
            run = subprocess.run([sys.executable,str(SCRIPT),'--source-kind','recapture',
                                  '--source',str(source),'--output',str(root/'resumed')],
                                 capture_output=True,text=True,cwd=ROOT)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            manifest = json.loads(run.stdout)
            self.assertEqual(manifest['new_model_calls'],0)
            self.assertEqual(manifest['delivery_status'],'received')

    def test_mixed_live_and_stored_inputs_rejected_before_loading_models(self):
        run = subprocess.run([sys.executable,str(SCRIPT),'--source-kind','recapture','--source','unused',
                              '--recapture-inputs','unused','--output','unused'],capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertIn('함께 쓸 수 없음',run.stderr)
