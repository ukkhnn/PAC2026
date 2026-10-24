# 문서 색인

갱신일: 2026-10-24 · 코드·로컬 검증 반영: 2026-10-24. 어떤 문서를 언제 읽는지 정리한다. 서술이 충돌하면 **더 늦은 실행 기록**이 우선하고, 범위 정의는 [데모 스펙](plan/DEMO_SPEC.md)이 우선한다.

## 최근 반영

- 10월 15일: 재촬영 모듈 병합, 판독·라벨 계보 정정, 추가 파일·부분 전달 검증 보강, 관리자 목업 분리.
- 10월 16일: 재촬영 기록 브리지·CLI, 통합/시연 실행의 `MANIFEST.roots` 등록, 서버 복구용 로컬 보존 사본 재대조.
- 10월 18일: `recapture-bundle.v1` 대시보드 읽기 어댑터·검증 연결과 fixture 3개 추가. 당시 전체 회귀 테스트 164개 통과.
- 10월 19일: 관리자 검증의 [허용 실패 13건 사유](runs/ADMIN_DASHBOARD.md#141-허용-실패-13건-항목별-사유) 정리. 실패 해결이나 실제 GPU 실행 기록은 아니다.
- 10월 24일: 저장 재촬영 결과의 문서·현대/두산 모의 전달 재개, 통합 관리자 검증기·어댑터·조건 편집 연결. 전체 회귀 180개·fixture HTTP 수신·5,069파일 검사 통과, 브라우저 26개 요약·주요 탭 확인. [검증 기록](runs/LOCAL_RESUME_VERIFICATION.md).
- 실제 GPU 재촬영·실제 결과의 화면 대조·서버 실물 회수는 남아 있다. 현재 완료 범위는 [마일스톤](plan/MILESTONES.md), 진단 후 항목별 상태는 [진단·처방 후속 현황](audit/DIAGNOSIS_AND_REMEDIATION.md#5-실행-후속-현황-2026-10-24)을 따른다.

## 처음 읽는 순서

1. [프로젝트 개요](plan/PROJECT_BRIEF.md) — 무엇을 왜 만드는가.
2. [데모 스펙](plan/DEMO_SPEC.md) — 확정 범위와 완료 기준. 기존 기획과 충돌하면 이 문서가 우선한다.
3. [마일스톤](plan/MILESTONES.md) — 지금 어디까지 됐는가.
4. [통합 파이프라인](runs/WELD_PIPELINE.md) — 현재 가장 긴 종단 실행.

## plan/ — 범위·기획

| 문서 | 내용 |
|---|---|
| [PROJECT_BRIEF](plan/PROJECT_BRIEF.md) | 문제 정의, 미션 요구사항, 기능 범위, 평가 계획 |
| [DEMO_SPEC](plan/DEMO_SPEC.md) | **구현 기준.** 확정 범위, 단일 시나리오, 데이터 계약, 관리자 재생, 완료 기준·미정 항목 |
| [MILESTONES](plan/MILESTONES.md) | 실제 진행 상태와 P0~P5 완료 기준. 새 일정은 미확정 |
| [DATA_REQUIREMENTS](plan/DATA_REQUIREMENTS.md) | 필요한 자료와 현장 검증 항목 |
| [DOCUMENT_APPLICATION_PLAN](plan/DOCUMENT_APPLICATION_PLAN.md) | 원문 확보·등록·표 검수, 정확 조회와 RAG, 필드별 근거 |
| [DEVELOPMENT_PLAN](plan/DEVELOPMENT_PLAN.md) | 2026-10-08 초기 개발 기획. 아카이브 |
| [PIPELINE_OPEN_RESOURCES_AND_SCENARIO](plan/PIPELINE_OPEN_RESOURCES_AND_SCENARIO.md) | 2026-10-09 공개 자료·시나리오 조사. 아카이브, 구현 명세보다 우선하지 않음 |
| [MENTORING_QUESTIONS](plan/MENTORING_QUESTIONS.md) | 2026-10-06 멘토링 질문지. 아카이브, 답변은 기록되지 않음 |

## spec/ — 명세

| 문서 | 내용 |
|---|---|
| [OCR_PIPELINE_SPEC](spec/OCR_PIPELINE_SPEC.md) | 인식 단계 구성, 문자·화살표·기호·대상 관계, 입출력·재촬영·검증 기준 |
| [WELDING_ROBOT_INPUT_SPEC](spec/WELDING_ROBOT_INPUT_SPEC.md) | 현대 Hi6·두산 DRL 공식 입력 항목·단위·제약의 외부 조사. 실제 제어 지원을 뜻하지 않음 |
| [WELDING_ROBOT_PARAMETERS](spec/WELDING_ROBOT_PARAMETERS.md) | 위 명세로 연결하는 짧은 안내 |

## runs/ — 실제 실행 기록

각 문서는 **완료된 한 단계의 기록**이다. 실행 당시의 사실을 담으며, 그 뒤 다른 실행이 한계를 해소한 경우 문서 안에서 갱신 표시를 단다.

| 문서 | 내용 |
|---|---|
| [LOCAL_RESUME_VERIFICATION](runs/LOCAL_RESUME_VERIFICATION.md) | **최신.** GPU 없이 저장 결과 재개·모의 수신·관리자 검증·브라우저 확인의 증거와 한계 |
| [WELD_PIPELINE](runs/WELD_PIPELINE.md) | 저장 A/B 마킹 판독 → 작업지시 조회 → WPS 검증 → 공통 명세 → 현대/두산 변환 → HTTP 모의 수신 |
| [RECAPTURE_LOOP](runs/RECAPTURE_LOOP.md) | 저장 A/B 분기 모듈·통합 실행의 기록 브리지·CLI. 대시보드 읽기·저장 결과의 후속 재개 구현, 실제 GPU 실행·실제 결과의 화면 검수는 미완료 |
| [RECOGNITION_AND_BINDING](runs/RECOGNITION_AND_BINDING.md) | 판독·연결 경로와 라벨 계보 정정: OCR 원문 보존·VLM 단독 판독, `B1Sb30N-15`→`BISB30N-15` 계보 명시 |
| [ROBOT_INPUT_PREVIEW](runs/ROBOT_INPUT_PREVIEW.md) | 등록 작업조건 자동 적용과 제조사 입력 변환 화면 |
| [ADMIN_DASHBOARD](runs/ADMIN_DASHBOARD.md) | 여러 실행을 담는 오프라인 관리자 패키지, 목업 분리·MANIFEST roots·재촬영/통합 실행 읽기·검증기 연결·과거 실패 해석·새 사본 검증 |
| [ISAAC_SHIPYARD_SCENE](runs/ISAAC_SHIPYARD_SCENE.md) | 조선소 수직 3면 강판·수기 메모 장면 `live-03`의 A/B RGB |
| [ISAAC_SCENE](runs/ISAAC_SCENE.md) | 기존 정형 마킹·작업대 기준 장면 `live-01` |
| [EXPLICIT_REVIEW](runs/EXPLICIT_REVIEW.md) | 수정 저장 → 명시적 재검토 → 선택적 모의 전달 CLI와 `review-bundle.v1` |
| [DOCUMENT_REVIEW_VIEWER](runs/DOCUMENT_REVIEW_VIEWER.md) | 문서·재검토 묶음 한 건의 단일 HTML 내보내기 |
| [DOCUMENT_DEMO](runs/DOCUMENT_DEMO.md) | 저장 관측 → 모사 작업문서 → WPS 범위 → HTTP 모의 수신 |
| [RUNPOD_INFERENCE](runs/RUNPOD_INFERENCE.md) | 공개 사진 10장의 실제 OCR/VLM과 원문 4개 검색 |
| [FIRST_SCENE](runs/FIRST_SCENE.md) | 최초의 후보→작업지시 연결 CLI (`python3 -m contextweld`) |

## setup/ — 환경

| 문서 | 내용 |
|---|---|
| [POD_VER1](setup/POD_VER1.md) | Runpod L40S 환경, Isaac·ROS·Foxglove 준비와 확인 결과 |
| [RUNPOD_DATA_SETUP](setup/RUNPOD_DATA_SETUP.md) | 사진·근거 원문 다운로드와 해시 확인 |

## sources/ — 출처

| 문서 | 내용 |
|---|---|
| [DATA_MODEL_PROVENANCE](sources/DATA_MODEL_PROVENANCE.md) | **출처 기준.** 확보 파일·모델의 원출처·revision·SHA-256·가공 과정. 기계 판독용 목록은 [`configs/data_model_provenance.json`](../configs/data_model_provenance.json) |
| [SOURCES](sources/SOURCES.md) | 대회·도메인 참고 자료 목록과 적용 범위 |

## audit/ — 진단·처방

현재 종단 연결의 문제를 사실(진단)과 제안(처방)으로 구분해 정리한다. 당초 처방과 지시서 항목은 `(claude 제안사항)`으로 보존하며, 실행 결과는 진단·처방서 5절에서 구분한다.

| 문서 | 내용 |
|---|---|
| [DIAGNOSIS_AND_REMEDIATION](audit/DIAGNOSIS_AND_REMEDIATION.md) | 재촬영 미병합·서사 불일치·라벨 오독 파생·OCR 미사용·서버 유실·목업·검증 허점의 진단과 처방 |
| [INSTRUCTIONS/](audit/INSTRUCTIONS/) | 영역별 복구 지시서(recapture-loop, recognition-and-binding, server-artifact-recovery, dashboard-mock-data, verification-integrity)와 [서버 복구 로컬 준비](audit/INSTRUCTIONS/server-artifact-recovery-local-prep.md) |

## 그 밖에

| 경로 | 내용 |
|---|---|
| [references/idea-proposal.pdf](references/idea-proposal.pdf) | 제출 기획서 |
| [references/mission-03.pdf](references/mission-03.pdf) | HD현대로보틱스 미션 03 원문 |
| [images/isaac_shipyard/](images/isaac_shipyard/) | 조선소 장면 A/B 미리보기 이미지와 [출처 기록](images/isaac_shipyard/README.json) |
| [assets/context-decision-proposal.html](assets/context-decision-proposal.html) | 2026-10-05 맥락 판단기 설계 제안. 아카이브, 현재 범위가 아님 |
| [assets/welding-context-guide.html](assets/welding-context-guide.html) | 2026-10-05 용접 도메인 입문 안내. 아카이브 |
| [../experiments/README.md](../experiments/README.md) | 실험실 — 고정 이미지 맥락 비교(CTX-001), 파이프라인 역할 실험(PV2), 과거 파일럿 |
