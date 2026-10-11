# 마킹부터 제조사 입력·모의 수신까지

2026-10-10. 실제 모델의 표기 판독에서 작업지시를 정확 조회하고, 문서 검증·원문 위치 검색·공통 작업명세·현대/두산 변환·HTTP 수신을 한 실행으로 연결한다. 저장 RGB를 사용하며 실제 로봇 이동·아크 실행은 수행하지 않는다.

```text
A/B RGB → 실제 OCR/VLM 원문 → 부재번호·이음 표기·지시 대상
→ 작업지시 정확 조회·도면의 이음 표기 연결
→ WPS 원문 해시·문서 충돌 검증·원문 위치 검색
→ 등록 작업조건 조회·공통 작업명세
→ 현대 Hi6 / 두산 DRL 변환
→ 대상·작업 요구·조건·명령을 함께 HTTP 전송 → 수신 원문·ACK
```

## 실행

기존 Runpod 추론 환경과 고정 모델을 사용한다. 원본 체크아웃을 수정하지 않는 별도 소스 사본에서 실행할 수 있다.

```sh
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/workspace/venvs/contextweld-inference/bin/python scripts/run_weld_pipeline.py \
  --capture-inputs output/recapture-handoff-20261010/inputs --source-kind capture \
  --output output/shipyard-connected-01 \
  --data-root /workspace/PAC2026/data/raw/demo-bootstrap-v1 \
  --index /workspace/PAC2026/output/document-rag/server-v1/index.json
```

`--capture-inputs`는 실제 판독 실행을 먼저 수행하고 그 결과를 연결한다. `--source`는 저장된 실제 인식 또는 문서 실행을 재사용한다. 둘 중 하나만 지정한다. 기존 실행 경로는 덮어쓰지 않는다. 등록 부재와 일치하지 않는 A 판독은 저장 B를 추가 관측한다. 이 선택은 `unresolved_target_identity_or_capture_quality`로 기록하며 모델의 반사 판정이나 실제 팔 이동으로 표시하지 않는다. A가 정확 조회되고 시각 관계가 관측되면 B를 호출하지 않는다.

모델 입력에는 정답 ID나 가능한 부재 목록을 제공하지 않는다. 판독 뒤 부재번호로 작업지시를 정확 조회한다. 실제 이음 표기 `J01`은 시연 도면의 `joint_marking_map`을 통해 업무 ID `JOINT-DEMO-01`과 연결한다. 이음 표기·지시 관계가 누락되거나 여러 개이면 전송하지 않는다. 다른 부재 표기를 기본 부재로 치환하지 않는다.

용접 수치는 마킹에서 만든 값이 아니다. 마킹으로 선택한 작업지시에 연결된 [등록조건](../configs/document_demo/weld_recipes.json)을 사용한다. 시연 작업지시·도면·등록조건의 출처는 데이터에 보존한다. 판독 결과·문서 조건·사용자 수정의 근거는 구분한다. 원본 WPS와 실제 적용성은 별개의 검증 범위다.

## 수신 패킷과 기록

기존 `demo-command.v1`에 다음을 추가한다.

- `target`: 프로젝트·블록·작업지시·부재·이음 ID
- `marking_binding`: 읽은 문자열, 프레임/이미지 해시, 관측·시각 관계, 문서 연결 근거
- `common_spec`: 공통 대상·공정·재질·자세·선택값과 근거
- `work_requirements`: 공정·재질·자세·관측된 지시 대상
- `robot_input`: 제조사 입력 필드·변환값·명령 문자열

수신기는 기존 문서 범위 검증과 함께 대상 일치·공통 선택값·단위 변환·명령 문자열을 검사한다. 현대와 두산에 각각 패킷을 보내고 명령 ID로 요청·수신 원문·ACK를 연결한다. `execution_authorized=false`이며 HTTP 수신은 실기 실행을 뜻하지 않는다. 기호·치수·실제 TCP 경로 생성은 이 연결의 지원 범위에 포함하지 않는다.

`weld-pipeline-bundle.v1`은 `inputs`, `results`, `evidence`, `commands`, `events.jsonl`, `manifest.json`, `checksums.json`을 보존한다. `verify_pipeline()`은 파일 해시, 인식 출처, 송신/수신 패킷, ACK의 ID·해시와 변환을 교차 확인한다.

```sh
python3 scripts/export_weld_pipeline_dashboard.py \
  --package output/dashboard-preview-20261010/pac-admin-dashboard \
  --bundle output/weld-pipeline-20261010/shipyard-connected-01 \
  --key shipyard-connected-01
```

관리자 화면은 저장된 전송/수신 기록을 재생한다. 전송한 조건은 수신 결과에 고정하여 보여주며, 수정 가능한 제조사 변환 카드는 별도의 현재 편집값이다. 화면에서 수정한다고 과거 전송 기록을 바꾸지 않는다.
