# 저장 재촬영 결과의 로컬 재개·관리자 검증

검증일: **2026-10-24**. Runpod 없이 저장 재촬영 관측 → 문서 검토 → 현대·두산 loopback 모의 수신 → 관리자 재생 경로를 구현·확인했다. 이번 재촬영 관측은 **test_fixture**다. 실제 GPU 추론이나 실제 팔 이동을 수행한 결과가 아니다. 10월 10일 실제 모델 결과는 별도로 보존·재검증했다.

## 구현과 실행 결과

| 항목 | 확인 결과 |
|---|---|
| 재개 입력 | `--source-kind recapture --source <검증된 묶음>`; 모델 경로 불필요, `new_model_calls=0` |
| 대상 연결 | 마지막 실제 입력 프레임의 관측·관계·판정 계보, 부재 정확 조회, 명시 이음 매핑, 유일한 joint 관계 검사 |
| 문서·조건 | 기존 WPS 원문 해시·문서 검증·검색·등록조건·제조사 변환 경로 사용 |
| 모의 수신 | fixture B 관측으로 `BISB30N-15`·`JOINT-DEMO-01` 연결. 현대·두산 모두 HTTP200 `received`, 송신·수신·ACK 대조 통과 |
| 기록 경계 | 원래 재촬영 묶음은 복사만 하고 별도 통합 실행 생성. `evidence_kind=test_fixture`, `physical_movement_triggered=false`, `execution_authorized=false` 유지 |
| 관리자 | 통합 묶음 검증기·읽기 어댑터·일반 패키지 생성기 연결. 중첩 재촬영 사진·요청·판정, 문서 원문, ACK, 조건 편집 표시 |
| 과거 보존 | 두 통합 묶음의 알려진 목록 누락을 새 사본에서 보충. 기록 내용·원본 해시는 변경하지 않음 |

기존 capture 예외의 의미는 유지했다. 재촬영 기록 브리지는 `needs_review`/`blocked`로 끝나고, 완료된 루프를 명시적으로 선택한 **새 실행**만 문서·전달을 계속한다. 실패·미확정·모호한 표기나 관계는 재개하지 않는다. 실행 명령과 입력 조건은 [통합 파이프라인](WELD_PIPELINE.md)에 있다.

## 자동 검증

Pillow가 있는 Python 환경에서 저장소 루트 기준으로 실행한다. HTTP 모의 수신 테스트는 loopback socket 사용이 가능해야 한다.

```sh
PYTHONPATH=src:tests python3 -m unittest discover -s tests -q
PYTHONPATH=src python3 -m contextweld_dashboard verify \
  output/local-resume-20261024/package
```

- 전체 회귀 **180개 통과**. 관측 연결, 재개·CLI, 변조 차단, 기존 통합 실행·브리지, 관리자 원본 연결, 보존 사본 검사를 포함한다.
- 첫 모의 전달 시도는 제한된 실행 환경의 socket bind 거절로 실패했다. 해당 기록을 보존하고 loopback이 허용된 실행에서 두 제조사 수신을 확인했다.
- 새 패키지 **5,069파일** 해시 검사 통과, `originals_unchanged=true`, `model_problems={}`.
- 참조 자료를 제외한 의미 검사: **verified 8 · partial 2 · expected failed 11**, CLI exit 0. 11건의 실패가 해결됐다는 뜻은 아니다.
- 통합 실행 두 건은 더 이상 허용 실패가 아니다. 기존 문서/재검토 9건의 재계산 불일치, 중단 인식 1건, manifest 없는 목업 1건을 진단용으로 유지한다. [과거 실패 사유](ADMIN_DASHBOARD.md#141-허용-실패-13건-항목별-사유)와 구분한다.

## 브라우저 검수

새 패키지의 내장 읽기 서버를 `127.0.0.1:8767`에서 열었다. 브라우저에서 수행한 범위는 다음과 같다.

| 범위 | 확인 내용 |
|---|---|
| 전체 26개 항목 | 요약 화면 이동·정상/부분/진단 표시. 문서·재검토 과거 실패를 성공으로 재생하지 않음 |
| 실제 `shipyard-connected-01` | 7개 탭, 보존된 A/B 1280×720 이미지·촬영 해시·판독 JSON, 문서 근거, 두 제조사 수신 기록 |
| `resumed-fixture-ok` | 7개 탭, fixture 표시·선택 B·새 모델 호출 0·중첩 재촬영 요청·문서·수신·별도 수정 기록 없음 |
| 재촬영 fixture 3종 | A만 사용, B 요청·재관측, 기술 실패의 사진·재촬영 설명·전달 미요청. 사용하지 않은 B는 저장 자료로 구분 |
| 재생 | 첫 단계와 최종 전체 보기 구분, 대상 연결이 생기기 전에는 이후 결과를 현재 값으로 표시하지 않음 |
| 조건 편집 | 현대/두산 전환, 속도 11 in/min의 두산 변환 4.656667 mm/s, 과거 전송값 유지, 전류 300 A의 범위 오류, 기본값 복원, JSON 원문 표시 |
| 오류 로그 | 검수 시점 브라우저 console error 없음 |

26×7개 모든 화면 조합·모든 화면 크기의 시각 검수를 수행한 것은 아니다. **JSON 다운로드는 링크·내용 표시와 클릭까지 확인했으나 브라우저 도구의 완료 대기가 시간 초과되어 파일 저장 완료는 미확인**이다.

`shipyard-recapture`는 manifest 없는 기존 목업이다. 원래 작성된 화면은 `output/dashboard-preview-20261010/pac-admin-dashboard`에 보존했고 새 일반 내보내기는 진단 화면을 만든다. 새 화면을 실제 모델 재촬영 성공 증거로 사용하지 않는다.

## 로컬 증거 위치

생성 결과와 원문은 Git 제외 경로에 보존한다.

| 경로 (`output/local-resume-20261024/` 기준) | 내용 |
|---|---|
| `fixture/runs/run_binding-fixture/` | B 재관측 fixture |
| `a-only/`, `failed/` | A만 사용·기술 실패 fixture |
| `resumed-fixture/` | 첫 socket 제한 실패 흔적 |
| `resumed-fixture-ok/` | 문서·현대/두산 HTTP 모의 수신 완료 묶음 |
| `preserved/`, `preservation/` | 과거 통합 묶음 사본과 목록 보충 보고서 |
| `package/` | 26개 항목의 새 관리자 패키지 |
| `build-report.json`, `package-verification.json` | 원본 불변·화면 모델·파일/묶음 검증 결과 |
| `browser-review.png` | 실제 저장 A/B를 보여주는 새 관리자 화면 |

## 남은 실행

Runpod 접근 재개 후 실제 모델로 재촬영 루프를 한 번 실행하고 결과를 이 재개 경로에 넣어 원문·화면을 대조한다. 모델이 A만으로 충분하다고 판단하면 B 성공을 강제로 만들지 않는다. 서버 산출물의 실물 대조·회수와 요청에 따른 팔 이동·새 RGB의 live 연동도 이번 완료 범위 밖이다.
