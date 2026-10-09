# Pod v1 — Runpod L40S 개발 환경

기록일: **2026-10-10, Asia/Seoul**. 환경 기록 버전: **1.0**.

PAC2026의 시뮬레이션 구현에 사용하는 일회성 Runpod Pod의 사양, 설치 절차, 환경변수와 실행 방법을 기록한다. 제품 범위는 [데모 스펙](DEMO_SPEC.md)을 따른다. 이 문서의 설치 안내와 실제 실행으로 확인한 상태는 구분한다.

**최신 상태:** 2026-10-10 후속 실행에서 Isaac Sim 6.1·UR10 손목 카메라의 A/B RGB와 Foxglove 두 영상을 검증했다. 아래 1.1절과 호환성 앱 출력은 초기 확인 당시의 기록이며, 최신 결과는 1.2절과 [Isaac 기준 장면 실행 안내](ISAAC_SCENE.md)를 따른다. 전체 데모 완료를 뜻하지 않는다.

## 1. 운영 방식과 확인 범위

이 환경은 **영속 저장소 없이 사용해도 되는 일회성 개발 서버**로 운용한다. 현재 `/workspace` 경로를 그대로 사용하며, 영속 볼륨 확보를 후속 설치의 선행 조건으로 두지 않는다. 재사용할 소스·설정·실행 스크립트·문서는 GitHub에 선별 보존한다. 서버 재생성 시 패키지 설치와 인증을 다시 수행할 수 있다.

### 1.1 초기 환경 확인 기록

관측값은 초기 서버 운영자가 제공한 명령 출력에 근거한다. 아래 `[확인 필요]`는 당시의 미확인 상태를 보존한 것이다. 명령 안내만으로 당시 실행 완료를 소급 기록하지 않는다.

| 항목 | 확인된 상태 |
|---|---|
| Ubuntu·GPU·드라이버 | OS와 `nvidia-smi` 출력 확인 |
| Vulkan | NVIDIA L40S 장치 열거 확인 |
| Isaac 호환성 검사 앱 | `isaacsim.exp.compatibility_check-6.1.0`의 `app ready`와 셸 프롬프트 복귀 확인 |
| 호환성 검사 전체 판정 | `[확인 필요]` 전체 검사 결과·종료 코드는 확보하지 않음 |
| GitHub 인증·서버 clone | `[확인 필요]` 서버의 인증 결과·체크아웃 커밋 미확보 |
| Claude Code 설치·로그인 | `[확인 필요]` 설치 버전·인증 결과 미확보 |
| ROS Jazzy 설치·통신 | `[확인 필요]` 패키지 조회·토픽 송수신 결과 미확보 |
| Isaac 본 앱·ROS Bridge | `[확인 필요]` 실행 명령 안내 후 기동 로그 미확보 |
| Foxglove Bridge·SSH 터널 | `[확인 필요]` 서버 기동·로컬 수신 결과 미확보 |
| 장면·카메라 RGB·로봇 토픽 | `[확인 필요]` 실제 센서 렌더링·발행 결과 미확보 |

### 1.2 후속 실제 장면·송출 확인 — 2026-10-10

`output/isaac-scene-20261010/live-01/`에서 기존 환경을 사용해 실제 렌더링과 송출을 확인했다. 초기 호환성 앱의 `app ready` 로그와 별개 실행이다.

| 항목 | 후속 확인 결과 |
|---|---|
| Isaac 장면·로봇 | Isaac Sim 6.1에서 UR10 관절 이동·고정 손목 장착, 같은 정형 마킹·작업대의 A/B 원본 RGB와 금속 반사 확인 |
| 카메라 | 손목 18 mm·전체 장면 26 mm, 1280×720. A/B 위치 오차 2.80/7.61 mm·회전 오차 0.00476/0.00972 rad, 설정한 허용오차 이내 |
| ROS 송출 | 시스템 ROS Jazzy·domain 26·FastDDS 재사용. Isaac가 저장한 PNG를 별도 시스템 Python 송출기가 `CompressedImage`로 발행. native Isaac ROS image writer는 이 실행에서 사용하지 않음 |
| Bridge 수신 | 기존 `127.0.0.1:8765` bridge에서 6개 토픽 수신. 손목·전체 장면·`/camera` 총 264개 PNG 디코딩, 이미지/상태의 촬영 시각·해시 264쌍 일치 |
| 연속성 | 상태 sequence 45–132의 88개 연속 수신, A·B·양방향 이동 확인. 전부 `new_capture`·`recent_capture` |
| 로컬 화면 | 기존 SSH 터널·Foxglove 연결에서 손목과 전체 장면 두 영상 확인 |
| 보존 | 기존 자료 1,339개 파일 변경·누락 없음, 기존 Isaac·bridge 프로세스 식별 일치. 설정·코드 사본·A/B 영상과 해시 보존 |

상세 근거는 `output/isaac-scene-20261010/env-audit/`의 `live-01-reception-01-summary.json`, `live-01-crosscheck.json`, `live-01-preservation-check-final.json`이다. 실행·ROS source 순서·토픽·시각 의미·소유 PID 확인 후 중단은 [Isaac 기준 장면 안내](ISAAC_SCENE.md)에 있다. 기존 bridge·터널·앱을 일괄 재시작하지 않는다.

P1은 기존 기준 장면에서 달성했다. 기존 정형 마킹·작업대 결과를 보존하고 조선소 병풍형 강판 패널·중앙 수기 메모 개선은 별도 구현 대기 상태다. 현재 A/B는 `capture_mode=pre_captured`인 예약 시연이며 모델 판단으로 팔을 움직이는 폐루프가 아니다. [문서 한 건의 오프라인 HTML 조회](DOCUMENT_REVIEW_VIEWER.md)는 별도 부분 구현이며 브라우저 시각 검수는 미완료다. 전체 P2·P3·P4와 여러 실행 통합·A/B 관리자 재생도 미완료다. 초기 호환성 검사 전체 PASS나 Isaac native ROS 영상 경로의 검증으로 확대하지 않는다.

## 2. 서버 사양과 경로

### 2.1 관측된 사양

| 항목 | 출력값 또는 기록 |
|---|---|
| 운영체제 | Ubuntu 24.04.3 LTS, `noble` |
| 실행 계정 | `root` |
| GPU | NVIDIA L40S |
| NVIDIA 드라이버 | `580.126.09` |
| GPU 메모리 | `46068 MiB` — `nvidia-smi` 표시값 |
| Vulkan Instance Version | `1.3.275` |
| GPU Vulkan API Version | `1.4.312` |
| Vulkan driver ID | `DRIVER_ID_NVIDIA_PROPRIETARY` |
| 디스크 | `/workspace`, `/` 조회가 모두 `overlay`, `200G`, 마운트 `/`로 표시 |
| 디스크 사용량 | 검사 당시 `344M`, 가용 `200G` — 반올림된 표시값 |
| 메모리 | `free -h`의 전체 표시값 `1.5Ti`; Pod 전용 할당량은 `[확인 필요]` |
| Swap | `0B` |
| Runpod 템플릿·이미지 태그 | `[확인 필요]` |
| 실제 CPU·RAM 제한 | `[확인 필요]` Runpod 할당 정보 또는 cgroup 제한 확인 필요 |

Vulkan Instance와 GPU API는 서로 다른 항목이다. 두 버전의 차이를 설치 실패로 판단하지 않는다. `free -h`는 호스트 메모리를 표시할 수 있으므로 전용 RAM 용량으로 사용하지 않는다.

`/workspace`도 루트 overlay에 있는 것으로 관측됐다. `[추론]` 별도 영속 볼륨이 연결되지 않은 구성으로 보며, 이번 운영에서는 이를 허용한다. Runpod의 container disk는 중지 시 소실될 수 있다. 일반 Volume과 Network Volume의 수명은 별도이며 경로 이름만으로 영속성을 판단하지 않는다. [Runpod 저장소](https://docs.runpod.io/pods/storage/types)

### 2.2 사용할 경로

아래는 구성 기준 경로이며, 모든 파일의 실제 생성 여부를 확인한 목록은 아니다.

| 경로 | 용도 |
|---|---|
| `/workspace/PAC2026` | 프로젝트 `dev` 체크아웃 |
| `/workspace/venvs/isaacsim-6.1` | Isaac 전용 Python 가상환경 |
| `/workspace/pac-env.sh` | ROS 공통 환경 설정 |
| `/opt/ros/jazzy` | 시스템 ROS Jazzy 설치 |
| `/run/user/0` | root의 임시 런타임 경로 |
| `/root/.local/bin/claude` | 기본 설치 기준 Claude Code 실행 경로 |
| `/workspace/PAC2026/output/environment/pod-ver1` | 선택적으로 남기는 환경 점검 결과, Git 제외 |

## 3. 구성과 터미널 역할

```text
Runpod Pod
  Isaac Sim + ROS Bridge ── ROS 2 / Fast DDS ── Foxglove Bridge
                                                 127.0.0.1:8765
                                                        │
                              SSH 로컬 포워딩 / TCP     │
                                                        ▼
Mac                                      127.0.0.1:8765
                                         Foxglove 앱
```

ROS 통신은 같은 Pod 내부에서 수행한다. Runpod의 공개 UDP 연결을 전제로 ROS DDS를 Mac까지 직접 확장하지 않는다. 로컬에는 Foxglove WebSocket을 SSH 터널로 전달한다. [Runpod 네트워크](https://docs.runpod.io/pods/configuration/expose-ports)

| 터미널 | 역할 | 환경 |
|---|---|---|
| 서버 A | Isaac Sim + ROS Bridge | ROS 공통 설정 + Isaac 가상환경 |
| 서버 B | Foxglove Bridge | ROS 공통 설정, Isaac 가상환경 비활성 |
| 서버 C, 선택 | 데모 발행·토픽 검사 | ROS 공통 설정 |
| Mac | SSH 포워딩 | Runpod에 등록한 개인 키 |

서버 A·B와 Mac의 SSH 터널은 계속 실행 상태로 둔다. 호환성 검사 앱은 별도 프로세스이며 종료된 뒤 같은 서버 A 터미널에서 Isaac 본 앱을 실행할 수 있다.

## 4. 환경변수

다음은 재현에 사용할 설정이다. 각 변수의 실제 적용값 전체를 서버에서 수집한 것은 아니다.

| 변수 | 값 | 적용 위치·의미 |
|---|---|---|
| `NVIDIA_DRIVER_CAPABILITIES` | `all` | 새 Pod의 시작 설정. 그래픽·CUDA 등 드라이버 기능 주입 |
| `LANG` | `en_US.UTF-8` | 서버 셸의 UTF-8 로케일 |
| `PATH` 추가 | `$HOME/.local/bin` | Claude 실행 파일 검색 |
| `ROS_DOMAIN_ID` | `26` | Isaac·ROS 노드·Foxglove에 동일 적용 |
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` | 같은 Pod에서 Fast DDS 사용 |
| `XDG_RUNTIME_DIR` | `/run/user/0` | root 소유, 권한 `0700`인 임시 경로 |
| `OMNI_KIT_ACCEPT_EULA` | `YES` | NVIDIA 약관에 동의한 경우 Isaac 실행 셸에서 적용 |
| `OMNI_KIT_ALLOW_ROOT` | `1` | 현재 root 계정으로 Isaac 실행 |
| `RUNPOD_IP` | 실제 Public IP로 치환 | Mac의 SSH 명령용 변수 |
| `RUNPOD_SSH_PORT` | 실제 외부 SSH 포트로 치환 | Mac의 SSH 명령용 변수. Pod 내부 `22`와 다를 수 있음 |

`NVIDIA_DRIVER_CAPABILITIES`는 컨테이너 시작 때 마운트할 드라이버 라이브러리를 결정한다. 실행 중인 셸의 `export`만으로 누락된 그래픽 라이브러리가 주입되지는 않는다. **현재 Pod는 Vulkan에서 L40S가 보이므로, 변수값 미확인만을 이유로 Pod 설정을 변경하지 않는다.** [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html)

ROS 설정은 프로세스를 실행할 셸마다 불러온다. Isaac 가상환경을 모든 셸에 자동 활성화하지 않고, 시스템 ROS를 source한 상태에서 Isaac 내부 ROS 라이브러리의 `LD_LIBRARY_PATH`를 임의로 중복 추가하지 않는다.

## 5. 설치·준비 명령

이 절은 **Ubuntu 24.04 / root / Bash** 기준 재구성 절차다. 이미 수행한 설치·clone은 상태를 확인하고 필요한 부분만 실행한다. 명령 블록 자체는 서버에서 실행 완료했다는 증거가 아니다.

### 5.1 기본 도구와 그래픽 확인

```bash
apt-get update
apt-get install -y \
  ca-certificates curl software-properties-common locales

add-apt-repository -y universe
apt-get update
apt-get install -y \
  git gh tmux unzip build-essential \
  python3.12 python3.12-venv python3.12-dev \
  libvulkan1 vulkan-tools libgl1 libegl1 libgomp1

locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8
export LANG=en_US.UTF-8

install -d -m 700 /run/user/0
export XDG_RUNTIME_DIR=/run/user/0

cat /etc/os-release
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
df -h /workspace /
free -h
vulkaninfo --summary
```

`DISPLAY`가 없어 surface 검사를 건너뛰는 메시지는 headless 환경에서 나타날 수 있다. `XDG_RUNTIME_DIR` 경고는 위 임시 경로로 대응한다. 실제로 이 설정 후 경고가 사라졌는지는 `[확인 필요]`다. NVIDIA L40S가 열거되는지와 Isaac 렌더러의 실제 성공은 각각 확인한다. [XDG 규격](https://specifications.freedesktop.org/basedir/latest/)

현재 드라이버를 Pod 내부에서 다시 설치하지 않는다. NVIDIA의 검증 목록에는 Ada/Linux의 R580 계열이 포함된다. `[추론]` 현재 `580.126.09`에서는 아래 Isaac 구성을 먼저 검증할 수 있다. Isaac 요구사항에 표시된 별도 테스트 드라이버를 현재 Pod의 실측값과 혼동하지 않는다. [Omniverse 드라이버 기준](https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html)

### 5.2 GitHub 연결과 프로젝트 확인

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
gh auth status

cd /workspace
git clone --branch dev --single-branch \
  https://github.com/ukkhnn/PAC2026.git

cd /workspace/PAC2026
git status --short --branch
git rev-parse HEAD
git log -1 --oneline
```

인증 URL과 일회용 코드는 운영자가 Mac 브라우저에서 직접 사용한다. 토큰을 clone URL이나 문서에 넣지 않는다. [GitHub CLI 인증](https://cli.github.com/manual/gh_auth_login)

이미 저장소가 있다면 clone 대신 아래를 사용한다. 로컬 변경을 확인한 뒤 `dev`로 전환해 갱신하며, 이력이 갈라진 경우 강제 초기화하지 않는다. 브랜치 전환이 실패하면 먼저 원인을 확인한다.

```bash
cd /workspace/PAC2026
git status --short --branch
git switch dev && git pull --ff-only origin dev
git rev-parse HEAD
```

서버에서 실제 사용한 커밋은 위 결과로 남긴다. [README](../README.md)와 [데모 스펙](DEMO_SPEC.md)을 먼저 읽는다. 로컬 전용 `AGENTS.md`, `CURRENT_TASK.md`, `.cowork/`는 새 clone에 자동으로 포함되지 않는다.

현재 제품 CLI의 선택적 확인 명령은 다음과 같다. 사진 OCR이나 시뮬레이션을 실행하는 명령은 아니다.

```bash
cd /workspace/PAC2026
PYTHONPATH=src /usr/bin/python3.12 -m unittest discover -s tests -v
PYTHONPATH=src /usr/bin/python3.12 -m contextweld \
  data/examples/part-order-scene.json --case normal
```

### 5.3 Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | bash -s stable

export PATH="$HOME/.local/bin:$PATH"
# 새 설치에서 한 번 추가한다. 이미 같은 설정이 있으면 생략한다.
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

claude --version
claude doctor

cd /workspace/PAC2026
claude
```

로그인은 첫 실행 안내에 따라 직접 수행한다. `stable`은 고정 버전 번호가 아니며 설치 시점과 자동 업데이트에 따라 달라진다. 실제 버전은 `claude --version`으로 별도 기록한다. [Claude Code 설치](https://code.claude.com/docs/en/setup)

### 5.4 ROS 2 Jazzy와 Foxglove 패키지

Ubuntu 24.04의 공식 ROS apt 저장소를 등록한다. ROS 저장소 등록 패키지의 버전은 실행 시 조회된다. [ROS Jazzy 설치](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)

```bash
ROS_APT_SOURCE_VERSION="$(
  curl -fsSL \
    https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
  | /usr/bin/python3.12 -c \
    'import json, sys; print(json.load(sys.stdin)["tag_name"])'
)"

curl -fL -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.noble_all.deb"

dpkg -i /tmp/ros2-apt-source.deb
apt-get update
apt-get install -y \
  ros-jazzy-ros-base \
  ros-dev-tools \
  ros-jazzy-rmw-fastrtps-cpp \
  ros-jazzy-demo-nodes-cpp \
  ros-jazzy-foxglove-bridge
```

공통 환경 파일을 처음 만들 때의 명령이다. 이미 내용을 조정한 파일이 있다면 확인한 뒤 반영한다.

```bash
cat > /workspace/pac-env.sh <<'EOF'
source /opt/ros/jazzy/setup.bash
export LANG=en_US.UTF-8
export ROS_DOMAIN_ID=26
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
EOF

source /workspace/pac-env.sh
ros2 pkg prefix foxglove_bridge
```

### 5.5 Isaac Sim 전용 환경

| 구성 요소 | 설치 기준 | 실제 버전 확인 |
|---|---|---|
| Python | 시스템 Python 3.12 | `[확인 필요]` patch 버전 |
| PyTorch | `2.11.0`, CUDA 12.8 wheel | `[확인 필요]` 설치 목록 |
| Isaac Python 패키지 | `isaacsim[all,extscache]==6.1.0.0` | `[확인 필요]` 설치 목록 |
| Isaac 호환성 앱 | `6.1.0` | 실행 로그에서 확인 |

위 패키지 조합은 기록일의 NVIDIA 공식 Python 설치 문서 기준이다. 전체 의존성 잠금 파일은 아직 확보하지 않았다. 기존 가상환경이 있다면 다시 만들기 전에 패키지 상태를 확인한다. [Isaac Python 설치](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html)

```bash
mkdir -p /workspace/venvs
/usr/bin/python3.12 -m venv /workspace/venvs/isaacsim-6.1
source /workspace/venvs/isaacsim-6.1/bin/activate

python -m pip install --upgrade pip
python -m pip install --no-cache-dir \
  torch==2.11.0 \
  --index-url https://download.pytorch.org/whl/cu128

python -m pip install --no-cache-dir \
  'isaacsim[all,extscache]==6.1.0.0' \
  --extra-index-url https://pypi.nvidia.com

python -m pip check
```

## 6. 검사와 프로세스 실행

### 6.1 호환성 검사 앱 — 관측된 실행 지점

`OMNI_KIT_ACCEPT_EULA=YES`는 NVIDIA 이용약관에 동의한다는 뜻이다. 동의한 경우에만 해당 설정으로 실행한다.

```bash
source /workspace/pac-env.sh
source /workspace/venvs/isaacsim-6.1/bin/activate
install -d -m 700 /run/user/0
export XDG_RUNTIME_DIR=/run/user/0
export OMNI_KIT_ACCEPT_EULA=YES
export OMNI_KIT_ALLOW_ROOT=1

isaacsim isaacsim.exp.compatibility_check \
  --no-window --/app/quitAfter=10
```

확보한 출력 발췌:

```text
[2.782s] [ext: isaacsim.exp.compatibility_check-6.1.0] startup
[2.849s] app ready
```

이후 `(isaacsim-6.1)` 셸 프롬프트로 돌아왔다. 명령에 종료 옵션이 있으므로 계속 실행되는 서버가 아니다. `app ready`는 검사 앱의 시작을 보여주며 전체 검사 PASS, 본 앱 기동, RTX 카메라 이미지 생성, ROS 통신을 증명하지 않는다. [Isaac 요구사항·검사 도구](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)

### 6.2 서버 A — Isaac Sim + ROS Bridge

같은 터미널에서 이어 실행하거나, 새 터미널에서 아래 환경을 다시 불러온다.

```bash
source /workspace/pac-env.sh
source /workspace/venvs/isaacsim-6.1/bin/activate
install -d -m 700 /run/user/0
export XDG_RUNTIME_DIR=/run/user/0
export OMNI_KIT_ACCEPT_EULA=YES
export OMNI_KIT_ALLOW_ROOT=1

isaacsim isaacsim.exp.full --no-window \
  --/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge
```

첫 시작은 확장 로딩·셰이더 준비에 시간이 걸릴 수 있다. 앱을 실행 상태로 유지한다. **Bridge를 켜는 것만으로 `/clock`, 카메라, 관절 상태 토픽이 자동 생성되지는 않는다.** 장면·센서·publisher를 구성하고 시뮬레이션을 실행해야 한다. [Isaac ROS 설정](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_ros.html)

### 6.3 서버 B — Foxglove Bridge

Isaac 가상환경을 활성화하지 않은 새 서버 터미널에서 실행한다. 같은 터미널을 재사용한다면 활성화된 Isaac venv를 `deactivate`한 뒤 진행한다.

```bash
source /workspace/pac-env.sh
ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  address:=127.0.0.1 \
  port:=8765
```

이 프로세스도 계속 실행 상태로 둔다. [Foxglove ROS 2](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2?modality=live), [Bridge 주소·포트 설정](https://github.com/foxglove/foxglove-sdk/blob/main/ros/src/foxglove_bridge/README.md)

### 6.4 Mac — SSH 포워딩과 Foxglove 접속

Runpod **Connect → SSH over exposed TCP**의 Public IP·외부 SSH 포트를 사용한다. Pod의 SSH 서비스가 TCP `22`로 노출되어 있어야 하며, Mac의 키는 Runpod에 등록된 키와 맞아야 한다. 아래 placeholder와 키 경로를 실제 값으로 바꾼다. [Runpod SSH](https://docs.runpod.io/pods/configuration/use-ssh)

```bash
# 로컬 Mac에서 실행
RUNPOD_IP='REPLACE_WITH_PUBLIC_IP'
RUNPOD_SSH_PORT='REPLACE_WITH_EXTERNAL_SSH_PORT'

ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:8765:127.0.0.1:8765 \
  -p "$RUNPOD_SSH_PORT" \
  -i ~/.ssh/id_ed25519 \
  root@"$RUNPOD_IP"
```

정상 연결 시 출력 없이 대기할 수 있다. 터미널을 유지한 채 Mac의 Foxglove 앱에서 **Open connection → Foxglove WebSocket**을 선택하고 접속한다.

```text
ws://localhost:8765
```

서버의 `8765`를 Runpod 공개 포트로 추가할 필요는 없다. Foxglove 연결은 Isaac 데스크톱 화면 스트리밍과 다르며, ROS에서 발행한 데이터를 표시한다.

Mac의 `8765`가 다른 앱에서 사용 중이면 로컬 쪽만 `18765`로 바꿀 수 있다. SSH의 `-L`을 `127.0.0.1:18765:127.0.0.1:8765`로 바꾸고 Foxglove에서 `ws://localhost:18765`로 연결한다.

### 6.5 선택적 연결 검사

서버 C에서 테스트 데이터를 발행한다.

```bash
source /workspace/pac-env.sh
ros2 run demo_nodes_cpp talker
```

다른 ROS 터미널에서 한 건 수신하거나, Mac Foxglove의 **Raw Messages** 패널에서 `/chatter`를 선택한다.

```bash
source /workspace/pac-env.sh
ros2 topic echo /chatter --once
```

Foxglove에서 메시지가 보이면 ROS 데모 노드→Bridge→SSH→Mac 연결을 확인한 것이다. 이는 Isaac 센서나 프로젝트 파이프라인의 통합 검증과 별개다. 이 검사 결과는 현재 `[확인 필요]`다.

## 7. 환경 기록과 종료 전 보존

실제 설치 버전·서버 커밋을 남길 때만 아래를 실행한다. 같은 파일명은 이전 기록을 덮어쓰므로 후속 실행은 별도 기록 경로를 사용한다. 패키지 목록은 설치 현황이며 모든 외부 자산을 포함한 완전한 재현 묶음은 아니다.

```bash
cd /workspace/PAC2026
mkdir -p output/environment/pod-ver1

git rev-parse HEAD > output/environment/pod-ver1/repo-commit.txt
/usr/bin/python3.12 --version > output/environment/pod-ver1/python-system.txt
claude --version > output/environment/pod-ver1/claude-version.txt
dpkg-query -W 'ros-jazzy-*' > output/environment/pod-ver1/ros-packages.txt

/workspace/venvs/isaacsim-6.1/bin/python -m pip list --format=freeze \
  > output/environment/pod-ver1/isaac-packages.txt
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader \
  > output/environment/pod-ver1/gpu.txt
```

없는 패키지나 명령의 오류를 설치 완료로 바꾸어 기록하지 않는다. 인증정보가 섞일 수 있는 전체 `env` 출력, GitHub 토큰, Claude 인증 파일, SSH 개인 키는 환경 기록에 넣지 않는다.

`output/`, 가상환경, 모델 가중치, 원본 데이터는 현재 Git 제외 정책의 대상이다. 필요한 코드·설정·선별한 환경 기록은 공개 가능 내용을 검토해 추적 경로에 저장한다. 보존할 실행 영상·이미지·대용량 결과가 있으면 Pod 종료 전에 별도 다운로드한다. **GitHub에 소스를 보존하는 것과 Git 제외 산출물을 보존하는 것은 별도 작업이다.**

## 8. 초기 환경의 후속 확인 순서 — 과거 기록

아래는 호환성 앱 기동만 확인했던 시점의 순서다. 현재 실제 RGB·손목 카메라·Foxglove 두 영상 확인은 1.2절을 따른다. 다음 구현은 기존 기준 장면을 보존한 형상 개선과 인식·문서·재생 연결이며, 아래 초기 검사를 다시 수행해야만 시작할 수 있는 것은 아니다.

1. 서버의 `git rev-parse HEAD`, Python·Claude·Isaac 패키지 버전을 기록한다.
2. 시스템 ROS 패키지와 Isaac 본 앱·ROS Bridge의 시작 로그를 확인한다.
3. `/chatter`를 사용해 Foxglove·SSH 연결을 검증한다.
4. 시뮬레이션에서 실제 RGB 한 장을 저장하고 해당 센서 토픽을 발행한다.
5. 프로젝트 장면·A/B 촬영·인식·모의 전달을 구현하면서 실행 명령과 결과를 추가한다.

당시 Vulkan 인식과 호환성 검사 앱 기동만으로 전체 데모 완성을 판단하지 않았다. 후속 A/B·Foxglove 검증도 전체 파이프라인 완료와 구분한다. 영속 볼륨 추가는 이번 환경의 필수 후속 작업이 아니다.

## 9. 출처와 변경 기록

외부 공식 문서는 본문의 해당 절에 연결했다. 확인일은 **2026-10-10**이다. `/latest/` 문서는 이후 바뀔 수 있으므로 실제 설치 버전은 명령 출력과 함께 남긴다. 사양과 짧은 실행 로그는 제공된 서버 출력이며, 명령 절차는 공식 문서를 바탕으로 정리한 구성 기준이다.

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.0 | 2026-10-10 | 일회성 L40S Pod의 관측 사양, 환경변수, GitHub·Claude·ROS·Isaac 설치, 프로세스 구분, Foxglove 터널, 실제 확인 범위 기록 |
