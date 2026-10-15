# 인식과 연결 — 라벨 계보·판독 경로 정정

기준일: **2026-10-15**. 진단·처방 P0-2([지시서](../audit/INSTRUCTIONS/recognition-and-binding.md))의 실행 기록이다. 시연 기준값 `BISB30N-15`의 계보를 명시하고, 판독·연결 경로의 표기를 실제 구현과 일치하도록 정정했다. 동작 변경은 없다.

## 라벨 계보

| 단계 | 문자열 | 출처 |
|---|---|---|
| 실제 라벨 표기 | `B1Sb30N-15` | 공개 사진의 실제 표기 |
| 저장된 OCR/VLM 원문 | `BISb30N-15` | `frame-007` 관측 원문(오독: `1`→`I`, 소문자 `b`) |
| 시연 기준값 | `BISB30N-15` | 위 원문의 대문자 정규화 파생 문자열. 시연 문서·장면 합성 표기의 입력 |
| A 프레임 판독 | `BISB3015` | `live-03` A의 오독. 작업지시 정확 조회 실패 → 저장 B 선택 |
| B 프레임 판독 | `BISB30N-15` | `live-03` B. 기준값과 일치해 `WO-DEMO-015` 연결 |

`BISB30N-15`는 배포자 정답으로 교정한 값이 아니라 저장된 실제 인식 원문의 정규화 파생값이며, 문서 연결의 불투명 키로 사용한다. A/B 판독 원문과 계보는 실행 묶음과 아래 출처에 보존한다.

## 판독·연결 경로 정정

- **VLM 단독 판독**: `capture_binding()`은 `read['markings']`(VLM)만으로 판독 결정을 내린다. OCR은 실행되지만 원문 보존 용도이며 판단에 사용하지 않는다. `weld_pipeline.py` docstring과 `OCR_PIPELINE_SPEC.md` 2절에 이 구조를 의도된 구현으로 문서화했다.
- **`observation_consensus` 표기 정정**: `workflow.py`가 기록하는 `validation.checks`의 첫 항목이 OCR·VLM 합의를 암시했으나 실제로 그런 게이트는 없으므로 `marking_observation_evidence_recorded`로 정정했다. **과거 실행 묶음·대시보드 사본의 기존 기재는 역사 기록으로 보존하며 재작성하지 않는다.**
- **잔여 파일 제거**: 삭제된 `ocr.py`의 잔여 `src/contextweld/__pycache__/ocr.cpython-311.pyc`를 제거했다. OCR 로직이 `recognition.py`에 인라인으로 있는 것은 의도된 구조다.
- **`requires_recapture` 예외 유지**: `capture_binding()`의 예외 동작은 유지한다. 결정과 사유는 [WELD_PIPELINE](WELD_PIPELINE.md)의 "부재 표기 계보와 재촬영 결정" 참조.

## 출처 갱신

계보를 명시하도록 다음 출처를 보강했다. 값·구조 변경은 없다.

| 파일 | 갱신 |
|---|---|
| `configs/document_demo/work_orders.json` | `provenance`에 실제 라벨→오독→정규화 계보 명시 |
| `configs/document_demo/drawing.json`, `configs/shipyard_pipeline/drawing.json` | `provenance`에 `part_id` 파생 계보 명시 |
| `configs/document_demo/drawing.svg` | 하단에 계보 한 줄 추가 |
| `configs/isaac_scene/night_welding.json`, `configs/isaac_scene/shipyard_handwriting.json` | `marking.source`에 파생 기준값 계보 명시 |
| `docs/runs/WELD_PIPELINE.md` | "부재 표기 계보와 재촬영 결정" 절 추가 |
| `docs/runs/ISAAC_SHIPYARD_SCENE.md`, `docs/sources/DATA_MODEL_PROVENANCE.md` | 계보 한 문장 추가 |

## 완료 확인

- 로컬 회귀: 전체 테스트 통과(기존 108 + 신규 recapture 43).
- 과거 실행 묶음(`output/` 미추적)과 서버 자료는 재작성하지 않았다. 서버 유실물 대조는 Runpod 접근 재개 시 수행한다.
