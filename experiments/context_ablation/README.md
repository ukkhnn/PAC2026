# 고정 이미지 맥락 실험

기준일: 2026-10-10. [프로토콜](PROTOCOL.md)의 조건으로 현재 Runpod OCR/VLM을 비교한다. 서버 이전 실험 성적은 이번 기준선에 사용하지 않는다. 원본 사진과 공개 라벨만 재사용한다.

대상 위치가 주어진 표기 28개(9사진)에 OCR, VLM 재판독, 주변 장면, 후보 목록, 합성 배치 문서를 순서대로 비교한다. 이미지 없는 대조군에도 같은 OCR·대상 위치·문서를 주며, 문자 거리 규칙과 잘못된 문서 조건을 따로 둔다. 입력·문서가 라벨에서 파생된 진단 실험이며 실제 현장 작업지시 성능이 아니다.

**실행 완료:** OCR 28회·VLM 148회·규칙 28개, 204개 기록과 574개 해시 검증. 정답은 A/B/C 각각 2개, D 16개, E 14개, F 5개, 규칙 7개다. 정답 없는 목록에서 3/4 오답 확정을 포함해 [결과와 한계](REPORT.md)에 기록했다. [수치·개별 판정](results/tables.md), [구조화 결과](results/summary.json)도 함께 제공한다.

## 실행

Runpod의 기존 `contextweld-inference` 환경과 고정 모델 디렉토리를 사용한다. 새 패키지 설치나 이미지 다운로드는 필요하지 않다. 실행별 출력 디렉토리는 항상 새 이름을 쓴다.

```sh
PY=/workspace/venvs/contextweld-inference/bin/python
$PY experiments/context_ablation/prepare.py --verify-only
$PY experiments/context_ablation/run.py \
  --inputs experiments/context_ablation/inputs.json \
  --fixtures experiments/context_ablation/fixtures.json \
  --data-root data/raw/demo-bootstrap-v1 \
  --output output/context-ablation-20261010/run-01
```

원문·프롬프트·이미지 입력 크기·오류·생성시간을 저장한다. 모델 실행기는 `ground_truth.json`을 읽지 않는다. `completion.json`과 `checksums.json`이 있어야 완료 실행이며, 실패 중간 결과는 삭제하지 않는다.

```sh
python3 experiments/context_ablation/score.py \
  --run output/context-ablation-20261010/run-01 \
  --truth experiments/context_ablation/ground_truth.json \
  --inputs experiments/context_ablation/inputs.json \
  --fixtures experiments/context_ablation/fixtures.json \
  --output output/context-ablation-20261010/run-01-summary.json
python3 -m unittest discover -s experiments/context_ablation -p 'test_*.py'
```

채점 출력은 원본 실행 묶음 밖에 새로 저장한다. 원본을 다시 추론하거나 전송하지 않는다. 선택된 후보의 정답률·잘못된 확정·보류·실행 오류를 분리하고, 같은 표기의 조건별 개선과 악화를 모두 계산한다. 그림이 필요하면 Matplotlib가 있는 환경에서 `report.py --summary <채점 JSON> --output <새 폴더>`를 실행한다.
