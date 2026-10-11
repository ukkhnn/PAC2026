# 사용자 수정 저장 → 명시적 재검토 → 선택적 모의 전달

기준일: **2026-10-10** · 계약: [데모 스펙 v1.5](../plan/DEMO_SPEC.md) 6.2·7.2·8절, [OCR 구성](../spec/OCR_PIPELINE_SPEC.md) 8.3·9절, [문서 적용 계획](../plan/DOCUMENT_APPLICATION_PLAN.md)의 작업자 수정 후 재검토 · 상태: **CLI 기반 문서 범위 규칙 재검토 구현·서버 실행 검증, 시각 관계 모델 재해석·입력 UI 미구현**

원래 관측과 실행 묶음을 그대로 둔 채 **① 수정 저장 ② 명시적 재검토 ③ 선택적 모의 전달**을 사용자가 서로 다른 명령으로 수행한다. 수정 저장은 재검토를 시작하지 않고, 재검토 완료는 전달 요청이 아니다. 전달은 `--deliver`를 준 **새 재검토 실행** 안에서만 일어난다. 데모 스펙 O07(수정·재검토 입력 위치)은 이번에 **서버 저장소의 CLI와 JSON 요청 파일**로 정했다. 웹 입력 화면·로그인·DB는 만들지 않았고 오프라인 HTML은 계속 읽기 전용이다.

## 1. 구현 범위와 남은 것

| 구분 | 이번 구현 | 남은 것 / 하지 않은 것 |
|---|---|---|
| 수정 저장 | 완료 묶음 밖 저장소에 수정·보류 1건당 파일 1개를 배타적으로 생성. 대상 묶음 재검증, 결과 해시·수정 전 값 대조, 지원 필드 제한, 재시도/충돌 구분 | 웹/화면 입력, 사용자 인증, 여러 사람의 승인 흐름 |
| 명시적 재검토 | `run_kind=review` 새 묶음. 선택 수정만 적용해 관측 후보 → 작업지시·도면 → WPS/개정 → 새 명세 → 필수값·단위·충돌 검사를 규칙으로 다시 실행. 해결/잔존 이슈를 수정 ID와 연결 | 이미지 의미·화살표·이음 같은 **시각 관계의 모델 재해석**은 미구현. 새 사진·새 OCR 없음 |
| 선택적 모의 전달 | 새 재검토 실행에서 검증 통과 시에만 기존 loopback `MockReceiver`로 전송. 요청 본문·ACK·수신기 원본 저장, 실패는 `failed`로 기록 | 실제 설비 전송, 현장 적용 승인 |
| 불변 묶음·조회 | `review-bundle.v1` 생산자·검증기·HTML 조회기. 부모 묶음 사본·선택 수정 스냅샷·요청·계보·재계산 검증 포함, 다른 디렉토리로 옮겨도 검증·조회 가능. 여러 실행 통합은 이후 [오프라인 관리자 패키지](ADMIN_DASHBOARD.md)가 담당 | A/B 재촬영 재생 |

지원하지 않는 수정(관계 대상 변경, 도면·WPS 개정 생성, 수치 직접 입력, 승인·검증·신뢰도 같은 내부 필드)은 **저장 단계에서 거절**한다. 따라서 그런 관계 문제는 기존 결과의 `needs_review`로 남는다.

## 2. 지원하는 수정

| `action` | 대상 결과 | 사용자가 넣는 값 (`after`) | 저장 시 확인 | 재검토에서의 효과 |
|---|---|---|---|---|
| `select_observed_candidate` | `results/observation-selection.json` (document_demo) 또는 `results/effective-interpretation.json` (review)의 관측 1건, 필드 `part_id` | `{"part_id": ...}` — 그 관측에서 **실제 OCR/VLM이 읽은 후보 중 하나** | 관측 ID 존재, 후보 포함, 수정 전 값·결과 해시 일치 | OCR 원문·정규화값은 그대로 두고 `effective_identifier`(`source_kind=user` 또는 `demo_fixture`)만 추가. 해당 관측의 판독 불일치 이슈는 삭제하지 않고 `resolved_issues`로 옮겨 수정 ID·선택 근거를 연결 |
| `restore_document_parameter` | `results/work-spec.json`, 필드 `parameters.<이름>` (프로파일에 있는 이름만) | `{"document_id", "revision", "row_id"}` — **수치는 넣을 수 없음** | 해당 파라미터가 누락으로 기록됨, 선택된 작업지시가 실제 참조하는 WPS 행과 일치, 그 행의 값이 `agent_transcription_checked` | 검수 WPS 행을 정확 조회해 값·단위·원문 위치를 다시 채움(`source_kind=document`). 필드에 `restored_by_correction_id`를 붙이고 원래 결함 주입 기록은 보존 |
| `hold` | 위 결과 중 하나 | `{"decision": "hold"}` | 결과 해시·현재 상태 일치 | 기록만 남긴다. 재검토에 선택하면 `hold_not_applicable`로 거절하며 실행·전달을 만들지 않음 |

모든 요청은 `correction-request.v1` 형식이며 허용 키 밖의 필드(예: `execution_authorized`, `confidence`, `validation`)가 있으면 거절한다. 작성 주체 `author.kind`는 `user` 또는 `demo_fixture`다. 자동 시연용으로 만든 수정은 `demo_fixture`로 표시하며 사람이 검수한 것처럼 기록하지 않는다. kind는 요청자가 선언한 값이며 신원 인증이 아니다.

## 3. 실행 방법

서버 저장소 루트에서 기존 Python을 사용한다. 표준 라이브러리만 쓰며 GPU·모델·네트워크 포트 공개가 필요 없다. 아래 경로의 run ID는 예시이며 이미 쓴 ID는 새 이름으로 바꾼다.

```sh
PY=/workspace/venvs/contextweld-inference/bin/python
SRV=output/document-demo-20261010/server
OUT=output/explicit-review-20261010

# 0) 수정 가능한 대상·수정 전 값·결과 해시를 요청 서식으로 확인 (읽기 전용)
$PY scripts/run/record_correction.py targets --bundle $SRV/run_document-missing-server-01 > targets.json
#    targets.json의 templates[].request 하나를 파일로 저장하고 correction_id·after·reason·author를 채운다.

# 1) 수정 저장만 한다. 재검토·모델 호출·전송 없음
$PY scripts/run/record_correction.py record --bundle $SRV/run_document-missing-server-01 \
  --request voltage-request.json --store $OUT/correction-store

# 2) 선택한 수정으로 재검토만 한다 (전달 미요청)
$PY scripts/run/run_review.py --parent-bundle $SRV/run_document-missing-server-01 \
  --store $OUT/correction-store --correction corr-voltage-01 \
  --review-request-id rr-voltage-01 --run-id review-voltage-01 --output-root $OUT \
  --requested-by operator-01 --requester-kind user --reason "전압 누락을 WPS 근거로 복구해 재검토"

# 3) 이미 내보낸 재검토를 나중에 전달하려면 그 묶음을 부모로 새 재검토·전달 실행을 만든다
$PY scripts/run/run_review.py --parent-bundle $OUT/run_review-voltage-01 \
  --store $OUT/correction-store --correction corr-voltage-01 \
  --review-request-id rr-voltage-deliver-01 --run-id review-voltage-deliver-01 --output-root $OUT \
  --requested-by operator-01 --requester-kind user --reason "재검토 결과를 모의 수신기로 전달" --deliver

# 4) 추론·전송 없이 검증, 5) 읽기 전용 HTML 내보내기
python3 scripts/verify/verify_review_bundle.py $OUT/run_review-voltage-deliver-01
python3 scripts/export/export_document_review.py $OUT/run_review-voltage-deliver-01 \
  --output $OUT/html/review-voltage-deliver-01.html
```

`--correction`은 여러 번 줄 수 있으며 준 순서를 기록한다. `--deliver`가 없으면 명령·ACK를 만들지 않는다. `--delivery-fault receiver_unavailable`은 시연용 결함 주입으로, 수신기를 열었다 닫은 뒤 실제 loopback 연결 실패를 만들고 요청·manifest에 기록한다. 종료 코드는 성공·재시도 0, 거절·충돌 2(거절 기록을 `<store>/rejections/` 또는 `<output-root>/rejected-requests/`에 새 파일로 남김), 기타 오류 1이다. 결함 주입 실행은 CLI 출력·manifest·HTML 머리말에 `시연용 결함 주입`으로 표시한다.

## 4. 재검토가 다시 실행하는 것

1. **입력 확인**: 즉시 부모 묶음을 스키마별 기존 검증기로 재검증한다(`document-demo-bundle.v1`은 기존 `inspect_document_bundle`을 그대로 사용). 저장소에서는 **선택한 ID의 파일만** 열고 목록을 훑지 않는다.
2. **계보·대상 확인**: 원래 document_demo 실행 → (이전 재검토들) → 즉시 부모를 `results/lineage.json`에 기록한다. 선택 수정의 대상 실행이 이 계보에 없으면 `unrelated_run`, 같은 run ID라도 묶음 해시가 다르면 `stale_target_bundle`, 결과 해시나 수정 전 값이 다르면 `stale_result`/`stale_before_value`로 거절한다.
3. **적용 순서와 수정 전 값 기준**: 단계 순서(관측 선택 → 문서 필드 복구)를 지키고 단계 안에서는 요청 순서대로 적용한다. 각 수정의 `before`는 대상 원결과의 값이며, 적용 직전의 현재 상태와도 같아야 한다. 같은 대상의 두 수정을 함께 고르거나 선행 수정을 빼면 `conflicting_or_stale_basis`로 거절한다. 조상 실행의 원결과를 대상으로 한 수정의 명시적 재사용은 허용하고 `relation_to_review=ancestor`로 기록한다.
4. **재판단**: 원래 인식 관측에서 후보를 다시 계산하고 선택 수정을 반영한 `effective-interpretation` → 기존 `build_spec`의 작업지시 정확 조회·도면/WPS 참조·개정·필드 조회·`validate_command` 검사를 다시 실행한다. 이전 이슈를 지우거나 성공을 강제하지 않으며 `issue-resolution.json`에 부모·원래 실행 대비 `resolved`/`open`/`new`를 수정 ID·근거와 함께 남긴다.
5. **결과**: 이슈가 남으면 `needs_review`(요청했어도 전달 `blocked`), 이슈가 없고 전달 미요청이면 `succeeded`·`not_requested`, 전달을 요청했으면 실제 ACK `received`일 때만 `succeeded`, 그 밖의 기술 실패는 `failed`다. 모든 묶음은 `application_authorized=false`, `execution_authorized=false`, `demo_complete=false`, `new_model_calls=0`이다.

| 처리 주체 | 기록 위치 |
|---|---|
| `user` / `fixture`(`demo_fixture`) | 수정 기록의 `source_kind`·`producer`, `correction_selected` 사건, `effective_identifier`, 요청 사건 |
| `model` | 원래 인식 실행의 OCR/VLM 원문·관측(재사용, 재작성 없음) |
| `rule` | 후보 재계산·작업지시 매칭·문서 조회·검증·이슈 대조 |
| `document` | WPS 전사에서 정확 조회한 범위값과 원문 위치 |

## 5. 묶음 구조와 검증

```text
run_<run_id>/
  manifest.json                    # review-bundle.v1, run_kind=review, parent/origin/recognition run, 요청·수정 ID, 전달 요청
  events.jsonl                     # review_requested → input_snapshot → lineage → correction_selected… → 규칙 단계 → (전달) → export
  corrections.jsonl                # 선택한 수정 기록 스냅샷(적용 순서)
  inputs/review-request.json       # 요청 내용과 request_sha256 (run_id·시각 제외 내용의 해시)
  inputs/corrections/<id>.json     # 저장소 파일의 바이트 사본
  inputs/parent/                   # 즉시 부모 묶음 전체 사본 (원래 문서 실행·인식 묶음 포함)
  inputs/environment.json          # 코드 해시·Git 상태
  results/lineage.json, effective-interpretation.json, correction-application.json,
          matching.json, work-spec.json(review-work-spec.v1), issue-resolution.json, delivery.json
  commands/                        # 전달한 경우에만 command.json, transport.json 또는 transport-error.json, receiver.jsonl
  checksums.json
```

`verify_review_bundle.py`(또는 HTML 내보내기)는 파일 목록·해시·symlink·경로 이탈 외에 다음을 확인한다: 부모 사본의 재귀 검증과 manifest 해시 연결, 계보 재계산, 요청 스냅샷 해시와 manifest 일치, 선택 수정 파일·`corrections.jsonl`·요청 해시의 일치, 각 수정의 대상·결과 해시·수정 전 값을 계보 안 원결과와 다시 대조, 해석·매칭·명세·이슈 대조의 **전체 재계산 일치**, 명세와 명령·전송 본문·ACK·수신기 원본의 일치, 보류/미요청 실행에 명령이 없는지, 결과 상태 규칙, 사건 순서와 생성 주체. 결과와 `checksums.json`을 함께 고친 의미 변조도 재계산 단계에서 거절된다. 묶음 전체를 일관되게 다시 만든 위조는 서명이 없으므로 탐지 범위 밖이다.

기존 `document-demo-bundle.v1` 검증은 의미를 바꾸지 않았다. 다만 서버의 보류 묶음 4개에서 **빈 `commands/` 디렉토리가 사라져**(2026-10-09T20:33:5xZ 이전 Git 정합의 untracked 정리 시점) 기존 검증기가 `FileNotFoundError`로 실패하던 문제를, 없는 디렉토리를 빈 디렉토리와 같은 “명령 없음”으로 보도록 고쳤다. 해당 묶음의 파일과 해시는 그대로이며 원본은 수정하지 않았다.

## 6. 재시도·충돌·실패

- 같은 `correction_id`·같은 요청 재전송은 `duplicate_retry`로 새 파일을 만들지 않는다. 같은 ID에 다른 내용은 `correction_id_conflict`(종료 코드 2)이며 기존 파일은 그대로다. 저장은 임시 파일 완성 후 hard link로 공개해 동시 저장에서도 한 건만 남는다.
- `review_request_id`는 출력 위치와 무관하게 **수정 저장소의 `<store>/review-requests/`**에 배타적으로 등록한다. 실행 디렉토리를 먼저 확보한 뒤 등록하며, 같은 내용의 재시도는 `--output-root`를 바꿔도 기존 실행 결과를 알려 주고 **다시 실행·전송하지 않는다**. 등록된 경로의 실행이 실제로 같은 요청인지(요청 ID·`request_sha256`)도 확인한다. 다른 내용은 `review_request_id_conflict`. 이전 시도가 미완료면 그 경로를 알려 주며 새 요청 ID로 다시 요청해야 한다.
- 새 `run_id`는 부모·조상·원래 인식 실행의 ID와 같을 수 없고(`run_id_reused`), 조상 재검토의 요청 ID도 다시 쓸 수 없다. 따라서 명세·명령 ID(`<run_id>-spec-001`, `<run_id>-command-001`)는 항상 새 값이다. 출력·저장소 경로가 어떤 실행 묶음 안에 있으면 거절한다.
- 전달 timeout·연결 실패·ACK 계약 불일치는 `commands/transport-error.json`에 보낸 요청 본문·오류·받은 HTTP 상태와 응답 본문(있을 때)을 남기고 `run_outcome=failed`, `export_status=complete`로 내보낸다. ACK를 만들지 않는다. 수신기 원본 기록에는 수신됐지만 클라이언트가 응답을 확인하지 못한 경우는 `receiver_side=received`, `client_ack_confirmed=false`로 구분해 표시하며 같은 명령을 자동 재전송하지 않는다. 예상하지 못한 예외는 `run_<id>.incomplete`에 `export_status=incomplete`로 보존한다.
- 완료 묶음은 바꾸지 않는다. 내보낸 뒤 전달을 원하면 그 묶음을 부모로 하는 새 재검토·전달 실행을 만든다.

## 7. 2026-10-10 서버 실제 실행

코드 기준 `f3e9123`(실행 시 `git_dirty=false`), 서버의 기존 `/workspace/venvs/contextweld-inference/bin/python` 3.12로 CLI를 그대로 실행했다. 입력은 [문서 연결 실행](DOCUMENT_DEMO.md)의 서버 묶음 `run_document-missing-server-01`, `run_document-observation-conflict-server-01`, `run_document-normal-server-01`이다. **새 모델 호출은 0회**이며 OCR/VLM 원문은 그 묶음 안의 `steel-batch-20261010-02` 실제 출력을 재사용했다. 수정 3건은 모두 자동 시연용 `demo_fixture`로 작성했고 사람이 원본을 검수한 기록이 아니다. 27단계가 모두 예상 종료 코드와 일치했다.

| 확인 사례 | 실행 / 단계 | 실제 결과 |
|---|---|---|
| 수정 저장만 | `corr-20261010-missing-voltage-01` 기록 | `recorded`. 저장소에 파일 1개만 생성, 재검토·모델·HTTP 없음 |
| 같은 수정 재시도 / 같은 ID 다른 내용 | 같은 요청 재전송 / 사유만 바꾼 요청 | `duplicate_retry`(새 파일 없음) / `correction_id_conflict`(종료 2, 기존 파일 불변) |
| 오래된 수정 전 값 | `before.present=true`로 보낸 요청 | `stale_before_value` 거절 |
| 보류 선택 | `corr-20261010-frame005-hold-01` 기록 후 재검토 요청 | 기록만 남음. 재검토 요청은 `hold_not_applicable`, 실행·전달 없음 |
| 선택 수정으로 검토, 전달 미요청 | `run_review-20261010-voltage-01` (부모 `document-missing-server-01`) | `succeeded`·`not_requested`. 부모 이슈 1건 `required_parameter_missing parameters.voltage`를 수정 ID로 해결, 전압 24–28 V를 WPS 2쪽 `Volt Range` 원문 위치와 함께 복구. 명령·ACK 없음. 207파일·11사건 |
| 내보낸 뒤 명시적 전달 | `run_review-20261010-voltage-deliver-01` (부모 = 위 재검토, HTML 내보낸 뒤 실행) | `succeeded`·`received`. HTTP 200, `review-20261010-voltage-deliver-01-command-001`, ACK의 `command_sha256` = 요청 본문 해시, 수신기 원본 1행이 ACK와 일치. 계보 `document-missing-server-01 → review-20261010-voltage-01`, 수정 대상은 조상 원결과. 부모 묶음의 checksums 해시가 실행 전 기록과 같아 불변 |
| 같은 요청 재시도 / 다른 내용 | 같은 `review_request_id`·다른 run ID / 전달 없이 다른 사유 | `duplicate_request`(`new_run_created=false`, `delivery_attempted_again=false`) / `review_request_id_conflict` |
| 수정 뒤에도 문제 잔존 | `run_review-20261010-frame005-01` (부모 `document-observation-conflict-server-01`, `--deliver`) | `needs_review`·`blocked`. OCR 원문 `BISb30N-29`·VLM `B1Sb3ON-29`는 보존하고 시연 선택 `BISB30N-29`만 `effective_identifier`로 적용. `ocr_vlm_disagreement` 1건은 수정 ID로 해결, frame-007용 작업지시와 맞지 않아 `work_order_no_valid_order` 등 9건 잔존. 명령 없음 |
| 네트워크/수신 실패 | `run_review-20261010-voltage-receiver-down-01` (`--delivery-fault receiver_unavailable`) | `failed`·`failed`, `export_status=complete`. 실제 `ConnectionRefusedError`, 수신기 기록 0행, ACK 없음. 결함 주입을 manifest·HTML 머리말에 표시 |
| 무관한 실행의 수정 | 정상 실행을 부모로 전압 수정 선택 | `unrelated_run` 거절, 실행 없음 |
| 다른 디렉토리로 옮긴 사본 | `portability-check/copied/bundle-only` | 검증·HTML 내보내기 성공. 파일 안의 `/workspace/` 경로 참조 0건 |
| 변조 후 checksum 재작성 | 전달 묶음 사본의 전압 상한을 99로 바꾸고 해시 재계산 | 검증 실패: `재검토 결과 재계산 불일치: results/work-spec.json` (사본은 결과 기록 후 삭제) |

입력 불변: 실행 전후 `output/document-demo-20261010/server`, `output/recognition/run_steel-batch-20261010-02`, `output/document-rag/server-v1/index.json`, `data/raw/demo-bootstrap-v1`, `configs/document_demo`, WPS 전사 파일의 **1,173개 파일 SHA-256과 디렉토리 52개가 모두 같았다**.

테스트: `PYTHONPATH=src python -m unittest discover -s tests` **83개 통과**(기존 59 + 조회 6 = 65, 신규 재검토 15·재검토 조회 3). 신규 테스트는 저장만/보류/미요청 성공/잔존 보류/실제 loopback 전달/내보낸 뒤 전달/저장·재검토 거절/계보를 건너뛴 선택 수정/재시도·동시 저장/출력 위치 변경 재시도/ID 재사용·묶음 내부 출력 거절/의미 변조·파일 누락·symlink·경로 이탈/전달 실패 3종·응답 지연/빈 `commands/` 처리/이동 사본 조회·HTML 이스케이프를 확인한다.

산출물(Git 제외): `output/explicit-review-20261010/`의 `run_review-20261010-*`(4개 묶음), `correction-store/`(수정 3건·거절 2건·요청 등록 4건), `requests/`(대상 목록·요청 JSON), `html/`(재검토 HTML 5개), `logs/`(27단계의 argv·종료 코드·출력), `rejected-requests/`, `input-hashes-*.json`, `results-summary.json`, 실행 드라이버 `drive_actual_runs.py`.

## 8. 한계

- 문서 범위 규칙 재검토다. 화살표·이음 같은 시각 관계 수정과 이미지 의미의 모델 재해석은 구현하지 않았고, 모델을 다시 부르지 않았다. 따라서 “전체 시각 관계 재해석 완료”가 아니다.
- frame-005는 후보를 골라도 맞는 작업문서가 없어 보류가 정상이다. 성공 시연을 위한 별도 `synthetic_demo` 작업문서는 만들지 않았다.
- 작성 주체 kind는 선언값이며 사용자 인증·서명은 없다. 묶음 전체를 일관되게 다시 만든 위조는 탐지 범위 밖이다.
- 영상에 수정 장면을 넣을지, 입력 화면을 둘지는 결정하지 않았다. 브라우저 시각 검수는 하지 않았다.
- 모든 결과는 `application_authorized=false`, `execution_authorized=false`, `demo_complete=false`다. 실제 용접 장비로 보내지 않는다.
