"""동일 공개 표본을 대안 OCR로 처리하고 기존 측정 코드로 채점한다."""

import argparse
from datetime import datetime
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from PIL import Image
from rapidocr import RapidOCR
import rapidocr
from omegaconf import OmegaConf

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'e1_ocr'
sys.path.insert(0,str(BASE))
from run import prepare,evaluate,write_json,sha


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum(): raise ValueError('잘못된 run_id')
    out=ROOT/'runs'/args.run_id;out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((BASE/'manifest.json').read_text());jobs,targets=prepare(out,manifest)
    write_json(out/'jobs.json',jobs);write_json(out/'targets.json',targets)
    params={'EngineConfig.onnxruntime.intra_op_num_threads':4,'EngineConfig.onnxruntime.inter_op_num_threads':4}
    engine=RapidOCR(params=params)
    (out/'config.yaml').write_text(OmegaConf.to_yaml(engine.cfg))
    records=[]
    for job in jobs:
        start=time.perf_counter()
        result=engine(job['path'])
        elapsed=time.perf_counter()-start
        observations=[]
        with Image.open(job['path']) as image: w,h=image.size
        if result.boxes is not None:
            if result.txts is None or len(result.txts)!=len(result.boxes): raise ValueError('OCR 출력 길이 불일치')
            for box,text,confidence in zip(result.boxes,result.txts,result.scores):
                points=box.tolist();xs,ys=zip(*points)
                observations.append({'bbox':[min(xs)/w,min(ys)/h,max(xs)/w,max(ys)/h],
                    'polygon':points,'candidates':[{'text':text,'confidence':float(confidence)}]})
        records.append({'id':job['id'],'seconds':elapsed,'observations':observations})
        write_json(out/'raw-partial.json',records)
        print(job['id'],len(observations),round(elapsed,3),flush=True)
    raw={'engine':'RapidOCR','version':importlib.metadata.version('rapidocr'),'onnxruntime':importlib.metadata.version('onnxruntime'),'device':'CPU','results':records}
    summary,cases=evaluate(raw,targets,manifest)
    write_json(out/'raw.json',raw);write_json(out/'summary.json',summary);write_json(out/'cases.json',cases)
    package=Path(rapidocr.__file__).parent
    metadata={'finished_at':datetime.now().astimezone().isoformat(),'python':platform.python_version(),'os':platform.mac_ver()[0],
        'manifest_sha256':sha(BASE/'manifest.json'),'source_sha256':{str(p.relative_to(ROOT.parent)):sha(p) for p in [ROOT/'run_alternative.py',ROOT/'PROTOCOL.md',BASE/'run.py',BASE/'score.py']},
        'models':{p.name:sha(p) for p in sorted((package/'models').glob('*.onnx'))}}
    write_json(out/'environment.json',metadata)
    (out/'requirements-lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    print(json.dumps({c:{k:v for k,v in s.items() if k!='per_image'} for c,s in summary['conditions'].items()},indent=2))


if __name__=='__main__':main()
