# 수기 마킹과 로봇 작업 연결 조사

조사일: 2026-10-26. **설계 제안과 외부 참고자료**이며 구현 완료 기록이 아니다. 외부 코드는 현재 환경에서 설치·실행 검증하지 않았다. 현재 완료 범위는 [데모 스펙](DEMO_SPEC.md)과 [실행 기록](../runs/LOCAL_RESUME_VERIFICATION.md)을 따른다.

수기 마킹이 용접할 이음과 작업 구간을 결정하도록 확장한다. 첫 시연 후보는 **같은 부재에서 마킹만 바꾸면 선택된 이음과 로봇 이동 경로가 바뀌는 장면**이다. 기존 Isaac Sim에 깊이 정보와 운동 계획을 연결하는 방식을 우선 검토한다. 새로운 강화학습은 로봇 이동의 선행 조건이 아니다.

## 현재 연결과 부족한 부분

현재 [통합 파이프라인](../runs/WELD_PIPELINE.md)은 사진의 부재번호·이음 표기 → 등록 작업지시 → 문서 검토 → 등록 조건 → 제조사 입력 변환 → HTTP 모의 수신을 연결한다. 마킹은 작업 식별에 영향을 주지만 전류·전압·속도는 미리 작성한 시연 레시피에서 가져온다.

| 정보 | 현재 출처와 상태 | 필요한 확장 |
|---|---|---|
| 부재 식별 | 사진 판독과 작업지시 조회 | 기존 근거 연결 활용 |
| 이음 식별 | `J01`과 시연 도면의 `joint_marking_map` | 표시와 실제 이음 후보의 공간적 대응 |
| 전류·전압·속도 | 등록 레시피 | 해석된 작업 요구에 맞는 등록 조건 선택 |
| 시작점·끝점·작업 길이 | 경로로 생성하지 않음 | 영상·깊이 또는 정합된 도면에서 계산 |
| 토치 자세·접근·작업·이탈 경로 | 미구현 | 실행 가능한 관절 궤적 생성과 검증 |

근거: [통합 코드](../../src/contextweld/weld_pipeline.py), [조건 변환](../../src/contextweld/robot_input.py), [시연 도면](../../configs/shipyard_pipeline/drawing.json), [조건표](../../configs/document_demo/weld_recipes.json). 실제 판독과 시연 문자열의 관계는 [판독 계보](../runs/RECOGNITION_AND_BINDING.md)를 유지한다.

## 작업과 직접 연결할 기능 제안

| 기능 | 마킹에서 해석할 정보 | 로봇 작업의 변화 |
|---|---|---|
| 대상 선택 | 화살표·표시가 가리키는 이음 | 작업할 이음과 경로 변경 |
| 범위 지정 | 시작·끝 표시 또는 명시된 길이 | 같은 이음의 작업 구간 변경 |
| 방식 선택 | 지원 표기 안의 용접 종류·치수·간헐 용접 지시 | 구간 구성과 적용 조건 후보 변경 |

첫 구현은 대상 선택과 범위 지정에 한정한다. 화살표를 용접 진행 방향으로 자동 간주하지 않는다. 실제 표기의 의미를 확인하고 시연용 약속은 별도로 명시한다. 모호하거나 문서와 충돌하면 확정을 보류한다.

전류·전압을 마킹에서 직접 읽어야만 목표가 성립하는 것은 아니다. 마킹이 작업 대상과 범위를 결정하고 문서가 공정 조건을 제공해도 작업과 직결된다. 반대로 표시가 바뀌어도 같은 이음·경로·조건을 내보내면 고정 시나리오 조회를 넘어섰다는 증거가 되지 않는다.

## 해외 연구와 제품 사례

### 수기 윤곽에서 로봇 프로그램 생성

Poznań University of Technology의 2020년 연구는 손으로 그린 윤곽을 카메라와 OpenCV로 처리하고 ABB IRB 140용 RAPID 프로그램으로 변환한다. 실험에는 용접 도구를 대신하는 레이저 장치를 사용했다. 평면 윤곽 인식과 경로 생성의 연결을 참고할 수 있지만 조선소 마킹의 의미나 복잡한 3차원 용접을 검증한 사례는 아니다. 독립 코드 배포는 이번 조사에서 확인하지 않았다. [논문 DOI](https://doi.org/10.3390/sym12091429), [논문 공개 사본](https://pdfs.semanticscholar.org/50a3/70d8360aaddad32cc75adfc70e9c3a19b392.pdf).

### 분필 표시로 용접 대상 지정

DKT는 분필 표시를 카메라로 찾아 가까운 이음을 선택하고 용접하는 흐름을 설명한다. 초기 설정과 용접 조건은 별도로 구성한다. 마킹을 작업자 의도의 입력으로 사용하는 제품 구상에 가깝다. 업체 설명이며 해당 영상은 애니메이션으로 명시돼 있어 독립 성능 검증이나 공개 구현의 근거로 사용하지 않는다. [공식 제품 설명](https://dokuti.com/en/ai-welding-robot/).

### 영상 관심 영역과 점군 결합

2024년 Coarse-to-Fine Detection of Multiple Seams for Robotic Welding은 RGB 영상으로 관심 영역을 찾고 3차원 점군에서 이음을 정밀 추출한다. 이를 응용해 마킹 해석으로 관심 영역을 정하고 기하 처리로 경로를 찾는 역할 분담을 제안한다. 논문 자체가 수기 마킹을 해석한 것은 아니다. [논문 원문](https://arxiv.org/abs/2408.10710).

## 공개 구현 후보

| 프로젝트 | 제공 기능 | 적용 후보와 제약 |
|---|---|---|
| [Welding Path Planner](https://github.com/jasdeeprenny/welding_path_ws) | ROS 2 Humble, 클릭한 영상 좌표를 점군으로 3차원화하고 `PoseArray` 표시 | 클릭을 마킹에서 얻은 대상·구간으로 대체하는 구조 참고. 경로 표시가 로봇 관절 실행을 뜻하지 않음. 재사용 전 라이선스 확인 필요 |
| [RoboWeldAR](https://github.com/ikh-innovation/roboweldar-weld-seam-detection) | 3차원 장면의 금속 패널과 위치·자세를 가진 용접 선분 후보 생성 | 후보 중 마킹이 지시한 이음을 선택하는 구조 참고. Apache-2.0. 안내 환경은 Python 3.6·CUDA로 의존성 적응 검토 필요 |
| [ROMI Lab Robotic Welding Demo](https://github.com/romi-lab/robotic-welding-demo) | 점군의 홈·중심선·경로 추출과 다층 계획 | 이음 기하 처리 참고. ROS Kinetic·Open3D 0.9 기반. 재사용 전 라이선스 확인 필요 |
| [Scan-N-Plan](https://github.com/ros-industrial-consortium/scan_n_plan_workshop) | 스캔·표면 복원·공구 경로·운동 계획·실행의 ROS 2 구조 | Apache-2.0. 범용 표면 처리이며 마킹 해석·용접 이음 선택은 추가 개발. [기능 안내](https://ros-industrial-consortium.github.io/scan_n_plan_workshop/), [구조](https://ros-industrial-consortium.github.io/scan_n_plan_workshop/architecture.html) |
| [Noether](https://github.com/ros-industrial/noether) | 메시 표면의 공구 경로 생성 | Apache-2.0. 공구 경로와 로봇 관절 운동 계획을 구분해 활용 |
| [Tesseract](https://tesseract-robotics.github.io/tesseract/getting_started.html) | 산업용 운동 계획·충돌 검사·환경 표현 | 운동 계획 후보. OCR 엔진과 다른 프로젝트이며 물리 시뮬레이터 자체는 아님 |

## 시뮬레이션 구성 선택

| 구성 | 역할 | 판단 |
|---|---|---|
| 기존 Isaac Sim + ROS 2 + MoveIt 2 | 카메라·깊이·로봇 장면과 운동 계획 연결 | 기존 조선소 장면·UR10·카메라를 활용하는 우선 후보 |
| Gazebo + ROS 2 + MoveIt 2 | 센서·물리·관절 제어·운동 계획 | 오픈소스 중심 대안. 장면 이전과 센서 설정 필요 |
| MuJoCo + 로봇 모델 | 동역학·제어·반복 실행 | 로컬 운동 실험 후보. 인식과 작업 계획은 별도 구성 |

Isaac Sim 공개 저장소 코드는 Apache-2.0이며 Omniverse Kit와 일부 모델·텍스처 등 추가 구성요소는 별도 조건을 따른다. [공식 라이선스](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/common/licenses-isaac-sim.html). [MoveIt 2 연동 예제](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_moveit.html)는 Franka 기반이므로 현재 UR10 모델·제어기에 맞는 설정이 필요하다. 문서 버전은 설치 환경과 맞춰 선택한다.

Gazebo는 RGB·깊이·RGBD 센서를 제공하며 UR 공식 시뮬레이션 패키지가 있다. ROS 2 Jazzy와 Gazebo Harmonic은 공식 안내의 조합 중 하나다. [센서 기능](https://gazebosim.org/libs/sensors/), [UR 시뮬레이션](https://github.com/UniversalRobots/Universal_Robots_ROS2_GZ_Simulation), [Gazebo 안내](https://gazebosim.org/docs/harmonic/).

MuJoCo는 macOS를 포함한 배포를 제공하며 Menagerie에 UR10e 모델이 있다. 현재 UR10과 같은 모델·제어 설정으로 간주하지 않는다. [MuJoCo](https://github.com/google-deepmind/mujoco), [모델 모음](https://github.com/google-deepmind/mujoco_menagerie).

먼저 필요한 정교함은 좌표 일치, 토치 자세·속도, 도달 가능성·충돌 검사와 궤적 추종이다. 열·용융·응고·용입 품질은 별도 모델과 검증이 필요한 범위다. 움직임 시뮬레이션이나 시각 효과만으로 용접 품질을 입증하지 않는다.

## 로봇 이동과 학습의 구분

목표 경로를 얻으면 좌표 변환, 역기구학, 운동 계획, 궤적 추종 제어로 움직일 수 있다. 새로운 강화학습은 필수가 아니다. MoveIt은 기구학·제약·충돌 검사를 지원하고 Pilz는 점간·직선·원호 이동을 제공한다. [MoveIt 개념](https://moveit.ai/documentation/concepts/), [Pilz 플래너](https://moveit.picknik.ai/main/doc/how_to_guides/pilz_industrial_motion_planner/pilz_industrial_motion_planner.html).

| 작업 | 첫 구현 접근 | 학습 여부 |
|---|---|---|
| 수기 표기 해석 | 기존 인식기와 지원 표기 규약 | 부족한 표기에 추가 학습 검토 |
| 마킹과 이음 대응 | 영상·깊이·도면의 기하 대응 | 제한된 장면에서 필수 아님 |
| 좌표·토치 자세·관절 궤적 | 좌표 변환·역기구학·운동 계획 | 필수 아님 |
| 위치 오차 보정 | 센서 피드백 제어 | 학습 없이도 접근 가능 |
| 경험으로 행동 정책 습득 | 강화학습·모방학습 | 해당 방식을 선택할 때 필요 |

학습을 생략해도 로봇 형상·관절 한계, 토치 끝점(TCP), 카메라 파라미터와 장착 변환, 장애물 모델은 필요하다. 기존 [로봇 코드](../../scripts/isaac/isaac_scene_robot.py)는 계산으로 A/B 촬영 자세를 만드는 기반이며 일반 용접 경로 계획까지 완료한 것은 아니다.

## 첫 구현과 검증 제안

1. 같은 부재에 직선 이음 두 개를 만들고 대상·구간을 지시하는 지원 마킹을 정한다.
2. RGB에 깊이·카메라 파라미터·시각·좌표계 정보를 함께 저장한다. [장면 코드](../../scripts/isaac/run_isaac_shipyard_scene.py)의 현재 RGB 출력에 추가할 작업이다.
3. 표시를 영상 속 이음과 연결하고 깊이 또는 정합된 도면을 통해 로봇 좌표의 시작점·끝점으로 변환한다.
4. 토치 모델·TCP와 접근·작업·이탈 경로를 구성한다. MoveIt 2로 도달 가능성·충돌·관절 제한을 검사하고 궤적을 실행한다.
5. 기존 문서·조건 변환 결과를 같은 작업과 연결하고 관리자에 마킹·선택 이음·계획 경로·실제 추종 경로를 표시한다.

| 입력 변화 | 확인할 결과 |
|---|---|
| 화살표를 왼쪽 이음에서 오른쪽으로 변경 | 선택 이음과 생성·실행 경로가 함께 변경 |
| 같은 이음의 시작·끝 표시 변경 | 작업 구간이 표시와 일치하게 변경 |
| 표시가 두 이음 사이에서 모호함 | 임의 선택 없이 확인 필요로 보류 |
| 경로에 장애물 또는 도달 불가 지점 존재 | 실행 차단과 원인 표시 |

보존할 근거는 원본 영상·깊이, 관측 좌표와 관계, 좌표 변환, 선택 이음, 작업 요구·조건 출처, 계획 궤적과 실제 관절 상태다. 시뮬레이터 정답 형상을 입력으로 사용하면 출처를 명시하고 카메라 인식 성공으로 집계하지 않는다. 물리 로봇 실행과 현대·두산 제어기 연결은 별도 범위다.

후속 구현 전에 지원할 실제 표기 또는 시연 규약, 깊이와 도면 중 사용할 기하 입력, 토치·로봇 모델을 확정한다. 적용 범위를 정한 뒤 구현 명세에 반영하며, 이번 조사는 기존 데모 스펙과 완료 상태를 변경하지 않는다.
