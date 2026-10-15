"""대상/조건/명령 연결 오류가 수신 단계에서 거절되는지, 번들 검증이 추가·변조 파일과 부분 전달 상태를 감지하는지 검사한다."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import contextweld.weld_pipeline as wp
from contextweld.weld_pipeline import capture_binding, run_pipeline, validate_robot_extension, verify_pipeline
from contextweld.robot_input import build_work_order_input_previews
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text())
class WeldingPipelineTests(unittest.TestCase):
 def setUp(self):
  self.orders=read('configs/document_demo/work_orders.json');self.drawing=read('configs/shipyard_pipeline/drawing.json')
  self.capture={'source_kind':'model','frames':[{'frame_id':'frame-B','image_sha256':'a'*64,'readout':{'markings':[{'text':'BISB30N-15','role':'part'},{'text':'J01','role':'joint'}],'relations':[{'part_text':'BISB30N-15','joint_text':'J01','target_description':'observed plate joint'}],'quality':{'requires_recapture':False}}}]}
  b=capture_binding(self.capture,self.orders,self.drawing)
  p=build_work_order_input_previews(read('data/knowledge/lanl-wps-3501-reviewed.json'),self.orders,read('configs/document_demo/weld_recipes.json'),{'hyundai':read('configs/robot_profiles/hyundai_hi6_current_voltage.json'),'doosan':read('configs/robot_profiles/doosan_drl_analog.json')},order_id=b['order_id'])
  self.commands={k:{'target':{'part_id':b['part_id'],'joint_id':b['joint_id']},'marking_binding':b,'common_spec':p['common_spec'],'robot_input':v} for k,v in p['previews'].items()}
 def test_both_manufacturers_preserve_marking_target(self):
  for c in self.commands.values():self.assertEqual(validate_robot_extension(c),[])
 def test_unread_part_does_not_select_default_order(self):
  self.capture['frames'][0]['readout']['markings'][0]['text']='OTHER-123'
  with self.assertRaises(ValueError):capture_binding(self.capture,self.orders,self.drawing)
 def test_wrong_joint_does_not_select_default_joint(self):
  self.capture['frames'][0]['readout']['markings'][1]['text']='J99'
  with self.assertRaises(ValueError):capture_binding(self.capture,self.orders,self.drawing)
 def test_ambiguous_relation_blocks(self):
  self.capture['frames'][0]['readout']['relations']*=2
  with self.assertRaises(ValueError):capture_binding(self.capture,self.orders,self.drawing)
 def test_target_substitution_rejected(self):
  c=deepcopy(self.commands['hyundai']);c['target']['part_id']='OTHER-123';self.assertTrue(validate_robot_extension(c))
 def test_common_value_substitution_rejected(self):
  c=deepcopy(self.commands['hyundai']);c['common_spec']['parameters']['current']['value']='200';self.assertTrue(validate_robot_extension(c))
 def test_wrong_unit_conversion_rejected(self):
  c=deepcopy(self.commands['doosan']);next(f for f in c['robot_input']['fields'] if f['name']=='travel_speed')['selected']['target']['value']='25.4';self.assertTrue(validate_robot_extension(c))
 def test_command_substitution_rejected(self):
  c=deepcopy(self.commands['hyundai']);c['robot_input']['command_preview']='arccond D, cur=250';self.assertTrue(validate_robot_extension(c))
class PipelineBundleTests(unittest.TestCase):
 """번들 검증 무결성: 미등재·변조 파일 탐지와 부분 전달 상태 표기."""
 def setUp(self):
  self.repo=ROOT
  self.data_root=ROOT/'data/raw/demo-bootstrap-v1'
  self.index=ROOT/'output/document-rag/server-v1/index.json'
  self.tmp=Path(tempfile.mkdtemp(prefix='weld-pipeline-test-'))
 def tearDown(self):
  shutil.rmtree(self.tmp,ignore_errors=True)
 def make_capture_source(self):
  src=self.tmp/'source';src.mkdir()
  capture={'schema_version':'marking-capture.v1','run_id':'test-source-01','started_at_utc':'2026-10-15T00:00:00Z',
           'source_kind':'model','capture_mode':'pre_captured','physical_movement_triggered':False,
           'frames':[{'frame_id':'frame-B','image_sha256':'a'*64,
                      'readout':{'markings':[{'text':'BISB30N-15','role':'part'},{'text':'J01','role':'joint'}],
                                 'relations':[{'part_text':'BISB30N-15','joint_text':'J01','target_description':'observed plate joint'}],
                                 'quality':{'requires_recapture':False}}}],'model_calls':3}
  (src/'capture.json').write_text(json.dumps(capture))
  return src
 def test_verify_detects_extra_file(self):
  root=self.tmp/'run_extra';root.mkdir();(root/'checksums.json').write_text('{}');(root/'stray.txt').write_text('x')
  with self.assertRaisesRegex(ValueError,'미등재'):verify_pipeline(root)
 def test_verify_detects_tampered_file(self):
  root=self.tmp/'run_tamper';root.mkdir();(root/'a.txt').write_text('one')
  (root/'checksums.json').write_text(json.dumps({'a.txt':'-'*64}))
  with self.assertRaisesRegex(ValueError,'해시 불일치'):verify_pipeline(root)
 def test_run_pipeline_verifies_end_to_end(self):
  bundle=run_pipeline(repo=self.repo,output=self.tmp/'run_ok',source=self.make_capture_source(),source_kind='capture',
                      data_root=self.data_root,index_path=self.index)
  self.assertTrue(verify_pipeline(bundle)['verified'])
  m=json.loads((bundle/'manifest.json').read_text())
  self.assertEqual((m['run_outcome'],m['delivery_status'],m['manufacturers']),('succeeded','received',['hyundai','doosan']))
 def test_partial_delivery_records_partial_status(self):
  real=wp.send_command
  def fake_send(url,command):
   if command['command_id'].endswith('-doosan'):
    return {'request':command,'http_status':200,'ack':{'schema_version':'demo-ack.v1','command_id':command['command_id'],
            'status':'rejected','execution_authorized':False,'application_authorized':False,'command_sha256':'0'*64,'reason':'test rejection'}}
   return real(url,command)
  with patch('contextweld.weld_pipeline.send_command',side_effect=fake_send):
   bundle=run_pipeline(repo=self.repo,output=self.tmp/'run_partial',source=self.make_capture_source(),source_kind='capture',
                       data_root=self.data_root,index_path=self.index)
  m=json.loads((bundle/'manifest.json').read_text())
  self.assertEqual(m['run_outcome'],'needs_review');self.assertEqual(m['delivery_status'],'partial')
  self.assertEqual(m['manufacturers'],['hyundai']);self.assertEqual(m['delivery_failures'],{'doosan':'rejected'})
  self.assertTrue((bundle/'results/deliveries.json').exists())
  self.assertTrue((bundle/'results/error.json').exists())
if __name__=='__main__':unittest.main()
