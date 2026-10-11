# Isaac 야간 작업장 A/B 영상

기준일: **2026-10-10**. Isaac Sim 6.1에서 UR10 손목 카메라가 두 자세로 이동하고, 고정 작업등의 금속 반사를 실제 RGB로 렌더링한다. ROS Jazzy가 저장된 RGB를 기존 Foxglove 연결로 송출한다. [데모 명세](../plan/DEMO_SPEC.md)의 장면·촬영 부분 실행이며, 기존 [문서 검토 실행](DOCUMENT_DEMO.md)과 아직 자동 연결되지 않았다.

## 확인 상태

최종 기준 실행은 **`output/isaac-scene-20261010/live-01/`**이다. 손목 18 mm·전체 장면 26 mm 설정에서 A/B RGB, 관절 이동, 고정 장착 변환과 Foxglove의 손목·전체 장면 두 영상을 확인했다. A는 고정 작업등 반사가 표기 중앙을 가리고, B는 `BISB30N-15`, `J01`, 화살표 전체가 보인다. 글자 확인은 육안 검수이며 OCR/VLM 측정 결과가 아니다. Foxglove 레이아웃 이름은 `ContextWeld · 기준 장면 AB`이며, 두 Image 패널의 실제 내보내기 설정도 보존했다.

| live-01 최초 정착 촬영 | 목표 대비 카메라 위치 오차 | 회전 오차 | 고정 장착·USD/PhysX 대조 |
|---|---:|---:|---|
| A | 2.80 mm | 0.00476 rad | 통과 |
| B | 7.61 mm | 0.00972 rad | 통과 |

허용오차는 위치 15 mm, 회전 0.018 rad다. 위 값은 최종 `manifest.json`의 A/B 촬영 기록이며 설정·코드 사본·A/B 이미지 4개의 해시도 일치한다. 이전 `tune-07`의 22 mm 결과는 튜닝 기록으로 보존한다.

서버 Foxglove WebSocket을 약 40초간 수신해 다음을 확인했고, 로컬 Foxglove 화면의 두 영상도 별도로 확인했다.

| 확인 항목 | live-01 결과 |
|---|---|
| 영상 전송 | 손목·전체 장면·`/camera` 각 88개, 총 264개 PNG가 1280×720 RGB로 디코딩됨 |
| 상태·촬영 대조 | sequence 45–132의 88개가 연속, 영상/상태의 촬영 시각·SHA 264쌍 일치, 불일치 0개 |
| alias | `/camera`와 손목 영상 88쌍 동일 |
| 실제 갱신 | A·B·양방향 이동 모두 수신, 상태는 모두 `new_capture`·`recent_capture`, `capture_age_seconds`는 0.254–0.484초 |
| TF | 동적 TF 87개, `map→world` 정적 TF 1개 수신 |
| 기존 자료·프로세스 | 기존 자료 1,339개 파일의 변경·누락 없음, 기존 Isaac·bridge 프로세스 식별 일치 |

근거는 `output/isaac-scene-20261010/env-audit/`의 `live-01-reception-01.json`, `live-01-reception-01-summary.json`, `live-01-crosscheck.json`, `live-01-preservation-check-final.json`이다. 파일 교체 시점의 일시적 읽기 재시도 로그가 있었지만 위 수신 구간의 연속성·해시·시각 대조는 통과했다. 이 검증은 해당 실행과 수신 구간에 대한 확인이다.

**기존 정형 마킹·작업대 장면을 기준 장면으로 보존한다.** `live-01`의 설정·소스 사본·장면·이미지와 이전 튜닝 결과를 덮어쓰지 않는다. 후속 요청인 조선소 병풍형 강판 패널·중앙 수기 메모·기존 빛 반사를 유지하는 장면은 아직 구현하지 않았다. 후속 구현은 별도 설정과 새 출력 디렉토리로 분리한다.

## 장면과 경계

실행 설정은 [night_welding.json](../../configs/isaac_scene/night_welding.json), 장면 생성은 [run_isaac_welding_scene.py](../../scripts/isaac/run_isaac_welding_scene.py), 로봇 이동은 [isaac_scene_robot.py](../../scripts/isaac/isaac_scene_robot.py)다.

| 항목 | 현재 설정 |
|---|---|
| 로봇 | NVIDIA UR10 USD, 바닥 기준 베이스 `[0, 0, 0.3]` m |
| 손목 장착 | `wrist_3_link`의 카메라 고정 이동 `[0.25, 0, -0.15]` m, 시각적 카메라 하우징·토치 |
| A 목표 | 카메라 `[0.55, -0.38, 1.05]` m |
| B 목표 | 카메라 `[0.85, -0.15, 1.05]` m |
| 공통 주시점 | 표기 금속판 중심 `[0.7, 0, 0.65]` m |
| 고정 작업등 | `[0.85, 0.38, 1.05]` m, 사각광 0.22×0.16 m, intensity 30000 |
| 금속 표면 | metallic 0.65, roughness 0.13, clearcoat 1.0, clearcoat roughness 0.06 |
| 노출·영상 | 자동 노출 끔, ISO 200, shutter 50, f/4, 1280×720, 손목 18 mm·전체 장면 26 mm |
| 렌더링 | `RealTimePathTracing`, samples 16, 초기·정착 각 80 step, 물리·렌더 dt 1/60 s |
| 시연 반복 | A/B 순서 이동, 기본 이동 120 step·유지 480 step, 12 step마다 최신 RGB 저장 |

카메라는 손목의 고정 자식이다. PhysX의 실제 링크 pose와 Jacobian으로 관절 목표를 계산하고, 관절 위치 목표로 움직인다. 카메라나 관절 상태를 프레임마다 순간 이동시키지 않는다. 목표 미수렴 시 실행이 실패할 수 있으며 충돌 없는 경로·실기 적합성은 검증하지 않았다.

표기 `BISB30N-15`, `J01`, 화살표는 이 장면을 위해 그린 합성 텍스처다. 공개 철골 사진을 전사하거나 실제 이음 형상을 복원한 자료가 아니다. 조명·재질·노출은 A/B 사이 고정이며 저장 RGB에 반사나 글자를 사후 합성하지 않는다.

`--live`도 **`capture_mode=pre_captured`, `presentation_mode=scheduled_pose_loop`**다. 새 RGB와 로봇 이동을 계속 보여 주지만 A/B 순서는 사전 정의되어 있다. 자동 OCR 판단→재촬영 폐루프, 이 장면의 인식→문서 검토 자동 연결, 실제 용접·실기 제어, 새 관리자 UI는 미완료다. `execution_authorized=false`를 유지한다.

## Runpod에서 시작

기존 [Pod 환경](../setup/POD_VER1.md)의 `/workspace/PAC2026`, Isaac 6.1 전용 환경, ROS Jazzy·domain 26·FastDDS, Foxglove bridge를 재사용한다. 아래는 **서버 Bash**용이다. ROS 설정은 `set -u` 상태에서 실패할 수 있으므로 먼저 해제하고 source한다. Isaac와 송출기는 서로 다른 Python을 쓴다. 새 설치나 기존 bridge 재기동은 필요 없다.

매번 비어 있는 새 출력 디렉토리를 만든다. 실패한 실행도 보존하고 새 디렉토리로 재시도한다. 기존 `manifest.json`이 있으면 장면 실행기가 거절하며, 미완성 디렉토리도 재사용하지 않는다.

```bash
set +u
source /workspace/pac-env.sh
cd /workspace/PAC2026
scene_root="output/isaac-scene-$(date -u +%Y%m%d)"
mkdir -p "$scene_root"
scene_out=$(mktemp -d "$scene_root/run-XXXXXXXX")
printf '%s\n' "$scene_out"

OMNI_KIT_ACCEPT_EULA=YES OMNI_KIT_ALLOW_ROOT=1 \
  /workspace/venvs/isaacsim-6.1/bin/python scripts/isaac/run_isaac_welding_scene.py \
  --config configs/isaac_scene/night_welding.json \
  --output "$scene_out" --live >"$scene_out/scene.log" 2>&1 &
printf '%s\n' "$!" >"$scene_out/scene.pid"

/usr/bin/python3 scripts/isaac/serve_isaac_scene_ros.py \
  --output-root "$scene_out" --camera-alias /camera \
  --publish-map-tf --publish-link-markers --repeat-interval 1 \
  >"$scene_out/publisher.log" 2>&1 &
printf '%s\n' "$!" >"$scene_out/publisher.pid"
```

`OMNI_KIT_ACCEPT_EULA=YES`는 기존 환경의 NVIDIA 약관 동의를 전제로 한다. `--native-ros`는 현재 실행에서 사용하지 않는다. Isaac가 PNG를 저장하고 별도 시스템 ROS 프로세스가 원본 바이트를 `sensor_msgs/msg/CompressedImage`로 전달한다. 시연 종료 없이 SSH 셸을 닫으려면 기존 세션 관리 환경을 사용한다.

최초 모델 자산 로딩 후 `scene.log`의 `SCENE_READY`, 두 `SENSOR_WARMUP` RGB shape, `CAPTURED A/B`, `PAIR_COMPLETE`를 확인한다. 송출기는 그 전까지 유효한 스냅샷을 기다린다. 한 쌍만 저장하려면 장면 명령에서 `--live`를 뺀다.

## 연결과 결과 확인

[기준 Foxglove 레이아웃](../../configs/isaac_scene/foxglove-baseline-layout.json)은 실제 앱에서 내보낸 두 Image 패널 설정이다. `Import from file…`로 불러오고 기존 `ws://localhost:8765` 연결을 선택하면 복구할 수 있다. 앱의 임시 변경 표시와 별도로 이 파일을 보존한다.

서버 bridge는 `127.0.0.1:8765`, Mac의 기존 SSH 터널은 `localhost:8765`를 사용한다. 열린 Foxglove 연결 `ws://localhost:8765`를 재사용한다. 터널이 없을 때만 [Pod 환경의 6.4절](../setup/POD_VER1.md)대로 연결하며 공개 포트를 추가하지 않는다.

| Foxglove 항목 | 토픽·프레임 |
|---|---|
| 기존 카메라 패널 | `/camera` — 손목 영상의 동일 사본 |
| 손목·전체 장면 Image 패널 | `/contextweld/wrist/image`, `/contextweld/overview/image` |
| 상태 확인 | `/contextweld/status` — `std_msgs/msg/String` 안의 JSON |
| 3D 기준 | `map→world` 정적 TF, `world→contextweld_wrist_optical` 실제 카메라 pose |
| 링크 위치 점 | `/contextweld/robot_link_samples` — 실제 링크 위치 샘플, 로봇 mesh가 아님 |

같은 실행 디렉토리를 지정해 확인한다. 다른 터미널에서는 `scene_out`을 방금 출력된 디렉토리로 설정한다.

```bash
/usr/bin/python3 scripts/isaac/serve_isaac_scene_ros.py \
  --output-root "$scene_out" --check-input
ros2 topic list -t
ros2 topic echo --once /contextweld/status
```

화면이 보이는 것과 최신 장면이 갱신되는 것을 함께 확인한다. 상태의 `sequence`, `view=A/B/moving_to_A/moving_to_B`, `captured_at_utc`, `published_at_utc`, `capture_age_seconds`를 본다. `publication_kind=new_capture`는 새 스냅샷, `held_capture_republish`는 같은 촬영의 재송출이다. 기본 5초 이상 지난 촬영은 `source_state=stale`이다. `--repeat-interval 1`은 늦게 접속한 패널을 위한 재송출이며 촬영 시각을 현재 시각으로 바꾸지 않는다.

촬영 시각은 렌더 step 이후 최신 RGB를 읽은 호스트 UTC다. `simulation_time`을 함께 남기지만 센서 고유 frame ID·정밀 노출 시각은 제공되지 않아 `native_sensor_frame_id=null`이다. 송출 header는 원래 `captured_at_utc`를 유지한다. 파일 교체 중이거나 경로·해시·영상 형식이 맞지 않으면 해당 읽기를 건너뛰고 다음 갱신을 기다린다.

## 기록과 중단

| 출력 | 의미 |
|---|---|
| `config.json`, `source/`, `manifest.json` | 실행 당시 설정·코드 사본, 해시, Git 상태, 카메라·로봇·고정 노출 메타데이터 |
| `frames/A-*.png`, `frames/B-*.png`, `*-capture.json` | 최초 정착 A/B의 실제 RGB, 관절·카메라 pose, 오차·장착 대조와 이미지 해시 |
| `scene.usda`, `assets/marking.png` | 장면·합성 표기. UR10 등의 외부 Isaac 자산은 별도로 필요 |
| `stream/current.json`, `stream/*.png` | 반복 시연의 최신 스냅샷. 이미지 먼저, JSON 마지막으로 교체 |
| `stream/session.json` | 정상 종료 시각. 갑작스러운 종료에서는 없을 수 있음 |
| `scene.log`, `publisher.log`, `*.pid` | 위 실행 명령의 로그·소유 PID |

최초 A/B와 manifest는 계속 갱신되는 전체 동영상 기록이 아니다. `stream/`도 최신 프레임만 보관한다. 보존할 시연은 해당 실행을 중단한 뒤 디렉토리 전체를 복사한다. 출력·원문·모델은 Git에 넣지 않으며 Pod 종료 전에 필요한 결과를 내려받는다.

**자신이 시작한 두 PID만 중단한다.** 먼저 아래 출력에서 실행 파일과 출력 디렉토리가 일치하는지 확인한다. PID가 재사용됐거나 소유가 불확실하면 중단 명령을 실행하지 않는다. 기존 Isaac 앱·bridge·터널에 대한 일괄 종료는 하지 않는다.

```bash
scene_pid=$(cat "$scene_out/scene.pid")
publisher_pid=$(cat "$scene_out/publisher.pid")
ps -p "$scene_pid" -o pid=,args=
ps -p "$publisher_pid" -o pid=,args=
```

소유 확인 후 실행한다.

```bash
kill -TERM "$scene_pid" "$publisher_pid"
```

장면 프로세스 종료와 `stream/session.json`을 확인한다. 중도 실패 시에도 원래 로그·프레임을 수정하지 않는다.

## API 근거

- [Isaac 카메라 API](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.sensors.experimental.rtx/docs/index.html): `CameraSensor`가 전용 render product와 annotator를 연결한다. 설치 소스 기준 해상도 인자는 `(height, width)`이며 `get_data('rgb')`는 데이터와 부가정보를 반환한다. `None` 여부로 RGB 준비를 확인한다.
- [Isaac Multi-Tick Rendering](https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_multitick_rendering.html): `tick_rate=0`은 매 렌더 프레임 자동 촬영이다. 이 장면은 기본 viewport 업데이트를 꺼도 별도 카메라 render product로 렌더링한다.
- [ROS Jazzy CompressedImage 정의](https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/CompressedImage.msg): 압축 영상·원촬영 시각·광학 프레임을 담는 계약이다. 현재 경로는 PNG 바이트를 재인코딩 없이 발행한다.
