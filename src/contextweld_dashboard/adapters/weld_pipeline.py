"""통합 실행을 원본 묶음 수정 없이 관리자 화면으로 읽는다."""
from ..model import block, notice, row, tab
from .common import absent, base_summary, build_steps, delivery_row, outcome_row, status

LABELS = {'recapture_reuse': '저장 재촬영 결과 재사용', 'marking_binding': '마킹 · 대상 연결',
          'document_validation': '문서 검증', 'document_retrieval': '원문 근거 검색',
          'manufacturer_conversion': '제조사 입력 변환', 'command_built': '모의 명령 생성',
          'delivery_ack': 'HTTP 모의 수신 확인'}


def build(source, reader, integrity, ctx):
    manifest = reader.json('manifest.json')
    events = reader.jsonl('events.jsonl')
    seqs = {e['payload_ref']: e['seq'] for e in events}
    final = max(e['seq'] for e in events)
    summary = base_summary(source, reader, kind_label='통합 전달 실행', title=manifest['run_id'], final_seq=final)
    summary['replay'] = {'enabled': True, 'reason': None}
    summary['flags'] = [row(k, reader.value('manifest.json', k)) for k in
                        ('source_kind','new_model_calls','physical_movement_triggered','execution_authorized')]
    binding_ref = 'results/marking-binding.json'
    target = block('fields', 'target', '판독에서 연결한 대상', seq=seqs[binding_ref], rows=[
        row(label, reader.value(binding_ref, key)) for label,key in
        [('부재','part_id'),('이음','joint_id'),('읽은 이음 표기','joint_text'),('작업지시','order_id'),
         ('선택 프레임','frame_id'),('관측 출처','source_kind')]])
    summary_blocks = [target, block('fields','outcome','실행 결과',rows=[
        outcome_row(reader,seq=final),delivery_row(reader,seq=final)])]
    if manifest.get('evidence_kind') == 'test_fixture':
        summary_blocks.insert(0, notice('fixture','warning','테스트용 관측으로 연결을 검증한 실행입니다. 실제 GPU 판독 결과가 아닙니다.'))
    if source.note:
        summary_blocks.insert(0, notice('source-note','info',source.note))
    capture_blocks = []
    recapture_blocks = []
    prefix = 'inputs/recapture-bundle/'
    if reader.exists(prefix+'manifest.json'):
        loop = reader.json(prefix+'manifest.json')
        for camera, field in [('손목','image_ref'),('전체 장면','overview_ref')]:
            items=[]
            for f in loop['frames']:
                image=ctx.image(reader,prefix+f[field],label=f['frame_id'])
                if image: items.append({'label':f['frame_id'],'image':image,'rows':[]})
            if items: capture_blocks.append(block('image_pair','pair-'+field,'A/B 원본 비교 · '+camera,items=items))
        for f in loop['frames']:
            ref=prefix+'results/'+f['frame_id']+'-recognition_decision.json'
            if reader.exists(ref):
                recapture_blocks.append(block('json','decision-'+f['frame_id'],f['frame_id']+' 저장 판정',value=reader.value(ref)))
        for i,ref in enumerate(loop['request_refs']):
            recapture_blocks.append(block('json','request-'+str(i),'저장 B 선택 요청',value=reader.value(prefix+ref)))
        recapture_blocks.insert(0,notice('reuse','info','원래 재촬영 묶음의 저장 결과입니다. 이 통합 실행은 새 모델 호출·팔 이동 없이 문서 검토와 모의 전달을 실행했습니다.'))
    elif reader.exists('inputs/capture/capture.json'):
        capture = reader.json('inputs/capture/capture.json')
        items = []
        for frame in capture['frames']:
            relative = 'frames/' + frame['frame_id'].removeprefix('frame-') + '-wrist.png'
            image = ctx.image(reader, relative, label=frame['frame_id'])
            if image and image['sha256'] == frame['image_sha256']:
                items.append({'label': frame['frame_id'], 'image': image, 'rows': []})
        if items:
            capture_blocks.append(block('image_pair','recorded-images','보존된 판독 입력',items=items))
        capture_blocks.append(block('json','capture','저장 판독 원문',value=reader.value('inputs/capture/capture.json')))
        if not items:
            capture_blocks.append(notice('images','info','이 원본 실행 묶음에는 촬영 이미지 사본이 없습니다. 장면 자료에서 원본 A/B를 확인하세요.'))
    else:
        capture_blocks.append(block('json','observed','원래 인식 관측',value=reader.value(reader.json(binding_ref)['source_ref'])))
    delivery_blocks = [target]
    for vendor in manifest['manufacturers']:
        ref=f'commands/{vendor}-delivery.json'
        delivery_blocks.append(block('fields','ack-'+vendor,vendor+' 모의 수신',seq=seqs[ref],rows=[
            row('HTTP',reader.value(ref,'http_status')), row('수신',reader.value(ref,'ack','status')),
            row('명령 ID',reader.value(ref,'ack','command_id')),
            row('부재',reader.value(ref,'request','target','part_id')),
            row('이음',reader.value(ref,'request','target','joint_id')),
            row('전송한 명령',reader.value(ref,'request','robot_input','command_preview'))]))
    delivery_blocks.append(block('robot_input','robot-'+source.key,'작업조건 · 제조사 변환',
        seq=seqs['results/robot-input.json'],preview=reader.json('results/robot-input.json')))
    delivery_blocks.append(block('raw_files','packets','송수신 원문',files=[{'root':reader.key,'path':f'commands/{v}-{suffix}'}
        for v in manifest['manufacturers'] for suffix in ('request.json','delivery.json','receiver.jsonl')]))
    evidence_blocks = [block('json','evidence-'+str(i),label,value=reader.value(ref),seq=seqs.get(ref))
        for i,(label,ref) in enumerate([('관측 연결',binding_ref),('문서 검증','results/document-spec.json'),
                                       ('원문 위치 검색','evidence/retrieval.json')])]
    return {'summary':summary,
        'steps':build_steps(reader,'events.jsonl',lambda e,i:status('success',basis=reader.value('events.jsonl',i,'stage')),labels=LABELS),
        'tabs':{'summary':tab('available',summary_blocks),'capture':tab('available',capture_blocks),
                'timeline':tab('available',[]),'recapture':tab('available',recapture_blocks) if recapture_blocks else absent('재촬영 루프 기록 없음'),
                'evidence':tab('available',evidence_blocks),'delivery':tab('available',delivery_blocks),
                'corrections':absent('별도 수정·재검토 기록 없음')}}
