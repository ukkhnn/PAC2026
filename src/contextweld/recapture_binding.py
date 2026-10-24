"""검증된 재촬영의 마지막 관측을 작업 대상에 정확 연결한다. 원본은 쓰지 않는다."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from contextweld.recapture_loop import verify_recapture_bundle
from contextweld.recognition import sha256


def recapture_binding(root: Path, orders: dict, drawing: dict) -> dict:
    manifest = verify_recapture_bundle(root)
    if (manifest['inference_status'] != 'succeeded'
            or manifest['visual_outcome'] != 'ready_for_document_review'):
        raise ValueError('재촬영 관측이 문서 검토 준비 상태가 아님')
    results = {ref: json.loads((root / ref).read_text()) for ref in manifest['result_refs']}
    frame = manifest['frames'][-1]
    fid = frame['frame_id']

    def one(stage):
        found = [(ref, value) for ref, value in results.items()
                 if value['stage'] == stage and value['input_frame_ids'] == [fid]]
        if len(found) != 1:
            raise ValueError('마지막 프레임의 관측·관계·판정이 유일하지 않음')
        return found[0]

    obs_ref, observation = one('observation')
    rel_ref, relation = one('relation')
    assessment_ref, assessment = one('capture_assessment')
    decision_ref, decision = one('recognition_decision')
    if (decision['action'] != 'continue'
            or set(decision['input_result_ids']) != {observation['result_id'], relation['result_id'], assessment['result_id']}
            or relation['input_result_ids'] != [observation['result_id']]):
        raise ValueError('마지막 판정과 관측 계보 불일치')
    items = observation['text_observations'] + observation['visual_objects']
    by_id = {item['observation_id']: item for item in items}
    texts = {key: (item.get('raw_text') or item.get('visible_text') or '').strip().upper()
             for key, item in by_id.items()}
    matches = [order for order in orders['orders'] if order['part_id'].upper() in texts.values()]
    if len(matches) != 1:
        raise ValueError('재촬영 부재와 작업지시가 유일하게 연결되지 않음')
    order = matches[0]
    labels = drawing.get('joint_marking_map', {})
    joint_labels = {text for text in texts.values() if labels.get(text) == order['joint_id']}
    if len(joint_labels) != 1:
        raise ValueError('재촬영 이음 표기와 도면 연결 미확정')
    joint_text = next(iter(joint_labels))
    target_check = next(c for c in assessment['field_checks'] if c['field'] == 'marking_target')
    candidates = []
    for item in relation['relations']:
        target_id = item.get('selected_target_observation_id')
        target = by_id.get(target_id, {})
        source_ids = item['source_observation_ids']
        if not set(source_ids) <= by_id.keys():
            raise ValueError('관계가 없는 관측을 인용함')
        linked_texts = {texts[key] for key in source_ids}
        if target_id in texts:
            linked_texts.add(texts[target_id])
        if (item['relation_id'] in target_check['relation_ids']
                and target_id in item['target_observation_candidates']
                and target.get('kind') == 'joint' and target.get('description')
                and order['part_id'].upper() in {texts[key] for key in source_ids}
                and joint_text in linked_texts):
            candidates.append(item)
    if len(candidates) != 1 or relation.get('unresolved'):
        raise ValueError('재촬영 표기와 실제 이음 대상 관계 미확정')
    selected = candidates[0]
    prefix = 'inputs/recapture-bundle/'
    return {
        'part_id': order['part_id'], 'joint_id': order['joint_id'],
        'part_text': order['part_id'], 'joint_text': joint_text, 'order_id': order['order_id'],
        'source_ref': prefix + obs_ref, 'source_hash': sha256(root / obs_ref),
        'source_kind': manifest.get('evidence_kind', 'actual_model'),
        'frame_id': fid, 'image_sha256': frame['sha256'], 'observations': deepcopy(items),
        'visual_relation': {'part_text': order['part_id'], 'joint_text': joint_text,
                            'target_description': by_id[selected['selected_target_observation_id']]['description'],
                            'relation_id': selected['relation_id'],
                            'source_observation_ids': selected['source_observation_ids'],
                            'selected_target_observation_id': selected['selected_target_observation_id']},
        'joint_mapping_source': 'drawing.joint_marking_map',
        'recapture_run_id': manifest['run_id'],
        'relation_ref': prefix + rel_ref, 'assessment_ref': prefix + assessment_ref,
        'decision_ref': prefix + decision_ref,
    }
