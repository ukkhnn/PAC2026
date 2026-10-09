"""원문에 연결된 질적 검토와 형식 검사를 재집계한다. 의미 판정을 자동으로 만들어내지 않는다."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def summarize(directory: Path) -> dict:
    rows=[json.loads(l) for l in (directory/'outputs.jsonl').read_text().splitlines()]
    reviews=json.loads((directory/'review.json').read_text())
    rubric={r['id']:r for r in json.loads((ROOT/'rubric.json').read_text())}
    expected={(c,q) for c in ['none','full','bm25'] for q in rubric}
    if len(rows)!=len(expected) or {(r['condition'],r['question_id']) for r in rows}!=expected:raise ValueError('출력 중복·누락')
    if len(reviews)!=len(expected) or {(r['condition'],r['question_id']) for r in reviews}!=expected:raise ValueError('검토 중복·누락')
    lookup={(r['condition'],r['question_id']):r for r in rows}
    for review in reviews:
        row=lookup[(review['condition'],review['question_id'])]
        if hashlib.sha256(row['output'].encode()).hexdigest()!=review['output_sha256']:raise ValueError('검토한 출력과 다름')
        try:obj=json.loads(row['output']);valid=True
        except json.JSONDecodeError:obj=None;valid=False
        schema=isinstance(obj,dict) and isinstance(obj.get('answer'),str) and isinstance(obj.get('sources'),list) and all(isinstance(i,str) for i in obj.get('sources',[]))
        if review['raw_json_valid']!=valid or review['schema_valid']!=schema:raise ValueError('형식 판정 불일치')
        if review['answerable']!=rubric[row['question_id']]['answerable']:raise ValueError('답변 가능 기준 불일치')
    summary={}
    for condition in ['none','full','bm25']:
        rs=[r for r in reviews if r['condition']==condition];outs=[r for r in rows if r['condition']==condition]
        summary[condition]={'factual_correct':sum(r['factual_correct'] is True for r in rs),'answerable':sum(r['answerable'] for r in rs),
            'correct_abstention':sum(r['correct_abstention'] is True for r in rs),'unanswerable':sum(not r['answerable'] for r in rs),
            'grounded_correct':sum(r['grounded_correct'] for r in rs),'schema_valid':sum(r['schema_valid'] for r in rs),'raw_json_valid':sum(r['raw_json_valid'] for r in rs),
            'input_tokens_total':sum(r['input_tokens'] for r in outs),'output_tokens_total':sum(r['output_tokens'] for r in outs),
            'seconds_total':sum(r['seconds'] for r in outs),'truncated':sum(r['reached_limit'] for r in outs)}
    summary['retrieval']={'recall_all_required_sources':sum(set(rubric[r['question_id']]['evidence'])<=set(r['provided_ids']) for r in rows if r['condition']=='bm25' and rubric[r['question_id']]['answerable']),
        'answerable':sum(r['answerable'] for r in rubric.values()),'k':2}
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('results',choices=['results','results-002']);args=parser.parse_args()
    directory=ROOT/args.results;summary=summarize(directory);dest=directory/'summary.json'
    if dest.exists():
        if json.loads(dest.read_text())!=summary:raise ValueError('저장 집계와 재계산이 다릅니다.')
    else:dest.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
