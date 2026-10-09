"""다운로드·추론 없이 모든 보존 결과, 원문 연결과 핵심 테스트를 검증한다."""

from datetime import datetime
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def read(path: str):
    return json.loads((ROOT/path).read_text())


def module(folder: str, name: str):
    sys.path.insert(0,str(ROOT/folder))
    return importlib.import_module(name)


def equal(actual,expected,label: str) -> None:
    if actual!=expected:raise ValueError(f'재현 불일치: {label}')


def main() -> None:
    checks=[];test_count=0
    for folder in ['e1_ocr','e1_rotation','e2_documents','e4_linking','e5_output_checks']:
        proc=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/folder),'-p','test_*.py','-v'],capture_output=True,text=True,check=True)
        count=int(re.search(r'Ran (\d+) tests?',proc.stdout+proc.stderr)[1]);test_count+=count
        checks.append(f'{folder}: {count} tests passed')
    env={**os.environ,'PYTHONPATH':str(ROOT.parent/'src')}
    proc=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT.parent/'tests'),'-v'],capture_output=True,text=True,env=env,check=True)
    count=int(re.search(r'Ran (\d+) tests?',proc.stdout+proc.stderr)[1]);test_count+=count;checks.append(f'product: {count} tests passed')
    subprocess.run([sys.executable,str(ROOT/'e1_ocr/verify.py')],check=True)
    base=module('e1_ocr','run');manifest=read('e1_ocr/manifest.json')
    rotation=module('e1_rotation','run_rotation')
    summary,cases,merged=rotation.summarize(read('e1_rotation/results/raw.json'),read('e1_rotation/results/targets.json'),manifest)
    for name,value in [('summary',summary),('cases',cases),('merged',merged)]:equal(value,read(f'e1_rotation/results/{name}.json'),'rotation '+name)
    checks.append('E1-002 raw outputs re-merged and re-scored')
    summary,cases=base.evaluate(read('e1_alternative/results/raw.json'),read('e1_alternative/results/targets.json'),manifest)
    equal(summary,read('e1_alternative/results/summary.json'),'alternative summary');equal(cases,read('e1_alternative/results/cases.json'),'alternative cases')
    checks.append('E1-003 raw outputs re-scored')
    score=module('e1_ocr','score');raw=read('e1_recognition/results/raw.json');cases=read('e1_recognition/results/cases.json')
    for row in cases:
        calls=[r for r in raw if r['id']==row['id']]
        equal(sorted(r['angle'] for r in calls),[0,90,180,270],row['id']+' angles')
        pool=sorted([c for r in calls for c in r['candidates']],key=lambda c:(-c['confidence'],c['angle']))
        unique=[];seen=set()
        for c in pool:
            key=score.normalize(c['text'])
            if key not in seen:unique.append(c);seen.add(key)
        equal(unique,row['candidates'],row['id']+' candidates')
        equal(score.score_text(row['expected'],{'candidates':unique[:3]}),row['selected'],row['id']+' selected')
        equal(score.score_text(row['expected'],{'candidates':[c for r in calls if r['angle']==0 for c in r['candidates']]}),row['zero'],row['id']+' zero')
    summary={}
    for mode in ['zero','selected']:
        values=[r[mode] for r in cases];edits=sum(s['edits'] for s in values);chars=sum(s['characters'] for s in values)
        summary[mode]={'exact':sum(s['normalized_exact'] for s in values),'labels':len(cases),'edits':edits,'characters':chars,'cer':edits/chars,'top3_exact':sum(s['top3_exact'] for s in values)}
    summary.update({'all_candidates_exact':sum(r['all_candidates_exact'] for r in cases),'ambiguous_targets':sum(len(r['candidates'])>1 for r in cases),
                    'mean_candidates':sum(len(r['candidates']) for r in cases)/len(cases),'calls':len(raw),'seconds':sum(r['seconds'] for r in raw)})
    equal(summary,read('e1_recognition/results/summary.json'),'recognition summary');checks.append('E1-004 ranking and character scores replayed')
    grading=module('e2_documents','grade_documents');retrieve=module('e2_documents','retrieve')
    corpus=read('e2_documents/corpus.json')
    for directory in ['results','results-002']:
        path=ROOT/'e2_documents'/directory
        equal(grading.summarize(path),read(f'e2_documents/{directory}/summary.json'),'document summary '+directory)
        rows=[json.loads(l) for l in (path/'outputs.jsonl').read_text().splitlines()]
        for row in rows:
            if row['condition']=='bm25':
                replayed=retrieve.retrieve(row['question'],corpus)
                equal([r['id'] for r in replayed],[r['id'] for r in row['retrieved']],'retrieval IDs '+row['question_id'])
                # 집합 순회에 따른 부동소수점 덧셈의 마지막 자리 차이만 허용한다.
                if any(not math.isclose(a['score'],b['score'],rel_tol=1e-12,abs_tol=1e-12) for a,b in zip(replayed,row['retrieved'])):
                    raise ValueError('BM25 점수 재현 불일치')
        checks.append(f'E2 {directory}: 27 output-bound reviews and retrieval replayed')
    linking=module('e4_linking','run_linking');cases,summary,orders=linking.build()
    equal(cases,read('e4_linking/results/cases.json'),'linking cases');equal(summary,read('e4_linking/results/summary.json'),'linking summary')
    equal(orders,read('e4_linking/results/synthetic-orders.json')['orders'],'synthetic orders');checks.append('E4-001 all 126 links replayed')
    output=module('e5_output_checks','run_checks');cases,summary=output.build()
    equal(cases,read('e5_output_checks/results/cases.json'),'output cases');equal(summary,read('e5_output_checks/results/summary.json'),'output summary')
    checks.append('E5-001 all 54 structural checks replayed')
    checksum_path=ROOT/'checksums.json'
    checksums=json.loads(checksum_path.read_text())
    for filename,expected in checksums.items():
        actual=hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()
        equal(actual,expected,'hash '+filename)
    checks.append(f'{len(checksums)} artifact hashes verified')
    result={'checked_at':datetime.now().astimezone().isoformat(),'tests_passed':test_count,'checks':checks}
    (ROOT/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
