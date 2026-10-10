# ContextWeld 실험실

**현재 실험: [고정 이미지 맥락 비교 CTX-001](context_ablation/REPORT.md) 실행 완료.** 공개 사진 9장의 주어진 ROI 28개에서 OCR 정답2·이미지와 후보 목록16·합성 작업 문서 추가14개다. 후보 목록의 도움과 문서 추가의 악화, 정답 없는 목록의 3/4 오답 확정을 함께 기록했다. 현장 정확도 평가가 아니며 [재현 안내](context_ablation/README.md)를 따른다.

아래 [2026-10-09 파일럿](REPORT-2026-10-09.md)은 역사 기록으로 보관하며, 새 실험의 기준선·현재 모델 성능·발표 성능 근거에서 제외한다. 원본 사진과 공개 라벨은 새 실험에서 재사용한다.

## 과거 파일럿 — 현재 성능 근거에서 제외

| ID | 질문 | 레포트 |
|---|---|---|
| E1-001 | 전체 사진과 정답 영역에서 Vision이 얼마나 읽는가? | [최초 기준선](e1_ocr/REPORT.md) |
| E1-002 | 네 방향을 읽으면 정답 후보가 생기는가? | [방향 비교](e1_rotation/REPORT.md) |
| E1-003 | 대안 OCR 구성은 같은 표본에서 어떤가? | [RapidOCR 비교](e1_alternative/REPORT.md) |
| E1-004 | 정답 영역에서 검출을 생략하면 어떤가? | [문자 인식 진단](e1_recognition/REPORT.md) |
| E2-001 | 작은 모델에 문서를 어떻게 제공할까? | [0.5B 문서 비교](e2_documents/REPORT-001.md) |
| E2-002 | 더 큰 모델에서도 같은 관찰이 유지되는가? | [1.5B 문서 비교](e2_documents/REPORT-002.md) |
| E4-001 | 실제 OCR을 가상 작업지시에 연결하면? | [연결 파일럿](e4_linking/REPORT.md) |
| E5-001 | 구조·출처 검사가 무엇을 막고 놓치는가? | [검사 파일럿](e5_output_checks/REPORT.md) |

E3의 분할/검색기 비교, E6 이력 효과, E7 전체 제품 통합 평가는 미실행이다. E4는 검색 대안 우열, E5는 도메인 적용조건 전체를 검증한 것이 아니다. [전체 계획](PLAN.md)과 [레포트 양식](REPORT_TEMPLATE.md)을 참고한다.

## 보존 구조

| 위치 | 내용 |
|---|---|
| 각 실험의 PROTOCOL 문서 | 해당 실행 전에 고정한 조건·판정 규칙 |
| 각 실험의 results/ 또는 results-002/ | 선별한 실제 출력·사례별 판정·집계·환경 |
| [e1_ocr/manifest.json](e1_ocr/manifest.json) | 모든 OCR 비교에 공통으로 사용한 표본·정답·URL·해시 |
| [e2_documents/corpus.json](e2_documents/corpus.json) | 문서 요약과 원문 절·출처 |
| [e2_documents/questions.json](e2_documents/questions.json) | 생성 입력용 질문. 채점 기준과 분리 |
| [e2_documents/rubric.json](e2_documents/rubric.json) | 사전에 고정한 채점 기준 |
| 각 실험의 inputs/·runs/ | 원본·모델·파생 이미지·실행별 로그. Git 제외 |
| .runtime/ | 별도 OCR 가상환경. Git 제외 |
| [checksums.json](checksums.json) | 보존한 코드·프로토콜·결과의 해시 |
| [VALIDATION.json](VALIDATION.json) | 최근 전체 재검증 결과 |

원본·대량 생성물은 Git에서 제외하고, 재현에 필요한 코드·manifest·선별 결과를 보존한다. 사용자 작업 이력·채팅 인계는 .cowork/에 별도 기록한다. 과거 E4의 수동 후보 연결과 현재 제품의 실제 모델·문서 실행을 구분하며 최신 구현은 [프로젝트 README](../README.md)를 따른다.

## 과거 파일럿 결과 확인

네트워크·모델 재추론 없이 과거 파일럿의 저장된 결과를 검증한다. Python 3.10 이상과 Pillow가 필요하다. CTX-001은 위 재현 안내의 별도 채점기로 검증한다.

```sh
python3 experiments/verify.py
```

이 명령은 테스트, 원문 재채점, 회전 후보 재병합, 생성 결과의 원문 연결·검색 재현, 가상 지시 재연결, 구조 검사 재실행과 파일 해시를 확인한다. 새로운 추론·다운로드 명령은 각 레포트에 있다. 새 run_id를 사용하고 기존 실험 결과를 덮어쓰지 않는다.

## 기록 원칙

- 실제 이미지·합성 제어 이미지·가상 작업지시·직접 작성한 문서 요약을 구분한다.
- 계획·실행·관찰·결정을 구분한다. 테스트 통과와 성능 개선은 다르다.
- 원본 후보·실패·정답을 보존한다. 결과를 보고 정답이나 교정 규칙을 바꾸지 않는다.
- 회전본·같은 부재의 사진을 새 독립 표본으로 세지 않는다.
- 필요한 비교만 진행한다. 미실행 항목을 계획표에서 완료로 표시하지 않는다.

설계 배경은 [개발 기획](../docs/DEVELOPMENT_PLAN.md)에 있다.
