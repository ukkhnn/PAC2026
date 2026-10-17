# 진단·처방서 — 종단(end-to-end) 연결의 현재 상태와 복구 계획

진단 기준일: 2026-10-14 · 후속 현황 갱신일: 2026-10-17(개발 반영 2026-10-16). 대상 저장소: `dev`.

1~4절은 진단 당시 사실과 제안을 보존한다. 현재 실행 상태는 [5절](#5-실행-후속-현황-2026-10-17)을 먼저 확인한다.

이 문서는 두 부분으로 나뉜다.

- **진단**: 코드·산출물·실행 원문·Git 이력을 대조해 확인한 **사실**.
- **처방**: 각 진단을 복구하기 위한 **제안**이다. 처방 항목은 전부 `(claude 제안사항)`으로 표시하며, 실행 여부와 우선순위는 별도 판단 대상이다. 코드로 구현된 사실이 아니다.

지시서는 [INSTRUCTIONS/](./INSTRUCTIONS/)에 영역별로 분리했다. 각 지시서의 항목 역시 제안이다.

---

## 1. 요약

데모는 "실제 마킹 판독 → 문서 조회 → 공통 명세 → 제조사 변환 → 모의 수신"이라는 종단 흐름을 목표로 하지만, 현재 저장소(`dev`)에는 **흐름의 일부가 존재하지 않고**, 존재하는 부분도 **문서·발표가 말하는 동작과 실제 코드·실행 원문이 어긋나는 지점**이 여럿 있다. 가장 큰 축은 다음 셋이다.

1. **재촬영 루프가 `dev`에 없다.** 구현 파일 8개가 별도 worktree와 handoff ZIP에만 남아 있고, 제품 코드의 재촬영 경로는 `requires_recapture`가 참이면 예외만 던진다.
2. **"빛반사 감지 → 재촬영"이라는 서사가 실제와 다르다.** 실제 A/B 원문은 모두 `requires_recapture=false`였고, B를 저장한 사유는 반사가 아니라 A의 판독 오독으로 인한 정확조회 실패였다.
3. **시연 기준값 자체가 실제 라벨이 아니라 모델 오독에서 파생됐다.** 공개 사진의 실제 라벨은 `B1Sb30N-15`인데, 시연 작업지시·도면·Isaac 장면 마킹의 기준 문자열은 여기서 파생된 `BISB30N-15`다. A 프레임은 이를 다시 `BISB3015`로 오독했다.

이 외에 OCR 실행·판단 불일치, 서버 산출물 유실, 대시보드 목업, 번들 검증의 허점이 뒤따른다.

---

## 2. 진단 (확인된 사실)

### A. 재촬영(recapture) 루프가 제품 코드에 없다

- 신규 8파일이 `dev`에 존재하지 않는다. `git ls-files`에서 `recapture` 관련 파일이 없고, `src/contextweld/`에도 없다.
  - `src/contextweld/recapture_inputs.py`, `recapture_inference.py`, `recapture_loop.py`
  - `scripts/run_recapture_loop.py`
  - `tests/test_recapture_inputs.py`, `test_recapture_inference.py`, `test_recapture_loop.py`
  - `docs/RECAPTURE_LOOP.md`
- 실제 위치는 `output/recapture-handoff-20261010/`(handoff ZIP·patch·code)와 별도 managed worktree(`~/.codex/worktrees/recapture-loop/PAC2026`)뿐이다.
- 제품 코드의 유일한 재촬영 연관 지점은 `src/contextweld/weld_pipeline.py`의 `capture_binding()`로, `read['quality']['requires_recapture']`가 참이면 `ValueError('재관측 뒤에도 판독 미확정')`를 던질 뿐 재촬영을 수행하지 않는다.
- 로컬 인계 기록(`.cowork/`의 MIGRATION·CURRENT_TASK·STATUS)은 2026-10-10에 멈춰 있어, 10-11 이후의 커밋과 `docs/` 폴더 재구성이 반영돼 있지 않다.

### B. "빛반사 감지 → 재촬영" 서사와 실제 제어 흐름이 다르다

- 실제 실행 원문(`output/weld-pipeline-20261010/shipyard-connected-01-capture/`)에서 A·B 두 프레임 모두 VLM이 `requires_recapture=false`로 답했다.
- B를 추가로 저장한 실제 사유는 반사가 아니라, **A 프레임의 판독 오독**(`BISB3015`)이 작업지시의 `part_id`와 정확히 일치하지 않아 유일 연결(정확조회)에 실패했기 때문이다.
- 즉 데모 문서와 발표 자료가 암시하는 "반사로 마킹이 가려짐 → 재촬영 → 복구" 경로는 실제로는 실행되지 않았다. 재촬영 분기 자체가 `dev`에 없고(A), 반사 감지가 트리거가 된 적도 없다.

### C. 시연 기준값이 실제 라벨이 아니라 모델 오독에서 파생됐다

- 공개 사진의 실제 라벨은 `B1Sb30N-15`다. A 프레임에서 VLM이 `BISB3015`로 오독했고, 시연 문서의 기준 문자열은 `BISB30N-15`다.
- `configs/document_demo/work_orders.json`은 `part_id: "BISB30N-15"`로 고정돼 있고, 그 `provenance` 필드가 스스로 "실제 OCR 출력 문자열을 불투명 식별자로 사용해 직접 작성한 문서 연결 시연. 사진의 실제 작업지시나 정답을 뜻하지 않음"이라고 명시한다.
- `configs/shipyard_pipeline/drawing.json`도 `part_id: "BISB30N-15"`, `joint_marking_map: {"J01": "JOINT-DEMO-01"}`로 고정돼 있다.
- Isaac 장면 `live-03`의 수기 마킹 문자열도 같은 파생 값이다. 따라서 "정확 연결"로 보이는 종단 실행도 실제 라벨 기준이 아니라 오독에서 파생된 기준을 사용한다.

### D. OCR은 실행되지만 통합 판단에 쓰이지 않는다

- `src/contextweld/recognition.py`는 PP-OCRv6 문자 인식을 실제로 실행하고(`normalize_ocr`, `predict` 경로), `src/contextweld/workflow.py`는 OCR/VLM 불일치를 `ocr_vlm_disagreement`로 남긴다.
- 그러나 통합 경로 `weld_pipeline.capture_binding()`은 `read['markings']`(VLM 결과)만 읽는다. OCR 결과는 마킹 연결 판단에 쓰이지 않는다.
- 실제 B 프레임에서 OCR은 `J01`을 `JOD`로 읽었지만, 통합 파이프라인은 VLM의 `J01`만 사용했다. 그런데도 검증 기록에는 `observation_consensus`(OCR·VLM 합의)가 확인 항목처럼 기재되어 실제 동작과 다르다.
- 별도 모듈이었던 `src/contextweld/ocr.py` 소스는 삭제돼 `git`에 추적되지 않고(`__pycache__/ocr.cpython-311.pyc`만 남음), OCR 로직은 `recognition.py`에 인라인으로 남아 있다.

### E. 서버 산출물이 유실됐다 (저장 전 종료)

- 서버(`/workspace`)에만 존재하고 로컬 저장소·GitHub에 없는 산출물이 다수다. 예: 모델 가중치(`/workspace/models/contextweld/*`), `steel-ocr` 원본(`/workspace/data-import/steel-ocr`), `pac-handoffs`/`pac-backups`, `output/pipeline-v2-20261010`, `output/context-ablation-20261010` 등.
- `dev`의 추적 파일은 HEAD `9451321` 시점 185개에서 이후 커밋으로 확장됐지만, 서버 실행 결과물 상당수가 로컬에 내려오지 않았다. 정확한 유실 목록은 서버 접근 재개 시 재대조해야 한다.

### F. 관리자 대시보드의 "성공" 상태가 목업으로 채워져 있다

- 대시보드 preview의 run 데이터 중 `run_kind`이 `presentation_scenario`인 항목(예: `shipyard-recapture.js`)은 `run_outcome`이 미리 정해진 시나리오 값으로 채워져 있다.
- 실제 종단 실행(`shipyard-connected-01.js`, `run_kind: weld_pipeline`)은 `succeeded`를 동적으로 기록했지만, 화면을 먼저 보여주기 위한 시나리오 데이터는 모델 원문·추론 시간·ACK를 만들지 않은 채 완성 상태로 표시된다(관련 기록: `.cowork/MIGRATION.md` 2026-10-10 항목).

### G. 번들 검증에 무결성 허점이 있다

- `weld_pipeline.verify_pipeline()`은 `checksums.json`에 나열된 파일만 재해시한다. 번들에 새 파일을 추가해도 검증이 통과한다(추가 파일 미탐지).
- 한쪽 제조사 수신이 거절되는 부분 전달 시 전체 `run_outcome`/전달 상태의 표기가 실제와 일치하는지 별도 확인이 필요하다.

---

## 3. 처방 (claude 제안사항)

아래는 우선순위를 매긴 제안이며, 항목마다 해당 지시서를 연결한다. 실행 여부는 별도 결정 대상이다.

| 우선순위 | 처방 요약 | 지시서 |
|---|---|---|
| P0 | 재촬영 루프 8파일을 `dev`에 병합하고, 재촬영 트리거의 실제 사유(정확조회 실패)를 문서에 반영 | [recapture-loop](./INSTRUCTIONS/recapture-loop.md) |
| P0 | 라벨 파생 계보 정정: 시연 기준값이 실제 라벨이 아닌 오독 파생임을 명시하고, 실제 라벨 기준으로 재기록 | [recognition-and-binding](./INSTRUCTIONS/recognition-and-binding.md) |
| P1 | OCR 결과를 통합 판단에 연결하거나, `observation_consensus` 기재를 실제 동작에 맞게 정정 | [recognition-and-binding](./INSTRUCTIONS/recognition-and-binding.md) |
| P1 | 서버 유실물 목록을 재대조하고 복구 가능한 산출물을 회수 | [server-artifact-recovery](./INSTRUCTIONS/server-artifact-recovery.md) |
| P2 | 대시보드 시나리오 목업을 실제 실행 기록과 구분해 표시 | [dashboard-mock-data](./INSTRUCTIONS/dashboard-mock-data.md) |
| P2 | 번들 검증이 추가·변조 파일을 감지하도록 보강 | [verification-integrity](./INSTRUCTIONS/verification-integrity.md) |

---

## 4. 처방의 전제와 경계

- 이 문서의 진단은 2026-10-14 시점의 로컬·Git 이력·보존 원문 대조로 확정한 사실이다. 서버 접근 재개 시 E 항목의 유실 목록은 다시 갱신해야 한다.
- 처방을 실행해도 실제 로봇 팔 제어·아크 실행·좌표 경로 생성은 범위에 없다(기존 범위 유지).
- "모델의 반사 진단 성공"으로 주장하지 않는다. 실제 반사 감지→재촬영 경로는 실행된 적이 없다(B).
- 처방 실행은 별도 요청이며, 이 문서 작성 자체는 코드 변경을 포함하지 않는다.


## 5. 실행 후속 현황 (2026-10-17)

아래는 제안의 추가 목록이 아니라 10월 15~16일 코드·실행 기록을 반영한 현황이다. 감사 우선순위 P0/P1/P2는 데모 스펙의 P0~P5 단계와 별개다.

| 진단 | 반영된 내용 | 남은 범위·근거 |
|---|---|---|
| A 재촬영 미병합 | 10월 15일 8파일 dev 병합, 16일 통합 기록 브리지·CLI·6개 테스트 추가 | 실제 GPU 루프·대시보드 어댑터·문서/전달 재개는 미완료. [RECAPTURE_LOOP](../runs/RECAPTURE_LOOP.md) |
| B 재촬영 서사 | B 선택 사유를 A의 정확 조회 실패로 정정. `requires_recapture` 예외는 유지 | 실제 반사 감지 성공·요청에 따른 팔 이동으로 주장하지 않음. [WELD_PIPELINE](../runs/WELD_PIPELINE.md) |
| C 라벨 계보 | 실제 `B1Sb30N-15` → 오독 `BISb30N-15` → 정규화 `BISB30N-15`의 계보를 configs·문서에 명시 | 파생 시연 기준값 유지, 과거 묶음 재작성 없음. [RECOGNITION_AND_BINDING](../runs/RECOGNITION_AND_BINDING.md) |
| D OCR 경로 | 검증 항목을 실제 VLM 단독 판독·OCR 원문 보존 경로로 정정 | OCR 합의 판독으로 동작을 바꾼 것이 아님. [RECOGNITION_AND_BINDING](../runs/RECOGNITION_AND_BINDING.md) |
| E 서버 산출물 | 로컬 보존 사본 5건 해시 일치, 회수 후보 판정·기대 해시 출처·서버 명령 준비 | 서버 실물 유무·회수 가능성은 Runpod 재개 후 재대조. 전체 유실 확정이나 복구 완료로 보지 않음. [로컬 준비](INSTRUCTIONS/server-artifact-recovery-local-prep.md) |
| F 관리자 목업 | 목업 칩·배너·실제 실행 링크, 통합/시연 3개 roots 등록 | 실제 재촬영 결과 적재·브라우저 전체 검수 미완료. [ADMIN_DASHBOARD](../runs/ADMIN_DASHBOARD.md) |
| G 번들 무결성 | 추가 파일 거절, 부분 전달 `partial`·`delivery_failures` 기록 | 과거 해시 누락·재계산 불일치는 보존. 관리자 의미 검사에 허용된 실패 13건이 남음. [검증 해석](../runs/ADMIN_DASHBOARD.md#14-검증-결과를-읽는-방법) |

10월 16일 로컬 회귀 테스트 161개 통과, 관리자 사본·격리 재빌드의 파일 검사 통과 기록을 반영했다. 이번 문서 갱신에서 모델 추론·서버 복구를 새로 수행한 것은 아니다.
