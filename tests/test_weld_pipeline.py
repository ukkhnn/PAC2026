"""대상/조건/명령 연결 오류가 수신 단계에서 거절되는지 검사한다."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from contextweld.weld_pipeline import capture_binding, validate_robot_extension
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
if __name__=='__main__':unittest.main()
