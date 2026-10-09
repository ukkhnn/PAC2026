# ContextWeld

**작업 맥락 기반 용접표기 해석 및 조건 추천 시스템**

> **현재 구현 기준: [데모 스펙 v1.5](docs/DEMO_SPEC.md) (2026-10-10).** Runpod에서 단일 시나리오의 인식·해석·재촬영·모의 파라미터 전달을 실행·기록하고, 로컬 관리자 화면에서 조회·재생한다. 근거 원문 적재·정확 조회/RAG도 구성한다. 아이디어 피칭이 목적이며, 데모의 실제 흐름·근거 설명을 우선하고 정확도 목표·독립 평가를 완료 조건으로 요구하지 않는다. 새 환경에서는 이 문서를 먼저 읽는다. 범위는 확정됐으며 전체 데모 구현은 아직 완료되지 않았다. 기존 기획과 충돌하면 데모 스펙이 우선한다.

ContextWeld는 선박 블록과 부재의 정형 마킹·수기 표기를 인식하고, 현재 작업지시·도면·용접 기준을 함께 검토해 작업과 용접조건 후보를 제안하는 프로젝트다. 판단 근거가 부족하거나 정보가 충돌하면 작업자에게 확인을 요청하고 그 결과를 기록한다. 사용자 수정은 별도로 저장하며, 명시적 재검토 요청에서 선택한 기록만 참조한다. 자동 학습·이력 자동 재사용은 이번 범위가 아니다.

[PAC 2026](https://ainnov.co.kr/pac2026) 분과 02 기업 문제 해결형 IR 피칭 대회의 HD현대로보틱스 미션 03을 대상으로 한다. 참가팀은 **Static Duo**다.

> 현재 단계: [공개 사진 10장의 실제 OCR/VLM·원문 4개 74청크 검색](docs/RUNPOD_INFERENCE.md)에 이어, 저장된 실제 관측을 [모사 작업지시·도면→WPS 조건 범위→HTTP 모의 수신](docs/DOCUMENT_DEMO.md)으로 연결했다. 정상 사례는 수신 응답을 기록했고, 필수값 누락·문서 공정 충돌·개정 불일치·실제 판독 불일치는 전송을 보류했다. 이어서 [사용자 수정 저장 → 명시적 재검토 → 선택적 모의 전달](docs/EXPLICIT_REVIEW.md)을 서버 CLI로 구현해 실제 저장 묶음에서 재검토만 성공(`succeeded`·`not_requested`), 별도 전달 요청으로 `received`, 수정 뒤에도 문제가 남아 `blocked`, 수신기 미가동 결함 주입 시 `failed`를 확인했다. 원본 입력 1,173개 파일 해시는 그대로이며 새 모델 호출은 없다. Runpod 테스트 83개가 통과했다. 별도 [Isaac 기준 장면](docs/ISAAC_SCENE.md)에서는 UR10 손목 카메라의 실제 A/B RGB·고정 반사·관절 이동과 Foxglove 손목/전체 장면 두 영상을 검증해 P1을 달성했다. 기존 정형 마킹·작업대 장면을 보존하고 조선소 병풍형 강판 패널·중앙 수기 메모로의 형상 개선은 대기 중이다. 기준일: 2026-10-10.

WPS 검수는 선택한 헤더·대표층 1의 전사 확인이며 사람의 적용 승인이 아니다. 사진의 실제 재질·두께·현장 WPS 적용성과 기준 장면의 인식→재촬영 연결은 미확인이다. 팔의 A/B 이동은 `pre_captured`로 기록하는 예약 시연이며 모델 판단으로 움직이는 폐루프가 아니다. [문서 검토 한 건의 오프라인 HTML 조회](docs/DOCUMENT_REVIEW_VIEWER.md)는 구현해 정상 `received`·누락/관측 충돌 `blocked`의 실제 묶음 3개를 내보냈다. 원본 582개 파일 해시 보존·신규 테스트 6개와 HTML 구조·표시 내용 검사를 통과했으며, 브라우저 파일 URL 제한으로 시각 검수는 미완료다. 명시적 재검토는 문서 범위 규칙 재검토이며 시각 관계의 모델 재해석과 수정 입력 화면은 구현하지 않았다. 전체 P2·P3·P4와 여러 실행 통합·A/B 관리자 재생은 미완료다. 별도 [실험실](experiments/README.md)의 과거 비교 결과와 현재 부분 실행을 구분한다.

## 첫 장면 실행

Python 3.10 이상에서 별도 설치 없이 저장소 루트에서 실행한다. 사진을 읽는 명령이 아니라 직접 작성한 후보와 가상 작업지시를 연결하는 예제다.

```sh
PYTHONPATH=src python3 -m contextweld data/examples/part-order-scene.json --case normal
```

`--case ambiguous`, `--case stale`, `--case wrong-context`로 확인 필요·만료·다른 블록 사례를 볼 수 있다.

## 해결하려는 문제

선박 부재의 표기는 문자·숫자·기호·약어가 혼재하며 오염·반사·훼손으로 판독이 어렵다. 문자 인식 결과만으로는 해당 표기가 어떤 부재, 작업 위치, 방향, 용접 작업을 의미하는지 판단하기 어렵다.

ContextWeld는 시각 정보에 작업 맥락과 기준 문서의 근거를 연결한다. 맥락이 해석에 도움이 되는 경우뿐 아니라 잘못된 맥락이 오판을 유발하는 경우도 검증한다.

## 주요 기능 목표

- 정형 마킹과 수기 표기의 영역 검출 및 인식 후보 표시.
- 부재·위치·방향·용접 지시의 구조화.
- 현재 작업지시·도면·WPS의 대상·개정·유효 시점과 일관성 검토.
- 표기 규칙과 용접 기준 검색을 통한 근거 및 조건 후보 제시.
- 불확실하거나 충돌하는 결과의 작업자 승인·수정·보류.
- 원본 이미지부터 해석·추천·확인 이력까지의 추적성 확보와 명시적 요청에 의한 별도 재검토.

```text
사진 → 표기 검출·인식 → 의미 구조화 → 맥락·기준 대조
                                     ↓
                            조건 후보 또는 확인 요청
                                     ↓
                              작업자 확인·이력 저장
```

## 문서

| 문서 | 내용 |
|---|---|
| [현재 데모 구현 기준](docs/DEMO_SPEC.md) | 확정 범위, 단일 시나리오, 데이터 계약, 관리자 재생, Runpod 인계, 완료 기준·미정 항목 |
| [OCR와 시각 관계 인식 구성](docs/OCR_PIPELINE_SPEC.md) | 초기 모델 구성, 문자·화살표·기호·대상 관계, 입출력·재촬영·명시적 재검토·검증 기준 |
| [문서 적용 계획](docs/DOCUMENT_APPLICATION_PLAN.md) | 원문 확보·등록·표 검수, 정확 조회와 RAG, 필드별 근거·문서 검증 |
| [용접 로봇 입력 상세 명세](docs/WELDING_ROBOT_INPUT_SPEC.md) | 현대·두산 공식 입력 항목·단위·조건부 제약의 기준. 실제 제어 지원을 뜻하지 않음 |
| [Pod v1 환경 기록](docs/POD_VER1.md) | Runpod·Isaac·ROS·Foxglove 준비 안내, 실제 확인 결과와 남은 검증 |
| [Isaac 기준 장면 실행](docs/ISAAC_SCENE.md) | UR10 손목 A/B RGB·고정 반사·Foxglove 두 영상의 검증 결과, 재실행·중단·보존 안내 |
| [실제 인식·문서 검색 실행](docs/RUNPOD_INFERENCE.md) | 고정 모델·환경, OCR/VLM 실행·원문 위치 검색·결과 보존·검증 |
| [문서 조건·모의 전달 실행](docs/DOCUMENT_DEMO.md) | 실제 관측과 모사 문서 연결, WPS 원문 범위·누락/충돌 검사, HTTP 모의 수신·별도 묶음 검증 |
| [사용자 수정·명시적 재검토](docs/EXPLICIT_REVIEW.md) | 수정 저장 → 선택 수정만 쓰는 새 재검토 → `--deliver` 때만 모의 전달의 CLI, `review-bundle.v1` 계약·검증, 실제 서버 실행 결과와 한계 |
| [문서 실행 기록 오프라인 조회](docs/DOCUMENT_REVIEW_VIEWER.md) | 검증된 문서·재검토 묶음 한 건을 원본 이미지·모델 출력·수정 기록·WPS 근거·모의 수신 내역을 담은 단일 HTML로 내보내기 |
| [Runpod 자료 준비](docs/RUNPOD_DATA_SETUP.md) | 사진·근거 원문 다운로드, 로컬 전송 대안, 실제 서버 확보 결과와 해시 확인 |
| [첫 장면 실행 안내](docs/FIRST_SCENE.md) | 후보·작업지시 입력, 판정 규칙, 실행·검증과 한계 |
| [실험실](experiments/README.md) | E1~E7 계획, 실제 OCR 실험 결과·실패 사례·재현 코드 |
| [개발 기획](docs/DEVELOPMENT_PLAN.md) | 초기 조사·실험의 배경과 최신 범위에 맞춘 적용 구분 |
| [프로젝트 개요](docs/PROJECT_BRIEF.md) | 문제 정의, 미션 요구사항, 기능 범위, 평가 계획 |
| [마일스톤](docs/MILESTONES.md) | 현재 완료 기준·실제 진행 상태와 세분화 논의 항목. 새 일정은 미확정 |
| [데이터 요구사항](docs/DATA_REQUIREMENTS.md) | 필요한 자료와 현장 검증 항목 |
| [참고 자료](docs/SOURCES.md) | 대회·도메인 출처와 적용 범위 |
| [공개 자료·시나리오 조사](docs/PIPELINE_OPEN_RESOURCES_AND_SCENARIO.md) | 이전 모델 후보·PCC 검증 예시의 조사 기록. 현재 구현 명세보다 우선하지 않음 |
| [제출 기획서](docs/references/idea-proposal.pdf) | ContextWeld 아이디어 요약서 |
| [미션 정의서](docs/references/mission-03.pdf) | HD현대로보틱스 미션 03 원문 |

## 디렉토리 구조

```text
.
├── README.md
├── .gitignore
├── docs/
│   ├── PROJECT_BRIEF.md
│   ├── MILESTONES.md
│   ├── DATA_REQUIREMENTS.md
│   ├── SOURCES.md
│   └── references/           # 기획서와 미션 원문
├── src/contextweld/          # 애플리케이션 구현
├── tests/                    # 핵심 기능 검증
├── experiments/              # 기술 선택 실험·실제 출력·레포트
├── scripts/                  # 데이터 준비·실행·평가 보조 도구
├── configs/                  # 비밀정보를 제외한 설정
├── data/
│   ├── README.md
│   ├── raw/                 # 원본 현장 자료, Git 제외
│   ├── examples/            # 공개 가능한 개발·시연 사례
│   ├── knowledge/           # 공개 가능한 표기 규칙·기준 자료
│   └── eval/                # 공개 가능한 평가 사례·정답
└── output/
    ├── evaluations/         # 평가 결과
    ├── demo/                # 시연 영상·스크린샷
    └── presentation/        # 발표자료
```

현재 `src/contextweld`에는 후보 연결, 실제 OCR/VLM 실행·기록, 문서 추출·검색, 문서 조건 검사와 모의 수신, 수정 저장(`corrections.py`)·명시적 재검토(`review.py`) 모듈이 있다. `scripts`에서 인식·검색·문서 연결·묶음 검증과 Isaac 장면 생성·ROS 영상 송출을 실행한다. `configs/document_demo`에는 모사 작업지시·도면·범위 검토용 프로파일이 있고, `configs/isaac_scene`에는 검증한 기준 장면 설정이 있다. `data/knowledge`에는 원문 위치와 검수 범위를 보존한 WPS 구조화 자료가 있다. `tests`에는 자동 테스트, `data/examples`에는 기존 가상 작업지시 예제가 있다. A/B 촬영과 인식·문서 처리를 한 실행으로 연결하는 작업, 시각 관계 재해석·수정 입력 화면·관리자 화면은 후속 범위다. experiments/의 OCR은 별도 실험용이다. 원본 현장 자료와 생성 산출물은 기본적으로 Git 추적에서 제외한다. 데이터 공개 기준은 [데이터 안내](data/README.md)를 따른다.
