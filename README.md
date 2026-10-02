# ContextWeld

**작업 맥락 기반 용접표기 해석 및 조건 추천 시스템**

ContextWeld는 선박 블록과 부재의 정형 마킹·수기 표기를 인식하고, 작업계획·이력·용접 기준을 함께 검토해 작업과 용접조건 후보를 제안하는 프로젝트다. 판단 근거가 부족하거나 정보가 충돌하면 작업자에게 확인을 요청하고 그 결과를 기록한다.

[PAC 2026](https://ainnov.co.kr/pac2026) 분과 02 기업 문제 해결형 IR 피칭 대회의 HD현대로보틱스 미션 03을 대상으로 한다. 참가팀은 **Static Duo**다.

> 현재 단계: 실행 가능한 로컬 spike. 5개 시연 사례, 실제 사진 OCR(macOS), 맥락 대조, 작업자 확인·수정·보류, 이력 저장·JSON 내보내기를 구현했다. 실제 현장 데이터·WPS와 현장 성능 결과는 아직 없다. 기준일: 2026-10-02.

## 빠른 실행

Python 3.10 이상에서 저장소 루트에서 실행한다. 외부 패키지나 API 키는 필요하지 않다.

```sh
python3 scripts/run_demo.py
```

브라우저에서 <http://127.0.0.1:8765>를 연다. 예제는 합성 이미지와 작성된 인식 후보를 사용한다. 업로드 사진은 macOS와 Swift 개발 도구가 있을 때 실제 Apple Vision OCR로 인식한다. 규칙은 시연용이며 전류·전압·이동속도는 미정이다.

[실행·시연 안내](docs/RUN_DEMO.md) · [코드 학습·교체 안내](docs/LEARNING_GUIDE.md) · [검증 기록](docs/VALIDATION.md)

## 해결하려는 문제

선박 부재의 표기는 문자·숫자·기호·약어가 혼재하며 오염·반사·훼손으로 판독이 어렵다. 문자 인식 결과만으로는 해당 표기가 어떤 부재, 작업 위치, 방향, 용접 작업을 의미하는지 판단하기 어렵다.

ContextWeld는 시각 정보에 작업 맥락과 기준 문서의 근거를 연결한다. 맥락이 해석에 도움이 되는 경우뿐 아니라 잘못된 맥락이 오판을 유발하는 경우도 검증한다.

## 주요 기능 목표

- 정형 마킹과 수기 표기의 영역 검출 및 인식 후보 표시.
- 부재·위치·방향·용접 지시의 구조화.
- 작업계획·선행작업·관련 이력과의 일관성 검토.
- 표기 규칙과 용접 기준 검색을 통한 근거 및 조건 후보 제시.
- 불확실하거나 충돌하는 결과의 작업자 승인·수정·보류.
- 원본 이미지부터 해석·추천·확인 이력까지의 추적성 확보.

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
| [Spike 명세](docs/SPIKE_SPEC.md) | 시연 사례, 가정, 구현 경계 |
| [프로젝트 개요](docs/PROJECT_BRIEF.md) | 문제 정의, 미션 요구사항, 기능 범위, 평가 계획 |
| [마일스톤](docs/MILESTONES.md) | 단계별 목표일, 완료 기준, 진행 상태 |
| [데이터 요구사항](docs/DATA_REQUIREMENTS.md) | 필요한 자료와 현장 검증 항목 |
| [참고 자료](docs/SOURCES.md) | 대회·도메인 출처와 적용 범위 |
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
│   ├── SPIKE_SPEC.md
│   ├── RUN_DEMO.md
│   ├── LEARNING_GUIDE.md
│   ├── VALIDATION.md
│   └── references/           # 기획서와 미션 원문
├── src/contextweld/          # 애플리케이션 구현
├── tests/                    # 핵심 기능 검증
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

구현은 Python 표준 라이브러리 서버·SQLite, HTML/CSS/JavaScript 화면, macOS의 Swift OCR 어댑터로 구성한다. 실행 기록과 업로드 자료는 `.local/`에 저장하고 Git 추적에서 제외한다. 원본 현장 자료와 생성 산출물은 기본적으로 Git 추적에서 제외한다. 데이터 공개 기준은 [데이터 안내](data/README.md)를 따른다.
