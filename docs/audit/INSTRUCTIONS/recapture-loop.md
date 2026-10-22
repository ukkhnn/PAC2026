# 지시서 — 재촬영(recapture) 루프 복구

대상: 진단 A·B 항목. 이 지시서의 모든 항목은 `(claude 제안사항)`이며 실행 여부는 별도 판단 대상이다.

## 실행 후속 상태 (2026-10-22)

아래 배경·작업·완료 기준은 10월 14일 제안 원문이다. 10월 15일 8파일 병합·재촬영 사유 정정을 완료했고, 16일 `requires_recapture` 예외를 유지한 기록 브리지·CLI를 추가했다. 루프의 `continue`가 판독 결정을 대체하지 않으며 통합 실행은 `needs_review`·전달 `blocked`로 끝난다. 18일 대시보드 읽기 어댑터·검증 연결을 구현했고 fixture 3개를 포함한 당시 전체 회귀 164개가 통과했다. 실제 GPU 루프·실제 결과의 화면 적재/검수·후속 문서/전달 연결은 남아 있다. 파일별 병합 대조와 현재 계약은 [재촬영 실행 안내](../../runs/RECAPTURE_LOOP.md)를 따른다.

## 배경

- 재촬영 루프 구현 8파일이 `dev`에 없다. `output/recapture-handoff-20261010/`(handoff ZIP·patch·code)와 별도 worktree에만 남아 있다.
- 제품 코드의 유일한 재촬영 지점은 `src/contextweld/weld_pipeline.py`의 `capture_binding()`으로, `requires_recapture=True`면 `ValueError`만 던진다.
- 실제 실행 원문에서 A·B 모두 `requires_recapture=false`였고, B 저장 사유는 반사가 아니라 A 오독(`BISB3015`)의 정확조회 실패였다.

## 작업 (claude 제안사항)

1. **8파일 병합** — `output/recapture-handoff-20261010/code/` 아래의 신규 파일을 현재 `dev` 구조에 맞춰 반영한다. 단, 현재 `dev`에는 `weld_pipeline.py`·`robot_input.py` 등 10-10 이후 변경이 누적돼 있으므로, handoff 시점(HEAD `9451321`)과의 충돌을 파일별로 확인한다.
   - `src/contextweld/recapture_inputs.py`, `recapture_inference.py`, `recapture_loop.py`
   - `scripts/run/run_recapture_loop.py`(현재 `scripts/`는 `run/` 하위로 재구성됨)
   - `tests/test_recapture_inputs.py`, `test_recapture_inference.py`, `test_recapture_loop.py`
   - `docs/runs/RECAPTURE_LOOP.md`(현재 `docs/`는 역할별 하위 폴더로 재구성됨)
2. **재촬영 트리거 사유 정정** — 현재 문서·발표가 암시하는 "반사 감지 → 재촬영" 서사를 실제와 맞춘다. 실제 B 저장 사유는 "A 판독의 정확조회(유일 연결) 실패"다. 반사 감지는 트리거로 실행된 적이 없다.
3. **`capture_binding` 연동 결정** — `requires_recapture=True`를 받았을 때 현재처럼 예외만 던질지, 재촬영 루프를 호출할지 연결 방식을 정한다. 실제 루프를 호출할 경우 `physical_movement_triggered`가 참이 되는 시점과 실제 팔 제어 범위 제외를 함께 기록한다.
4. **인계 기록 갱신** — `.cowork/`의 MIGRATION·CURRENT_TASK·STATUS에 10-11 이후 커밋과 `docs/` 재구성, 그리고 이 지시서 실행 결과를 반영한다.

## 완료 기준 (claude 제안사항)

- 8파일이 `dev`에 추적되고, 기존 테스트(현재 로컬 108개)에 신규 3개 테스트가 포함돼 통과한다.
- 재촬영 트리거의 실제 사유가 문서에 반영돼, "반사 감지 성공"으로 주장하는 문구가 남지 않는다.
- handoff 원본(ZIP·patch)은 보존하며, 병합본과의 해시 대조 기록을 남긴다.
