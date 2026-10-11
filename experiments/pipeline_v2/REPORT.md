# PV2 결과 보고 — 현재 파이프라인 기준 축소 실행 (2026-10-10)

> 이전 후보 실험 CTX-001과 2026-10-09 파일럿은 이번 근거에서 제외했다. 정답이 든 후보 목록과 라벨 파생 문서는 쓰지 않았다. 모델 입력은 중립 이름의 원본 사진과 제품 기본 프롬프트뿐이다. 정답은 평가 전용 파일에만 있다.
> 사용자의 15분 제한 때문에 사전 등록한 계획([PROTOCOL.md](PROTOCOL.md)) 중 E1 축소판 8장만 새로 실행했다. 나머지는 미실행이며 그 주장은 하지 않는다.

## 1. 핵심 결과

새로 실행한 사진은 사용 이력이 없는 공개 사진 8장이다. 제품 CLI는 수정하지 않았고 run ID는 `pv2-e1-quick-val01`이다.

1. **단일 판독기는 잘못된 부재 ID를 자동 확정했다.** OCR 단독은 5/8, VLM 단독은 2/8이다. **ContextWeld 합의 게이트의 잘못된 확정은 0/8이다.** 8장 모두 작업자 확인(보류)으로 보냈다.
2. **보류 8장 중 4장은 게이트 후보 목록에 정답 ID가 들어 있었다.** 작업자는 수정 저장의 `select_observed_candidate`로 이 후보를 바로 고를 수 있다. 나머지 4장은 두 판독기 모두 정답을 읽지 못했다.
3. **선별 사례.** 효과를 보여주려고 고른 장면이며 대표 성능이 아니다.
   - `pv2-img-052`: OCR이 `M55624-16`을 점수 0.979로 확신했지만 오독이었다. VLM이 정답 `M5SB24-16`을 읽어 둘이 엇갈렸고 게이트가 멈췄다. OCR 점수 임계값만으로는 거르지 못했을 사례다.
   - `pv2-img-004`: OCR(`BISBON-8`)과 VLM(`BISB30N-8`)이 서로 다른 오답을 냈다. 단일 판독기라면 어느 쪽이든 오부재로 진행했겠지만 게이트가 막았다.
   - `pv2-img-057`: VLM이 사진에 없는 `B-1000`을 지어냈다. OCR 지지가 없어 보류됐다.
4. **대가.** 이번 8장의 자동 확정은 0건이다. 단일 판독기가 맞힌 4건도 보류됐다. 현재 버전은 "오확정 없이 작업자 확인으로 넘기는 안전장치"이고 자동화율은 아직 낮다.
5. **반례.** 사용 이력이 있는 기존 10장을 재채점하면 두 판독기가 `1→I` 같은 오답에 합의해 게이트를 통과한 사례가 2건 있다. 문서 데모 "정상" 사례도 그중 하나다. 이 오류는 판독기를 늘리는 것만으로는 막을 수 없다. 표기 규칙과 작업 대상 목록 같은 맥락 검증이 다음 단계다 `[추론]`.
6. **사진만으로는 용접 조건이 나오지 않는다.** 8/8 모두 작업 명세 필드가 비어 있고 문서 인용은 0건이다. 조건값은 작업지시→WPS 정확 조회로만 채운다(코드 근거).

## 2. 현재 파이프라인 — 코드로 확인한 범위

| 단계 | 실제 동작 | 판정에 쓰이는가 |
|---|---|---|
| OCR | PP-OCRv6 medium det/rec, CPU, 점수 임계 0 | 예. 정규식(하이픈 포함 영숫자)에 맞는 문자열이 후보가 됨 |
| 시각 관측 | Qwen3-VL-8B가 사진만 보고 객체·`visible_text`를 냄(greedy, 4096토큰) | 예. OCR 상자와 IoU ≥ 0.1인 `kind=text`만 교차확인에 씀 |
| 문서 검색 | BM25 고정 질의 `weld symbols arrow reference line fillet weld meaning`, TWI만, top-3. 모든 프레임에 같은 청크 | 아니오. 관계 프롬프트에만 들어감 |
| 관계 해석 | 사진+OCR+관측+검색 근거로 표기-대상 관계 제안 | 아니오. 하위 문서 검토가 읽지 않음 |
| bootstrap 판정 | 작업 필드를 모두 비우고 항상 `needs_review` | — |
| 문서 검토(별도 실행) | OCR·VLM 합의 → 작업지시 정확 일치(범위·개정·상태) → 도면·WPS 정합 → 필드 검증 → 모의 전달/차단 | 예. 단 작업지시·도면은 모사 1건 |
| 명시적 재검토 | 선택한 수정만 적용한 문서 규칙 재판정, 새 모델 호출 0 | 시각 재해석 없음 |

미구현 범위:
- 재촬영 판단과 폐루프. `recapture_request`는 항상 null이다.
- Isaac A/B 프레임 인식. 이번에도 실행하지 못했다.
- 장면 `J01`과 문서 `JOINT-DEMO-01`의 연결. `J01`은 하이픈이 없어 후보 정규식에 걸리지도 않는다.
- 실제 작업지시·도면·BOM·표기 규칙 문서. 확보된 적이 없다.
- 열입력 조합 검사.

## 3. 실험 설계와 선택 이유

사전 등록한 질문은 다섯 개다.

| ID | 질문 | 상태 |
|---|---|---|
| E1 | 단일 판독기보다 OCR·VLM 합의 게이트가 잘못된 ID 통과를 줄이는가, 대가는 얼마인가 | 8장만 실행 |
| E1-R | 관계 단계에서 문서 근거를 빼면 출력이 바뀌는가 | 미실행 |
| E2 | 반사·가림 앞에서 멈추는가 | 미실행 |
| E3 | 사진만 본 VLM이 근거 없는 용접 조건을 내는가 | 미실행 |
| E4 | 문서 결함을 규칙과 LLM 중 누가 놓치는가 | 미실행 |

E1을 고른 이유는 세 가지다.
- 미션 심사 기준인 "오인식 방지"에 직접 대응한다.
- 제품이 실제로 판정에 쓰는 단계(OCR, 독립 VLM 판독, 합의 게이트)만으로 답할 수 있다.
- 후보 목록 없이 공개 라벨로 채점할 수 있다.

같은 실행 출력에 세 진행 규칙을 적용했다. 모델 추가 호출은 없다.
- `D_gate`(제품): `workflow.observed_candidates`를 그대로 호출한다. 이슈가 없고 고유 후보가 1개일 때만 진행한다.
- `D_ocr`: 정규식에 맞는 OCR 문자열이 고유하게 1개면 진행한다.
- `D_vlm`: 정규식에 맞는 VLM `kind=text` 문자열이 고유하게 1개면 진행한다.

결과는 사진 단위로 `PROCEED-correct`, `PROCEED-wrong`, `HOLD`로 나눈다. 정답 비교는 제품 정규화(strip+대문자)로 한다.

자료:
- 공개 Steel OCR 960 데이터셋의 고정 revision `37725284…`, MIT다.
- 서버에 있던 10장은 모두 이전 실험에 썼다. 그래서 같은 revision의 라벨 있는 나머지 216장을 격리 경로에 받았다. LFS sha256은 전수 대조했다.
- 이번 실행은 그중 val 분할의 단일 코드 사진을 중립 ID 순서로 앞 8장 고른 것이다. 선택에 모델 출력은 쓰지 않았다.

## 4. 결과

### 4.1 새 실행 `pv2-e1-quick-val01` — 미사용 val 단일 코드 8장

단일 코드 사진 8장(전체 8장).

| 규칙 | 올바른 진행 | 잘못 진행 | 보류 |
|---|---|---|---|
| D_gate(제품 합의 게이트) | 0 | 0 | 8 |
| D_ocr(OCR 단독) | 2 | 5 | 1 |
| D_vlm(VLM 단독) | 2 | 2 | 4 |

- 판독기 정확 일치(사진 안 어느 위치든): OCR 2/8, VLM 2/8. `1/I`·`O/0` 혼동 허용 진단: OCR 2, VLM 3.
- 관계 단계: 관계가 나온 사진 2장, 문서 인용 0건. 작업 명세 필드가 빈 사진 8/8. `quality_issues`가 비어 있지 않은 사진 0장.

| 사진 | 정답 | OCR 후보 | VLM text 후보 | 게이트 이슈 | D_gate | D_ocr | D_vlm |
|---|---|---|---|---|---|---|---|
| pv2-img-004 | B1SB30N-8 | BISBON-8(0.723) | BISB30N-8 | ocr_vlm_disagreement | HOLD | PROCEED-wrong | PROCEED-wrong |
| pv2-img-009 | B1SB40N-23 | B1IS-2(0.659) | B1SB40N-23 | ocr_vlm_disagreement | HOLD | PROCEED-wrong | PROCEED-correct |
| pv2-img-010 | B1SB30N-37A | BI563N-37A(0.770) | — | no_vlm_identifier_support | HOLD | PROCEED-wrong | HOLD |
| pv2-img-034 | B1SB30N-37A | BI53N-37A(0.661) | — | no_vlm_identifier_support | HOLD | PROCEED-wrong | HOLD |
| pv2-img-052 | M5SB24-16 | M55624-16(0.979) | M5SB24-16 | ocr_vlm_disagreement | HOLD | PROCEED-wrong | PROCEED-correct |
| pv2-img-053 | B1SB30N-16 | B1SB30N-16(0.942) | — | no_vlm_identifier_support | HOLD | PROCEED-correct | HOLD |
| pv2-img-057 | B1SB40N-45 | — | B-1000 | no_supported_marking | HOLD | HOLD | PROCEED-wrong |
| pv2-img-065 | B1SB30N-23 | B1SB30N-23(0.950) | — | no_vlm_identifier_support | HOLD | PROCEED-correct | HOLD |

- VLM 호출 16회, 합계 260.3초, 최대 69.7초.

### 4.2 참고: 기존 bootstrap 묶음 재채점 — 새 증거 아님

`output/recognition/run_steel-batch-20261010-02`는 사용 이력이 있는 10장이다. 같은 채점기를 저장 출력에 적용만 했으며 채점기 시험용이다. 단일 코드 7장 결과는 다음과 같다.

| 규칙 | 올바른 진행 | 잘못 진행 | 보류 |
|---|---|---|---|
| D_gate(제품) | 0 | 2 | 5 |
| D_ocr | 1 | 4 | 2 |
| D_vlm | 0 | 5 | 2 |

- 게이트를 통과한 2건은 frame-002와 frame-007이다. 두 판독기가 모두 `B1Sb30N`의 `1`을 `I`로 읽어 같은 오답에 합의했다.
- frame-007의 오독 문자열 `BISB30N-15`로 모사 작업지시를 작성했다. 그래서 문서 데모의 "정상 성공"은 오독과 오독에서 만든 문서가 일치한 순환 결과다.
- Isaac 장면의 표기 `BISB30N-15`도 같은 오독에서 왔다.
- OCR이 유일하게 정확히 읽은 frame-001은 VLM이 `I`로 읽는 바람에 게이트가 보류시켰다.
- `1/I`, `O/0` 혼동을 허용하는 진단 기준으로는 정답 판독이 OCR 4/7, VLM 6/7이다. 오류 대부분이 이 혼동이다.

## 5. 측정 검증과 한계

- 제품 코드(`src/`, `scripts/`, `configs/`)는 바꾸지 않았다. 새 묶음은 제품 CLI가 스스로 해시를 검증한 `bootstrap-bundle.v1`이다. `scripts/verify/verify_run_bundle.py`로 다시 검증했다(6절).
- 채점기는 새 출력을 보기 전에 기존 묶음으로 시험했다. 단위 테스트와 독립 재계산은 시간 제한으로 하지 못했다 `[확인 필요]`.
- 표본 8장으로는 비율·유의성을 말할 수 없다. 건수 사례로만 쓴다.
- 문서 데모의 작업지시가 오독 문자열로 쓰였으므로, 관측 게이트를 통과한 오독이 실제 업무에서 막힐지는 알 수 없다. 실제 작업지시 목록에 그 ID가 있느냐에 달렸다 `[확인 필요]`.
- 정답 규약이 `B1Sb30N`(라벨)과 `B15b30N`(파일명)으로 다르다. 사진의 `1`은 세로 획 하나라서 `I`와 시각적으로 구분되지 않는다. 이 혼동은 판독기를 하나 더 붙인 교차확인으로는 원리상 풀리지 않는다. 표기 규칙(코드 문자 체계)이나 작업 대상 목록 같은 맥락이 있어야 풀린다 `[추론]`. 이 맥락 경로는 현재 제품에 없고 검증하지 않았다.
- 실행 중간의 Isaac 송출 수신 검사는 생략했다. 실행 전후 프로세스·파일 해시만 비교했다(6절).

## 6. 보존 확인

- 보호 파일 3,535개: 삭제·내용 변경 0. 바뀐 것은 실행 중인 Isaac 프로세스가 덧붙이는 로그 3개(`live-01.log`, `live-03.log`, `live-03-publisher.log`)뿐이다.
- 추가 파일 19개는 병렬 대시보드 세션의 파일이다(`src/contextweld_dashboard/` 등). 이 실험은 손대지 않았다.
- Isaac 앱(17447), 두 장면 실행기(54450, 76786), 송출기(77687), foxglove_bridge(18392/18402)는 모두 유지됐다. 보조 프로세스 `ros2-daemon`(56811)은 사후 점검 때 없었다. 이 실험은 ROS 명령을 실행하지 않았으며 원인은 미확인이다 `[확인 필요]`.
- 원본 체크아웃의 기존 미커밋 수정 4개 파일은 그대로다. 비교 상세는 `output/pipeline-v2-20261010/postflight/protection-compare.json`에 있다.
- 시작 전 모델 23개 파일 해시가 일치했다. VLM 최대 GPU 메모리는 17.38 GiB, 실행 시간은 311초였다.

## 7. 발표에서 쓸 수 있는 주장 / 쓰면 안 되는 주장

쓸 수 있다(이번 실행과 코드 근거 범위 안):
- "사용 이력이 없는 공개 사진 8장에서 단일 판독기 자동 확정은 잘못된 부재 ID를 OCR 5건, VLM 2건 냈다. ContextWeld 합의 게이트는 0건이고 전부 작업자 확인으로 넘겼다." 반드시 '8장 축소 실행'을 함께 말한다.
- "OCR 점수 0.979인 오독도 있었다. 점수 임계값만으로는 거르지 못하는 오류를 독립 판독기 교차확인이 잡았다(사례)."
- "보류된 사진의 절반(4/8)은 정답 후보를 작업자에게 제시했다."
- "사진 단독으로는 용접 조건이 생성되지 않는다. 조건은 작업지시→WPS 정확 조회로만 채운다."
- 한계도 같이 말한다. "같은 오독에 두 판독기가 합의하면 통과한다. 그래서 표기 규칙·작업 대상 목록 맥락 검증이 다음 단계다." 

쓰면 안 된다:
- "문서 맥락이 인식 정확도를 높인다." 현재 검색은 고정 질의이고 인용이 0이며 판정에 쓰이지 않는다. 검증 실험도 없다.
- "문서 데모 정상 사례가 올바른 부재 인식을 보여준다." 오독 문자열에 맞춘 순환 결과다.
- 이번 결과나 CTX-001 수치를 현장 정확도·Isaac 판독 성능·재촬영 효과로 제시하는 것.
- 반사 시 재촬영 판단 성공, 폐루프 동작.
- 합의 게이트가 오독을 모두 막는다는 주장. 같은 오답에 합의한 사례가 있다.

## 8. 재현

```sh
cd /workspace/PAC2026
/usr/bin/python3 experiments/pipeline_v2/prepare_data.py            # 새 경로에서만 실행 가능(덮어쓰기 거부)
# 새 실행 1묶음: run_e1.execute()로 제품 CLI 호출(명령 전문은 runs/e1/quick-ledger.json의 argv)
PYTHONDONTWRITEBYTECODE=1 /workspace/venvs/contextweld-inference/bin/python -B \
  experiments/pipeline_v2/score.py output/pipeline-v2-20261010/runs/e1/run_pv2-e1-quick-val01 \
  --out output/pipeline-v2-20261010/scores/e1-quick.json
python3 scripts/verify/verify_run_bundle.py output/pipeline-v2-20261010/runs/e1/run_pv2-e1-quick-val01
python3 experiments/pipeline_v2/tools/snapshot.py compare \
  output/pipeline-v2-20261010/preflight/protection-before.json output/pipeline-v2-20261010/postflight/protection-after.json
```

남은 계획은 `run_e1.py`의 전체 23묶음과 PROTOCOL의 E1-R·E2·E3·E4다. 그대로 이어서 실행할 수 있다. 예상 GPU 시간은 Isaac 동시 실행 기준 약 5시간이다 `[추론]`.

## 9. 대시보드 인계와 통합 메모

[DASHBOARD_HANDOFF.md](DASHBOARD_HANDOFF.md)와 [INTEGRATION_MEMO.md](INTEGRATION_MEMO.md)를 따른다.
