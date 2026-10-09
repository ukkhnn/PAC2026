"""정답 영역 진단에서 검출을 생략하고 방향별 문자 후보를 보존한다."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from PIL import Image
from rapidocr import RapidOCR

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'e1_ocr'
sys.path.insert(0,str(BASE))
from run import prepare,write_json,sha
from score import normalize,score_text


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum():raise ValueError('잘못된 ID')
    out=ROOT/'runs'/args.run_id;out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((BASE/'manifest.json').read_text());jobs,targets=prepare(out,manifest)
    engine=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':4,'EngineConfig.onnxruntime.inter_op_num_threads':4})
    rows=[];raw=[]
    for target in targets:
        pool=[]
        for angle in [0,90,180,270]:
            with Image.open(out/'crops'/f"{target['id']}.png") as im:
                if angle: im=im.transpose({90:Image.Transpose.ROTATE_90,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_270}[angle])
                start=time.perf_counter();result=engine(im,use_det=False,use_cls=False);elapsed=time.perf_counter()-start
            candidates=[{'text':text,'confidence':float(score),'angle':angle} for text,score in zip(result.txts or [],result.scores or [])]
            raw.append({'id':target['id'],'angle':angle,'seconds':elapsed,'candidates':candidates})
            pool.extend(candidates)
        ordered=sorted(pool,key=lambda c:(-c['confidence'],c['angle']))
        unique=[];seen=set()
        for candidate in ordered:
            norm=normalize(candidate['text'])
            if norm not in seen:unique.append(candidate);seen.add(norm)
        zero=[c for c in pool if c['angle']==0]
        row={**target,'zero':score_text(target['expected'],{'candidates':zero}),'selected':score_text(target['expected'],{'candidates':unique[:3]}),
            'candidates':unique,'all_candidates_exact':normalize(target['expected']) in seen}
        rows.append(row);write_json(out/'raw-partial.json',raw)
        print(target['id'],row['zero']['prediction'],row['selected']['prediction'],flush=True)
    summary={}
    for mode in ['zero','selected']:
        scores=[r[mode] for r in rows];edits=sum(s['edits'] for s in scores);chars=sum(s['characters'] for s in scores)
        summary[mode]={'exact':sum(s['normalized_exact'] for s in scores),'labels':len(rows),'edits':edits,'characters':chars,'cer':edits/chars,'top3_exact':sum(s['top3_exact'] for s in scores)}
    summary.update({'all_candidates_exact':sum(r['all_candidates_exact'] for r in rows),'ambiguous_targets':sum(len(r['candidates'])>1 for r in rows),
        'mean_candidates':sum(len(r['candidates']) for r in rows)/len(rows),'calls':len(raw),'seconds':sum(r['seconds'] for r in raw)})
    write_json(out/'raw.json',raw);write_json(out/'cases.json',rows);write_json(out/'summary.json',summary)
    write_json(out/'environment.json',{'finished_at':datetime.now().astimezone().isoformat(),'reference_environment':'../e1_alternative/results/environment.json',
        'source_sha256':{p.name:sha(p) for p in [ROOT/'run_recognition.py',ROOT/'PROTOCOL.md']},'manifest_sha256':sha(BASE/'manifest.json')})
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
