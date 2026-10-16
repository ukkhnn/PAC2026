# 지시서 — 서버 유실물 복구

대상: 진단 E 항목. 이 지시서의 모든 항목은 `(claude 제안사항)`이며 실행 여부는 별도 판단 대상이다.

## 배경

서버(`/workspace`)에만 존재하고 로컬 저장소·GitHub에 없는 산출물이 다수다. 서버 종료 전에 내려받지 못해 유실 위험이 있다. 로컬·Git 이력으로는 정확한 목록을 확정할 수 없고, 서버 접근이 재개돼야 재대조가 가능하다.

## 작업 (claude 제안사항)

1. **서버 재접근 시 재대조** — `/workspace` 아래에서 로컬·GitHub에 없는 경로를 전수 대조한다. 이전에 확인된 후보는 다음과 같다.
   - 모델 가중치: `/workspace/models/contextweld/*`(Qwen3-VL-8B, PP-OCRv6 det/rec 등)
   - 원본 데이터: `/workspace/data-import/steel-ocr`
   - 인계·백업: `/workspace/pac-handoffs`, `/workspace/pac-backups`
   - 실행 산출물: `output/pipeline-v2-20261010`, `output/context-ablation-20261010`, `output/explicit-review-20261010`, `output/isaac-*` 등
2. **복구 가능 항목 우선 회수** — 모델 가중치는 재다운로드 가능한지(고정 revision·SHA), 산출물은 재생성 가능한지(입력·설정 보존 여부)를 기준으로 복구 우선순위를 정한다. 재생성 불가능하고 유일한 산출물을 우선 내려받는다.
3. **해시 대조 기록** — 회수한 파일은 기존 기록(`docs/sources/DATA_MODEL_PROVENANCE.md`, `configs/data_model_provenance.json`)과 SHA-256을 대조하고, 새로 회수한 항목은 출처 기록에 추가한다.

## 완료 기준 (claude 제안사항)

- 서버 접근 재개 후 유실·복구 목록이 문서화되고, 복구된 파일의 SHA가 기록된다.
- "서버에만 존재"하던 산출물이 재생성 가능·불가능으로 구분돼, 재생성 불가능한 항목이 우선 보존된다.

## 로컬 준비 완료 (2026-10-16)

서버 접근 재개 전 로컬에서 가능한 선행 작업을 완료하고
[server-artifact-recovery-local-prep.md](server-artifact-recovery-local-prep.md)에 기록했다.

- 로컬 보존 사본 무결성 재계산 전부 통과(365 + 1,339 + 21 + 150 + 141 + 1 파일). 도구는
  `scripts/verify/recheck_preservation_copies.py`, 리포트는 `output/p1-local-prep-recheck-20261016.json`(미추적).
- 서버 전용 후보 판정표 8경로 확정(회수 우선순위: pac-handoffs·pac-backups·explicit-review 먼저, 모델은 HF
  고정 revision 재다운로드 가능 확인).
- 기대 해시 대조 목록 v0.1(출처 지도)과 서버 접속 시 명령 초안을 보충 문서 3·4절에 정리.
- 서버 스냅샷 19파일 재분류: 일치 4 / 변경 7 / 이동+변경 8 / 유실 0. 변경분은 전부 추적 커밋으로 설명 가능.

남은 것은 서버 접근 재개 후의 1번(재대조)·2번(우선 회수)·3번(해시 대조 기록) 실행이다. 이때부터
실물 확인이 가능하다.
