"""실제 관측·제외 이유를 보존하며 기존 작업지시 matcher에 연결한다."""

from pathlib import Path
import sys
from typing import Any

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from contextweld.matching import WorkOrder,identifier,match_orders


def link_observation(observation: dict[str,Any], orders: list[WorkOrder], context: dict[str,str]) -> dict[str,Any]:
    texts=[c['text'] for c in observation['candidates']]
    accepted=[];rejected=[]
    for text in texts:
        try:identifier(text)
        except ValueError as exc:rejected.append({'text':text,'reason':str(exc)})
        else:accepted.append(text)
    result=match_orders(accepted,orders,**context)
    status=result['status']
    if rejected and accepted and status=='matched':status='review_required'
    return {'observation':observation,'observed_texts':texts,'accepted_candidates':accepted,
        'rejected_candidates':rejected,'matcher_result':result,'status':status,
        'review_reason':'unsupported_alternative_preserved' if status!=result['status'] else None,
        'execution_authorized':False}
