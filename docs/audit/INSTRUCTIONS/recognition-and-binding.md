# 지시서 — 라벨 계보 정정과 OCR 판단 연결

대상: 진단 C·D 항목. 이 지시서의 모든 항목은 `(claude 제안사항)`이며 실행 여부는 별도 판단 대상이다.

## 배경

- 공개 사진의 실제 라벨은 `B1Sb30N-15`다. A 프레임은 `BISB3015`로 오독, 시연 기준값은 `BISB30N-15`로 파생됐다.
- `configs/document_demo/work_orders.json`의 `provenance`는 이를 스스로 "실제 OCR 출력 문자열을 불투명 식별자로 사용해 작성한 시연"이라고 명시한다. `drawing.json`도 같은 파생값을 고정한다.
- OCR은 `recognition.py`에서 실행되지만 통합 판단(`weld_pipeline.capture_binding`)은 VLM `read['markings']`만 사용한다. B 프레임에서 OCR은 `J01`을 `JOD`로 읽었으나 무시됐고, 그런데도 검증 기록에는 `observation_consensus`가 확인 항목처럼 적힌다.
- `src/contextweld/ocr.py` 소스는 삭제돼 git에 없고(`__pycache__` 잔재만), OCR 로직은 `recognition.py`에 인라인으로 남아 있다.

## 작업 (claude 제안사항)

1. **실제 라벨 기준 재기록** — 시연 작업지시·도면·Isaac 장면 마킹의 기준 문자열을 실제 라벨 `B1Sb30N-15`에 맞추거나, "오독 파생 시연값"임을 사용자가 보는 문서에 명시한다. 둘 중 하나를 고르되, "실제 라벨 정확 판독"으로 오인될 여지를 없앤다.
2. **A/B 판독 계보 명시** — A=`BISB3015`(오독), B=`BISB30N-15`(파생값), 실제 라벨=`B1Sb30N-15`의 관계를 실행 기록에 남겨, 어떤 문자열이 어느 단계에서 왔는지 추적 가능하게 한다.
3. **OCR 판단 연결 또는 기록 정정** — 다음 중 택일한다.
   - (a) OCR 결과를 마킹 연결 판단에 실제로 반영하고, `observation_consensus`가 실제 합의를 뜻하도록 한다.
   - (b) OCR을 여전히 판단에 쓰지 않는다면, 검증 기록의 `observation_consensus` 기재를 실제 동작(VLM 단독)에 맞게 정정한다.
4. **`ocr.py` 정리** — 삭제된 소스의 잔재(`__pycache__/ocr.cpython-311.pyc`)를 정리하고, OCR 로직이 `recognition.py`에 인라인으로 있는 상태를 의도된 구조로 문서화한다.

## 완료 기준 (claude 제안사항)

- 실제 라벨과 시연 파생값의 구분이 코드·문서 어디서든 혼동되지 않는다.
- OCR 실행 여부와 판단 사용 여부가 실제 코드와 일치해, "OCR·VLM 합의"를 주장하는 기록이 없어진다.
