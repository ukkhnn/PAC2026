# 실제 관측에서 문서 조건과 모의 수신까지

기준일: **2026-10-10**. 실행 당시 [데모 스펙](../plan/DEMO_SPEC.md) v1.4, [문서 적용 계획](../plan/DOCUMENT_APPLICATION_PLAN.md) v1.3 기준의 **문서 검토용 부분 실행**이다. 데모 스펙은 이후 v1.5가 됐고 이 묶음은 생산 당시의 `demo-1.4+ocr-1.2+documents-1.3`을 그대로 기록한다. 실제 저장 관측 → 모사 작업지시·도면 → 공개 WPS의 필드·원문 위치 → 필수값·충돌 검사 → 실제 loopback HTTP 모의 수신을 연결했다.

A/B 촬영·재촬영·사용자 수정/재검토는 아직 이 실행에 포함되지 않는다. 저장된 문서 실행은 [오프라인 조회 HTML](DOCUMENT_REVIEW_VIEWER.md)로 내보낼 수 있으며 전체 관리자 재생 기능은 미완료다. 모의 ACK는 문서 범위값의 수신·형식 확인이며 사진의 실제 작업이나 용접 적용 승인, 용접 실행 성공을 뜻하지 않는다.

## 1. 실제 입력과 모사 입력

| 항목 | 이번 입력 | 구분 |
|---|---|---|
| 원관측 | `steel-batch-20261010-02`의 frame-007, OCR `BISb30N-15`와 겹치는 VLM 텍스트가 일치 | 이전 Runpod 실제 모델 출력 재사용. 새 모델 호출 0회 |
| 후보 처리 | 하이픈으로 나뉜 영숫자 식별자, 양끝 공백 제거·대문자 정규화 | `I/1`, `S/5`, `O/0` 교정 없음. 다른 관측 후보도 버리지 않음 |
| 작업지시 | `WO-DEMO-015`, `PAC-DEMO/BLOCK-DEMO`, `BISB30N-15`, 개정 1 | 직접 작성한 시연 자료. 사진의 실제 업무·정답이 아님 |
| 도면 | `DRAWING-DEMO-015` 개정 1, `JOINT-DEMO-01` | [구조화 도면](../../configs/document_demo/drawing.json)과 [설명용 그림](../../configs/document_demo/drawing.svg). 사진 형상 복원·이음 검출이 아님 |
| WPS | LANL `3501-xxxx-1`, 원문 헤더 REV. NO. 1, 대표층 1 | [원문 필드 전사](../../data/knowledge/lanl-wps-3501-reviewed.json). 사람의 공정 승인 아님 |
| 출력 | `document-range-review.v1` | [문서 범위 검토용 프로파일](../../configs/document_demo/target_profile.json), 실기 제어 지원 아님 |

관측을 확인한 뒤 연결 예제를 만들기 위해 모사 작업지시를 작성했다. 따라서 이 사례는 실제 작업지시 매칭 정확도의 독립 평가가 아니다. 사진의 부재가 실제로 어떤 식별자·재질·두께·접합부인지는 이 실행으로 확정하지 않는다. 영상에서 확인되지 않은 이음 ID는 `fixture` 출처의 도면 참조로 남긴다.

실행 입력은 [scenario.json](../../configs/document_demo/scenario.json)과 [work_orders.json](../../configs/document_demo/work_orders.json)이다. 원래 인식 묶음과 원문을 변경하지 않고, 새 실행에 입력 스냅샷과 원래 모델 출력을 포함한다. 공개 사진 bootstrap의 모델 설정과 생성 원문은 [인식 실행 안내](RUNPOD_INFERENCE.md)를 따른다.

## 2. WPS 필드와 검증 범위

확보한 원문 PDF의 두 페이지를 렌더링하고 선택한 필드·머리글 **38개 영역**을 추출 텍스트와 대조했다. 구조화 파일은 원문 해시·개정·페이지·bbox·표 행/열, 원문값·정규화값을 함께 보존한다. 검수는 `agent_text_and_render_crosscheck`, `human_reviewed=false`다.

| 전달 필드 | 값 | 원문 위치 |
|---|---|---|
| 공정 | `FCAW` | 2쪽 용접층 조건표, 대표층 1 |
| 전류 | `130–250 A` | 같은 행의 Amps 열 |
| 전압 | `24–28 V` | 같은 행의 Volts 열 |
| 이동속도 | `7–18 in/min` | 같은 행의 Travel/ipm 열. 단위 약어만 정규화 |

원문: [LANL WPS 3501-xxxx-1](https://engstandards.lanl.gov/esm/welding/welding_specs/3501-xxxx-1.pdf). 로컬 확보본 SHA-256은 `608db44080beab287dc1cd7e5a0b44744d63b0c51058e7ea159503af5b8dae10`이다. 1쪽의 별도 130 A/24 V 요약값은 보존하지만 새 단일 설정값으로 선택하지 않는다.

이번 검증은 관측 후보 일치, 작업 범위·유효시점·최신 개정, 작업지시/도면/참조 WPS 일치, 모사 문서 간 공정·재질 등의 일치, 필수 범위값·단위·근거 참조를 검사한다. WPS 원문 해시는 실행 전에 확인하며 취소·만료된 최신 작업지시 대신 이전 지시를 되살리지 않는다.

**현장 적용은 미확인으로 남긴다.** 실제 사진의 물성, 단위가 명시되지 않은 두께 필드, GWS/WFP·프로젝트 승인, 반자동 절차의 로봇 적용성과 운전 조합은 확정하지 않는다. 대표층 주석과 열입력 상한을 포함한 제약 8개도 명령에 함께 보낸다. 범위의 임의 중앙값이나 전류·전압·속도의 특정 조합을 생성하지 않는다. `application_authorized=false`, `execution_authorized=false`, `range_combination_validated=false`를 유지한다.

WPS 숫자는 검수된 구조화 행에서 정확히 조회한다. 기존 BM25는 같은 원문 해시의 보조 문맥을 반환한다. 과거 색인의 미확인 `revision=null`은 그대로 두고, 새 전사본의 개정 1과 원문 해시가 같음을 별도 기록한다. 검색 결과를 새 모델 입력으로 넣거나 모델이 새로 인용했다고 표시하지 않는다.

## 3. 실행

Runpod의 기존 `/workspace/venvs/contextweld-inference/bin/python`을 사용했다. 이 후속 연결은 Python 표준 라이브러리로 실행되며 GPU·모델 재로딩·새 패키지 설치가 필요하지 않다. 사전에 [자료 준비](../setup/RUNPOD_DATA_SETUP.md)와 [실제 인식·색인 생성](RUNPOD_INFERENCE.md)이 완료되어 있어야 한다. 원본/색인/기존 실행 묶음은 일반 Git에 포함되지 않는다.

저장소 루트에서 실행한다. 예시 run ID를 이미 사용했다면 새 이름으로 바꾼다.

```sh
/workspace/venvs/contextweld-inference/bin/python scripts/run/run_document_demo.py \
  --recognition-bundle output/recognition/run_steel-batch-20261010-02 \
  --document-index output/document-rag/server-v1/index.json \
  --output-root output/document-demo \
  --run-id document-normal-demo-001 \
  --case normal --deliver
```

`--deliver`가 있을 때만 검사 통과 후 `127.0.0.1`의 임시 포트에서 모의 수신기를 열고 HTTP 요청을 보낸다. 없으면 명세·검증 결과까지만 저장한다. 수신기는 실행 종료 시 닫히며 외부 주소로 전달하지 않는다. 응답 대기 한도는 5초다.

`--case`는 `normal`, `missing`, `conflict`, `revision-mismatch`, `observation-conflict`를 지원한다. 사례별로 새 run ID를 쓴다. `missing/conflict/revision-mismatch`는 선언된 결함을 실행용 복사본에만 주입하며 입력 시나리오와 주입 내역을 기록한다. `observation-conflict`는 실제 frame-005의 다른 두 문자열을 그대로 재사용한다. 결과 상태는 시나리오 이름이 아니라 실제 검사로 결정한다.

서버 없이 내려받은 묶음을 검사할 수 있다. 이 명령은 추론·송신을 호출하지 않는다.

```sh
python3 scripts/verify/verify_document_demo.py \
  output/document-demo/run_document-normal-demo-001
```

테스트는 저장소 루트에서 실행한다. 모의 HTTP 검증을 위해 localhost 소켓을 열 수 있어야 한다.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 4. Runpod 실제 확인 결과

최초 연결 실행의 코드 기준은 `dev/9bcb89a`와 당시 새 구현 파일들의 해시다. 각 묶음의 `inputs/environment.json`에 실제 코드 해시·Git 상태·환경을 기록했다.

| 사례 / run ID 끝부분 | 실제 검사 | 실행 결과 | 전달 |
|---|---|---|---|
| `document-normal-server-01` | 관측 일치·문서/개정·4개 필드 통과 | `succeeded` | HTTP 200 / `received` |
| `document-missing-server-01` | 전압 필수값 누락 | `needs_review` | `blocked`, 명령·수신 기록 없음 |
| `document-conflict-server-01` | 작업지시 FCAW / 도면 GMAW 충돌 | `needs_review` | `blocked`, 명령·수신 기록 없음 |
| `document-revision-mismatch-server-01` | 참조 개정 2 / 확보 개정 1 | `needs_review` | `blocked`, 다른 개정으로 대체 없음 |
| `document-observation-conflict-server-01` | OCR `BISb30N-29` / VLM `B1Sb3ON-29` | `needs_review` | `blocked`, 문서로 오독 교정 없음 |

로컬 Python 3.11과 Runpod Python 3.12에서 **각각 59개 테스트**가 통과했다. 정상 수신뿐 아니라 필수값·단위 오류 거절, 같은 명령의 중복과 본문 충돌, 다른 프로젝트의 동일 작업번호, 취소 지시, 기록 변조, 통신 실패 시 원문 보존을 확인했다. 시험용 합성 입력과 위 실제 관측 재사용 실행은 구분한다.

다섯 실행을 로컬로 복사한 뒤 파일 해시·원관측·문서 명세 재계산·명령·수신 로그의 연결을 확인했다. 정상 묶음은 196개 해시 대상 파일·9사건, 보류 묶음은 각각 193개 파일·7사건이다. `checksums.json` 자체는 해시 목록에서 제외한다.

## 5. 산출물과 다음 연결

| 경로 | 내용 |
|---|---|
| `output/document-demo-20261010/server/run_document-*-server-01/` | 다섯 실제 실행의 서버·로컬 보존본 |
| `results/work-spec.json` | 필드별 값·단위·근거, 검증 문제, 현장 적용 미확인 항목 |
| `results/matching.json` | 선택한 작업지시와 제외 이유 |
| `evidence/wps-reviewed.json`, `evidence/retrieval.json` | 전사 필드/위치·제약, 원문 검색 문맥 |
| `commands/command.json`, `transport.json`, `receiver.jsonl` | 정상 실행의 실제 전송 본문·ACK·수신기 원본 기록 |
| `inputs/recognition/` | 변경하지 않은 이전 실제 인식 묶음의 사본 |
| `output/document-demo-20261010/server-results.json` | 로컬 오프라인 검증 결과 요약 |
| `output/document-demo-20261010/source-review/` | PDF 렌더와 전사 영역 대조 기록 |

묶음 스키마는 `document-demo-bundle.v1`, `run_kind=document_demo`, `capture_mode=public_dataset`, `evaluation_scope=document_review`다. 기존 bootstrap과 전체 `scenario`, 사용자 수정 `review`를 구분한다. `succeeded`는 요청한 문서 검토·모의 수신 범위만의 성공이다. 모든 사례에서 `demo_complete=false`이며 P2 전체·A/B·수정 재검토·관리자 화면 완료를 뜻하지 않는다.

필요한 관측 원문과 문서 발췌·필드·페이지 참조는 묶음에 있고 WPS 전체 PDF는 포함하지 않는다. 원문 재배포 허가가 확인되지 않았다는 등록 정보를 유지한다. 해시·파일 누락과 기록 불일치는 오류로 처리하고 완료된 묶음을 덮어쓰지 않는다.

이 묶음의 관측·근거·명령·ACK를 읽는 [최소 오프라인 조회](DOCUMENT_REVIEW_VIEWER.md)를 추가했다. 정상·누락·관측 충돌 세 묶음의 내보내기·표시 내용·원본 불변을 확인했으며 브라우저 시각 검수는 미완료다. 다음 연결점은 A/B 입력과 실제 인식에 따른 재촬영 분기다. 사용자 수정·명시적 재검토는 이 묶음들을 부모로 하는 별도 `review-bundle.v1` 실행으로 [구현했다](EXPLICIT_REVIEW.md). 이 문서의 묶음과 계약은 바꾸지 않았다. 실제 장면용 문서 적용성은 별도 범위로 남는다.

2026-10-10 재검토 작업 중 서버의 보류 묶음 4개(`missing`, `conflict`, `revision-mismatch`, `observation-conflict`)에서 빈 `commands/` 디렉토리가 사라져 `verify_document_demo.py`가 `FileNotFoundError`로 실패하는 것을 확인했다. 디렉토리 수정 시각은 이전 Git 정합의 untracked 정리 시점(2026-10-09T20:33:5xZ)이며 파일 목록과 해시는 그대로다. 묶음은 고치지 않고 검증기가 없는 `commands/`를 빈 디렉토리와 같은 “명령 없음”으로 보도록 수정했다. 이후 다섯 묶음 모두 다시 검증을 통과한다.
