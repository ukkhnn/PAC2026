# 작업조건 자동 적용과 현대·두산 입력 변환

기준일: 2026-10-10. 작업지시에 연결된 등록조건을 조회하여 전류·전압·이동속도의 기본값을 채우고 현대 Hi6 또는 두산 DRL 입력 형식으로 변환한다. 화면의 **작업조건**에서 값을 수정할 수 있으며, 제조사를 바꿔도 공통 항목의 수정값을 유지한다. 기존 문서 범위 전달 계약 `document-range-review.v1`은 유지한다.

## 구현 범위

| 자동 적용 항목 | 등록조건 | 현대 Hi6 | 두산 DRL 아날로그 |
|---|---|---|---|
| 전류 | 180 A | cur = 180 | 참조값으로 보존, 명령에 넣지 않음 |
| 전압 | 26 V | vol = 26 | v_target = 26 |
| 용접 이동속도 | 10 in/min | spd = 25.4 cm/min | vel_target = 4.233333 mm/s |
| 와이어 송급속도 | 6 m/min | 이 모드에서 미사용 | f_target = 6 |

현대는 전류 A·절대전압 V를 받는 모드를 프로파일에 명시한다. 실제 `cur`·`vol` 의미와 허용 범위는 연결 용접기 설정에 따라 다르다. 두산은 DRL 3.7.0의 아날로그 함수만 지원하며, 전류를 송급속도로 환산하지 않는다. `f_target`은 등록조건의 독립 값을 읽는다. 두 프로파일 모두 특정 로봇 본체나 용접기 모델을 선정하지 않았고 Isaac의 UR10 장면과 별개의 출력 형식이다.

근거는 [현대 공식 arccond 문서](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/5_arccond.md), [두산 공식 아날로그 용접조건 문서](https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar), [제조사 입력 상세 명세](WELDING_ROBOT_INPUT_SPEC.md)다. 현대의 확보 원문 SHA-256은 프로파일에 보존한다. 아크 시작·활성화·경로·통신·Job 등록은 생성하지 않는다.

## 기본값의 기준과 인식 연결 상태

`configs/document_demo/weld_recipes.json`의 `RECIPE-DEMO-015`가 `WO-DEMO-015` 개정 1과 LANL WPS 개정 1의 `layer-1`에 연결된다. 사용자가 허용한 시연 기본값을 명시해 두었으며, WPS 범위의 중간값을 자동 선정하지 않는다. WPS 범위 근거와 등록조건의 선택값 근거를 분리해 저장한다. 레시피 원데이터에는 `source_kind=fixture`를 유지한다.

현재 화면의 `180 A`, `26 V`, `10 in/min`, 송급 `6 m/min`은 **이미지의 마킹에서 직접 검출한 수치가 아니다.** 시연 레시피에 등록한 값이다. 마킹 식별자 `BISB30N-15`와 작업지시 `WO-DEMO-015`의 연결도 현재 화면에서는 시나리오 설정을 사용한다. 실제 OCR/VLM 판독 결과를 이 화면의 작업지시 선택과 기본값 적재로 자동 연결하는 부분은 아직 구현하지 않았다. 기존에 저장한 인식·문서 실험의 결과가 이 화면에서 새로 실행된 것은 아니다.

기준 파이프라인은 **원본 사진 → 문자 인식 및 화살표·기호·접합부 검출 → 문서와 함께 관계 해석 → 공통 용접 작업명세 → 조건 누락·충돌 검증 → 제조사 변환 → 작업 프로그램 또는 등록 작업**이다. 전류·전압 등이 마킹에 직접 쓰여 있다고 가정하지 않는다. 현재 화면은 지정된 시나리오의 대상·작업지시에서 공통 명세를 만들고 검증한 뒤 제조사별 미리보기를 파생한다. 사진에서 관계를 해석해 이 화면으로 자동 적재하는 앞부분과 실제 작업 프로그램 생성·등록은 아직 연결하지 않았다.

`build_work_order_input_previews(wps, work_orders, recipe_book, profiles, order_id=...)`가 작업지시 ID·개정, WPS 문서·개정·행, 필드 단위와 값의 범위를 확인한 뒤 두 제조사 미리보기를 함께 만든다. 누락·중복·불일치는 보류한다. 이 자동화는 등록조건 조회와 입력 변환이며, WPS만으로 용접조건을 새로 추론하거나 현장 적용성을 승인하는 기능은 아니다.

반환값의 `common_spec`은 설명용 표가 아니라 제조사 변환이 실제 입력으로 사용하는 중간 산출물이다. `common-weld-spec-preview.v1`에 대상 부재·이음, 작업지시·WPS 참조, 공정·재질·자세와 근거가 있는 공통 파라미터를 저장한다. 대상에는 `observation_ref=null`, `source_kind=fixture`, 관계에는 `relation_origin=scenario_mapping`을 남긴다. 두 제조사 변환은 같은 `common_spec.parameters`에서 선택값을 읽는다. 대상·공정 누락, 작업지시 상태, 공정·재질 충돌과 수치·단위를 검사한 뒤 파생하며, 검증 범위는 `document_fields_and_numeric_ranges_only`다. `physical_applicable=false`, `execution_authorized=false`는 유지한다.

## 화면 수정과 기록

전류·전압·용접 이동속도와 두산의 와이어 송급속도를 수정하면 변환된 입력값과 명령 미리보기가 갱신된다. 전류·전압·이동속도의 입력 단위는 WPS 원문의 `A`, `V`, `in/min`이며, 제조사 토글은 같은 속도를 현대 `cm/min` 또는 두산 `mm/s`로 변환한다. 두산 화면에서 전류는 참조값이다. 전류를 수정해도 송급속도를 계산하지 않으며, 송급은 별도 등록값 `6 m/min`에서 시작한다.

전류·전압·이동속도가 WPS 범위를 벗어나거나 입력 형식이 잘못되면 명령을 표시하지 않고 변환안 저장을 막는다. 송급속도는 양수의 사용자 수정값을 허용한다. 이때 레시피의 `6–6 m/min`은 원래 등록값을 표현한 것이므로 수정값의 허용 범위로 사용하지 않으며, `source_range_applies_to_override=false`로 기록한다. 원문에 없는 송급 허용 범위를 새로 만들지 않는다. 백엔드의 자동 레시피 조회는 등록값 일치 검사를 유지하고, 브라우저에서 만든 개인 변환안의 명시적 수정과 구분한다.

기본값으로 복원하면 등록조건을 다시 사용한다. 수정은 브라우저의 작업 상태에만 반영하며 원본 WPS·작업지시·레시피 파일은 바꾸지 않는다. 새로고침하면 등록된 기본값과 현대 프로파일로 돌아간다.

변환안 JSON은 `overrides[field]`의 `before`, `after`, `source_kind=user`로 원래 선택값과 사용자 수정값을 분리한다. 변경된 필드는 `selection_origin=user_override`와 `selection_evidence`의 `dashboard_input` 출처를 사용하고, 이전 레시피 근거는 `original_selection_evidence`에 보존한다. 공통 명세의 파라미터도 현재 수정값과 맞추며 `origin=user`와 사용자 근거를 기록하고, 기존 레시피 근거는 `original_evidence`에 남긴다. WPS 범위 근거도 유지한다. 사용자 수정이 있으면 `review_required=true`이며 `execution_authorized=false`는 그대로다. 수정값을 인식 결과나 원문에 쓰인 값으로 기록하지 않는다. **변환안 JSON 보기** 버튼은 현재 결과를 모달에 표시하고, 모달 안의 **JSON 파일 내려받기** 링크로 저장할 수 있게 한다. 작업지시 갱신이나 로봇 전송은 수행하지 않는다.

## 사용

```sh
PYTHONPATH=src python3 -m contextweld.robot_input \
  --wps data/knowledge/lanl-wps-3501-reviewed.json \
  --profile configs/robot_profiles/hyundai_hi6_current_voltage.json \
  --current 180 --voltage 26 --travel-speed 10 \
  --output output/hyundai-input-preview.json
```

선택값은 WPS의 원문 단위로 받는다. 위 명령은 다음 미리보기를 만든다.

```text
arccond D, cur=180, vol=26, spd=25.4
```

위 CLI는 현대 단일 변환용 개발 도구다. 선택값을 생략하면 범위만 변환하고 `needs_setpoints`를 반환한다. 대시보드의 자동 설정은 아래 설치기와 작업지시 조회 함수를 사용한다. Python은 Decimal, 브라우저는 정수 기반 십진 연산으로 변환한다. 두산의 나눗셈 결과는 소수점 아래 6자리에서 HALF_UP 반올림하며, 변환식과 정밀도를 JSON에 남긴다.

## 로컬 관리자 화면에 붙이기

기존 관리자 내보내기 패키지와 `shipyard-recapture` 시나리오가 있는 상태에서 실행한다.

```sh
python3 scripts/add_robot_dashboard_preview.py \
  --package output/dashboard-preview-20261010/pac-admin-dashboard
```

`전달 내역` 탭에 공통 명세 → 조건 검증 → 제조사 변환의 구성과 제조사 토글, 8번째 단계를 추가한다. 원문 범위, 수정 가능한 작업조건, 제조사 필드, 변환값, 명령을 함께 표시한다. 현대·두산 선택과 공통 작업조건은 탭이나 제조사를 바꿔도 유지된다. 설치기는 `robot-input-preview.json`에 공통 명세와 양쪽 제조사의 기본 변환 결과를 저장하며, 화면의 **변환안 JSON 보기**는 현재 선택한 제조사의 수정 내용을 포함한 결과를 표시한다.

설치기는 `presentation_scenario`만 수정한다. 실제 인식·문서·재검토 실행 묶음은 수정하지 않는다. 패키지에 결과 JSON·raw 조회 파일·화면 스크립트를 추가하고 파일 목록과 체크섬을 갱신한다. 같은 패키지에 재실행해도 단계·블록을 중복 생성하지 않는다. 서버의 대시보드 생성기와 자동 통합한 상태는 아니며, 내보낸 사본에 적용하는 추가 단계다.

## 상태의 의미

- `preview_ready`: 필드·단위 변환과 개별 WPS 범위 검사가 끝난 상태.
- `range_combination_validated=false`: 선택한 전류·전압·속도의 조합을 용접 품질 조건으로 검증한 것은 아니다.
- `hardware_verified=false`, `application_authorized=false`, `execution_authorized=false`, `delivery_requested=false`: 실기 적합성·적용 승인·전송과 분리한다.
- 두산은 `flag_dry_run=1`과 목표값으로 고정한 `vel_min/vel_max`를 표시한다. 해당 플래그도 실제 실행 시 모션을 허용할 수 있으며, 이 도구는 명령 문자열을 생성할 뿐 실행하지 않는다.
- 현대·두산 실기 전송과 실제 모션은 이번 구현에 포함하지 않는다.

## 확인

핵심 변환·자동조회 테스트 17개가 통과했다. 정상·경계값·정확한 소수 변환·선택 누락·지원하지 않는 모드·비유한 수치·범위 초과·근거 불일치·작업지시/등록조건 연결·CLI 저장과 공통 명세의 실제 입력 사용을 확인했다. 기본 이동속도 `10 in/min`의 변환 결과는 현대 `25.4 cm/min`, 두산 `4.233333 mm/s`다.

실제 브라우저 DOM에서 이동속도를 `10 → 11 in/min`으로 수정한 뒤 두산 `4.656667 mm/s` 변환, JSON 모달의 공통 명세 값 일치, 변경 전 `10`·변경 후 `11` 기록과 `original_evidence`의 fixture 근거 보존을 확인했다. 결과 JSON은 `output/dashboard-preview-20261010/ui-doosan-edited-preview.json`에 보관했다. 전류 `300 A` 입력 후 현대 토글에서도 명령은 `null`이고 JSON 보기 버튼은 비활성인 것을 확인했다.

브라우저 파일 다운로드 성공 여부는 자동화 이벤트 대기로 확인하지 못했으며, JSON 모달 표시와 결과 내용은 확인했다. 기존 앱 전체의 완료 여부나 과거 실험 성능을 재검증한 작업은 아니다.

## 후속 통합 완료

2026-10-10 [실제 마킹부터 수신까지 연결](WELD_PIPELINE.md)을 구현·실행했다. 이 문서 앞부분의 미연결 설명은 최초 독립 미리보기 단계의 상태다. `shipyard-connected-01`에서는 실제 A/B 판독으로 선택된 부재·이음에서 작업지시를 조회하고, 공통명세·양 제조사 명령·대상 정보를 함께 전송해 HTTP 수신을 확인했다. 기존 `shipyard-recapture`는 독립 시연 사본으로 보존하며 최신 통합 실행과 구분한다.
