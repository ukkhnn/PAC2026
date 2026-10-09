# E2-001 — 작은 모델의 문서 제공 비교

2026-10-09 · 실행 완료. [사전 프로토콜](PROTOCOL.md), [원문 27개](results/outputs.jsonl), [개별 검토](results/review.json).

## 결론

0.5B 모델은 필요한 문서를 받아도 질문에 답하지 않거나 문서 ID만 반환하는 경우가 많았다. 검색은 필요한 근거를 6/6 질문에서 찾았지만 검색 제공 조건의 완전한 사실 답변은 0/6이었다. **이 결과를 검색 실패나 RAG 불필요의 증거로 사용하지 않는다.** 모델·프롬프트 조합의 수행 능력이 비교를 제한했다.

| 지표 | 문서 없음 | 요약 자료집 전문 | BM25 상위 2개 |
|---|---:|---:|---:|
| 답변 가능한 사실 질문 정답 | 0/6 | 2/6 | 0/6 |
| 자료 밖 질문의 적절한 보류 | 3/3 | 3/3 | 3/3 |
| 정답이며 필요한 출처 ID도 제시 | 0/6 | 2/6 | 0/6 |
| 요청 JSON 객체 형식 준수 | 0/9 | 0/9 | 0/9 |
| 실제 JSON 구문으로 파싱 가능 | 0/9 | 1/9 | 0/9 |
| 입력 토큰 합 | 979 | 2968 | 1463 |

전문 제공에서 Q1과 Q2의 의미 답변·출처는 맞았으나 코드 fence 또는 배열을 써서 단일 JSON 객체 지시를 지키지 않았다. 문서 없음은 모든 질문에 UNKNOWN을 반환했다. 자료 밖 질문에 보류한 것만으로 좋은 모델이라고 판단할 수 없다.

## 검토와 근거

- Q3 전문 조건은 필수 개념 세 가지 중 하나만 답해 오답으로 처리했다.
- Q5 전문 조건, Q2·Q3 검색 조건은 문서 ID만 반환해 의미 답변으로 인정하지 않았다.
- 상위 2개 검색에 필요한 문서가 모두 포함된 질문은 6/6이었다. 검색의 근거 회수와 생성의 활용 실패를 분리했다.
- 잘린 응답은 없었다. 응답 형식 문제를 뒤에서 몰래 고쳐 원래 준수한 것처럼 세지 않았다.
- 개별 판정은 고정 rubric에 대한 작업 에이전트의 질적 검토이며 도메인 전문가의 독립 검토는 아니다.

자료는 [TWI의 2020년 용접기호 해설](https://www.twi-global.com/technical-knowledge/job-knowledge/weld-symbols)을 2026-10-09 확인하고 작성한 140단어의 영어 요약 6개다. [corpus.json](corpus.json)에 출처 절을 기록했다. 전문이라는 말은 이 작은 요약 자료집 전체를 뜻한다. 실제 규정 전문·표·기업 WPS를 다룬 결과가 아니다.

[Qwen2.5-0.5B-Instruct 배포 페이지](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct)의 공개 모델을 고정 버전으로 내려받아 CPU float32·greedy로 실행했다. 가중치 해시는 [model-manifest.json](model-manifest.json), 입력·코드 해시는 [environment.json](results/environment.json)에 있다. 외부 생성 API를 사용하지 않았다.

## 실행·한계

조건별 추론 시간 합은 71.784초, 45.060초, 16.754초였다. 일부 구간은 OCR 비교와 동시에 수행됐고 첫 실행 초기화도 포함되어 속도 비교 근거로 사용하지 않는다. 모델·자료·질문·채점 기준 모두 작은 개발 실험이며 독립 평가가 아니다.

```sh
python3 -m unittest discover -s experiments/e2_documents -p 'test_*.py' -v
python3 experiments/e2_documents/prepare_models.py small
python3 experiments/e2_documents/run_documents.py rerun-small-001
```

실행기는 정답 rubric을 읽지 않는다. 같은 corpus·질문·prompt를 더 큰 로컬 모델에서 확인하는 E2-002를 별도 프로토콜로 진행한다. 이 결과를 고치거나 덮어쓰지 않는다.
