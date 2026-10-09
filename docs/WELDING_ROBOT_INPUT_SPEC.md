# 현대와 두산 용접로봇 입력 파라미터 상세 명세

확인일: **2026-10-10 KST**. 대상은 HD현대로보틱스의 Hi6 계열 아크용접·HRScript 문서와 두산로보틱스의 **DRL Programming Manual V3.7.0 한국어**다. 제조사 공식 원문의 입력 항목을 비교한 조사 명세이며, 실제 장비에서 실행 검증한 사양서는 아니다.

용접로봇의 입력은 **용접조건, 경로·자세, 용접기 연결 설정**으로 나뉜다. 전류·전압만 전달하거나 마킹의 문자만 읽어서는 이 입력을 모두 구성할 수 없다. 마킹에서 얻은 작업 요구사항을 등록조건 또는 작업 기준에 연결하고, 좌표·통신 설정은 해당 설비에서 공급해야 한다.

기존 [파라미터 요약](WELDING_ROBOT_PARAMETERS.md)의 상세 후속 자료다. 특히 기존 요약의 `arccond` 전류·전압 고정 범위는 이번에 확인한 원문과 다르므로 **3.3절과 6절의 정정 내용**을 적용한다. 이 조사는 [데모 스펙](DEMO_SPEC.md)의 모의 전달 범위를 실기 제어로 변경하지 않는다.

## 1 조사 대상과 표 읽는 방법

| 구분 | 현대 | 두산 |
|---|---|---|
| 회사 | HD현대로보틱스 | 두산로보틱스 |
| 프로그램 계층 | HRScript의 아크 명령과 펜던트 조건표 | DRL의 `app_weld_*`와 모션 함수 |
| 문서 기준 | HRBOOK Hi6 진입점, 공식 `doc-arc-weld`·`doc-hrscript`의 `ko` 브랜치 | `/ko/programming-manual/3.7.0/` |
| 버전 해석 | 공개 원문에 `${cont_model}` 템플릿과 버전별 주석이 섞임. 단일 설치 소프트웨어 버전으로 고정된 문서가 아님 | 3.7.0을 기준으로 고정. 외부 C/C++ API 1.33.4와 같은 버전 번호가 아님 |
| 제한 | 설정한 용접기가 지원하는 명령·모드만 사용 가능 | 해당 Welding 장에 **P 시리즈 미지원** 명시 |
| 미지정 구성 | 본체 모델, 설치 제어기 버전, 용접기 모델·펌웨어·옵션 | 본체 모델, 제어기·DRL 설치 버전, 용접기·통신맵 |

근거: [현대 아크용접 목차][H00], [Hi6 HRBOOK][H20], [두산 Welding][D00], [두산 외부 API 목차][D29]. 로봇 본체의 가반하중·도달거리는 이 입력 명세의 범위 밖이다. 현대용접의 용접기와 HD현대로보틱스의 제어기는 구분한다.

| 표기 | 해석 |
|---|---|
| 기본값 | 원문이 제시한 함수 생략값 또는 화면 초기값. 작업에 적합한 추천값이라는 뜻이 아님 |
| 원문 범위 | 해당 명령 또는 화면에 쓰인 범위. 다른 화면·용접기·WPS까지 통용되는 범위가 아님 |
| `미기재` | 해당 원문에 기본값·범위·단위가 없음. 0이나 무제한으로 해석하지 않음 |
| `[확인 필요]` | 장비 확인 또는 제조사 설명 없이는 결정할 수 없는 항목 |
| `[추론]` | 공식 입력 사양을 바탕으로 제안한 프로젝트 설계. 제조사 제공 스키마가 아님 |

숫자 범위가 여러 곳에서 다르면 가장 넓은 값을 채택하지 않는다. 설치 버전, 활성 모드, 연결 용접기, 적용 작업 기준의 제한을 각각 확인한다. 기본값이 0인 필드도 생략한 채 유효한 용접이 된다는 보장은 없다.

## 2 주요 입력 비교

| 입력 의미 | 현대 | 두산 아날로그 | 두산 디지털 |
|---|---|---|---|
| 등록 용접조건 | `arcon cnd` | 해당 함수에 같은 번호 필드 없음 | 해당 함수에 같은 번호 필드 없음 |
| 용접기 내부 작업 선택 | `arcon job`, 용접기별 Prog/Job | 전용 필드 없음 | `job_num`, `synergic_id` |
| 본조건의 주 지령 | 전류 A / 송급 m/min / 파워 % 등 연결 용접기에 따라 다름 | `f_target` m/min | `r_wire_feed_speed`; 단위·배율은 용접기 매핑 확인 |
| 전압 | 절대 V / 시너직 보정 % / VP / 아크길이 보정 등 | `v_target` V | `voltage_correct`; 절대전압 필드로 간주하지 않음 |
| 이동속도 | `move spd`에 단위 지정, `arccond spd`는 cm/min | `vel_target` mm/s | `vel_target` mm/s |
| 위빙 | 등록조건 번호와 패턴·거리·Hz·dwell | 패턴별 함수, 폭 mm·주기 s·offset | 아날로그와 같은 위빙 함수군 |
| 시작·종료 시퀀스 | 조건표의 초기·본·종료조건 | `weld_proc_param[9]` | 동일 이름의 배열 없음. 용접기 Job·통신 설정 확인 |
| 위치·자세 | `Pose` 및 `move` | `posx` 및 `movel` 등 | 동일 |
| 외부 결선·통신 | 용접기 설정·신호 할당 | 채널·출력모드·물리량 대응표 | EtherNet/IP의 8종 매핑 |

근거: [H01]–[H07], [H18]–[H19], [D01]–[D06], [D08]–[D12]. **제조사 내부의 조건 ID, 용접기 Job ID, 로봇 프로그램 ID는 별개의 식별자**다.

## 3 현대 입력 상세

### 3.1 조건 설정과 프로그램 실행의 관계

디지털 아크 설정에서 작업자는 `arcon cnd=X` 줄의 **속성**으로 시작·본조건 편집 화면을 연다. 여기서 종료조건과 보조조건으로 이동해 관련 값을 편집한다. `weaving`과 `stitch`도 조건번호에 연결된 속성 화면을 가진다. 이동 위치는 `move`에 기록된 포즈 또는 포즈 변수로 지정한다. [H05], [H06], [H07], [H11], [H18]

설정 관계는 `용접기 종류·통신 설정 → 아크/위빙 등 조건표 등록 → 경로와 조건번호를 참조하는 프로그램`이다. **아크 명령의 인수는 외부 PC가 바로 호출하는 HTTP API가 아니다.** 외부 인식 결과를 받는 프로그램·변수·통신 계약은 별도 구현 대상이다.

### 3.2 아크 시작과 종료

명령 형식이며 완성된 실행 프로그램은 아니다.

```text
arcon
arcon cnd=<아크조건번호>
arcon cnd=<아크조건번호>, job=<용접기Job번호>
arcon cnd=<아크조건번호>, job=<용접기Job번호>, cur=<값>, vol=<값>, vol_offset=<값>
arcoff
arcoff welder=<용접기번호>, delay=<지연시간>
```

| 명령·필드 | 입력 의미 | 원문 단위·범위 | 생략·적용 조건 |
|---|---|---|---|
| `arcon cnd` | 시작·본조건을 저장한 번호 | 1–100 | 조건표 참조. 시작조건 UI는 1–32로 표기되어 충돌 |
| `arcon cur` | 명령 표에서는 출력전류 | A, 0–500 | 공식 예제에서는 등록조건의 전류만 덮어씀 |
| `arcon vol` | 명령 표에서는 출력전압 | V, 20–40 | 공식 예제에서는 등록조건의 전압만 덮어씀 |
| `arcon vol_offset` | 시너직 전압 offset | V, −200–200로 표기 | `[확인 필요]` 이 범위를 연결 용접기의 실제 보정 범위로 사용하지 않음 |
| `arcon job` | 용접기 내부 저장 Job | 0–9999 | Job 모드를 지원하는 용접기에 한함. 0의 의미는 용접기 확인 |
| 인수 없는 `arcon` | 이전 용접조건 재사용 | 별도 수치 없음 | 원문 예제는 재시도·재기동을 미실행한다고 명시 |
| `arcoff welder` | 정지할 용접기 선택 | 1–2 | 2대 구성에서의 용접기 번호. 아크조건 번호가 아님 |
| `arcoff delay` | 종료 지연 | 0–2 s | 2대 구성의 지정 용접기 종료 지연 |

근거: [H01], [H02]. HRScript 문서는 위 항목을 주로 `변수`로 표현하고 엄격한 언어 자료형·필드별 기본값을 모두 제시하지 않는다. ID의 정수성·수치 변환은 설치 제어기 계약에서 확인한다. 아래 용접기별 UI의 범위를 위 명령 범위로 대체하지 않는다.

### 3.3 구간별 조건 변경과 용접 데이터베이스

```text
arccond <D 또는 L>, cnd=<WDB번호>, gap=<값>, spd=<값>, rd=<값>, ld=<값>, freq=<값>, cur=<값>, vol=<값>
```

| 필드 | 의미 | 원문 단위·범위 |
|---|---|---|
| 첫 인자 `D`, `L` | 즉시 변경 / 선형 보간 변경 | 문자 선택 |
| `cnd` | 용접 데이터베이스 WDB·보간조건 번호 | 1–1000 |
| `gap` | 이음 간격 입력 | −1–1000 mm. −1의 특수 의미는 `[확인 필요]` |
| `spd` | 즉시 변경할 용접 이동속도 | 1–1000 cm/min |
| `rd`, `ld` | 벽방향·타방향 위빙 폭 | 각각 1–50 mm |
| `freq` | 위빙 주파수 | 1–10 Hz |
| `cur` | 전류·와이어 피딩속도·시너직 전류 | **용접기 설정별 범위 상이**, 공통 수치 범위 없음 |
| `vol` | 전압·전압 offset·시너직 전압 | **용접기 설정별 범위 상이**, 공통 수치 범위 없음 |

근거: [H04]. 기존 요약의 `cur=1–1000 A`, `vol=1–200 V`는 이번에 확인한 원문으로 뒷받침되지 않는다. 여기서는 해당 수치를 채택하지 않는다. `D` 직접 변경과 `L`의 WDB 보간 구간 구성도 구분해야 한다.

### 3.4 시작조건 화면의 공통 항목

| 항목 | 의미 | 단위·범위 | 원문 기본값 |
|---|---|---|---|
| 조건번호 | 편집할 시작조건 | 1–32 | 미기재 |
| 설명 | 조건 식별용 문구 | 문자열, 길이 미기재 | 미기재 |
| 가스 예출 | 점화 전 보호가스 출력 | 0–10 s | 0.5 |
| WCR 대기시간 | WCR 입력 대기 한도 | 1–10 s | 2 |
| 로봇 지연시간 | 점화 후 용접선 이동 대기 | 0–10 s | 0 |
| 초기조건 유지시간 | 초기 지령 유지 | 0–10 s | 미기재 |
| 슬로프 시간 | 초기→본조건 전환 | 0–10 s | 미기재 |
| 제한치 초과 허용시간 | 전류·전압 제한 초과 감시 | 0–10 s | 0. 0이면 해당 제한 감시 미사용 |
| 전압 상한·하한 | 감시 임계치 | 각각 0–100 V | 미기재 |
| 전류 상한·하한 | 감시 임계치 | 각각 0–1000 A | 미기재 |

근거: [H05]. WCR 대기 실패와 제한 초과 후의 처리는 재시도·재기동 조건에 연결된다. 감시 임계치는 지령 전류·전압과 다른 항목이다.

### 3.5 용접기에 따라 달라지는 본조건과 초기조건

아래는 **로봇 제어기 화면에 기재된 값**이다. 해당 제조사의 모든 용접기 모델에 적용되는 정격이 아니다. `%`, `VP`, `V`, `A`, `m/min`을 각각 보존한다. [H05]

| 용접기·항목 | 본조건 범위와 기본값 | 초기조건 범위와 기본값 |
|---|---|---|
| 효성 전류 | 40–350 A / 100 A | 40–350 A / 120 A |
| 효성 개별모드 전압 | 10–38 V / 10 V | 10–38 V / 10 V |
| 효성 시너직 전압 보정 | 50–150% / 50% | 50–150% / 50% |
| EWM 와이어 송급 | 0–25 m/min / 3.1 | 0–25 m/min / 3.72 |
| EWM 전압 offset | −10–10 VP / 2 | −10–10 VP / 2 |
| Fronius TPS 파워 | 0–100% / 100% | 20–200% / 120% |
| Fronius 아크길이 보정 | −30–30% / 0 | −30–30% / 0 |

원문의 초기조건 설명은 본조건 대비 비율을 말하지만 표는 효성 A·EWM m/min을 사용한다. 화면의 **비율 변환 버튼**은 비율을 입력받아 본조건에서 환산한 값을 넣는다. `[확인 필요]` 설치 화면에서 절대값 입력과 비율 입력을 구분해야 하며, 표의 120 A를 120%로 바꾸어 저장해서는 안 된다. 시너직 기본 코드는 효성 `040`, EWM `185`이고, 공통 표의 Fronius 항목은 미지원으로 적혀 있다. 코드의 뜻과 사용 가능 목록은 용접기별 선택표가 필요하다. [H05]

| 용접기 | 추가 입력 | 범위·선택지·기본값 |
|---|---|---|
| 효성 | 용접모드 | 일반 / 펄스 |
| 효성 | 슬로우다운 조정 | 0–255%, 기본 100. 점화 전 송급 조정 |
| 효성 | 인덕터 효과 | 0–255%, 기본 100 |
| Fronius | 동작모드 | `Prog-Std`, `Prog-Pulse`, `CMT`, `JOB`, `TIG` |
| Fronius | Prog/Job 번호 | 선택 모드에 따라 저장 program 또는 Job. 범위 미기재 |
| Fronius | 다이나믹 보정 | −5–5%, 기본 0 |
| EWM AlphaQ | JOB 모드 | 무효: 시너직·송급·offset 적용 / 유효: 저장 Job 사용 |
| EWM | 용접모드·슈퍼 펄스 | 펄스 사용, 2단 펄스 사용 여부 |
| EWM | Job 번호 또는 시너직 번호 | 용접법·재질·가스·와이어 직경으로 선택하는 화면 제공 |
| EWM | 동적 보정 | −40–40, 기본 0, 단위 미기재 |
| EWM | Lift 아크 시작 | 미사용 / 사용 |

근거: [H08], [H09], [H10]. 이 선택 화면은 재질·가스·와이어 직경이 **조건 선택의 입력**이 될 수 있음을 보여준다. 마킹에서 이를 모두 읽을 수 있다는 근거는 아니다.

### 3.6 종료조건

| 항목 | 원문 단위·범위 | 기본값·적용 의미 |
|---|---|---|
| 효성 종료 전류 | 28–350 A | 28 A |
| EWM 종료 송급 | 0–25 m/min | 2.17 |
| Fronius TPS 종료 파워 | 10–100% | 70% |
| 종료 전압·보정 | 효성 개별 10–38 V; 효성 시너직 50–150%; EWM −10–10 VP; Fronius −30–30% | 각각 10, 50, 2, 0 |
| Downslope 시간 | 0–10 s | 0.10 s. 본조건→종료조건 전환 |
| Burnback | 0–200 ms | 0. 용접기별 처리 차이 있음 |
| 가스 후출 | 0–10 s | 0 |
| 크레이터 이동 시간·거리 | 0–10 s / 0–100 mm | 모두 0. 후진 거리와 시간으로 이동속도 결정 |
| 크레이터 위빙 여부 | 미사용 / 사용 | 미사용. 원문에 V70.04부터 지원 주석 |
| 크레이터 위빙 폭 | 본조건 대비 % | 수치 범위·기본값 미기재 |
| 크레이터 위빙 주파수 | Hz | 수치 범위·기본값 미기재 |
| 크레이터 와이어 제어 | 종료 후 역인칭 여부 | 선택 코드·기본값 미기재 |
| 역인칭 시간·속도 | s / % | 수치 범위·기본값 미기재 |
| 자동 용착 해제 횟수 | 0–9회 | 0이면 용착 검사를 하지 않고 진행 |
| 용착 해제 조건번호 | 0–32 | 0이면 현재 시작조건의 본조건 사용 |
| 용착 해제 출력 유지시간 | 0–10 s | 0 |

근거: [H06]. 종료 전류 설명에도 비율과 절대단위가 혼재한다. 표의 단위와 설치 화면을 대조한다. `V70.04`를 Hi6의 모든 설치 버전에 대응하는 것으로 추정하지 않는다.

### 3.7 위빙

`weaving on`으로 조건을 선택하고 `weaving off`로 종료한다. 원문 문법에는 위치 인자 형식, 예제에는 `weaving on, cnd=1`이 함께 나온다. `[확인 필요]` 설치 언어 버전에서 허용 문법을 고정한다. [H03]

| 조건표 항목 | 범위·선택지 | 기본값·의미 |
|---|---|---|
| 조건번호 | 1–1000 | 1 |
| 형태 | 단진동 / 삼각 / L형 / 원형 / 버티컬 | 미기재 |
| 주파수 | 0–10 Hz | 2. 0이면 구간 이동시간 방식 |
| 벽방향·타방향 거리 | 각각 1–25 mm | 각각 2.5 |
| 기본 각도 | 0.1–180° | 90 |
| 벽방향 기준 | 수직 / 수평 / 토치자세 | 미기재 |
| offset 각도 | 토치자세 기준 좌우 기울기 | 범위·기본값 미기재 |
| 진행 각도 | −90–90° | 0이면 진행방향과 위빙방향이 직각 |
| 경계 제한 | 유효 / 무효 | 시작·종료 경계 안으로 위빙 제한 |
| dwell 중 로봇 동작 | 이동 / 정지 | 좌우 끝점 정지 중 진행 여부 |
| 구간 이동시간 | 0.01–10 s | 1. 주파수 0일 때 사용 |
| 구간 정지 타이머 | 0–2 s | 0 |
| 구동축 | 로봇 / 부가축 | 부가축 선택 시 번호도 지정, 표시 기본 번호 1 |

근거: [H07]. 주파수를 지정하면 **주기 전체에서 dwell을 제외한 시간 동안** 위빙 이동을 수행한다. `arccond`의 편측 폭 범위 1–50 mm와 조건표의 1–25 mm는 동일 제한으로 합치지 않는다.

### 3.8 간헐 용접과 다층 용접

마킹의 간헐 용접 요구와 연결할 후보인 스티치 입력은 다음과 같다. [H11], [H12]

| 입력 | 의미·제약 |
|---|---|
| `stitch on, cnd=…` | 스티치 조건번호 1–20. `stitch off`로 종료 |
| ON 유지시간·OFF 유지시간 | 용접 신호를 선행해서 켜고 끄는 시간 |
| 시작 거리 | 첫 스티치 전에 ON 속도로 진입하는 구간 길이 |
| ON 거리·OFF 거리 | 각각 용접 구간·비용접 구간의 길이 |
| 횟수·구분 | 해당 조건 반복 횟수와 다음 조건 구분으로의 전환 |
| OFF 속도 | 비용접 구간 이동속도 |
| ON 속도 | 용접 구간의 **스텝 속도**로 지정 |

시간·거리·속도 필드의 구체적 단위와 수치 제한은 이 장의 설명문에 미기재다. `[확인 필요]` 화면·설치 버전으로 확정한다. [추론] 마킹의 피치가 시작점 간 거리로 정의된 경우 `OFF 거리 = 피치 − ON 거리`로 변환할 수 있지만, 표기 규칙을 확인하기 전에는 적용하지 않는다.

| `multipass` 인수 | 의미 | 원문 범위 |
|---|---|---|
| `save` / `load` / `off` | 센싱 궤적 저장 / 재현 / 종료 | 명령 선택 |
| `trj` | 저장·재생 궤적 번호 | 1–50 |
| `period` | 저장 샘플링 거리 | 5–100 mm. 시간 주기가 아님 |
| `side`, `height` | 원 궤적 기준 좌우·상하 이동 | 각각 −20–20 mm |
| `reverse` | 재생 방향 | 0 정방향 / 1 역방향 |
| `tas`, `was` | 토치 전후·좌우 각도 이동 | 각각 −20–20° |

근거: [H13]. `multipass`에는 단일 `pass_count` 인수가 없다. 패스 수 요구를 실제 반복 경로와 패스별 조건으로 구성해야 한다.

### 3.9 경로와 터치센싱

| 명령·입력 | 의미·단위·제약 |
|---|---|
| `Pose`의 `x,y,z` | 직교 위치 mm |
| `Pose`의 `rx,ry,rz` | 방향 오일러각 deg. 회전 순서의 타 제조사 호환은 `[확인 필요]` |
| `Pose`의 `crd` | `joint` 기본, `base`, `robot`, `u1`–`u10` |
| `Pose`의 `cfg` | 직교좌표의 로봇 자세 구성. 플래그 조합 또는 `auto` |
| `Pose`의 부가축·메커니즘 | 축값의 mm/deg, 포함 메커니즘 정보. 셀 구성에 맞게 지정 |
| `move` 보간 | `P` 축 / `L` 직선 / `C` 원호; 정치툴 `SP/SL/SC` |
| `move tg` | 목표 포즈 또는 시프트식. 기록된 숨은 포즈가 있으면 생략 가능 |
| `move spd` | `mm/sec`, `cm/min`, `sec`, `%` 중 단위를 붙임. `%`는 절대속도가 아님 |
| `move accu` | 0–7. 낮을수록 정밀, 0은 불연속 동작 |
| `move tool` | 툴 번호 0–31 |
| `move x`, `until` | 출발 시 실행할 대입문 문자열 / 이동 종료 조건식. 통상 인식 결과가 생성할 항목은 아님 |

근거: [H18], [H19]. 포즈의 자료형이 허용하는 큰 수치 범위는 로봇의 도달 가능 범위가 아니다. `Pose`에서 좌표계를 생략하면 축좌표이므로 XYZ로 읽은 값을 무조건 넣으면 안 된다.

| `touchsen` 입력·결과 변수 | 역할 |
|---|---|
| `cnd` | 터치센싱 조건번호 1–8 |
| `crd` | `robot`, `base`, `tool`, `tool_prj` |
| `dir` | 센싱 방향 문자열 배열. 지원 방향은 센싱 타입별로 다름 |
| `rotation` | 지정 좌표축 기준 센싱방향 회전 표현 |
| `lift_up` | 바닥 탐색 후 상승량 mm |
| `pose` | 측정 포즈를 받을 변수 |
| `gap` | Butt/VGroove에서 **측정된 gap을 저장할 변수**. 원하는 gap을 입력하는 필드가 아님 |
| `mpose`, `mshift` | 마스터 기준 포즈와 양산 시 계산된 위치차 변수 |

근거: [H14]. 센싱 좌표와 결과 변수는 마킹의 문자·화살표 위치를 그대로 대입하는 공간이 아니다.

### 3.10 재시도와 재기동 설정

| 구분 | 설정 항목 | 원문 범위·기본값 |
|---|---|---|
| 점화 재시도 | retract 시간 / 속도 | 0–10 s / 0–100%, 기본 0 / 10 |
| 점화 재시도 | 횟수 / 조건번호 | 0–9 / 0–32, 기본 5 / 0 |
| 점화 재시도 | 동작모드 | 재진입 / 시프트 / 다방향 |
| 점화 재시도 | 이동속도 | 1–999 cm/min, 기본 100 |
| 점화 재시도 | 후퇴 거리 | 0–99.99 mm, 기본 3 |
| 점화 재시도 | 전후·좌우·상하 시프트 | 각각 −99.9–99.9 mm, 기본 2 / 2 / 1 |
| 중단 후 재기동 | 횟수 / 조건번호 | 0–9 / 0–32, 기본 3 / 0 |
| 중단 후 재기동 | 중첩량 | 0–99.9 mm, 기본 5 |
| 중단 후 재기동 | 복귀 이동속도 | 1–150 mm/s, 기본 50 |
| 중단 후 재기동 | 중첩 용접속도 | 10–999 cm/min, 기본 50 |
| 중단 후 재기동 | 원인별 오버랩 처리 | 자동 / 반자동 / 무시 / 금지. 원인별 허용 선택지가 다름 |
| 설비 공통 | 용착 검출시간 | 0.1–10 s, 기본 0.2 |
| 설비 공통 | ARC OFF 검출시간 | 0–10 s, 기본 0.3 |

근거: [H15], [H16], [H17]. 조건번호 0의 재사용 의미와 재진입 모드의 예외는 원문을 따른다. 자동 오버랩은 Arc 꺼짐에만 허용되며, `무시`는 Arc 꺼짐·제한 초과에 한정된다. 이 항목들은 설비 운용 설정이며 마킹에서 자동 추출할 목표로 두지 않는다.

## 4 두산 입력 상세

### 4.1 활성화와 조건 적용 순서

| 단계 | 아날로그 | 디지털 |
|---|---|---|
| 설비 설정 | 채널·입출력 모드·물리량 대응 확인 | EtherNet/IP 8종 인터페이스, `Monitoring+GPR` 설정 |
| 용접 구간 활성화 | `app_weld_enable_analog(...)` | `app_weld_enable_digital()` |
| 본조건 지정 | `app_weld_set_weld_cond_analog(...)` | `app_weld_set_weld_cond_digital(...)` |
| 선택적 위빙 지정 | `app_weld_weave_cond_*` | 같은 함수군 |
| 경로 실행 | `movel` 등에서 `app_type=DR_MV_APP_WELD` | 동일 |
| 구간 조건 조정 | `app_weld_adj_welding_cond_analog(...)` | `app_weld_adj_welding_cond_digital(...)` |
| 종료 | `app_weld_disable_analog()` | `app_weld_disable_digital()` |

근거: [D01]–[D06], [D16], [D22], [D23], [D25]. 조건·위빙 설정은 enable–disable 구간 안에서 유효하다. 한 구간에는 하나의 기준 용접조건과 위빙조건을 두고, 구간별 변경은 조정 함수로 수행한다. `enable_digital()` 원문은 **EtherNet/IP만 지원**한다고 명시한다. 이는 이 함수의 제한이며 두산 로봇의 모든 통신 기능이 EtherNet/IP뿐이라는 뜻은 아니다.

### 4.2 아날로그 본조건

`app_weld_set_weld_cond_analog()`의 전체 인수다. [D01]

| 인수 | 자료형 | 기본값 | 단위·의미·범위 |
|---|---|---|---|
| `flag_dry_run` | int | 0 | 0 실용접 / 1 모의용접. 1에서도 모션·위빙·offset은 진행 |
| `v_target` | float | 0 | 목표전압 V. 공통 최소·최대 미기재 |
| `f_target` | float | 0 | 목표 와이어 피딩속도 m/min. 이 함수 인수표에 전류 A 필드 없음 |
| `vel_target` | float | 0 | 목표 이동속도 mm/s |
| `vel_min` | float | 0 | 속도 조정 하한 mm/s |
| `vel_max` | float | 0 | 속도 조정 상한 mm/s |
| `weld_proc_param` | list(float[9]) | 아래 표 | 시작·종료 시퀀스, 배열 순서 고정 |

| 배열 index | 의미 | 단위·범위 | 기본값 |
|---|---|---|---|
| 0 `Rsf` | 시작 피딩 / 본 피딩 | 비율, 0 초과 2 이하 | 0.2 |
| 1 `Rsv` | 시작 전압 / 본 전압 | 비율, 0 초과 2 이하 | 0.2 |
| 2 `Tss` | 용접 전 가스 출력 | s, 0 이상 | 0.5 |
| 3 `Tas` | 시작조건 유지 | s. 원문 범위식이 `Twc`로 잘못 표기됨 | 0.5 |
| 4 `Twc` | 본조건 전환시간 | s, 0 이상 | 0.5 |
| 5 `Rff` | 끝 피딩 / 본 피딩 | 비율, 0 초과 2 이하 | 0.2 |
| 6 `Rfv` | 끝 전압 / 본 전압 | 비율, 0 초과 2 이하 | 0.2 |
| 7 `Taf` | 끝조건 유지 | s, 0 이상 | 0.5 |
| 8 `Tsf` | 용접 후 가스 출력 | s, 0 이상 | 0.5 |

`f_target`을 전류로 자동 변환하지 않는다. 공식 설명도 전류가 모재·와이어·송급·돌출길이·전압에 영향을 받는다고 명시한다. `[확인 필요]` 설정 함수의 피딩 단위와 일부 활성화·모니터링 설명의 전류 표현이 혼재하므로, 전류지령 방식의 용접기는 별도 인터페이스 검증이 필요하다. [D01], [D02], [D20]

### 4.3 아날로그 입출력 연결

`app_weld_enable_analog()`의 입력이다. **용접작업별 값이 아니라 실제 결선에 대한 설정**이다. [D02]

| 인수 | 자료형·기본값 | 내용 |
|---|---|---|
| `ch_v_out` | int[2], `[1,0]` | 전압지령 출력 `[채널, 모드]` |
| `ch_f_out` | int[2], `[2,0]` | 피딩지령 출력 `[채널, 모드]` |
| `ch_v_in` | int[2], `[1,0]` | 측정전압 입력 `[채널, 모드]` |
| `ch_c_in` | int[2], `[2,0]` | 측정전류 입력 `[채널, 모드]` |
| `spec_v_out` | float[4], 모두 0 | `[최소전압 V, 대응출력, 최대전압 V, 대응출력]` |
| `spec_f_out` | float[4], 모두 0 | `[최소피딩 m/min, 대응출력, 최대피딩 m/min, 대응출력]` |
| `spec_v_in` | float[4], 모두 0 | `[센서 최소 V, 대응입력, 센서 최대 V, 대응입력]` |
| `spec_c_in` | float[4], 모두 0 | `[센서 최소 A, 대응입력, 센서 최대 A, 대응입력]` |
| `ch_arc_on` | int, 1 | 아크 출력 디지털 채널 1–16 |
| `ch_gas_on` | int, 2 | 가스 출력 채널 1–16, 미연결 0 |
| `ch_inching_fwd` | int, 3 | 정송급 채널 1–16, 미연결 0 |
| `ch_inching_bwd` | int, 4 | 역송급 채널 1–16, 미연결 0 |
| `ch_blow_out` | int, 5 | 토치 청소가스 채널 1–16, 미연결 0 |

아날로그 채널은 1–2, 미지정/센서 없음은 0이다. 모드는 `0=4–20 mA`, `1=0–10 V`다. 이 **제어신호 전압·전류**를 실제 용접전압·용접전류와 혼동하지 않는다. 대응값의 단위는 선택한 신호모드의 mA 또는 V다.

### 4.4 디지털 본조건

`app_weld_set_weld_cond_digital()`의 인수다. 아래 모든 인수의 원문 기본값은 **0**이다. 통신 매핑을 완료한 항목만 조건으로 사용할 수 있다. [D03]

| 인수 | 자료형 | 의미·단위·제약 |
|---|---|---|
| `flag_dry_run` | int | 0 실용접 / 1 모의용접 |
| `vel_target` | float | 용접 이동속도 mm/s |
| `vel_min`, `vel_max` | float | 속도 조정 하한·상한 mm/s |
| `welding_mode` | int | 용접모드 코드. 코드별 뜻은 연결 용접기에서 정의 |
| `s_2t` | int | 2T / 2T special 설정 |
| `pulse_mode` | int | 펄스모드 코드 |
| `wm_opt1` | int | 추가 용접모드 |
| `simulation` | int | 용접기 시뮬레이션 신호. `flag_dry_run`과 별개 |
| `ts_opt1`, `ts_opt2` | int | 추가 시험신호 |
| `job_num` | int | 용접기 Job 번호. 인수표는 `Job_num`, 예제는 `job_num`으로 불일치 |
| `synergic_id` | int | 시너직 번호 |
| `r_wire_feed_speed` | float | 송급 지령. 예제·목표 모니터링은 m/min, 실제 배율·허용범위는 통신맵 확인 |
| `voltage_correct` | float | 전압/아크길이 보정. 절대 V 지령으로 대체 불가 |
| `dynamic_correct` | float | 아크 특성 보정 |
| `r_opt1`–`r_opt15` | 각각 float | 15개의 추가 조건. 각 의미·단위·범위는 용접기별 정의 |

Job·시너직·모드·보정값의 보편적 최소·최대는 이 함수 문서에 없다. `job_num=4` 같은 예제 숫자는 허용 목록이나 추천값이 아니다. 디지털 조건에는 아날로그의 `weld_proc_param`이 없으므로 가스·시작·종료 시퀀스는 실제 용접기 Job과 통신 사양을 확인해야 한다.

### 4.5 용접 중 조건 조정

| 입력 의미 | 아날로그 인수 | 디지털 인수 | 자료형·단위·범위 |
|---|---|---|---|
| 조정/복귀 선택 | `flag_reset` | `flag_reset` | int, 0 조정 / 1 복귀 |
| 전압 | `v_target` | 전용 절대전압 인수 없음 | float, V |
| 피딩 | `f_target` | `f_target` | float, m/min |
| 이동속도 | `vel_target` | `vel_target` | float, mm/s |
| 위빙 offset | `wv_offset` | `wv_offset` | float[2], `[Y,Z]` mm. 두 원소 모두 필요 |
| 폭 변경 비율 | `wv_width_ratio` | `wv_width_ratio` | float, 0–2 |
| 동적 보정 | 없음 | `dynamic_cor` | float, 단위·범위 미기재 |
| 전압 보정 | 없음 | `voltage_cor` | float, 단위·범위 미기재 |
| Job 선택 | 없음 | `job_number` | 원문 조정표는 float. 본조건의 int와 달라 `[확인 필요]` |
| 시너직 선택 | 없음 | `synergic_id` | 원문 조정표는 float. 본조건의 int와 달라 `[확인 필요]` |

근거: [D05], [D06]. 숫자 조정값의 생략값은 함수 정의상 `None`이며 미지정 조건은 유지한다. 아날로그 `flag_reset` 기본값은 0이다. 디지털은 함수 정의 `None`, 표 0으로 충돌하므로 명시적으로 지정하는 편이 낫다.

명령으로 조정한 상태에서는 펜던트 실시간 조정이 제한된다. `flag_reset=1`은 펜던트에서 실시간 조정했던 최종 상태로 복귀할 수 있으며, 위빙폭 비율은 1로 돌아간다. 따라서 복귀를 항상 최초 파일 값으로의 복원이라고 표현하면 안 된다.

### 4.6 위빙 입력

공통 인수는 `wv_offset=float[2]` 기본 `[0,0]` mm, `wv_ang=float` 기본 0°다. offset은 위빙 좌표의 Y·Z 이동, 각도는 위빙 X축 기준 평면 회전이다. 위빙 X는 경로 진행방향이고, Y는 X와 TCP Z방향의 외적으로 정의된다. 이미지의 픽셀 좌표와 다르다. [D08]–[D12]

| 함수 | `wv_param`의 순서 | 기본값 |
|---|---|---|
| [`app_weld_weave_cond_zigzag`][D08] | `[폭 mm, 주기 s]`, float[2] | `[3,0.6]` |
| [`app_weld_weave_cond_sinusoidal`][D09] | `[폭 mm, 주기 s]`, float[2] | `[3,0.6]` |
| [`app_weld_weave_cond_circular`][D10] | `[X폭 mm,Y폭 mm,X주기 s,Y주기 s]`, float[4] | `[3,3,0.3,0.3]` |
| [`app_weld_weave_cond_trapezoidal`][D11] | `[P1x,P1y,P2x,P2y,T12,A12,D1,T21,A21,D2]`, float[10] | `[0,1.5,0,-1.5,0.3,0.1,0.3,0.3,0.1,0.3]` |
| [`app_weld_weave_cond_cwave`][D12] | `[각도,폭1,폭2,T1,T2,D1,D2,D3,D4]`, float[9] | `[45,10,10,0.5,0.5,0.2,0.2,0.2,0.2]` |

사다리꼴의 앞 4개 값은 mm, `T12/T21`은 왕복 각 구간 이동시간 s, `A12/A21`은 가감속시간 s, `D1/D2`는 끝점 dwell s다. C파형의 각도는 deg, 두 폭은 mm, 나머지 시간은 s다.

각 패턴의 공통 최소·최대는 해당 인수표에 미기재다. `[확인 필요]` 폭이 전체 진폭인지 편측 진폭인지와 패턴별 시간 합산 규칙은 도형·설치 버전으로 검증해야 한다. C파형은 정의의 `wv_ang/wv_param`과 표의 `wv_angle/ww_param`이 불일치한다. 문서의 숫자 배열만 바꿔 다른 패턴 함수에 넣지 않는다.

### 4.7 EtherNet/IP 통신 필드

아래는 **조건 값의 주소·표현을 지정하는 설정 함수**다. 같은 이름의 본조건 숫자와 혼동하면 안 된다. R2M은 로봇→용접기, M2R은 용접기→로봇 방향이다. 공식 문서는 아래 8종 설정과 EIP `Monitoring+GPR` 설정을 요구한다. [D07], [D13]–[D19], [D28]

| `app_weld_set_interface_eip_` 뒤 함수명 | 매핑 대상 |
|---|---|
| [`r2m_process`][D13] | `welding_start`, `robot_ready`, `error_reset` |
| [`r2m_mode`][D14] | `welding_mode`, `s_2t`, `pulse_mode`, `wm_opt1` |
| [`r2m_test`][D15] | `gas_test`, `inching_plus`, `inching_minus`, `blow_out_torch`, `simulation`, `ts_opt1`, `ts_opt2` |
| [`r2m_condition`][D07] | `job_num`, `synergic_id`, `r_wire_feed_speed`, `voltage_correct`, `dynamic_correct` |
| [`r2m_option`][D28] | `opt1`–`opt15` |
| [`m2r_process`][D17] | `current_flow`, `process_active`, `main_current`, `machine_ready`, `comm_ready` |
| [`m2r_monitoring`][D18] | `welding_voltage`, `welding_current`, `wire_feed_speed`, `wire_stick`, `error`, `error_num` |
| [`m2r_other`][D19] | `opt1`–`opt10` |

각 신호는 함수 정의상 **9개 값의 평탄한 배열**로 지정한다. 원문 표는 이를 `int[7]` 부분과 `float[2]` 부분으로 나눠 설명한다. 기본 배열은 모두 0이다.

| index | 의미 | 원문 값 |
|---|---|---|
| 0 | 사용 여부 | 0 미사용 / 1 사용 |
| 1 | 데이터 종류 | 0 On/Off / 1 선택 / 2 수치 |
| 2 | 자릿수 | 0 정수 / 1 소수 1자리 / 2 소수 2자리 |
| 3 | byte 위치 | 개별 함수 표 0–255 |
| 4 | bit 위치 | 개별 함수 표 0–7 |
| 5 | 크기 코드 | 0=1bit disable Low, 1=1bit disable High, 2=2bit, 3=4bit, 4=8bit, 5=15bit, 6=16bit, 7=32bit |
| 6 | 유효 데이터 비트 수 | 물리량 변환에 사용 |
| 7 | 물리량 최솟값 | float, 신호별 단위 |
| 8 | 물리량 최댓값 | float, 신호별 단위 |

근거: [D13], [D07]. Welding 상위 페이지의 byte/bit 범위는 위 개별 함수 표와 충돌하므로 **개별 함수와 용접기 시그널 데이터시트를 대조**한다. 수치 데이터에는 유효 비트 수와 물리량 범위가 필요하며, signed 표현·바이트 순서·단위도 장비별로 확인해야 한다.

`m2r_process`의 `main_current`를 설정하면 모션 시작 연동이 해당 신호를 사용하고, `process_active`를 설정하면 모션 종료 연동이 해당 신호를 사용한다. 미설정 시에는 `current_flow`와 연동한다. 이름에 current가 있어도 이 항목은 전류 A 지령이 아니라 상태 신호다. [D17]

### 4.8 위치와 모션

| 입력 | 의미·기본값·제약 |
|---|---|
| `posx(x,y,z,A,B,C,ori_type,sol,turn)` | 작업공간 포즈. XYZ 위치와 방향 표현을 함께 지정 |
| `ori_type` | 기본 `DR_ELR_ZYZ`; ZYX, XYZ, fixed XYZ, rotation vector, quaternion 지원 |
| `A,B,C` | 선택한 표현의 방향 값. Euler·rotation vector는 deg |
| quaternion | `[x,y,z,qx,qy,qz,qw]` 리스트 입력. 회전 성분은 단위 quaternion |
| `sol` | 구성 선택 0–7. `None` 자동 선택은 원문에 추후 지원 예정 표기 |
| `turn` | 원문에 추후 지원 예정 표기 |
| `movel pos` | 목표 `posx` 또는 위치 리스트 |
| `vel/v`, `acc/a` | float 또는 float[2], 기본 None. 선속도 mm/s·선가속도 mm/s²; 배열이면 회전 성분도 지정 |
| `time/t` | 도착시간 s, 기본 None. 지정 시 일반 모션의 vel·acc보다 우선 |
| `radius/r` | 블렌딩 반경 mm, 기본 None |
| `ref` | BASE / WORLD / TOOL / 사용자 좌표. 생략 시 설정된 기준좌표 |
| `mod` | 절대 `DR_MV_MOD_ABS` 기본 / 상대 `DR_MV_MOD_REL` |
| `ra` | `DR_MV_RA_DUPLICATE` 기본 / `DR_MV_RA_OVERRIDE` |
| `app_type` | `DR_MV_APP_NONE` 기본 / `DR_MV_APP_WELD` 용접 연동 |

근거: [두산 posx][D24], [두산 movel][D25]. **용접 연동이면 이동속도는 `movel vel` 대신 용접조건의 속도로 대체**된다. `[확인 필요]` `time` 기반 모션과 용접 연동의 결합 우선순위까지 명시된 것으로 해석하지 않는다. 데모 변환기는 이런 모호한 조합을 만들지 않는 것이 적절하다.

### 4.9 경로 보정과 신호 감시

| 함수·입력 | 자료형·기본값 | 의미·범위 |
|---|---|---|
| `app_weld_adj_motion_offset(offset)` | float[2], `[0.0,0.0]` | seam tracking의 Y·Z offset. 해당 페이지에 단위·범위 미기재 |
| `app_weld_get_extreme_point(time)` | float, 50 | 위빙 최외각 정보 획득 지연, ms |
| `app_weld_signal_contact_status`의 `ch_arc/ch_gas/ch_wire/ch_mcn` | 각 int[2], `[0,1]` | `[입력채널, 접점종류]` |
| 위 함수의 채널 | int | 1–20, 기본 0. 17–20은 SI1–SI4와 공용 |
| 위 함수의 접점종류 | int | A접점 1 / B접점 2 |
| 위 함수의 `timeout` | float, 1.0 | Arc Wait 최대 대기시간 s |

근거: [D04], [D26], [D27]. 신호 감시 채널은 아날로그 enable의 출력 채널과 별도다. 공용 채널 배치는 실제 설비 설정과 확인한다.

### 4.10 반환값과 실측 데이터

위의 DRL 용접 설정 함수들은 통상 **0 성공, 음수 실패**를 반환하고 잘못된 자료형·값·런타임·강제 종료에 대한 예외를 명시한다. 조회 함수는 아래 상태 항목을 반환한다. 외부 C/C++ API의 반환 규약과 혼합하지 않는다. [D01], [D03], [D20], [D21]

| 반환 항목 | 의미·단위 |
|---|---|
| `v_target`, `f_target`, `vel_target` | 목표값. V / m/min / mm/s. 아날로그 조회표의 `f_target`에는 전류 A 표현도 혼재 |
| `voltage_cor`, `dynamic_cor` | 디지털의 현재 보정 목표. 전압 보정은 조회표상 V |
| `v_meas`, `c_meas` | 측정전압 V / 측정전류 A |
| `f_meas` | 디지털 측정 피딩속도. 원문 단위 **mm/s**, 목표 피딩의 m/min과 다름 |
| `wv_offset` | 현재 위빙 Y·Z offset mm |
| `status` | 0 비용접 / 1 정상 용접 / 9 이상 / 99 Dry-run |
| `sig_out` | 아날로그의 arc/gas/정송급/역송급 출력 상태 |
| `error`, `wire_stick`, `error_num` | 디지털 에러·팁융착·에러번호 |
| `current_flow`, `process_active`, `machine_ready` | 디지털 전류 발생·공정 활성·준비 상태 |
| `option1`–`option10` | 미리 매핑한 추가 수신 신호 |

**아날로그의 측정 채널이 없으면 측정값 자리에 목표전압·목표피딩 값이 반환될 수 있다.** `c_meas`라는 이름만 보고 실제 전류 측정으로 저장하면 안 된다. 센서 연결 여부와 데이터의 원천을 함께 기록한다. 디지털의 목표·측정 피딩 단위 차이도 설치 장비에서 확인한 뒤 변환한다. [D20], [D21]

## 5 마킹 해석 결과와 연결할 항목

### 5.1 인식 결과와 설비 설정의 경계

현대 미션은 표기를 부재번호·작업 위치·방향·용접 종류로 구조화하고, 표기 규칙과 작업 기준에 연결해 조건을 설정하도록 요구한다. 모든 마킹에 전류·전압·속도가 직접 적혀 있다는 뜻은 아니다. [미션 원문][M01]

아래는 **[추론] 프로젝트의 추출·연결 설계**다. 제조사 원래 입력 필드와 작업 요구사항을 구분한다.

| 확보 정보 | 권장 내부 표현 | 제조사 입력으로의 연결 |
|---|---|---|
| 부재·이음 식별 | `part_id`, `joint_id` | 해당 작업 프로그램·조건표 조회. 곧바로 `job_num`으로 대입하지 않음 |
| 화살표와 표기의 연결 | 표기영역, 지시 대상, 관계 | 실제 용접 대상/구간과 연결. 화살표를 항상 이동방향으로 해석하지 않음 |
| 용접 종류·요구 치수 | 종류, 각장/목두께 구분, 수치·단위 | WPS·등록조건 선택. 각장 하나로 전류를 계산하지 않음 |
| 간헐 용접 길이·피치·범위 | 각각 의미를 보존한 길이 | 현대 stitch의 ON/OFF 거리·반복 구간 후보 |
| 방향·순서·패스 지시 | 방향의 기준, 작업 순서, 패스 요구 | 경로 순서·패스별 프로그램 구성 |
| 승인 조건·용접기 설정 | 전류/송급/파워 중 지령 종류와 값 | 현대 `cur` 또는 조건표, 두산 `f_target/r_wire_feed_speed` |
| 전압 관련 조건 | 절대전압/보정 종류·값·단위 | 제조사·용접기별 전압/offset 필드 |
| 속도·위빙·시퀀스 | 단위와 파형별 의미 | 제조사 필드로 변환 |
| CAD·교시·센싱 결과 | 좌표계·TCP·포즈·경로 | 현대 Pose/move, 두산 posx/movel |
| 설비 등록정보 | 모델·버전·통신·신호·조건 ID 대장 | 설치 프로파일. 마킹에서 생성하지 않음 |

### 5.2 최소 전달 계약

[추론] 노드 간 결과는 **해석된 작업 요구사항**과 **그 요구사항에 연결된 제조사 조건**을 함께 보존한다. 다음 묶음을 권장한다. 제조사에 바로 보내는 JSON API 형식은 아니다.

| 묶음 | 반드시 구분할 내용 |
|---|---|
| 근거 | 이미지·표기영역·읽은 값·관계·문서번호·개정 |
| 대상 | 프로젝트·부재·이음·작업 ID |
| 작업 요구 | 용접 종류·치수·길이·피치·방향·순서와 미확정 항목 |
| 설비 프로파일 | 로봇·제어기·소프트웨어·용접기·인터페이스·단위·지원 기능 |
| 조건 선택 | 로봇 프로그램 ID / 아크조건 ID / 위빙 ID / WDB ID / 용접기 Job·시너직 ID |
| 상세 지령 | `current_A` / `wire_feed_m_min` / `power_percent`처럼 물리량을 구분한 값 |
| 전압 종류 | absolute V / offset V / percent / VP / 용접기별 arc-length 보정 |
| 운동 | 경로 참조·좌표계·TCP·자세 표현·속도·보간 |
| 검증 상태 | 누락·문서 충돌·미지원 항목, 추천/확인/모의전달/실기실행의 상태 구분 |

등록조건을 선택할 때도 선택 근거가 필요하다. 예컨대 인식한 숫자가 `6`이라는 사실만으로 `arcon cnd=6` 또는 `job_num=6`을 만들지 않는다. 숫자의 의미가 각장인지 부재번호 일부인지 조건번호인지 먼저 해석해야 한다.

### 5.3 단위 변환과 동등하지 않은 필드

| 변환·비교 | 처리 |
|---|---|
| 이동속도 mm/s → cm/min | ×6. 예: 5 mm/s = 30 cm/min |
| 이동속도 cm/min → mm/s | ÷6 |
| 피딩속도 m/min → mm/s | ×1000/60. 예: 6 m/min = 100 mm/s |
| Hz ↔ s | 동일 주기 정의에서 `T=1/f`; dwell 포함 여부·다축 위빙은 별도 |
| 폭 | 전체 폭·편측 거리·XY 폭을 구분. 이름이 width라는 이유로 1:1 복사하지 않음 |
| 전류 ↔ 송급 ↔ 파워 | 단순 단위변환이 아님. 용접기·재료·프로그램 대응 필요 |
| V ↔ % ↔ VP | 일반 환산식 없음. 용접기 사양 필요 |
| 자세 3개 숫자 | Euler 순서·기준좌표·단위를 함께 변환. XYZ 위치와 회전 숫자만 복사하지 않음 |
| 제어기 `cnd` ↔ 용접기 `job` | 다른 번호 체계. 해당 셀의 등록 대장으로 연결 |

숫자 예시는 단위 검산용이며 실제 용접조건 추천이 아니다.

## 6 원문 불일치와 적용 전 확인 항목

| 항목 | 확인한 차이 | 이 명세의 처리 |
|---|---|---|
| 현대 `arccond cur/vol` | 기존 프로젝트 요약은 고정 범위, 현재 공식 원문은 용접기별 상이 | 고정 범위를 폐기하고 3.3절 적용 [H04] |
| 현대 시작조건 번호 | `arcon` 1–100 / UI 1–32 | 두 표를 분리. 설치 버전 확인 전 최대값 확정 안 함 [H01], [H05] |
| 현대 위빙 | 명령의 폭 1–50 / UI 1–25 mm; 주파수 하한 1 / 0 Hz | 입력 지점별 범위 보존 [H04], [H07] |
| 현대 초기·종료 지령 | 설명은 비율, 표는 일부 A·m/min | 값의 물리량과 비율 변환 UI 확인 [H05], [H06] |
| 현대 `weaving on` 문법 | 정의는 위치 인자, 예제는 `cnd=` | 제어기 문법 확인 [H03] |
| 두산 디지털 Job | 조건표 `Job_num` / 예제·매핑 `job_num` / 조정 `job_number` | 함수별 이름을 보존하고 실기 파서 확인 [D03], [D06], [D07] |
| 두산 디지털 조정 ID | 초기조건은 int / 조정표는 float | 허용 형식을 설치 버전에서 확인 [D03], [D06] |
| 두산 디지털 reset | 정의 None / 표 0 | 명시 인자로 지정 [D06] |
| 두산 C파형 | 정의 `wv_ang/wv_param` / 표 `wv_angle/ww_param` | 표기 충돌 기록, 실행 문법 확정 전 코드 생성 보류 [D12] |
| 두산 EIP 주소 | 상위 장의 byte·bit 설명과 개별 함수 표 불일치 | 개별 함수·용접기 시그널 데이터시트 대조 [D00], [D13] |
| 두산 아날로그 `Tas` | 범위식에 `Twc` 표기 | Tas 제한을 문서 확인값처럼 단정하지 않음 [D01] |
| 두산 예제 주석 | 60 mm/s를 1 cm/min로 표시, dry-run 값과 실용접 주석 불일치 | 인수표와 단위식 우선. 60 mm/s는 360 cm/min [D01], [D03] |
| 두산 아날로그 전류 표현 | 설정은 피딩, 활성화·조회 설명에 전류도 등장 | current A 입력 지원으로 일반화하지 않음 [D01], [D02], [D20] |
| 두산 측정 피딩 | 목표 m/min / 측정 mm/s | 신호·단위 출처 보존 [D21] |
| 신호 설정과 물리적 효과 | 기본값·문법 성공만으로 실제 출력 보장 안 됨 | 장비 프로파일·지원 기능·측정 피드백 확인 |

실제 연동을 확정하려면 **설치 제어기 버전, 용접기 모델·모드, 통신 데이터시트, 조건/Job 목록, TCP·좌표계, 작업 기준과 등록조건의 대응표**가 필요하다. 이 문서는 공식 입력 구조를 조사한 것이며, 해당 설비의 지원·경로·출력·용접 품질을 시험한 결과는 포함하지 않는다.

## 7 출처와 조회 기준

모든 링크의 확인일은 **2026-10-10 KST**다. 두산 D00–D28은 한국어 DRL V3.7.0, D29는 별도 외부 API 1.33.4다. 현대는 공개 `ko` 브랜치의 해당 파일을 읽었으며, 브랜치 링크는 추후 변경될 수 있다. 특정 설치 버전의 인증 사양으로 취급하지 않는다.

| 출처 묶음 | 확인한 범위 |
|---|---|
| H00–H04 | 현대 목차, 아크 시작·종료·위빙 명령, WDB 조건 변경 |
| H05–H10 | 현대 시작·종료·위빙 화면, 용접기별 추가 입력 |
| H11–H17 | 현대 스티치·멀티패스·터치센싱·재시도·재기동·설비 설정 |
| H18–H20 | 현대 이동·포즈와 Hi6 문서 진입점 |
| D00–D07 | 두산 지원 제한, 조건 설정·연결·조정·EIP 조건 매핑 |
| D08–D19 | 두산 위빙 5종, EIP 나머지 매핑 |
| D20–D27 | 두산 모니터링·종료·위치·이동·보정·신호 감시 |
| D28 | 두산 EIP 추가 송신 조건 매핑 |
| D29 | 두산 외부 API의 별도 버전·문서 계층 확인 |
| M01 | 현대 대회 미션의 마킹→작업지시→조건 설정 요구 |

재조회 시 핵심 변경 여부를 확인할 수 있도록, 읽은 현대 원문의 Git blob 식별자를 남긴다. 이는 커밋 ID가 아니라 파일 내용 ID다.

| 파일 | Git blob SHA |
|---|---|
| `doc-arc-weld/2_Command/1_arcon.md` | `04d7b72fa83c6bcbd267b01e4579f05553496fe2` |
| `doc-arc-weld/2_Command/5_arccond.md` | `a0323e9162328ffea85d4b7f41b1012535f3efce` |
| `doc-arc-weld/5_Condition_editing/3_Start_condition/README.md` | `d8d7096c016280f253716d304bd1fedbec3a4b40` |
| `doc-hrscript/5-moving-robot/4-move.md` | `8635dae4e8b55dc033eee52dbf63e4df8f1dbcc9` |

[H00]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/SUMMARY.md
[H01]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/1_arcon.md
[H02]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/2_arcoff.md
[H03]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/3_weavon.md
[H04]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/5_arccond.md
[H05]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/3_Start_condition/README.md
[H06]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/4_End_condition/README.md
[H07]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/6_Weaving_function/1_Weaving_function/1_condition_.md
[H08]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/3_Start_condition/1_hyosung.md
[H09]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/3_Start_condition/2_fronius.md
[H10]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/3_Start_condition/3_ewm.md
[H11]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/14_stitch.md
[H12]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/8_Application_function/6_Stitch/3_parameter.md
[H13]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/11_multipass.md
[H14]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/13_touchsen.md
[H15]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/5_Aux_condition/1_retry.md
[H16]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/5_Aux_condition/2_restart.md
[H17]: https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/4_Setting/2_Arc_setting/README.md
[H18]: https://github.com/hyundai-robotics/doc-hrscript/blob/ko/5-moving-robot/4-move.md
[H19]: https://github.com/hyundai-robotics/doc-hrscript/blob/ko/5-moving-robot/1-pose.md
[H20]: https://hrbook-hrc.web.app/#/view/doc-arc-weld/ko/README?cont_model=Hi6
[D00]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/welding
[D01]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar
[D02]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_enable_analog-ch_v_out-1-0-spec_v_out-0-0
[D03]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_digital-flag_dry_run-0-vel_
[D04]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_adj_motion_offset
[D05]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_adj_welding_cond_analog-flag_reset-0-v_ta
[D06]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_adj_welding_cond_digital-flag_reset-none-
[D07]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_condition-job_num-0
[D08]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_zigzag-wv_offset-0-0-wv_ang-0-
[D09]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_sinusoidal-wv_offset-0-0-wv_an
[D10]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_circular-wv_offset-0-0-wv_ang-
[D11]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_trapezoidal-wv_offset-0-0-wv_a
[D12]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_cwave
[D13]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_process-welding_sta
[D14]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_mode-welding_mode-0
[D15]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_test-gas_test-0-0-0
[D16]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_enable_digital
[D17]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_m2r_process-current_flo
[D18]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_m2r_monitoring-welding_
[D19]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_m2r_other-opt1-0-0-0-0-
[D20]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_get_welding_cond_analog
[D21]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_get_welding_cond_digital
[D22]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_disable_analog
[D23]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_disable_digital
[D24]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/posx-x-0-y-0-z-0-a-0-b-0-c-0
[D25]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/movel
[D26]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_get_extreme_point
[D27]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_signal_contact_status
[D28]: https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_option-opt1-0-0-0-0
[D29]: https://doosanrobotics.github.io/doosan-robotics-api-manual/GL013304/applications/welding/welding.html
[M01]: https://ainnov.co.kr/public/assets/download/pac/pac2026_hd-hyundai-robotics_mission_3.pdf
