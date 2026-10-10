# PV2 → 관리자 대시보드 인계

대시보드 담당이 PV2 실제 산출물을 읽을 때 쓸 경로·형식·검증 방법·표시 한계를 정리한다. PV2는 대시보드·HTML exporter·제품 계약을 수정하지 않았다.

## 실제 완료 산출물

| 항목 | 경로 | 형식 | 비고 |
|---|---|---|---|
| 새 인식 실행 | `output/pipeline-v2-20261010/runs/e1/run_pv2-e1-quick-val01/` | 제품 `bootstrap-bundle.v1` + `recognition.v1` 결과 | run ID `pv2-e1-quick-val01`, 공개 사진 8장, 제품 CLI 수정 없음 |
| 실행 명령·시간 | `output/pipeline-v2-20261010/runs/e1/quick-ledger.json`, `runs/e1/logs/pv2-e1-quick-val01.{log,wrapper.json}` | JSON / 텍스트 | wrapper에 CUDA 최대 메모리 |
| 채점 결과 | `output/pipeline-v2-20261010/scores/e1-quick.json` | `pv2-e1-scores.v1` | 사진별 `decision`/`outcome`(D_gate·D_ocr·D_vlm). **정답 비교가 들어 있는 평가 자료** |
| 참고 재채점 | `output/pipeline-v2-20261010/scores/reference-batch02-seen.json` | `pv2-e1-scores.v1` | 기존 묶음 재채점이며 새 추론이 아님 |
| 평가 정답 | `output/pipeline-v2-20261010/data/eval/ground_truth.json` | `pv2-ground-truth.v1` | 모델 입력이 아님. 화면에 쓸 경우 "평가 정답"으로 분리 표시 |

검증 명령:

```sh
python3 scripts/verify_run_bundle.py output/pipeline-v2-20261010/runs/e1/run_pv2-e1-quick-val01
```

## 표시 한계(반드시 지킬 것)

- 새 묶음의 `capture_mode=public_dataset`, `scenario_id=steel-public-bootstrap`은 제품의 고정값이고 이번 자료에는 맞는 값이다. Isaac A/B와는 무관하다.
- frame의 `source.relative_path`는 중립 이름(`images/pv2-img-NNN.jpg`)이다. 원래 파일명은 평가 자료에만 있다.
- `scores/*.json`의 `D_gate` 진행 판정은 채점기가 제품 `observed_candidates`를 묶음의 관측에 적용한 결과다. 묶음 안의 `recognition_decision`(항상 `needs_review`)과 다르다. 대시보드가 이를 제품의 실제 전송·작업지시 연결로 표시하면 안 된다. 이 실행에는 작업지시·문서 검토·전달이 없다.
- 장면 `J01`, 문서 `JOINT-DEMO-01`, 새 사진 8장 사이의 연결은 없다. 문서 데모 "정상"(`BISB30N-15`)은 오독 문자열로 만든 모사 문서와의 일치다. 이를 올바른 인식으로 표시하지 마.
- E1-R·E2·E3·E4는 미실행이다. 빈 칸이나 "미실행"으로 표시하고 가상 값을 만들지 마.
- 신뢰도: VLM은 null이고 OCR `recognition_score`만 있다.
