"""통합 실행 화면 모델의 원문 연결과 자체 완결 패키지를 확인한다."""
from pathlib import Path
import tempfile
import unittest
import admin_dashboard_support as support
from contextweld.weld_pipeline import run_pipeline
from contextweld_dashboard.adapters import build_model
from contextweld_dashboard.bundle_io import BundleReader
from contextweld_dashboard.catalog import added_source
from contextweld_dashboard.integrity import inspect
from contextweld_dashboard.model import SCHEMA_RUN
from contextweld_dashboard.package import build_package
from contextweld_dashboard.package_tools.verify_package import verify
from recapture_support import make_bundle
ROOT=Path(__file__).resolve().parents[1]

class WeldDashboardTests(unittest.TestCase):
    def test_model_links_to_sources_and_packaged_assets_are_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            source=make_bundle(root/'source')
            output=run_pipeline(repo=ROOT,output=root/'resumed',source=source,source_kind='recapture',
                data_root=ROOT/'data/raw/demo-bootstrap-v1',index_path=ROOT/'output/document-rag/server-v1/index.json')
            item=added_source(output,set())
            self.assertEqual((item.group,item.kind),('connected','weld_pipeline'))
            check=inspect(output)
            model=build_model(item,BundleReader(output,item.key),check,support.context_for([item]))
            run={'schema':SCHEMA_RUN,'key':item.key,'integrity':check,'roots':{item.key:str(output)},'files':[],**model}
            support.assert_valid(self,run)
            self.assertGreater(support.assert_linkage(self,run,{item.key:output}),60)
            self.assertEqual(run['tabs']['recapture']['availability'],'available')
            self.assertIn('테스트용 관측',support.all_text(run))
            report=build_package(root/'package',[item],viewer_html=False)
            self.assertFalse(report['model_problems'])
            self.assertTrue(verify(root/'package')['ok'])
            self.assertTrue((root/'package/assets/robot_input.js').is_file())
            self.assertEqual(inspect(root/'package/bundles'/item.key)['state'],'verified')
