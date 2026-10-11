# 첫 장면: 부재번호 후보와 작업지시 연결

기준일: 2026-10-08. 첫 구현 범위는 **후보 입력 → 유효 작업지시 연결 → 근거·제외 이유 출력**이다. Python 3.10 이상, 표준 라이브러리만 사용한다.

2026-10-10 문서 정합: 이 문서는 기존 CLI의 실제 기능·입력 계약을 설명한다. 새 전체 데모는 [데모 스펙](../plan/DEMO_SPEC.md), 인식은 [OCR 명세](../spec/OCR_PIPELINE_SPEC.md), 문서 구축은 [문서 적용 계획](../plan/DOCUMENT_APPLICATION_PLAN.md)을 따른다. 여기의 작업지시 조회는 그중 현재 작업 맥락의 정확 조회 기반이며 문서 RAG나 최종 인식 스택이 완성됐다는 뜻은 아니다.

사진 OCR, 웹 화면, 문서 RAG, 작업자 승인 저장은 아직 없다. 예제의 부재번호 후보는 직접 작성한 값이며 실제 인식 출력이 아니다. 이 모듈의 연결 결과는 용접 실행 승인이 아니다.

## 실행

저장소 루트에서 실행한다.

```sh
PYTHONPATH=src python3 -m contextweld data/examples/part-order-scene.json --case normal
```

`--case` 값을 바꿔 다음 장면을 확인한다.

| 사례 | 입력·맥락 | 기대 결과 |
|---|---|---|
| `normal` | 후보 B-108, 동일 블록, 개정 1·2 존재 | `matched`: 유효한 개정 2 연결, 개정 1은 `superseded` |
| `ambiguous` | 후보 B-108·B-103, B-103 지시는 만료 | `review_required`: B-108 지시만 남아도 원래 복수 후보를 유지 |
| `stale` | 후보 B-103, 유일한 지시가 만료 | `unmatched`: 지시 만료 이유 표시 |
| `wrong-context` | 후보 B-108, 입력 블록 BLK-02 | `unmatched`: BLK-01 지시를 사용하지 않음 |

다른 입력은 예제 JSON을 복사해 같은 구조로 작성하고 파일 경로를 바꿔 실행한다. JSON 파싱·입력 검증 오류는 표준 오류로 출력하고 종료 코드 2를 반환한다. 정상적인 조회는 연결 실패·확인 필요 상태도 JSON으로 출력하며 종료 코드 0을 반환한다.

## 입력 구조

| 위치 | 항목 |
|---|---|
| 최상위 | `schema_version: 1`, `dataset_kind`, `provenance`, `orders`, `cases` |
| 작업지시 | `project_id`, `block_id`, `order_id`, `part_id`, `revision`, `valid_from`, `valid_until`, `state`, `instruction` |
| 사례 | `id`, `candidate_source`, `candidates`, `project_id`, `block_id`, `as_of` |

- `candidates`는 한 표기 영역에 대한 부재번호 대안의 배열이다. 서로 다른 여러 부재를 동시에 읽은 값은 영역별 사례로 나눠 입력한다. 빈 배열은 판독 불가를 뜻한다.
- 예제의 `dataset_kind`는 `synthetic`, `candidate_source`는 `synthetic_manual`이다. `provenance`에는 작성·제공 출처를 적는다.
- ID는 영문·숫자·밑줄·하이픈으로 제한한다. 앞뒤 공백 제거와 대문자 변환만 수행하고 `O`와 `0` 같은 문자를 추측해 바꾸지 않는다. 대소문자를 구분하지 않는 시연 규약이며 기업 규약이 확보되면 재검토한다.
- 시각은 `2026-10-08T10:00:00+09:00`처럼 시간대가 있는 ISO 8601 값이어야 한다. 유효 구간은 시작 포함·종료 제외이며 `valid_until: null`은 종료 미지정이다.
- `revision`은 양의 정수다. 동일 프로젝트·블록·작업지시 안에서 부재는 고정하고 개정 번호 순서와 적용 시점이 역전되지 않아야 한다. 같은 시점이면 높은 개정 번호를 택한다.
- `state`는 `released`, `cancelled`, `on_hold`를 지원한다. 취소·보류는 같은 작업지시의 새 개정으로 입력한다. 완료·재개 등 상세 생산 상태는 아직 다루지 않는다.

## 판단 규칙과 출력

먼저 작업지시별로 조회 시점에 이미 적용된 가장 높은 개정을 찾는다. 그 개정이 만료·취소·보류 상태면 이전 개정으로 되돌아가지 않는다. 미래에 적용될 개정은 현재 판단에 사용하지 않는다.

같은 프로젝트·블록과 정확한 부재번호가 일치한 지시만 연결한다. 관측 후보가 여러 개이거나 한 부재에 유효한 작업지시가 여러 개면 순위·점수로 임의 선택하지 않는다.

| 출력 | 의미 |
|---|---|
| `status` | `matched`, `review_required`, `unmatched`, `unreadable` |
| `reason` | 상태를 결정한 이유 코드 |
| `observed_candidates` | 입력 후보 원문, 순서와 중복 포함 |
| `normalized_candidates` | 정규화한 중복 없는 후보 |
| `context` | 조회한 프로젝트·블록·시점 |
| `matches` | 연결된 작업지시 내용·개정·유효기간 |
| `excluded_orders` | 제외된 작업지시와 제외 이유 |
| `execution_authorized` | 항상 `false`. 연결은 실행 승인이 아님 |

이유 코드는 `different_scope`, `not_yet_effective`, `superseded`, `expired`, `cancelled`, `on_hold`, `part_not_in_candidates` 등이다. `matched`도 인식 정답이나 작업 실행 가능성을 보증하지 않으며 입력 데이터 기준으로 유일한 연결 후보라는 뜻이다.

입력은 해당 작업의 필요한 개정 이력을 포함하는 신뢰된 스냅샷이라고 가정한다. 누락된 취소 이력, 문서 진위, 실제로 그 시점에 문서를 수신했는지는 검증할 수 없다. `valid_from`과 별도의 수신 시점은 아직 지원하지 않으므로 소급 변경 문서를 넣은 과거 조회를 당시 지식 상태의 재현이라고 표현하지 않는다.

## 검증

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

2026-10-08 기준 자동 테스트 14개 통과. 범위·ID 정확 일치, 후보 보존, 복수 후보·지시, 개정 선택, 취소·보류·만료 후 이전 개정 복원 방지, 미래 개정, 시간 경계·시간대, 잘못된 입력 및 CLI 예제를 검증했다.

이는 작성한 로직의 동작 검증이다. 공개 이미지 인식 성능이나 설계 대안의 비교 실험 결과가 아니다. 독립 평가셋은 아직 없으며 현장 성능은 미측정이다.

## 다음 연결

실제 OCR 어댑터에서 나온 영역별 부재번호 후보를 이 입력에 연결하고 원본 이미지·영역·인식기 정보를 함께 보존한다. 현재 CLI에는 이음·WPS·도면의 상세 연결 계약이 없으므로 기존 작업지시 일치만으로 후속 용접 명세를 완성했다고 처리하지 않는다. [OCR 명세](../spec/OCR_PIPELINE_SPEC.md)의 시나리오·소량 인식 확인과 [문서 적용 계획](../plan/DOCUMENT_APPLICATION_PLAN.md)의 원문·구조화 값 검수를 거쳐 전체 흐름에 연결한다. 독립 성능 평가를 피칭 데모 연결의 선행 조건으로 두지 않는다.
