# ContextWeld

**작업 맥락 기반 용접표기 해석 및 조건 추천 시스템**

> **현재 구현 기준: [데모 스펙 v1.9](docs/plan/DEMO_SPEC.md) (2026-10-24).** Runpod에서 단일 시나리오의 인식·해석·재촬영·모의 파라미터 전달을 실행·기록하고, 로컬 관리자 화면에서 조회·재생한다. 근거 원문 적재·정확 조회/RAG도 구성한다. 아이디어 피칭이 목적이며, 데모의 실제 흐름·근거 설명을 우선하고 정확도 목표·독립 평가를 완료 조건으로 요구하지 않는다. 새 환경에서는 이 문서를 먼저 읽는다. 범위는 확정됐으며 전체 데모 구현은 아직 완료되지 않았다. 기존 기획과 충돌하면 데모 스펙이 우선한다.

ContextWeld는 선박 블록과 부재의 정형 마킹·수기 표기를 인식하고, 현재 작업지시·도면·용접 기준을 함께 검토해 작업과 용접조건 후보를 제안하는 프로젝트다. 판단 근거가 부족하거나 정보가 충돌하면 작업자에게 확인을 요청하고 그 결과를 기록한다. 사용자 수정은 별도로 저장하며, 명시적 재검토 요청에서 선택한 기록만 참조한다. 자동 학습·이력 자동 재사용은 이번 범위가 아니다.

[PAC 2026](https://ainnov.co.kr/pac2026) 분과 02 기업 문제 해결형 IR 피칭 대회의 HD현대로보틱스 미션 03을 대상으로 한다. 참가팀은 **Static Duo**다.

이 README의 문서·코드·로컬 검증 갱신일은 **2026-10-24**이다. 전체 데모는 부분 완료 상태다.

## 현재 구현 상태

| 영역 | 완료된 내용 | 남은 내용 |
|---|---|---|
| 인식 → 문서 → 전달 | [조선소 저장 A/B 마킹](docs/runs/WELD_PIPELINE.md)에서 작업지시·시연 도면·WPS 검증·등록조건·현대/두산 입력으로 연결하고, 양쪽 loopback HTTP200 `received`와 원문·ACK 일치 확인 | 실제 작업 적용성, 실기 용접·좌표 경로 생성 |
| 재촬영 | [저장 A/B 분기 모듈](docs/runs/RECAPTURE_LOOP.md) dev 병합, `requires_recapture` 예외 시 루프를 실행·보존하는 기록 단계·CLI·대시보드 읽기 구현. 검증된 저장 결과에서 새 문서·현대/두산 모의 전달 실행으로 재개하고 fixture 검증 | 실제 GPU 루프 및 실제 결과 재개 확인, 요청에 따른 실제 팔 이동 |
| 수정·재검토 | [서버 CLI 수정 저장·명시적 재검토·선택적 전달](docs/runs/EXPLICIT_REVIEW.md), [작업조건 편집·제조사 변환 화면](docs/runs/ROBOT_INPUT_PREVIEW.md) | 인식 결과 자체를 고치는 화면, 시각 관계의 모델 재해석 |
| 관리자 재생 | [오프라인 패키지](docs/runs/ADMIN_DASHBOARD.md), 목업/실제 실행 구분, 통합·시연 실행의 `MANIFEST.roots` 등록, 재촬영·통합 묶음 읽기/검증·조건 편집 연결, 26개 요약·주요 탭 브라우저 확인 | 실제 GPU 재촬영 결과의 A/B 재생, 모든 탭 조합·다운로드 완료 확인 |
| 자료 보존 | [서버 복구 로컬 준비](docs/audit/INSTRUCTIONS/server-artifact-recovery-local-prep.md): 보존 사본 5건 해시 재대조, 회수 후보·기대 해시·서버 명령 정리 | Runpod 재개 후 서버 실물 대조·회수, 모델 가중치·원본 자료 확인 |

2026-10-24 로컬 회귀 테스트는 **180개 통과**했다. 새 GPU 호출 없이 fixture 재촬영 결과에서 문서 검토와 현대·두산 loopback HTTP200 수신을 확인했다. 새 관리자 패키지는 **5,069파일** 검사와 원본 불변 검사를 통과했고, 의미 검사는 `verified 8 · partial 2 · expected failed 11`이다. 통합 실행 두 건은 관리자 검증기를 연결해 허용 실패에서 제외했다. 나머지 과거 문서·재검토 9건, 중단 인식 1건, manifest 없는 목업 1건은 실패 표시를 유지한다. `verify` 종료 코드 0을 모든 묶음의 성공으로 해석하지 않는다. [로컬 재개·브라우저 검증 기록](docs/runs/LOCAL_RESUME_VERIFICATION.md)에 실행 명령·증거 경로·다운로드 미확인 등 검수 한계를 정리했다.

## 실행 근거와 해석 범위

실제 통합 실행 `shipyard-connected-01`에서 A 판독 `BISB3015`는 등록 부재 정확 조회에 실패했고 저장 B의 `BISB30N-15`·`J01`·지시 대상을 읽어 연결했다. B 선택 사유는 `unresolved_target_identity_or_capture_quality`이며 반사 감지 성공으로 해석하지 않는다. 시연 기준값 `BISB30N-15`는 실제 라벨 `B1Sb30N-15`의 오독·정규화 파생값이다([판독·연결 계보](docs/runs/RECOGNITION_AND_BINDING.md)). OCR 원문을 보존하지만 통합 판독은 VLM 단독이며 OCR/VLM 합의로 표시하지 않는다.

재촬영 브리지는 마지막 판독의 `requires_recapture=true`로 연결이 중단된 경우에만 선택적으로 실행한다. 촬영 프레임 해시를 대조하고 루프 번들을 `inputs/recapture-bundle/`에 보존한다. 루프 결과가 `continue`여도 기존 판독 결정을 대체하지 않으며 통합 실행은 `needs_review`·전달 `blocked`로 끝난다. 이 경로는 로컬 테스트로 확인했고 실제 GPU 실행은 남아 있다. 완료된 재촬영 묶음을 명시적으로 선택하는 `--source-kind recapture`는 원본 보류 기록을 유지한 새 실행에서 문서·전달을 계속한다. 추가 모델 호출 없이 마지막 관측의 계보·대상 관계를 검증하며 fixture와 실제 모델 출처를 구분한다.

[조선소 `live-03`](docs/runs/ISAAC_SHIPYARD_SCENE.md)의 UR10 손목 A/B RGB·예약 관절 이동·Foxglove 영상 수신은 확인했다. 현재 `pre_captured` 방식은 모델 판단에 따른 팔 이동 폐루프가 아니다. 합성 표기 `J01`은 시연 도면의 `joint_marking_map`으로만 `JOINT-DEMO-01`에 연결한다. 용접 수치는 사진에서 검출한 값이 아니라 등록된 시연 작업조건이며, WPS 선택 헤더·대표층 전사 확인은 사람의 적용 승인이 아니다. 사진의 실제 재질·두께·현장 WPS 적용성은 미확인이다.

[PV2 축소 실행](experiments/pipeline_v2/REPORT.md)은 공개 사진 8장의 개발 진단이다. 단독 판독은 OCR 5/8·VLM 2/8이었고, 현재 합의 게이트의 잘못된 자동 확정은 0/8이지만 8장 모두 작업자 확인으로 보냈다. 보류 4장은 후보에 정답이 있었고, 두 판독기가 같은 오답에 합의한 반례도 2건 기록했다. [CTX-001](experiments/context_ablation/REPORT.md)과 2026-10-09 이전 파일럿은 정답 포함 후보에 따른 평가 설계 문제로 현재 성능·발표 근거에서 제외하고 출처 추적용으로 보존한다.

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

전체 목록과 읽는 순서는 **[문서 색인](docs/README.md)**에 있다. 아래는 자주 보는 문서다.

| 문서 | 내용 |
|---|---|
| [현재 데모 구현 기준](docs/plan/DEMO_SPEC.md) | 확정 범위, 단일 시나리오, 데이터 계약, 관리자 재생, 완료 기준·미정 항목 |
| [마일스톤](docs/plan/MILESTONES.md) | 실제 진행 상태와 P0~P5 완료 기준 |
| [로컬 재개·검증](docs/runs/LOCAL_RESUME_VERIFICATION.md) | GPU 없이 저장 재촬영 결과로 문서·모의 전달 재개, 관리자 검증·브라우저 확인 |
| [통합 파이프라인](docs/runs/WELD_PIPELINE.md) | 마킹 판독부터 제조사 입력·HTTP 모의 수신까지의 최신 종단 실행 |
| [작업조건·제조사 변환](docs/runs/ROBOT_INPUT_PREVIEW.md) | 등록조건 자동 적용과 현대 Hi6·두산 DRL 입력 변환 화면 |
| [오프라인 관리자 패키지](docs/runs/ADMIN_DASHBOARD.md) | 여러 실행을 서버 없이 조회·재생하는 내보내기 패키지 |
| [OCR와 시각 관계 인식 구성](docs/spec/OCR_PIPELINE_SPEC.md) | 모델 구성, 문자·화살표·기호·대상 관계, 입출력·재촬영·검증 기준 |
| [용접 로봇 입력 상세 명세](docs/spec/WELDING_ROBOT_INPUT_SPEC.md) | 현대·두산 공식 입력 항목·단위·제약의 기준. 실제 제어 지원을 뜻하지 않음 |
| [데이터·모델 출처](docs/sources/DATA_MODEL_PROVENANCE.md) | 확보 파일·모델의 원출처·revision·해시·가공 과정 |
| [Pod v1 환경 기록](docs/setup/POD_VER1.md) | Runpod·Isaac·ROS·Foxglove 준비와 확인 결과 |
| [실험실](experiments/README.md) | PV2 축소 실행, 설계가 무효화된 CTX-001, 과거 파일럿의 보존 범위 |
| [제출 기획서](docs/references/idea-proposal.pdf) · [미션 정의서](docs/references/mission-03.pdf) | 대회 제출물과 미션 원문 |

## 디렉토리 구조

```text
.
├── README.md
├── conftest.py               # 테스트가 src/를 찾도록 경로 설정
├── docs/
│   ├── README.md             # 문서 색인
│   ├── plan/                 # 범위·기획·요구사항·과거 조사
│   ├── spec/                 # 인식 구성·제조사 입력 명세
│   ├── runs/                 # 실제 실행 기록
│   ├── setup/                # Runpod 환경·자료 준비
│   ├── sources/              # 외부 출처와 데이터·모델 이력
│   ├── audit/                # 진단·처방과 실행 후속 상태
│   ├── assets/               # 2026-10-05 단독 HTML 기획서·안내
│   ├── images/               # 장면 미리보기 이미지
│   └── references/           # 기획서와 미션 원문
├── src/
│   ├── contextweld/          # 인식·문서·검증·전달 구현
│   └── contextweld_dashboard/  # 오프라인 관리자 패키지 생성기
├── scripts/
│   ├── isaac/                # Isaac 장면 생성·ROS 송출·수신 점검
│   ├── prepare/              # 자료·모델·색인 준비
│   ├── run/                  # 인식·문서·재검토·통합 실행
│   ├── export/               # 오프라인 조회·관리자 내보내기
│   └── verify/               # 저장 묶음 검증
├── tests/                    # 핵심 기능 검증
├── experiments/              # 기술 선택 실험·실제 출력·레포트
├── configs/                  # 비밀정보를 제외한 설정
│   ├── document_demo/        # 모사 작업지시·도면·등록조건·범위 프로파일
│   ├── isaac_scene/          # 작업대·조선소 장면 설정
│   ├── robot_profiles/       # 현대 Hi6·두산 DRL 입력 프로파일
│   └── shipyard_pipeline/    # 통합 실행용 시연 도면
├── data/
│   ├── raw/                  # 원본 현장 자료, Git 제외
│   ├── examples/             # 공개 가능한 개발·시연 사례
│   ├── knowledge/            # 공개 가능한 표기 규칙·기준 자료
│   └── eval/                 # 공개 가능한 평가 사례·정답
└── output/                   # 생성 산출물, Git 제외
    ├── evaluations/
    ├── demo/
    └── presentation/
```

`src/contextweld`에는 후보 연결(`matching.py`), 실제 OCR/VLM 실행·기록(`recognition.py`), 문서 추출·검색(`documents.py`), 문서 조건 검사와 모의 수신(`workflow.py`·`mock_delivery.py`), 수정 저장(`corrections.py`)·명시적 재검토(`review.py`), 등록조건의 제조사 입력 변환(`robot_input.py`)과 마킹부터 전달까지의 통합 실행(`weld_pipeline.py`), 저장 A/B 분기(`recapture_loop.py`)와 기록 연결(`recapture_bridge.py`), 검증된 저장 관측의 대상 연결(`recapture_binding.py`)이 있다. `src/contextweld_dashboard`는 검증된 실행 묶음을 서버 없이 여는 관리자 패키지를 만든다.

`scripts`는 역할별로 나뉘어 있다. 준비는 `prepare/`, 인식·문서·재검토·통합 실행은 `run/`, Isaac 장면과 ROS 송출은 `isaac/`, 오프라인 조회·관리자 내보내기는 `export/`, 저장 묶음 검증은 `verify/`에 있다.

`configs/document_demo`에는 모사 작업지시·도면·등록조건과 범위 검토용 프로파일이, `configs/isaac_scene`에는 기존 작업대와 조선소 수기 장면의 설정이, `configs/robot_profiles`에는 현대·두산 입력 프로파일이 있다. `data/knowledge`에는 원문 위치와 검수 범위를 보존한 WPS 구조화 자료가, `data/examples`에는 가상 작업지시 예제가 있다.

시각 관계의 모델 재해석, 인식 결과를 화면에서 고치는 입력, 모델 판단에 따른 재촬영 폐루프는 후속 범위다. `experiments/`의 실험 코드는 제품 경로와 분리해 보존한다. 원본 현장 자료와 생성 산출물은 기본적으로 Git 추적에서 제외하며, 데이터 공개 기준은 [데이터 안내](data/README.md)를 따른다.
