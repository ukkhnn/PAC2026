#!/usr/bin/env python3
"""실제 인식 묶음부터 현대·두산 HTTP 모의 전달까지 한 실행으로 연결한다."""
from pathlib import Path
import argparse,json,sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from contextweld.weld_pipeline import run_pipeline
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--capture-inputs',type=Path);p.add_argument('--source-kind',choices=['capture','document'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--data-root',type=Path,default=REPO/'data/raw/demo-bootstrap-v1');p.add_argument('--index',type=Path,default=REPO/'output/document-rag/server-v1/index.json')
a=p.parse_args()
if bool(a.source)==bool(a.capture_inputs):p.error('--source 또는 --capture-inputs 중 하나가 필요해')
if a.capture_inputs:
 import subprocess
 a.source=a.output.parent/(a.output.name+'-capture');a.source_kind='capture'
 subprocess.run([sys.executable,str(REPO/'scripts/run/run_marking_capture.py'),'--inputs',str(a.capture_inputs),'--output',str(a.source)],check=True)
r=run_pipeline(repo=REPO,output=a.output,source=a.source,source_kind=a.source_kind,data_root=a.data_root,index_path=a.index);v=json.loads((r/'manifest.json').read_text());print(json.dumps(v,ensure_ascii=False));sys.exit(0 if v['run_outcome']=='succeeded' else 1)
