"""새 모델 호출 없이 동일 실제 응답에 검사를 적용한다."""

from collections import Counter
import json
from pathlib import Path
from check_output import check_output

ROOT=Path(__file__).resolve().parent


def build() -> tuple[list,dict]:
    results=[]
    for name,directory in [('E2-001','results'),('E2-002','results-002')]:
        path=ROOT.parent/'e2_documents'/directory
        outputs=[json.loads(l) for l in (path/'outputs.jsonl').read_text().splitlines()]
        reviews={(r['condition'],r['question_id']):r for r in json.loads((path/'review.json').read_text())}
        for row in outputs:
            review=reviews[(row['condition'],row['question_id'])]
            result=check_output(row['output'],row['provided_ids'])
            results.append({'experiment':name,'condition':row['condition'],'question_id':row['question_id'],'provided_ids':row['provided_ids'],
                'check':result,'answerable':review['answerable'],'factual_correct':review['factual_correct'],'correct_abstention':review['correct_abstention']})
    summary={}
    for name in ['E2-001','E2-002']:
        summary[name]={}
        for cond in ['none','full','bm25']:
            rows=[r for r in results if r['experiment']==name and r['condition']==cond]
            summary[name][cond]={'responses':len(rows),'statuses':dict(Counter(r['check']['status'] for r in rows)),
                'correct_factual_candidates':sum(r['check']['status']=='candidate' and r['factual_correct'] is True for r in rows),
                'incorrect_or_partial_factual_candidates':sum(r['check']['status']=='candidate' and r['answerable'] and r['factual_correct'] is False for r in rows),
                'correct_factual_answers_sent_to_review':sum(r['check']['status']=='review_required' and r['factual_correct'] is True for r in rows)}
    return results,summary


if __name__=='__main__':
    out=ROOT/'results';out.mkdir(exist_ok=False)
    cases,summary=build()
    for name,data in [('cases.json',cases),('summary.json',summary)]: (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
