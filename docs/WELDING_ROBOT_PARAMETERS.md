# 두산·HD현대로보틱스 용접 프로그램 입력 파라미터

확인일: **2026-10-09**. 공식 제조사 프로그래밍 문서와 공식 공개 매뉴얼 저장소를 확인했다. 아래 수치는 **명령·설정 화면의 입력 범위**이며 특정 재료에 권장하는 용접조건이 아니다. 실제 장비·용접기·제어기 버전이 지정되지 않았으므로 지원 여부와 현장 설정은 별도 확인이 필요하다.

파이프라인 단계별 모델·자료와 공개 시연은 [오픈 모델·공개 자료·시나리오](PIPELINE_OPEN_RESOURCES_AND_SCENARIO.md)에 정리했다. 이 문서는 제조사 입력 항목을 독립적으로 확인하는 용도다.

## 1. 먼저 구분할 것

| 구분 | 두산 | HD현대로보틱스 |
|---|---|---|
| 이번 조사 기준 | **DRL Programming manual V3.7.0 한국어**의 Welding 명령 | **HRBOOK의 Hi6 선택 상태**, 공식 `hyundai-robotics/doc-arc-weld` 한국어 문서 |
| 명령을 결정하는 요소 | 제어기 소프트웨어 버전, 아날로그/디지털 연결, 연결 용접기 | Hi6 제어기 소프트웨어 버전, HRScript, 아크 옵션, 연결 용접기 |
| 확인된 제한 | V3.7.0 Welding 문서에 **P 시리즈 미지원** 명시 | 용접기에서 지원하지 않는 `arcon` 형태는 사용할 수 없음 |
| 이번 조사로 확정하지 않은 것 | 특정 M/H/A/E 기종별 전체 용접 기능 지원 | 특정 HA/HH/HDR 기종과 제어기·옵션 조합별 전체 지원 |
| 잘못된 분류 | “두산 로봇이면 전부 같은 파라미터·범위” | “현대 로봇이면 전부 전류 A·전압 V 직접 입력” |

근거: [두산 V3.7.0 Welding](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/welding), [현대 Hi6 아크용접 HRBOOK](https://hrbook-hrc.web.app/#/view/doc-arc-weld/ko/README?cont_model=Hi6), [현대 arcon](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/1_arcon.md).

로봇 본체 모델은 가반하중·도달범위·자세·접근 가능성과 연결되지만, 아래 프로그램 필드는 주로 **제어기 API와 용접기 인터페이스**에 속한다. 현대용접(Hyundai Welding)의 용접기 자료와 HD현대로보틱스 제어기 자료도 서로 구분한다.

## 2. 두산 DRL V3.7.0

### 2.1 아날로그 용접조건

`app_weld_set_weld_cond_analog()`에서 지정한다. `app_weld_enable_analog()`와 `app_weld_disable_analog()` 사이에서 유효하고, 한 구간의 기준조건을 설정한 뒤 조정 명령으로 변경하는 구조다.

| 인수 | 의미·단위 | 문서상 범위/주의 |
|---|---|---|
| `flag_dry_run` | 실용접/모의용접 선택 | `0` 실용접, `1` 모션·위빙·옵셋만 |
| `v_target` | 목표전압, V | 용접기·인터페이스 허용범위 확인 |
| `f_target` | 목표 와이어 피딩속도, m/min | 전류 A와 구별 |
| `vel_target` | 용접 이동속도, mm/s | 펜던트 cm/min와 다름 |
| `vel_min`, `vel_max` | 이동속도 조정 하한·상한, mm/s | 허용 조정영역 |
| `weld_proc_param` | 시작·종료 시퀀스, float 9개 | 아래 순서 고정 |

`weld_proc_param` 순서: `[Rsf, Rsv, Tss, Tas, Twc, Rff, Rfv, Taf, Tsf]`.

| 항목 | 뜻 | 단위·범위 |
|---|---|---|
| `Rsf`, `Rsv` | 시작 피딩속도/전압의 본조건 대비 비율 | V3.7.0: 각각 `0 < 값 ≤ 2` |
| `Tss` | 가스 예출 시간 | s, ≥0 |
| `Tas` | 시작조건 유지시간 | s, 범위 식의 변수명 오기 존재 |
| `Twc` | 본조건 전환시간 | s, ≥0 |
| `Rff`, `Rfv` | 종료 피딩속도/전압의 본조건 대비 비율 | V3.7.0: 각각 `0 < 값 ≤ 2` |
| `Taf`, `Tsf` | 종료조건 유지/가스 후출 시간 | s, ≥0 |

전류는 와이어 피딩속도 외에도 모재·와이어·돌출길이·전압 등에 영향받으므로, 이 함수에 임의의 `current` 인수를 추가하거나 A를 `f_target`에 넣지 않는다.

근거: [아날로그 조건 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar).

### 2.2 아날로그 접속 설정 — 매 용접 이음의 조건과 분리

| `app_weld_enable_analog()` 인수 | 설정 내용 |
|---|---|
| `ch_v_out`, `ch_f_out` | 전압/피딩 지령 채널과 출력모드. 채널 1~2, 미지정 0; 모드 0=4~20mA, 1=0~10V |
| `spec_v_out`, `spec_f_out` | `[용접기 최소값, 대응 제어출력, 용접기 최대값, 대응 제어출력]` |
| `ch_v_in`, `ch_c_in` | 측정전압/전류 센서 채널과 모드. 센서 없으면 채널 0 |
| `spec_v_in`, `spec_c_in` | 센서 물리량과 제어기 입력의 최소·최대 대응 |
| `ch_arc_on` | 아크 출력 디지털 채널 1~16 |
| `ch_gas_on`, `ch_inching_fwd`, `ch_inching_bwd`, `ch_blow_out` | 가스·정/역송급·청소 신호. 1~16, 미연결 선택항목은 0 |

이는 실제 결선과 용접기 전기적 사양에서 설정한다. 사진·WPS 인식 결과가 수정할 대상은 아니다.

근거: [아날로그 활성화 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_enable_analog-ch_v_out-1-0-spec_v_out-0-0).

### 2.3 디지털/EtherNet/IP 용접조건

`app_weld_set_weld_cond_digital()`에서 지정한다. 아래 값 중 해당 용접기와 통신 인터페이스가 설정된 항목만 사용할 수 있다.

| 인수 | 목적 | 단위·범위 주의 |
|---|---|---|
| `flag_dry_run` | 실용접/모의용접 | 0/1 |
| `vel_target`, `vel_min`, `vel_max` | 이동속도와 조정범위 | mm/s |
| `welding_mode`, `s_2t`, `pulse_mode`, `wm_opt1` | 공정모드·2T 동작·펄스·모드옵션 | 정수 코드 의미는 용접기별 |
| `job_num` | 용접기에 저장된 Job 선택 | 제어기 로봇 프로그램 ID와 다름 |
| `synergic_id` | 시너직 조건 선택 | 재료·와이어·가스 조합과 용접기 등록표 확인 |
| `r_wire_feed_speed` | 와이어 피딩 지령 | 예제 및 모니터링은 m/min; 통신 배율 확인 |
| `voltage_correct` | 전압/아크길이 보정 | 절대전압 `v_target`와 다름 |
| `dynamic_correct` | 아크 특성 보정 | 용접기별 사양 |
| `simulation`, `ts_opt1`, `ts_opt2` | 시뮬레이션·시험 신호 | `flag_dry_run`와 의미를 합치지 않음 |
| `r_opt1`~`r_opt15` | 추가 옵션 | 옵션별 의미·단위·범위는 용접기별 |

인수표에는 `Job_num`, 예제에는 `job_num`으로 표기되어 있다. [확인 필요] 실제 설치 버전의 정확한 인수 대소문자는 SDK/제어기에서 확인한다. 문서 예제 숫자를 보편적 허용범위로 사용하지 않는다.

근거: [디지털 조건 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_digital-flag_dry_run-0-vel_).

`app_weld_set_interface_eip_r2m_condition()`는 `job_num`, `synergic_id`, `r_wire_feed_speed`, `voltage_correct`, `dynamic_correct`의 통신 위치·자료형·소수점·최솟값·최댓값을 연결한다. 이 설정은 용접기 통신 시그널 데이터시트가 근거다. 공식 문서상 R2M `process/mode/test/condition/option`, M2R `process/monitoring/other` **8종 설정**이 필요하고 EIP 설정은 `Monitoring+GPR`로 지정한다.

근거: [EtherNet/IP 조건 매핑 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_interface_eip_r2m_condition-job_num-0).

### 2.4 두산 위빙·경로·모니터링

| 명령·인수 | 입력 구조 |
|---|---|
| `app_weld_weave_cond_zigzag()` | `wv_offset=[Y,Z]` mm, `wv_ang` deg, `wv_param=[폭 mm, 주기 s]` |
| `app_weld_weave_cond_trapezoidal()` | 공통 offset/angle + 두 점 XY, 왕복 이동시간·가감속시간·각 끝점 dwell |
| 사다리꼴 `wv_param` 순서 | `[p1x,p1y,p2x,p2y,t12,a12,dwell1,t21,a21,dwell2]`; XY는 mm, 시간은 s |

위빙 좌표는 진행방향과 TCP 방향으로 정의되므로 이미지 화면의 좌우를 그대로 Y/Z로 쓰지 않는다. 제조사 간 “폭”이 전체 폭인지 편측 거리인지, dwell이 주기에 포함되는지도 보존해야 한다.

근거: [지그재그 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_zigzag-wv_offset-0-0-wv_ang-0-), [사다리꼴 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_weave_cond_trapezoidal-wv_offset-0-0-wv_a).

용접 경로는 별도 위치·자세와 `movel` 등의 모션 명령이 담당하며 공식 예제는 `app_type=DR_MV_APP_WELD`를 사용한다. 디지털 모니터링은 목표와 측정을 분리한다: `f_target`은 m/min, `vel_target`은 mm/s, `v_meas`는 V, `c_meas`는 A, `f_meas`는 문서상 mm/s다. `status`는 0/1/9/99(비용접/정상/이상/Dry-run), 준비·에러·와이어융착 신호도 반환한다. **지령값을 실측값처럼 저장하지 않는다.**

근거: [디지털 모니터링 V3.7.0](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_get_welding_cond_digital).

## 3. HD현대로보틱스 Hi6 아크용접

### 3.1 HRScript의 명령과 번호 체계

| 명령 | 입력 항목 | 공식 명령 문서의 범위 |
|---|---|---|
| `arcon` | `cnd` 시작·본조건 번호 | 1~100. 아래 편집화면과 불일치 |
| `arcon` | `cur`, `vol` | 0~500 A, 20~40 V |
| `arcon` | `vol_offset` | -200~200 V로 기재. 설치 용접기 의미 확인 필수 |
| `arcon` | `job` | 0~9999. Job 모드 지원 용접기 내부 번호 |
| `arcoff` | `welder`, `delay` | 2대 구성에서 용접기 1~2와 지연 0~2 s |
| `weaving on` | 위빙 `cnd` | 1~1000 |

근거: [arcon](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/1_arcon.md), [arcoff](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/2_arcoff.md), [weaving on](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/3_weavon.md).

`arcon`의 `cnd`, 용접기 `job`, 위빙 `cnd`, `arccond`의 WDB `cnd`, 로봇 작업 프로그램 번호는 서로 다른 ID다. 공통 데이터에 하나의 `job_id`만 두면 잘못 매핑하기 쉽다.

### 3.2 `arccond` — 구간별 조건·WDB 보간

| 필드 | 뜻 | 문서 범위 |
|---|---|---|
| 첫 인자 `D`/`L` | 즉시변경/선형보간 변경 | 문자 |
| `cnd` | WDB 및 보간조건 번호 | 1~1000 |
| `gap` | 이음 간격 | -1~1000 mm; -1의 사용 의미는 적용 기능 확인 |
| `spd` | 이동속도 | 1~1000 cm/min |
| `rd`, `ld` | 벽방향·타방향 위빙 폭 | 각 1~50 mm |
| `freq` | 위빙 주파수 | 1~10 Hz |
| `cur`, `vol` | 전류·전압 | 1~1000 A, 1~200 V |

여기 적힌 문법 수용범위가 `arcon`·용접기 하드웨어·WPS의 허용범위를 대신하지 않는다. 보간 조건의 물리적 적용성은 별도 검증 대상이다.

근거: [arccond](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/5_arccond.md).

### 3.3 디지털 용접기의 시작·본조건

같은 화면의 핵심 지령이라도 용접기에 따라 단위가 다르다.

| 용접기/모드 | 본조건의 주 지령 | 전압 관련 지령 |
|---|---|---|
| 효성 | 용접전류 40~350 A | 개별모드 10~38 V, 시너직 보정 50~150% |
| EWM | 송급속도 0~25 m/min | 옵셋 -10~10 **VP** |
| Fronius TPS | 용접파워 0~100% | 아크길이 보정 -30~30% |

| 공통 설정 | 문서 범위 |
|---|---|
| 조건번호 | 편집화면 1~32. `arcon` 설명의 1~100과 다름 |
| 가스 예출·로봇 지연·초기조건 유지·슬로프·제한 초과 허용시간 | 각각 0~10 s |
| WCR 대기 | 1~10 s |
| 감시 전압 상하한 | 0~100 V |
| 감시 전류 상하한 | 0~1000 A |

초기조건 지령도 본조건의 지령 종류를 따라 별도 지정한다. 시너직 코드·설명 필드도 존재한다. **VP/%와 V, 파워 %와 전류 A를 같은 값으로 취급하지 않는다.**

근거: [시작조건 편집](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/5_Condition_editing/3_Start_condition/README.md).

### 3.4 종료조건

| 항목 | 범위·단위 |
|---|---|
| 종료 주 지령 | 효성 28~350 A; EWM 0~25 m/min; Fronius TPS 10~100% |
| 종료 전압/보정 | 효성 개별 10~38 V, 시너직 50~150%; EWM -10~10 VP; Fronius -30~30% |
| Downslope·가스 후출 | 각각 0~10 s |
| Burnback | 0~200 ms |
| 크레이터 이동 | 시간 0~10 s, 거리 0~100 mm |
| 추가 항목 | 크레이터 위빙 여부·폭 비율·Hz, 역인칭 시간·속도, 용착 해제 횟수·조건·시간 |

[확인 필요] 종료조건의 설명문은 일부 항목을 비율이라고 부르지만 표는 효성 A, EWM m/min으로 나눈다. 해당 설치 화면·용접기 정의를 우선 확인해야 한다. 크레이터 위빙의 `V70.04` 지원 주석도 있으므로 이를 모든 Hi6 버전의 공통 기능이라고 쓰면 안 된다.

근거: [Hi6 HRBOOK 종료조건](https://hrbook-hrc.web.app/#/view/doc-arc-weld/ko/5_Condition_editing/4_End_condition/README?cont_model=Hi6).

### 3.5 위빙 조건 화면

| 항목 | 화면 문서의 범위·선택지 |
|---|---|
| 조건 번호 | 1~1000 |
| 형태 | 단진동·삼각·L형·원형·버티컬 |
| 주파수 | 0~10 Hz. 0이면 구간 이동시간 방식 |
| 벽방향·타방향 거리 | 각각 1~25 mm |
| 기본 각도 | 0.1~180° |
| 진행 각도 | -90~90° |
| 벽방향 기준 | 수직·수평·토치자세 |
| 구간 이동시간·정지 타이머 | 0.01~10 s / 0~2 s |
| 기타 | 경계 제한, dwell 중 이동/정지, 구동축(로봇/부가축), 부가축 번호 |

`arccond`의 폭 1~50 mm·주파수 1~10 Hz와 이 화면의 범위를 혼합하지 않는다. 위빙 “전체 폭”과 “편측 거리”의 공통 표현을 정의한 후 각각 변환한다.

근거: [Hi6 HRBOOK 위빙조건](https://hrbook-hrc.web.app/#/view/doc-arc-weld/ko/6_Weaving_function/1_Weaving_function/1_condition_?cont_model=Hi6).

## 4. 파이프라인의 공통 작업 명세에 넣을 필드 제안

아래는 [추론] 위 공식 API를 비교해 제안하는 내부 표현이며 기존 제품 구현 상태가 아니다.

| 공통 필드 묶음 | 최소 보존 내용 | 출처/소유자 |
|---|---|---|
| 대상·근거 | 프로젝트/부재/이음 ID, 문서번호·개정, 이미지 영역, OCR 원문·후보, WPS ID | 사진·작업지시·도면·WPS |
| 적용 조건 | 공정, 모재, 두께, 이음, 자세, 용가재·직경, 가스, 예열·층간온도, 패스 | 승인 WPS·작업지시 |
| 용접 지령 | 지령 종류(`current`/`wire_feed`/`power_pct`/`welder_job`), 값·단위·허용범위 | WPS와 검증된 용접기 조건 |
| 전압 지령 | 절대 V / offset V / % / VP / arc-length 보정 중 종류·값 | 용접기별 조건표 |
| 운동 | 속도, 경로점, 좌표계, TCP, 토치 자세, 접근·이탈, 보간 | CAD·교시·센서·캘리브레이션 |
| 위빙 | 패턴, 편측 폭/전체 폭 구분, 주파수/주기, dwell, 기울기·offset | WPS/등록 조건 + 제조사 매핑 |
| 시퀀스 | 가스 예출·후출, 시작/종료조건, ramp·crater·burnback | 승인 조건과 용접기 설정 |
| 등록 ID | 로봇 프로그램 ID, 제어기 아크조건 ID, 위빙조건 ID, WDB ID, 용접기 Job ID | 셀별 등록 대장 |
| 셀 프로파일 | 제조사·본체·제어기·소프트웨어·용접기 모델/버전·통신맵 | 설비 구성. 사진 인식 대상 아님 |
| 검증 | 누락/충돌/미지원 항목, 단위 변환 이력, 전문가 확인, 실행 승인 상태 | 검증 단계 |

단위 변환: **1 mm/s = 6 cm/min**, **1 cm/min = 1/6 mm/s**. 따라서 내부 이동속도가 5 mm/s라면 두산 DRL `vel_target=5`, 현대 cm/min 필드에는 30이다. 이는 단위변환 예시이며 용접조건 추천이 아니다. 주파수↔주기 변환도 동일한 파형·dwell 정의일 때만 적용한다.

## 5. 확인 필요 사항과 구현 방향

| 항목 | 처리 |
|---|---|
| 실제 로봇/제어기/용접기 모델·버전 미지정 | 셀 프로파일 확정 전 특정 모델 지원·가용 범위 확정 금지 |
| 두산 예제·표의 오기 | 속도환산·Dry-run 주석·Tas 변수명 충돌. 인수표·단위식을 대조하고 설치 버전 확인 |
| 두산 EN V3.2.1 비율 상한 1 / KO V3.7.0 상한 2 | 두 공식 문서의 표기가 다름. 언어·문서 갱신 차이도 있어 실제 버전별 동작 차이는 [확인 필요] |
| 현대 `arcon cnd` 1~100 / 시작조건 UI 1~32 | 둘을 별도 출처로 보존하고 실제 제어기에서 확인 |
| 현대 위빙 폭·주파수 명령/화면 범위 차이 | API별 제한과 용접기 제한을 각각 검증 |
| 공개 문서가 학습용 오픈 데이터인지 | 공개 열람과 자유 재배포·학습 라이선스는 별개. 제조사 문서 링크·요약 중심 사용 |

문서 표기 차이 근거: [두산 V3.2.1 아날로그](https://manual.doosanrobotics.com/en/programming-manual/3.2.1/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar), [두산 V3.7.0 아날로그](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar). 현대 공개 매뉴얼 사용 안내: [다운로드 안내](https://down-hd.web.app/docs/manpdf/).

[추론] 현 단계 시연은 **검증된 등록조건/등록작업 선택**을 먼저 보여주는 편이 적합하다. 인식 결과와 WPS가 일치하면 `robot_program_id`·`controller_condition_id`·`welder_job_id` 후보를 제시하고, 좌표·TCP·설비 프로파일·승인이 없으면 실행 가능한 프로그램 생성을 보류한다. 새 프로그램 생성은 CAD/3D 좌표와 자세·도달성·충돌 검증이 추가로 확보된 경우의 별도 경로로 둔다.

실물 로봇·제어기·용접기 실행 검증은 수행하지 않았다.
