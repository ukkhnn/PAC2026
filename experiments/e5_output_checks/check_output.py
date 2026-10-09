"""출력의 구조와 출처 실재성을 확인한다. 의미의 옳음은 보증하지 않는다."""

import json


def check_output(text: str, provided_ids: list[str]) -> dict:
    result={'status':'review_required','reason':None,'raw_output':text,'execution_authorized':False,'semantic_verified':False}
    try:obj=json.loads(text)
    except json.JSONDecodeError:return {**result,'reason':'invalid_json'}
    if not isinstance(obj,dict) or not isinstance(obj.get('answer'),str) or not obj['answer'].strip() or not isinstance(obj.get('sources'),list) or not all(isinstance(s,str) for s in obj['sources']):
        return {**result,'reason':'invalid_schema'}
    if any(s not in provided_ids for s in obj['sources']):return {**result,'reason':'source_not_provided'}
    if obj['answer'].strip().upper()=='UNKNOWN':
        return {**result,'status':'review_required' if obj['sources'] else 'abstained','reason':'abstention_with_sources' if obj['sources'] else 'explicit_unknown'}
    if not obj['sources']:return {**result,'reason':'missing_evidence'}
    return {**result,'status':'candidate','reason':'structure_and_source_ids_valid','parsed':obj}
