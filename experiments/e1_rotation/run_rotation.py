"""동일 표본에 네 방향 Vision을 실행하고 정답 비참조 후보 병합을 평가한다."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'e1_ocr'
sys.path.insert(0,str(BASE))
from run import prepare, evaluate, write_json, sha
from score import assign, normalize
from rotation import merge


def summarize(raw: dict, targets: list, manifest: dict) -> tuple[dict,list,dict]:
    base_results=[]; merged_results=[]
    names=sorted({r['id'].rsplit('@',1)[0] for r in raw['results']})
    for name in names:
        variants=[{**r,'angle':int(r['id'].rsplit('@',1)[1])} for r in raw['results'] if r['id'].rsplit('@',1)[0]==name]
        if sorted(r['angle'] for r in variants)!=[0,90,180,270] or any(r.get('error') for r in variants):
            raise ValueError(f'실행 누락·중복·오류: {name}')
        zero=next(r for r in variants if r['angle']==0)
        base_results.append({**zero,'id':name})
        merged_results.append({'id':name,'seconds':sum(r['seconds'] for r in variants),'observations':merge(variants)})
    engine={k:v for k,v in raw.items() if k!='results'}
    base={**engine,'results':base_results}
    merged={**engine,'results':merged_results}
    # 기존 채점기의 top3에는 실제로 앞 3개만 전달한다. 전체 후보 지표는 별도 계산한다.
    limited={**merged,'results':[{**r,'observations':[{**o,'candidates':o['candidates'][:3]} for o in r['observations']]} for r in merged_results]}
    baseline_summary, baseline_cases=evaluate(base,targets,manifest)
    rotation_summary, cases=evaluate(limited,targets,manifest)
    lookup={r['id']:r for r in merged_results}
    for item in manifest['images']:
        image_cases=[r for r in cases if r['image_id']==item['id']]
        obs=lookup[item['id']+'-full']['observations']
        mapping=assign([r['full_bbox'] for r in image_cases],obs)
        for index,row in enumerate(image_cases):
            crop_obs=lookup[row['id']+'-crop']['observations']; cm=assign([row['crop_bbox']],crop_obs)
            for condition,observ in [('full',obs[mapping[index]] if index in mapping else None),('crop',crop_obs[cm[0]] if 0 in cm else None)]:
                candidates=observ['candidates'] if observ else []
                row[condition]['all_candidates']=candidates
                row[condition]['candidate_count']=len(candidates)
                row[condition]['all_candidates_exact']=any(normalize(c['text'])==normalize(row['expected']) for c in candidates)
    for condition in ['full','crop']:
        values=[r[condition] for r in cases]
        rotation_summary['conditions'][condition].update({
            'all_candidates_exact':sum(v['all_candidates_exact'] for v in values),
            'ambiguous_targets':sum(v['candidate_count']>1 for v in values),
            'mean_candidates_per_target':sum(v['candidate_count'] for v in values)/len(values),
            'max_candidates':max(v['candidate_count'] for v in values),
            'actual_ocr_calls':sum(r['id'].split('@')[0].endswith('-'+condition) for r in raw['results'])})
    return {'rotation0':baseline_summary,'rotation_pool':rotation_summary},cases,merged


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum(): raise ValueError('잘못된 run_id')
    out=ROOT/'runs'/args.run_id;out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((BASE/'manifest.json').read_text())
    jobs,targets=prepare(out,manifest)
    write_json(out/'targets.json',targets)
    (out/'rotations').mkdir()
    rotated=[]
    for job in jobs:
        for angle in [0,90,180,270]:
            path=Path(job['path'])
            if angle:
                path=out/'rotations'/f"{job['id']}-{angle}.png"
                with Image.open(job['path']) as im:
                    im.transpose({90:Image.Transpose.ROTATE_90,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_270}[angle]).save(path)
            rotated.append({'id':job['id']+'@'+str(angle),'path':str(path)})
    write_json(out/'jobs.json',rotated)
    binary=BASE/'.build/vision'
    write_json(out/'environment.json',{'started_at':datetime.now().astimezone().isoformat(),'manifest_sha256':sha(BASE/'manifest.json'),
        'source_sha256':{str(p.relative_to(ROOT.parent)):sha(p) for p in [ROOT/'rotation.py',ROOT/'run_rotation.py',ROOT/'PROTOCOL.md',BASE/'vision.swift',BASE/'run.py',BASE/'score.py']},'binary_sha256':sha(binary)})
    proc=subprocess.run([str(binary),str(out/'jobs.json'),str(out/'raw.json')],capture_output=True,text=True,timeout=240)
    (out/'engine.log').write_text(proc.stdout+proc.stderr);proc.check_returncode()
    raw=json.loads((out/'raw.json').read_text())
    summary,cases,merged=summarize(raw,targets,manifest)
    write_json(out/'summary.json',summary);write_json(out/'cases.json',cases);write_json(out/'merged.json',merged)
    print(json.dumps({k:{c:{m:v for m,v in s.items() if m!='per_image'} for c,s in value['conditions'].items()} for k,value in summary.items()},indent=2))


if __name__=='__main__': main()
