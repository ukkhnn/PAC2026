#!/usr/bin/env python3
"""검증된 통합 전달 실행을 기존 관리자 패키지의 새 실행으로 추가한다."""
from pathlib import Path
from copy import deepcopy
import argparse,json,shutil,sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(REPO/'src'))
from add_robot_dashboard_preview import read_assignment,write_assignment,read_json,digest,write_json
from contextweld.weld_pipeline import verify_pipeline

def export(package:Path,bundle:Path,key:str):
    verify_pipeline(bundle)
    sums=read_json(bundle/'checksums.json')
    for name,sha in sums.items():
        if digest(bundle/name)!=sha:raise ValueError('실행 묶음 해시 불일치: '+name)
    manifest=read_json(bundle/'manifest.json')
    if manifest['run_outcome']!='succeeded':raise ValueError('정상 통합 실행이 아님')
    root=package/'bundles'/key
    if root.exists():raise FileExistsError('기존 실행을 덮어쓰지 않는다')
    shutil.copytree(bundle,root)
    conversion=read_json(root/'results/robot-input.json'); binding=read_json(root/'results/marking-binding.json');deliveries=read_json(root/'results/deliveries.json')
    source=read_assignment(package/'data/runs/shipyard-recapture.js');run=deepcopy(source)
    def val(value,file='manifest.json',ptr=''):return {'v':value,'src':f'{key}::{file}#{ptr}'}
    def row(label,value,file='manifest.json',ptr=''):return {'label':label,'value':val(value,file,ptr)}
    def fields(title,rows,seq=None):
        b={'type':'fields','title':title,'rows':rows}
        if seq:b['seq']=seq
        return b
    raw=[]
    for i,p in enumerate(sorted(x for x in root.rglob('*') if x.is_file())):
        name=p.relative_to(root).as_posix();rid=f'{key}/{i:04d}' if p.suffix in ('.json','.jsonl','.txt','.svg') else None
        raw.append({'path':name,'media_type':'application/json' if p.suffix=='.json' else 'text/plain','raw_id':rid,'recorded_sha256':sums.get(name),'sha256':digest(p),'size':p.stat().st_size,'state':'verified'})
        if rid:write_assignment(package/'data/raw'/f'{rid}.js',f'raw[{json.dumps(rid)}]',{'text':p.read_text(errors='replace')})
    events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
    labels={'marking_binding':'마킹 판독 · 대상 연결','document_validation':'작업지시 · WPS 검증','document_retrieval':'원문 위치 검색','manufacturer_conversion':'현대 · 두산 입력 변환','command_built':'대상 · 명령 묶음 생성','delivery_ack':'HTTP 전송 · 수신 확인'}
    steps=[]
    for e in events:
        s={'seq':e['seq'],'label':labels[e['stage']],'src':f"{key}::events.jsonl#",'frames':[],'payload':{'root':key,'path':e['payload_ref']},'status':{'class':'success','label':'수신 확인' if e['stage']=='delivery_ack' else '완료','basis':val(e['stage'],'events.jsonl'),'note':None}}
        for k,v in {**{k:v for k,v in e.items() if k!='seq'},'type':'stage_completed','producer':'rule','elapsed_ms':None,'input_frame_ids':[binding.get('frame_id')] if binding.get('frame_id') else [],'input_result_ids':[],'request_id':None,'command_id':None}.items():s[k]=val(v,'events.jsonl')
        steps.append(s)
    targetrows=[row('부재 ID',binding['part_id'],'results/marking-binding.json','/part_id'),row('이음 ID',binding['joint_id'],'results/marking-binding.json','/joint_id'),row('읽은 부재 표기',binding['part_text'],'results/marking-binding.json','/part_text'),row('읽은 이음 표기',binding.get('joint_text'),'results/marking-binding.json','/joint_text'),row('작업지시',conversion['order_id'],'results/robot-input.json','/order_id'),row('지시 대상',binding.get('visual_relation',{}).get('target_description'),'results/marking-binding.json','/visual_relation/target_description')]
    conditionseq=next(e['seq'] for e in events if e['stage']=='manufacturer_conversion')
    ackrows=[]
    for k,d in deliveries.items():
        file=f'commands/{k}-delivery.json';label='현대' if k=='hyundai' else '두산'
        ackrows.extend([row(label+' 수신 상태',d['ack']['status'],file,'/ack/status'),row(label+' HTTP 응답',d['http_status'],file,'/http_status'),row(label+' 수신 부재',d['request']['target']['part_id'],file,'/request/target/part_id'),row(label+' 수신 이음',d['request']['target']['joint_id'],file,'/request/target/joint_id'),row(label+' 수신 명령',d['request']['robot_input']['command_preview'],file,'/request/robot_input/command_preview'),row(label+' 명령 ID',d['ack']['command_id'],file,'/ack/command_id')])
    retrieval=read_json(root/'evidence/retrieval.json')
    evidencerows=[]
    for h in retrieval['hits']:
        evidencerows.append(row('원문 근거',{'document_id':h.get('document_id'),'locator':h.get('locator')},'evidence/retrieval.json'))
    def tab(blocks):return {'availability':'available' if blocks else 'absent','absent_reason':None if blocks else '이번 실행에 해당 기록 없음','blocks':blocks}
    rawblock={'type':'raw_files','title':'실제 전송 묶음 · 수신 원문','files':[{'root':key,'path':f'commands/{k}-{suffix}'} for k in deliveries for suffix in ('request.json','delivery.json','receiver.jsonl')]}
    deliveryblocks=[fields('마킹에서 연결된 전달 대상',targetrows,1),fields('전송 · 수신 결과',ackrows,len(steps)),{'id':key+'-input','type':'robot_input','title':'공통 작업조건 · 제조사 변환','seq':conditionseq,'preview':conversion},rawblock]
    captureblocks=[]
    if (root/'inputs/capture/capture.json').exists():
        cap=read_json(root/'inputs/capture/capture.json');items=[]
        for f in cap['frames']:
            sf=f['source_frame'];image_source=REPO/'output/recapture-handoff-20261010/inputs'/sf['image_ref'];dest=root/'frames'/Path(sf['image_ref']).name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(image_source,dest)
            items.append({'label':f['frame_id'],'image':{'path':f'bundles/{key}/frames/{dest.name}','width':sf['width'],'height':sf['height'],'sha256':digest(dest),'label':f['frame_id']},'rows':[row('실제 판독',f['readout']['markings'],'inputs/capture/capture.json')]})
        captureblocks=[{'type':'image_pair','title':'실제 판독 입력', 'items':items}]
    else:
        original=root/'inputs/document-run/inputs/recognition';m=read_json(original/'manifest.json');f=next(f for f in m['frames'] if f['frame_id']=='frame-007')
        path=(original/f['image_ref']).relative_to(root).as_posix();captureblocks=[{'type':'image_pair','title':'실제 마킹 입력','items':[{'label':f['frame_id'],'image':{'path':f'bundles/{key}/{path}','width':f['width'],'height':f['height'],'sha256':f['sha256'],'label':'실제 공개 철골 사진'},'rows':targetrows[:3]}]}]
    summary=deepcopy(source['summary']);summary.update(title='마킹 → 로봇 입력 → 수신 확인',kind_label='통합 전달 실행',group='connected',group_label='통합 파이프라인',display_path=f'bundles/{key}',run_id=val(manifest['run_id']),scenario_id=val('marking-to-delivery'),run_kind=val('weld_pipeline'),run_outcome=val('succeeded'),delivery_status=val('received'),capture_mode=val(manifest['capture_mode']),started_at_utc=val(manifest['started_at_utc']),finished_at_utc=val(manifest['finished_at_utc']),schema_version=val(manifest['schema_version']),final_seq=len(steps),headline=[],links=[],flags=[])
    integrity={'state':'verified','label':'통합 실행 해시 확인','message':None,'checks':[],'copy_matches_original':True}
    run.update(key=key,roots={key:f'bundles/{key}'},summary=summary,integrity=integrity,steps=steps,files=raw,tabs={'summary':tab([fields('마킹 · 전달 대상',targetrows),fields('수신 확인',ackrows)]),'capture':tab(captureblocks),'timeline':tab([]),'recapture':tab([]),'evidence':tab([fields('문서 원문 위치',evidencerows),{'type':'raw_files','title':'명세 · 판독 근거','files':[{'root':key,'path':p} for p in ['results/marking-binding.json','results/document-spec.json','results/robot-input.json','evidence/retrieval.json']]}]),'delivery':tab(deliveryblocks),'corrections':tab([])})
    write_assignment(package/'data/runs'/f'{key}.js',f'runs[{json.dumps(key)}]',run)
    index=read_assignment(package/'data/index.js');index['groups']=[{'key':'connected','label':'통합 파이프라인'}]+[g for g in index['groups'] if g['key']!='connected'];index['runs']=[{'key':key,'data_file':f'data/runs/{key}.js','bundle_dir':f'bundles/{key}','group':'connected','kind':'weld_pipeline','kind_label':'통합 전달 실행','integrity':integrity,'steps':len(steps),'summary':summary,'tab_availability':{k:v['availability'] for k,v in run['tabs'].items()},'viewer_html':None}]+index['runs'];write_assignment(package/'data/index.js','index',index)
    # 관리자 패키지 MANIFEST roots에도 등록해 verify CLI가 사본을 추적하게 한다.
    man_path=package/'MANIFEST.json'
    man=read_json(man_path) if man_path.is_file() else {'schema':'contextweld-admin-dashboard.package.v1','roots':[],'files':[],'volatile_files':[],'local_preview':None}
    try:source=str(bundle.resolve().relative_to(REPO))
    except ValueError:source=str(bundle)
    entry={'copied_subset':None,'excluded':[],'group':'connected','key':key,'kind':'weld_pipeline','package_dir':f'bundles/{key}','source':source}
    man['roots']=[r for r in man.get('roots',[]) if r.get('key')!=key]+[entry]
    write_json(man_path,man)
    print(f'Exported {key}: marking binding, 2 manufacturers, real HTTP ACK')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--key',required=True);a=p.parse_args();export(a.package,a.bundle,a.key)
