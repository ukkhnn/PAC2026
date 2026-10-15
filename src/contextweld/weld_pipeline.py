"""실제 마킹 → 문서 선택 → 공통 명세 → 제조사 변환 → HTTP 모의 수신 연결."""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib, json, re, shutil
from pathlib import Path
from typing import Any
from contextweld.recognition import sha256, utc_now, write_json
from contextweld.robot_input import build_work_order_input_previews
from contextweld.workflow import build_spec, command_from_spec, inspect_document_bundle, read_json
from contextweld.documents import load_index, search_documents
from contextweld.mock_delivery import MockReceiver, send_command


def validate_robot_extension(command: dict[str, Any]) -> list[dict[str, str]]:
    """수신 측에서도 대상·공통값·제조사 변환값·명령의 연결을 검사한다."""
    errors=[]
    def err(path,code):errors.append({'path':path,'code':code})
    try:
        preview=command['robot_input']; common=command['common_spec']; binding=command['marking_binding']
        for name in ('part_id','joint_id'):
            if common['target'][name]!=command['target'][name] or binding[name]!=command['target'][name]:err('target.'+name,'marking_target_mismatch')
        if not binding.get('source_ref') or not binding.get('part_text'):err('marking_binding','recognition_evidence_required')
        if common['validation']['status']!='valid' or preview['status']!='preview_ready':err('robot_input','validation_not_ready')
        if preview['execution_authorized'] is not False or common['execution_authorized'] is not False:err('robot_input','must_be_false')
        targets={}
        fields={f['name']:f for f in preview['fields']}
        if not {'current','voltage','travel_speed'} <= fields.keys():err('robot_input.fields','required_parameter_missing')
        doosan=preview['manufacturer']=='Doosan Robotics'
        if preview['manufacturer'] not in ('Doosan Robotics','HD Hyundai Robotics'):err('robot_input.manufacturer','unsupported_manufacturer')
        if doosan and 'wire_feed' not in fields:err('robot_input.fields','wire_feed_required')
        for name,f in fields.items():
            source=f['selected']['source']; target=f['selected']['target']; param=common['parameters'][name]
            n=Decimal(str(source['value']))
            if not n.is_finite() or n<=0:raise ValueError('invalid number')
            if str(param['value'])!=str(source['value']) or param['unit']!=source['unit']:err('common_spec.parameters.'+name,'selected_value_mismatch')
            if not Decimal(str(f['source']['min']))<=n<=Decimal(str(f['source']['max'])):err('robot_input.'+name,'outside_source_range')
            expected=n*Decimal(str(f['factor']))
            if f.get('divisor'):expected=(expected/Decimal(str(f['divisor']))).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP)
            if Decimal(str(target['value']))!=expected or source['unit']!=f['source']['unit'] or target['unit']!=f['target']['unit']:err('robot_input.'+name,'conversion_mismatch')
            if not f.get('ref_only'):targets[f['robot_field']]=str(target['value'])
        if doosan:
            v=targets['vel_target'];expected=f"app_weld_set_weld_cond_analog(flag_dry_run=1, v_target={targets['v_target']}, f_target={targets['f_target']}, vel_target={v}, vel_min={v}, vel_max={v})"
        else:expected=f"arccond D, cur={targets['cur']}, vol={targets['vol']}, spd={targets['spd']}"
        if preview['command_preview']!=expected:err('robot_input.command_preview','command_field_mismatch')
    except (KeyError,TypeError,ValueError,ArithmeticError):err('robot_input','invalid_robot_extension')
    return errors


def capture_binding(capture: dict, orders: dict, drawing: dict) -> dict:
    """실제 판독 문자열을 정확 조회한다. 문서의 정답으로 판독을 고치지 않는다.

    판독 결정은 VLM `read['markings']` 단독이며 OCR 원문은 capture.json에 보존하되 판단에
    사용하지 않는다(계보·결정: docs/runs/RECOGNITION_AND_BINDING.md). `requires_recapture=true`
    예외 유지는 2026-10-15 진단·처방의 결정이다: 재관측 뒤에도 미확정인 상태를 조용히 진행하지
    않는다. 병합한 recapture_loop 모듈은 아직 여기에 연결하지 않는다."""
    if capture.get('source_kind')!='model' or not capture.get('frames'):raise ValueError('실제 인식 기록 필요')
    f=capture['frames'][-1];read=f['readout']
    if read['quality']['requires_recapture']:raise ValueError('재관측 뒤에도 판독 미확정')
    parts={m['text'].strip().upper() for m in read['markings'] if m['role']=='part'}
    matches=[o for o in orders['orders'] if o['part_id'].upper() in parts]
    if len(matches)!=1:raise ValueError('마킹과 작업지시가 유일하게 연결되지 않음')
    order=matches[0]
    joints={m['text'].strip().upper() for m in read['markings'] if m['role']=='joint'}
    labels=drawing.get('joint_marking_map',{})
    linked=[label for label in joints if labels.get(label)==order['joint_id']]
    if len(linked)!=1:raise ValueError('실제 이음 표기와 도면의 이음 연결 미확정')
    relations=[r for r in read['relations'] if r['part_text'].strip().upper()==order['part_id'].upper() and (r.get('joint_text') or '').strip().upper()==linked[0] and r.get('target_description')]
    if len(relations)!=1:raise ValueError('마킹의 실제 지시 대상 미확정')
    return {'part_id':order['part_id'],'joint_id':order['joint_id'],'part_text':order['part_id'],'joint_text':linked[0],
            'source_ref':'inputs/capture/capture.json','source_hash':None,'source_kind':'model','frame_id':f['frame_id'],
            'image_sha256':f['image_sha256'],'observations':deepcopy(read['markings']),
            'visual_relation':deepcopy(relations[0]),'joint_mapping_source':'drawing.joint_marking_map','order_id':order['order_id']}


def run_pipeline(*,repo:Path,output:Path,source:Path,source_kind:str,data_root:Path,index_path:Path) -> Path:
    if output.exists():raise FileExistsError('새 실행 경로 필요')
    output.mkdir(parents=True)
    for d in ('inputs','results','evidence','commands'):(output/d).mkdir()
    run_id=output.name; events=[]
    def event(stage,ref):
        seq=len(events)+1;events.append({'seq':seq,'event_id':f'event-{seq:03d}','stage':stage,'recorded_at_utc':utc_now(),'payload_ref':ref,'parent_event_ids':[f'event-{seq-1:03d}'] if seq>1 else []})
    manifest={'schema_version':'weld-pipeline-bundle.v1','run_id':run_id,'started_at_utc':utc_now(),'capture_mode':'pre_captured' if source_kind=='capture' else 'public_dataset','execution_authorized':False,'application_authorized':False,'physical_movement_triggered':False,'delivery_status':'blocked','run_outcome':'running','source_kind':'actual_model','input_reused':True}
    orders=read_json(repo/'configs/document_demo/work_orders.json');drawing=read_json(repo/('configs/shipyard_pipeline/drawing.json' if source_kind=='capture' else 'configs/document_demo/drawing.json'))
    profile=read_json(repo/'configs/document_demo/target_profile.json');wps=read_json(repo/'data/knowledge/lanl-wps-3501-reviewed.json')
    scenario=read_json(repo/'configs/document_demo/scenario.json')
    deliveries={}
    delivery_failures={}
    try:
        if source_kind=='capture':
            shutil.copytree(source,output/'inputs/capture');capture=read_json(source/'capture.json');binding=capture_binding(capture,orders,drawing)
            binding['source_hash']=sha256(output/'inputs/capture/capture.json')
            observed={'candidates':[binding['part_id']],'observations':binding['observations'],'issues':[]}
            order_path=output/'inputs/work_orders.json';draw_path=output/'inputs/drawing.json'
            write_json(order_path,orders);write_json(draw_path,drawing)
            spec,matching=build_spec(run_id=run_id,observed=observed,scenario=scenario,orders=orders,drawing=drawing,wps=wps,profile=profile,order_path=order_path,drawing_path=draw_path,faults=[])
            manifest['new_model_calls']=capture['model_calls'];manifest['source_run_id']=capture['run_id']
        else:
            inspect_document_bundle(source);shutil.copytree(source,output/'inputs/document-run')
            spec=read_json(source/'results/work-spec.json');spec['run_id']=run_id;spec['spec_id']=run_id+'-spec'
            binding={'part_id':spec['target']['part_id'],'joint_id':spec['target']['joint_id'],'part_text':spec['target']['part_id'],'joint_text':None,
                     'source_ref':'inputs/document-run/results/observation-selection.json','source_hash':sha256(source/'results/observation-selection.json'),
                     'source_kind':'model','observations':spec['target_evidence']['part_id']['observations'],'joint_mapping_source':'document_reference'}
            manifest['new_model_calls']=0;manifest['source_run_id']=read_json(source/'manifest.json')['run_id']
        write_json(output/'results/marking-binding.json',binding);event('marking_binding','results/marking-binding.json')
        if spec['validation']['issues']:raise ValueError('문서 검증 실패: '+json.dumps(spec['validation']['issues'],ensure_ascii=False))
        write_json(output/'results/document-spec.json',spec);event('document_validation','results/document-spec.json')
        if sha256(data_root/wps['source']['relative_path'])!=wps['source_hash']:raise ValueError('WPS 원문 해시 불일치')
        index=load_index(index_path,data_root)
        retrieval=search_documents(index,scenario['retrieval_query'],document_ids=[wps['document_id']],top_k=3,data_root=data_root)
        if not retrieval['hits']:raise ValueError('WPS 근거 검색 결과 없음')
        write_json(output/'evidence/retrieval.json',retrieval);event('document_retrieval','evidence/retrieval.json')
        recipes=read_json(repo/'configs/document_demo/weld_recipes.json')
        converted=build_work_order_input_previews(wps,orders,recipes,{key:read_json(repo/f'configs/robot_profiles/{name}') for key,name in [('hyundai','hyundai_hi6_current_voltage.json'),('doosan','doosan_drl_analog.json')]},order_id=spec['target']['work_order_id'])
        if converted['status']!='preview_ready':raise ValueError('제조사 변환 검증 실패')
        common=converted['common_spec'];common['target'].update(part_id=binding['part_id'],joint_id=binding['joint_id'],observation_ref=binding['source_ref'],source_kind='model')
        common['relation_origin']='visual_marking_and_document_mapping' if source_kind=='capture' else 'recognition_and_document_mapping'
        common['target_evidence']=binding
        converted['marking_binding']=binding
        write_json(output/'results/robot-input.json',converted);event('manufacturer_conversion','results/robot-input.json')
        for key,preview in converted['previews'].items():
            command=command_from_spec(spec,profile);command['command_id']=run_id+'-'+key
            command.update(marking_binding=binding,common_spec=common,robot_input=preview,
                           work_requirements={'process':common['process'],'material':common['material'],'position':common['position'],
                            'target_description':binding.get('visual_relation',{}).get('target_description'),'source_kind':'document_and_model'})
            # 기존 문서 검증 계약에 제조사 입력을 추가하고 양쪽을 수신기에서 검사한다.
            write_json(output/f'commands/{key}-request.json',command);event('command_built',f'commands/{key}-request.json')
            try:
                with MockReceiver(profile,output/f'commands/{key}-receiver.jsonl') as receiver:delivery=send_command(receiver.url,command)
            except Exception:
                delivery_failures[key]='delivery_error'
                raise
            write_json(output/f'commands/{key}-delivery.json',delivery);event('delivery_ack',f'commands/{key}-delivery.json')
            if delivery['ack']['status']!='received':
                delivery_failures[key]=delivery['ack']['status']
                raise ValueError('수신기 검증 거절')
            deliveries[key]=delivery
        write_json(output/'results/deliveries.json',deliveries)
        manifest.update(run_outcome='succeeded',delivery_status='received',manufacturers=list(deliveries))
    except Exception as exc:
        write_json(output/'results/error.json',{'type':type(exc).__name__,'message':str(exc)})
        event('blocked','results/error.json')
        # 한쪽이라도 수신된 부분 전달은 blocked가 아니라 실제 상태(partial)로 기록한다.
        if deliveries:
            write_json(output/'results/deliveries.json',deliveries)
            manifest.update(run_outcome='needs_review',delivery_status='partial',
                            manufacturers=list(deliveries),delivery_failures=delivery_failures)
        else:
            manifest.update(run_outcome='needs_review',delivery_status='blocked')
    manifest['finished_at_utc']=utc_now();manifest['export_status']='complete'
    write_json(output/'manifest.json',manifest)
    (output/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events))
    write_json(output/'checksums.json',{str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and p!=output/'checksums.json'})
    return output


def verify_pipeline(root: Path) -> dict[str, Any]:
    """전송 패킷·수신 원문·ACK·인식 출처와 파일 해시를 교차 확인한다."""
    sums=read_json(root/'checksums.json')
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=root/'checksums.json'}
    extra=sorted(actual-set(sums))
    if extra:raise ValueError('통합 묶음 미등재 파일: '+', '.join(extra))
    for name,digest in sums.items():
        if sha256(root/name)!=digest:raise ValueError('통합 묶음 해시 불일치: '+name)
    manifest=read_json(root/'manifest.json')
    if manifest['run_outcome']!='succeeded':raise ValueError('통합 실행 미완료')
    binding=read_json(root/'results/marking-binding.json')
    if sha256(root/binding['source_ref'])!=binding['source_hash']:raise ValueError('인식 출처 불일치')
    receipts={}
    for key in manifest['manufacturers']:
        request=read_json(root/f'commands/{key}-request.json')
        delivery=read_json(root/f'commands/{key}-delivery.json')
        records=[json.loads(line) for line in (root/f'commands/{key}-receiver.jsonl').read_text().splitlines()]
        if len(records)!=1 or records[0]['command']!=request or delivery['request']!=request:raise ValueError('송신/수신 패킷 불일치')
        ack=delivery['ack'];record=records[0]
        digest=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if record['ack']!=ack or ack['command_sha256']!=digest or ack['command_id']!=request['command_id'] or ack['status']!='received' or delivery['http_status']!=200:raise ValueError('ACK 연결 불일치')
        if validate_robot_extension(request):raise ValueError('제조사 명령/대상 연결 오류')
        receipts[key]={'part_id':request['target']['part_id'],'joint_id':request['target']['joint_id'],'http_status':200,'status':ack['status'],'command_id':ack['command_id'],'command':request['robot_input']['command_preview']}
    return {'verified':True,'run_id':manifest['run_id'],'files_checked':len(sums),'receipts':receipts}
