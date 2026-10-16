#!/usr/bin/env python3
"""실제 인식 묶음부터 현대·두산 HTTP 모의 전달까지 한 실행으로 연결한다.

--recapture-inputs를 주면 capture_binding이 `requires_recapture`로 실패했을 때
재촬영 루프를 기록 단계로 실행한다(의사결정 비변경, Option 1). 루프 판정은
판독 결정을 대체하지 않으며 파이프라인은 그대로 needs_review/blocked로 끝난다.
실제 모델 호출이므로 recapture의 det/rec/vlm 모델 경로·revision이 필요하다.
"""
from pathlib import Path
import argparse,json,sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from contextweld.weld_pipeline import run_pipeline
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--capture-inputs',type=Path);p.add_argument('--source-kind',choices=['capture','document'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--data-root',type=Path,default=REPO/'data/raw/demo-bootstrap-v1');p.add_argument('--index',type=Path,default=REPO/'output/document-rag/server-v1/index.json')
p.add_argument('--recapture-inputs',type=Path,help='재촬영 루프 입력(recapture-inputs.v1). capture_binding이 재촬영 판독으로 실패할 때 기록 단계로 실행한다')
p.add_argument('--recapture-output-root',type=Path,help='루프 번들 출력 루트(기본: REPO/output/recapture-loops)')
p.add_argument('--recapture-run-id',help='루프 run_id(기본: <output 이름>-recapture)')
p.add_argument('--recapture-ocr-device',default='cpu')
p.add_argument('--recapture-document-ids',nargs='+',default=['twi-weld-symbols'])
p.add_argument('--recapture-query',default='weld symbols arrow reference line fillet weld meaning')
p.add_argument('--recapture-top-k',type=int,default=3)
p.add_argument('--recapture-max-new-tokens',type=int,default=4096)
p.add_argument('--recapture-max-pixels',type=int,default=802816)
for component in ('det','rec','vlm'):
 p.add_argument(f'--recapture-{component}-model-dir',type=Path)
 p.add_argument(f'--recapture-{component}-revision')
a=p.parse_args()
if bool(a.source)==bool(a.capture_inputs):p.error('--source 또는 --capture-inputs 중 하나가 필요해')
if a.capture_inputs:
 import subprocess
 a.source=a.output.parent/(a.output.name+'-capture');a.source_kind='capture'
 subprocess.run([sys.executable,str(REPO/'scripts/run/run_marking_capture.py'),'--inputs',str(a.capture_inputs),'--output',str(a.source)],check=True)
recapture=None
if a.recapture_inputs:
 for component in ('det','rec','vlm'):
  if not getattr(a,f'recapture_{component}_model_dir') or not getattr(a,f'recapture_{component}_revision'):
   p.error(f'--recapture-{component}-model-dir/--recapture-{component}-revision 필요 (실제 모델 호출)')
 if not 1<=a.recapture_top_k<=10 or a.recapture_max_new_tokens<128 or a.recapture_max_pixels<65536:
  p.error('잘못된 재촬영 검색·생성 예산')
 from contextweld.recognition import PaddleEngine,QwenEngine,environment_record,model_record,sha256
 from contextweld.recapture_inference import PipelineObserver
 config={'schema_version':'recapture-inference-config.v1','evidence_kind':'actual_model',
  'environment':environment_record(REPO),'labels_used':False,
  'implementation_sha256':{str(x.relative_to(REPO)):sha256(x) for x in [REPO/'src/contextweld/recapture_inputs.py',REPO/'src/contextweld/recapture_loop.py',REPO/'src/contextweld/recapture_inference.py',Path(__file__).resolve()]},
  'models':{'det':model_record(a.recapture_det_model_dir,'PaddlePaddle/PP-OCRv6_medium_det',a.recapture_det_revision),
            'rec':model_record(a.recapture_rec_model_dir,'PaddlePaddle/PP-OCRv6_medium_rec',a.recapture_rec_revision),
            'vlm':model_record(a.recapture_vlm_model_dir,'Qwen/Qwen3-VL-8B-Instruct',a.recapture_vlm_revision)},
  'document_index_sha256':sha256(a.index),
  'ocr':{'device':a.recapture_ocr_device,'doc_orientation':False,'unwarping':False,
         'textline_orientation':False,'rec_score_threshold':0.0,'input_channels':'BGR',
         'enable_mkldnn':False,'cpu_threads':4},
  'vlm':{'device':'cuda:0','dtype':'bfloat16','attention':'sdpa','do_sample':False,
         'max_new_tokens':a.recapture_max_new_tokens,'max_pixels':a.recapture_max_pixels,'min_pixels':65536,
         'json_syntax_retries':1,'stages':['observation','relation','capture_assessment']},
  'retrieval':{'document_ids':a.recapture_document_ids,'query':a.recapture_query,'top_k':a.recapture_top_k}}
 observer=PipelineObserver(
  ocr_factory=lambda:PaddleEngine(a.recapture_det_model_dir,a.recapture_rec_model_dir,a.recapture_ocr_device),
  vlm_factory=lambda:QwenEngine(a.recapture_vlm_model_dir,a.recapture_max_new_tokens,a.recapture_max_pixels),
  document_index=json.loads(a.index.read_text(encoding='utf-8')),data_root=a.data_root.resolve(),
  document_ids=a.recapture_document_ids,query=a.recapture_query,top_k=a.recapture_top_k)
 recapture={'inputs_root':a.recapture_inputs,
            'output_root':a.recapture_output_root or REPO/'output/recapture-loops',
            'run_id':a.recapture_run_id or a.output.name+'-recapture',
            'observer':observer,'config':config}
r=run_pipeline(repo=REPO,output=a.output,source=a.source,source_kind=a.source_kind,data_root=a.data_root,index_path=a.index,recapture=recapture);v=json.loads((r/'manifest.json').read_text());print(json.dumps(v,ensure_ascii=False));sys.exit(0 if v['run_outcome']=='succeeded' else 1)
