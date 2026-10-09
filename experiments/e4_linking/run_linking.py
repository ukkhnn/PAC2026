"""실제 전체 이미지 관측을 가상 작업지시에 연결한다. 정답은 사후 분석에만 사용한다."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from adapter import WorkOrder,link_observation

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'e1_ocr'))
from score import assign,normalize


def build() -> tuple[list,dict,list]:
    manifest=json.loads((ROOT.parent/'e1_ocr/manifest.json').read_text())
    raw=json.loads((ROOT.parent/'e1_alternative/results/raw.json').read_text())
    cases=json.loads((ROOT.parent/'e1_alternative/results/cases.json').read_text())
    orders=[]
    for image in manifest['images']:
        ids=sorted({normalize(a['transcription']) for a in image['annotations'] if a['transcription']!='###'})
        for i,part in enumerate(ids):orders.append({'project_id':'EXP','block_id':image['id'],'order_id':f"{image['id']}-O{i:02d}",'part_id':part,'revision':1,'valid_from':'2026-10-08T00:00:00+09:00','valid_until':None,'state':'released','instruction':'가상 연결 시험. 실제 용접 작업지시 아님.'})
    parsed=[WorkOrder.from_dict(x) for x in orders]
    cancelled=parsed+[WorkOrder.from_dict({**o,'revision':2,'valid_from':'2026-10-09T00:00:00+09:00','state':'cancelled'}) for o in orders]
    result=[]
    for image in manifest['images']:
        observations=next(r for r in raw['results'] if r['id']==image['id']+'-full')['observations']
        labels=[c for c in cases if c['image_id']==image['id']]
        mapping=assign([c['full_bbox'] for c in labels],observations);inverse={p:g for g,p in mapping.items()}
        for index,obs in enumerate(observations):
            enriched={**obs,'source_image_id':image['id'],'source_image_sha256':image['sha256'],'engine':'RapidOCR 3.10.0','observation_index':index}
            for variant in ['normal','wrong_block','cancelled']:
                context={'project_id':'EXP','block_id':'ABSENT' if variant=='wrong_block' else image['id'],'as_of':'2026-10-09T01:00:00+09:00'}
                linked=link_observation(enriched,cancelled if variant=='cancelled' else parsed,context)
                target=labels[inverse[index]] if index in inverse else None
                # 기대 정답은 연결 호출이 끝난 뒤 평가 기록에만 붙인다.
                linked.update({'variant':variant,'scoring_target_id':target['id'] if target else None,
                    'label_expected':target['expected'] if target else None,
                    'correct_part_link':bool(target and linked['status']=='matched' and all(m['part_id']==normalize(target['expected']) for m in linked['matcher_result']['matches']))})
                result.append(linked)
    summary={v:{'observations':len([r for r in result if r['variant']==v]),
        'statuses':dict(Counter(r['status'] for r in result if r['variant']==v)),
        'linked_observations':sum(bool(r['matcher_result']['matches']) for r in result if r['variant']==v),
        'correct_part_links_on_scored_regions':sum(r['correct_part_link'] for r in result if r['variant']==v),
        'wrong_part_links_on_scored_regions':sum(r['scoring_target_id'] is not None and r['status']=='matched' and not r['correct_part_link'] for r in result if r['variant']==v),
        'execution_authorized':sum(r['execution_authorized'] for r in result if r['variant']==v)} for v in ['normal','wrong_block','cancelled']}
    return result,summary,orders


if __name__=='__main__':
    out=ROOT/'results';out.mkdir(exist_ok=False)
    cases,summary,orders=build()
    for name,data in [('cases.json',cases),('summary.json',summary),('synthetic-orders.json',{'kind':'synthetic_from_dataset_labels','orders':orders})]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
