# 저장 A/B 재촬영 분기와 관리자 연결

작성 기준: 2026-10-10, `9451321`의 제품 인식 함수를 재사용하는 독립 모듈. 갱신일: 2026-10-22(코드 반영 2026-10-18). 최초 모듈은 기존 생산자를 수정하지 않았으며, 이후 통합 실행에 기록 브리지와 CLI를 추가했다. [데모 명세](../plan/DEMO_SPEC.md)의 `pre_captured` 경로에 해당하며 실제 팔 이동 연동인 P4는 구현하지 않는다.

## 구현 범위

`A 입력 → OCR → 시각 관측 → 범위 제한 문서 검색/관계 → 촬영 품질 판단 → 규칙 분기`를 실행한다. 미확정인 필수 시각정보에 관측 문제가 있고 시점 변경이 도움이 될 수 있다는 근거가 있을 때만 요청을 만들고, 저장된 B를 입력해 같은 경로로 다시 추론한다. 최대 재촬영은 1회다.

| 관측 결과 | 동작 |
|---|---|
| 표기 텍스트·표기 대상이 관측됨 | B를 호출하지 않고 문서 검토 준비 상태로 종료 |
| 정보 미확정 + 해당 정보의 관측 문제 + 시점 변경 가능성 | 저장 B 선택 요청 → B 실제 추론 |
| 의미만 모호함, 카메라로 개선할 근거 없음 | `needs_review`, 요청 없음 |
| B에서도 정보 미확정 | `needs_review`, 추가 요청 없음 |
| 모델/파싱/검색 실행 오류 | `failed`, 확보한 원문·사건·오류를 보존 |

`continue`와 `ready_for_document_review`는 **필수 시각정보가 관측됐다는 모델 판단**이다. 정답 여부·정확도 상승·문서 적용 승인·용접 실행을 의미하지 않는다. 문서 적용/모의 전달을 아직 연결하지 않았으므로 정상 추론의 전체 `run_outcome`도 `needs_review`다.

기존 `OBSERVATION_PROMPT`, `RELATION_PROMPT`, OCR/VLM 엔진, 좌표 정규화, 검색 함수를 그대로 사용한다. 재촬영에 필요한 구조화 근거를 얻기 위해 `capture_assessment` VLM 호출을 한 번 추가했다. 정확한 모델 원문을 보존하고 참조를 검증한다. 품질 판단은 두 필드(`marking_text`, `marking_target`)에 대해 관측 여부·근거를 반환한다. 문서나 장면의 정답으로 판독을 보정하지 않는다. 정답 포함 후보 목록, GT ROI, 정답과의 일치 판정은 이 모듈에 없다.

장면 manifest의 정답 표기·반사 예측·마스크·GT 좌표는 모델 입력에서 제외한다. 입력 준비 단계는 manifest SHA와 시나리오 ID, 원본 RGB와 촬영 메타데이터만 보존한다. 시스템이 단지 `unreadable`이라고 판단했다면 화면도 “판독 어려움”으로 표시한다. `glare`가 반환돼도 “모델의 반사 의심”이며 반사 원인 검증으로 표시하지 않는다.

## 현재 검증 범위

실제 `live-03`의 손목 A/B와 전체 장면 4 PNG, 촬영 JSON 2개를 불변 입력으로 준비·해시 검증했다. 입력 패키지의 `inference_status=not_run`은 준비 상태이며 실행 결과가 아니다. 분기·오류·원문·인과·해시 검증은 별도 `test_fixture` 관측으로 검사한다. 실제 모델의 A/B 출력과 모델에 의한 재촬영 요청은 아직 실행하지 않았다.

로컬 Python 3.11.9에서 신규 43개를 포함한 전체 126개 테스트가 통과했다. 전체 회귀 테스트의 HTTP 모의 수신은 로컬 loopback에 한정되며 서버·GPU를 사용하지 않았다. 신규 8개 파일 패치는 2026-10-10 기준 체크아웃(`9451321`)에서 `git apply --check`로 충돌 없음을 확인했다. 기존 미커밋 파일과 장면 자료 40개의 SHA는 유지됐다.

다른 작업의 GPU 실험·관리자 UI와 충돌하지 않도록 서버 실행은 별도 시점에 수행한다. 이 문서의 명령은 준비된 실행 경로이며 실행 완료 증거가 아니다. 대시보드 읽기 어댑터는 2026-10-18 구현 완료(`후속 통합 순서` 1번), 실제 화면 검수는 통합 단계에 남아 있다.

## 병합 기록 (2026-10-15, dev 반영)

2026-10-10 handoff 이후 dev가 `scripts/run/`·`docs/runs/` 체계로 재편되면서 handoff 패치의 경로가 어긋나, 병합은 파일별 배치와 해시 대조로 수행했다. handoff 원본(ZIP·patch·코드 8개)은 `output/recapture-handoff-20261010/`에 그대로 보존한다.

| 병합 위치 | handoff 원본과의 관계 |
|---|---|
| `src/contextweld/recapture_inputs.py` | 바이트 동일 (SHA-256 `ea704e6f…b56a26`) |
| `src/contextweld/recapture_inference.py` | 바이트 동일 (SHA-256 `331b3120…d27e66`) |
| `src/contextweld/recapture_loop.py` | 바이트 동일 (SHA-256 `e62e3d82…2cb8ce`) |
| `tests/test_recapture_inputs.py` | 바이트 동일 (SHA-256 `b8078472…f307f9`) |
| `tests/test_recapture_inference.py` | 바이트 동일 (SHA-256 `aec56c27…61c868`) |
| `tests/test_recapture_loop.py` | 바이트 동일 (SHA-256 `c14ff1f1…242a7d`) |
| `scripts/run/run_recapture_loop.py` | `REPO` 기준만 `parents[1]`→`parents[2]`로 수정 (원본 SHA-256 `abb51beb…2a851e`) |
| `docs/runs/RECAPTURE_LOOP.md` | 문서 내 스크립트 경로·링크를 dev 체계로 수정 (원본 SHA-256 `2aa6f544…c737fa`) |

기존 `capture_binding()`의 `requires_recapture=true` 예외는 유지한다(결정과 사유는 [WELD_PIPELINE.md](WELD_PIPELINE.md)의 재촬영 결정 문단 참조). 2026-10-16 연결(Option 1): `run_pipeline()`이 이 예외를 받아 이 모듈을 기록 단계로 실행하고(`src/contextweld/recapture_bridge.py`) 완료 번들을 weld 묶음의 `inputs/recapture-bundle/`에 보존한다. 루프 판정은 weld 판독 결정을 대체하지 않으며 연결은 기록만이다.

## 통합 실행의 기록 브리지 (2026-10-16 구현)

| 조건·결과 | 현재 동작 |
|---|---|
| `source_kind=capture`, 마지막 판독 `requires_recapture=true`, 재촬영 설정 있음 | `capture_binding` 예외를 받아 `run_recapture_step()` 실행 |
| 촬영 기록의 프레임 해시가 재촬영 입력에 없음 | 다른 저장 A/B로 루프를 실행하지 않고 거절 |
| 루프 완료·검증 성공 | `inputs/recapture-bundle/` 복사, manifest에 `recapture_bundle_ref`, `recapture_run_id`, `recapture_outcome`, `recapture_visual_outcome` 기록 |
| 루프의 시각 판정이 `continue` | 통합 실행은 여전히 `needs_review`·전달 `blocked`; 후속 문서·명령 생성으로 진행하지 않음 |
| 설정 없음 또는 다른 연결 오류 | 기존 보류 경로 유지; 루프를 자동 호출하지 않음 |

`src/contextweld/recapture_bridge.py`와 `tests/test_recapture_bridge.py` 6개 테스트로 이 연결을 확인했다. 10월 16일 전체 회귀는 161개 통과했으며 위 최초 126개는 10월 10일 기록이다. 실제 GPU 실행 증거는 아직 없다. 10월 10일 `shipyard-connected-01`의 저장 B 선택은 이 브리지 실행이 아니다.

통합 CLI `scripts/run/run_weld_pipeline.py`의 기존 입력에 아래 옵션을 추가한다. 명령 전체의 입력 경로는 [통합 실행 안내](WELD_PIPELINE.md)를 따른다.

| 옵션 | 의미·기본값 |
|---|---|
| `--recapture-inputs` | `recapture-inputs.v1` 입력 루트. 촬영 기록과 해시 대조 |
| `--recapture-output-root`, `--recapture-run-id` | 기본 `output/recapture-loops`, `<통합 output 이름>-recapture` |
| `--recapture-{det,rec,vlm}-model-dir`, `--recapture-{det,rec,vlm}-revision` | 실제 추론을 위한 경로·고정 revision 6항목 필수. 아래 독립 실행과 같은 값 사용 |
| `--recapture-ocr-device` | 기본 `cpu` |
| `--recapture-document-ids`, `--recapture-query` | 기본 `twi-weld-symbols`, 용접 기호·화살표 검색 질의 |
| `--recapture-top-k`, `--recapture-max-new-tokens`, `--recapture-max-pixels` | 기본 `3`, `4096`, `802816`; 허용 범위는 각각 1~10, 128 이상, 65536 이상 |

## 파일과 실행

| 파일 | 역할 |
|---|---|
| `src/contextweld/recapture_inputs.py` | 고정 `frames/`만 읽어 출처·픽셀·포즈·SHA를 검증·복사 |
| `src/contextweld/recapture_inference.py` | 기존 제품 추론과 촬영 품질 근거를 프레임 단위로 실행 |
| `src/contextweld/recapture_loop.py` | 조건부 B 선택·사건 기록·불변 묶음/인과 검증 |
| `scripts/run/run_recapture_loop.py` | 준비·실행·검증 명령 |
| `tests/test_recapture_*.py` | 모델 성능이 아닌 분기·계약·오류·보존 테스트 |

기존 환경의 Python/Pillow를 사용한다. 실제 실행만 기존 Paddle/Qwen 추론 환경을 요구한다. 새 의존성이나 모델 설치는 필요하지 않다. 모든 출력은 새 경로/새 run ID로 생성하며 기존 디렉토리와 `.incomplete`를 덮어쓰지 않는다. 경로는 심볼릭 링크 대신 실제 절대경로를 사용한다.

```bash
python scripts/run/run_recapture_loop.py prepare \
  --scene-root /workspace/PAC2026/output/isaac-shipyard-20261010/live-03 \
  --destination output/recapture-inputs/live-03
python scripts/run/run_recapture_loop.py verify-inputs --inputs-root output/recapture-inputs/live-03
```

GPU를 사용하는 다른 추론이 끝난 뒤, 이 변경을 반영한 별도 체크아웃에서 실행한다. 모델 경로·revision은 기존 [실제 추론 환경](RUNPOD_INFERENCE.md)의 고정값이다. 데이터/색인은 원본 읽기 전용, 출력은 별도 경로다.

```bash
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/workspace/venvs/contextweld-inference/bin/python scripts/run/run_recapture_loop.py run \
  --inputs-root output/recapture-inputs/live-03 \
  --output-root output/recapture-runs --run-id shipyard-recapture-01 \
  --data-root /workspace/PAC2026/data/raw/demo-bootstrap-v1 \
  --document-index /workspace/PAC2026/output/document-rag/server-v1/index.json \
  --det-model-dir /workspace/models/contextweld/PP-OCRv6_medium_det/8e0f56fb2ef86b461d99cfc7ac5c137738985f61 \
  --det-revision 8e0f56fb2ef86b461d99cfc7ac5c137738985f61 \
  --rec-model-dir /workspace/models/contextweld/PP-OCRv6_medium_rec/e5a92bcbc5cc1b494628e458d267778f0704fd7c \
  --rec-revision e5a92bcbc5cc1b494628e458d267778f0704fd7c \
  --vlm-model-dir /workspace/models/contextweld/Qwen3-VL-8B-Instruct/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b \
  --vlm-revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b
python scripts/run/run_recapture_loop.py verify --bundle output/recapture-runs/run_shipyard-recapture-01
```

시점별 OCR 1회·VLM 관측/관계/품질 3호출이며 JSON 구문 재시도는 최대 1회다. A 결과가 요청을 만들지 않으면 B 추론은 0회다. 현재 구현은 각 프레임마다 모델을 해제·재로드하므로 지연 최적화는 하지 않았다. `run`의 exit 0은 실행과 저장 완료이며 작업 승인/정답 판정이 아니다. 기술 실패는 가능한 기록을 완료 묶음으로 내보내고 exit 1을 반환한다. 중단·쓰기 실패는 `.incomplete`로 남을 수 있다.

## 대시보드 읽기 계약

2026-10-18 기존 bootstrap/document/review 스키마를 유지하면서 `recapture-bundle.v1` 읽기 어댑터를 추가했다. `catalog`의 종류 분류·어댑터 등록·`integrity.VERIFIERS`에 연결되어 있다. 읽기 전에 `verify_recapture_bundle()`을 호출한다. 미지원 스키마를 bootstrap으로 강제 처리하지 않는다.

```text
run_<id>/
  manifest.json            # 실행 결과와 export_status 분리
  checksums.json           # 자체 파일 제외 전체 SHA
  events.jsonl             # seq 순서, 부모·입력·요청 IDs
  inputs/                  # A/B 원본 입력 패키지; 미래 결과가 아님
  frames/frame-A.json      # 실제 사용된 프레임만 기록
  frames/frame-B.json      # 요청했을 때만 존재
  results/                 # 원문·프롬프트·구조화 관측·품질·분기
  evidence/                # 검색 발췌·실제 제공/인용 ID
  requests/recapture-01.json # 요청한 경우만 존재
```

| 화면 | 읽을 기록 |
|---|---|
| 요약 | `run_kind`, `capture_mode`, `run_outcome`, `inference_status`, `visual_outcome`, `recapture_outcome`, `export_status` |
| A/B 이미지·포즈 | manifest `frames`의 `image_ref`/`overview_ref`, `camera_pose`, 원 촬영/현재 입력 시각 |
| OCR·관계 오버레이 | `results`의 `text_observations`, `visual_objects`, `relations`; `original_pixels` |
| 재촬영 이유 | `capture_assessment`의 필드별 상태·설명·quality_evidence와 `recognition_decision` 규칙 |
| 요청과 후속 관측 | request의 source IDs, 사건의 `request_id`/부모, B의 `capture_request_id` |
| 반사 여부 | 품질 evidence의 실제 code/explanation; 장면 설정의 반사와 모델 진단 구분 |
| 문서 근거 | 저장 retrieval의 검색 범위·hits·used/cited IDs·원문 위치; 전체 원문 포함을 가정하지 않음 |
| 보류·실패 | terminal decision 또는 `results/error.json`; 전달 내역은 `not_requested` |

사건은 `seq` 순으로 읽는다. `input_result_ids`와 `parent_event_ids`가 현재 단계에 사용된 원인을 지정한다. 재생 시 아직 발생하지 않은 B 결과를 현재 값으로 표시하지 않는다. 입력 패키지에 B 사진이 있어도 B 사건 전에는 관측 결과로 취급하지 않는다. 비교 화면에서 미래 프레임을 미리 보여주려면 “저장 자료 미리보기”로 구분한다.

`capture_request_id`는 이번 요청에 대한 **저장 프레임 선택 연결**이다. `origin_capture_request_id=null`, `request_link_semantics=saved_frame_selection`이며 원래 B 촬영이 이번 요청 뒤에 일어난 것은 아니다. `physical_movement_triggered=false`, `recognition_feedback_enabled=false`를 유지한다. 이번 실행에 없는 `movement_started/completed`를 영상 길이에 맞춰 생성하지 않는다. 팔 이동 녹화는 별도 예약 장면 자료로만 연결한다.

UI는 새 묶음을 읽기만 하며 추론·검색·ROS·전송을 실행하지 않는다. 원본 기록을 고치지 않고, 모델/규칙/시뮬레이터/테스트 fixture를 구분한다. `evidence_kind=test_fixture`는 모델 결과로 표시하지 않는다.

## 후속 통합 순서

2026-10-24 기준 기록 브리지와 아래 1번, 4번의 저장 결과 기반 문서·전달 재개는 구현했다. 실제 A/B GPU 루프(2번), 실제 결과 화면 대조(3번), live provider는 서버 접근 재개 후 작업이다.

1. ~~`recapture-bundle.v1` 전용 대시보드 읽기 어댑터를 구현한다. 기존 bootstrap/document/review와 실제 전달 화면은 보존한다.~~ **완료(2026-10-18).** `contextweld_dashboard.adapters.recapture`로 구현하고 `catalog`·`integrity.VERIFIERS`에 연결했다. `tests/test_dashboard_recapture.py`가 화면 모델의 저장 값을 원본 묶음과 다시 대조해 재생이 원문에서만 나오는지 확인한다.
2. 공유 GPU 사용이 겹치지 않는 시점에 실제 A/B 루프를 한 번 실행한다. 강제로 A 실패/B 성공을 만들지 않는다.
3. 검증된 실제 결과 묶음을 대시보드 어댑터로 읽고 재촬영 여부·이유·A/B 차이를 원문과 대조한다.
4. **문서 적용·모의 전달 재개 구현(2026-10-24).** 검증된 묶음을 `run_weld_pipeline.py --source-kind recapture --source <묶음>`에 넘겨 새 실행을 만든다. 원본 보류 기록은 유지하고 추가 추론 없이 마지막 관측을 정확 연결한다. [실행 규약](WELD_PIPELINE.md)·[로컬 fixture 검증](LOCAL_RESUME_VERIFICATION.md)을 참조한다. 요청→이동 완료→새 RGB의 시간/ID를 기록하는 live provider는 미구현이다.

10월 18일 어댑터 검증은 A만 사용해 진행하는 경우, B를 요청해 재관측하는 경우, 기술 실패의 fixture 3개다. 당시 전체 회귀는 164개 통과했다(10월 16일 161개 + 3개). 원본 묶음과 화면 모델의 연결을 검사한 결과이며 실제 GPU·브라우저 시각 검수는 아니다.

단위 테스트 결과는 실험 성능 자료가 아니다. 현재 독립 실험의 설계·채점·정답은 변경하지 않는다.
