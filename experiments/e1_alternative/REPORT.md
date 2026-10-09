# E1-003 — RapidOCR 대안 구성 결과

2026-10-09 · 실행 완료. [프로토콜](PROTOCOL.md), [원문 출력](results/raw.json), [전체 사례](results/cases.json).

## 결론

전체 사진에서는 Vision보다 문자 오류가 줄었지만, 완전 일치는 **0/28 → 1/28(+1/28)**에 그쳤다. 정답 crop을 같은 검출 파이프라인에 다시 넣으면 누락이 늘어 악화됐다. 전체 이미지의 작은 개선과 crop의 악화를 함께 고려하며 이 구성의 현장 우세를 주장하지 않는다.

| 지표 | Vision 전체 | RapidOCR 전체 | Vision 정답 crop | RapidOCR 정답 crop |
|---|---:|---:|---:|---:|
| 완전 일치 | 0/28 | 1/28 | 0/28 | 0/28 |
| 영역 대응 | 18/28 | 21/28 | 17/28 | 6/28 |
| 문자 오류 / 정답 문자 | 206/280 | 162/280 | 205/280 | 238/280 |
| CER | 73.57% | 57.86% | 73.21% | 85.00% |
| Vision 대비 사례별 오류 감소/동일/증가 | 기준 | 15/5/8 | 기준 | 3/10/15 |

정답을 읽은 사례는 S08-R06 `B1Sb40N-9` 한 개다. 반면 S01 전체 출력은 `IS-NE9SIS`처럼 여전히 잘못 읽었다. S05 `B1Sb30N-29`는 두 구성 모두 `BISb30N-29`여서 식별자 전체가 맞지 않았다. 이미지 2장에 18/28개 라벨이 몰린 개발 표본이라는 한계가 그대로 적용된다.

## 구성과 재현 조건

[RapidOCR 공식 안내](https://github.com/RapidAI/RapidOCR)와 [라이선스](https://github.com/RapidAI/RapidOCR/blob/main/LICENSE)를 2026-10-09 확인했다. RapidOCR 3.10.0, ONNX Runtime 1.30.0을 별도 가상환경에 설치했다. 사용 모델은 `PP-OCRv6_det_small.onnx`, `ch_ppocr_mobile_v2.0_cls_mobile.onnx`, `PP-OCRv6_rec_small.onnx`다. 패키지는 Apache-2.0, ONNX Runtime은 MIT로 배포 표시된다.

기본 검출·방향 분류·인식 및 내부 전처리를 사용했으며 외부 네 방향 회전은 적용하지 않았다. 이는 모델 하나만 바꾼 엄밀한 인과 비교가 아니라 두 OCR 구성의 비교다. 데이터 라벨로 문자 사전을 제한하지 않았고, 모델에 작업지시나 문자 정답을 주지 않았다.

38개 호출이 완료됐다. 빈 검출은 인식 실패 결과로 보존했고 오류 없이 성공한 것으로 성능을 과장하지 않았다. API 예외는 없었다. 전체 호출 합 29.384초, crop 호출 합 167.550초였다. 마지막 crop 호출이 54.483초였고 당시 별도 생성 실험도 실행됐다. [추론] 자원 경합이 시간에 영향을 주었을 수 있다. 첫 호출 초기화·서로 다른 환경·내부 확대도 포함하므로 이 시간으로 속도 순위를 정하지 않는다.

설정은 [config.yaml](results/config.yaml), 패키지 잠금 목록은 [requirements-lock.txt](results/requirements-lock.txt), 가중치와 코드 해시는 [environment.json](results/environment.json)에 있다. 코드와 모델은 공개 배포본이며 시스템 Python과 기존 제품 코드는 변경하지 않았다.

```sh
python3 -m venv experiments/.runtime/ocr
experiments/.runtime/ocr/bin/python -m pip install -r experiments/e1_alternative/results/requirements-lock.txt
experiments/.runtime/ocr/bin/python experiments/e1_alternative/run_alternative.py rerun-001
```

이미 설치돼 있다면 마지막 명령만 사용한다. E1-001의 입력 이미지와 manifest가 필요하다. 모델 포함 패키지를 고정하고 실제 가중치 해시가 일치하는지 검증한다.

## 다음 판단

정답 crop의 검출 실패가 문자 인식기의 한계를 가리는지 E1-004에서 검출을 생략해 진단한다. E1-003의 성적을 그 결과로 교체하지 않는다. 자동 전체 이미지 인식의 현재 관찰은 1/28이며 추가 검증이 필요하다.
