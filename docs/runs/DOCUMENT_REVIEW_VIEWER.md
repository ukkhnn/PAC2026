# 문서 실행 기록 오프라인 조회

`scripts/export/export_document_review.py`는 저장된 `document-demo-bundle.v1` 또는 `review-bundle.v1` 한 개를 스키마에 맞는 검증기로 검증하고 단일 HTML로 내보낸다. HTML은 서버·인터넷 없이 브라우저에서 직접 열 수 있다. Python 표준 라이브러리와 저장소의 기존 검증 함수만 사용하며 추가 패키지를 설치하지 않는다.

```bash
python3 scripts/export/export_document_review.py \
  output/document-demo-20261010/server/run_document-normal-server-01 \
  --output output/document-review-20261010/normal.html
```

생성된 HTML을 브라우저의 파일 열기로 선택한다. 정상·누락·관측 불일치 실행은 각각 다른 파일로 내보낸다. 기존 HTML은 덮어쓰지 않으므로 재실행 때 새 출력 경로를 사용한다. 원본 묶음 내부에는 출력할 수 없다.

화면에는 다음 근거가 저장된다.

- 선택 프레임의 원본 PNG/JPEG 바이트와 출처·해시, 해당 프레임의 OCR/VLM 원문 및 구조화 결과
- 실제 관측 후보와 작업지시 matching, 시연용 `fixture / synthetic_demo` 문서와 공개 원문 구분
- WPS 필드의 값·범위·단위·원문 값·페이지·bbox·좌표계, 헤더·행·열·개정·원문 해시 및 검색 발췌
- 검증 이슈·누락 필드·전송 보류 이유, 현장 적용에 남은 정보와 시험용 결함 주입
- UTC 시간순 사건, 원래 seq·부모 사건·payload 참조, 실제 저장된 모의 request·ACK·수신기 원문
- `execution_authorized`, `application_authorized`, `demo_complete`를 포함한 실행 범위

`verify_document_demo.py`와 동일한 `inspect_document_bundle`을 HTML 생성 전후에 호출한다. 파일 해시뿐 아니라 원관측 선택·문서 명세 재계산·실제 모의 수신 기록의 연결도 검증한다. 검증 실패 시 HTML을 저장하지 않는다. 원본 묶음은 읽기만 하며, 결과는 신규 파일 생성 모드로 저장한다.

HTML에는 JavaScript, 외부 폰트·CDN·fetch가 없다. 모든 원문과 JSON을 HTML 이스케이프해 텍스트로 표시하고 PNG/JPEG만 data URI로 삽입한다. SVG 등 미지원 이미지는 재생성하지 않고 안내한다. CSP는 외부 연결과 스크립트를 차단한다. 파일에는 이미지와 원문이 포함되므로 공유 범위는 입력 묶음과 같게 취급한다.

미기록 값은 `unknown` 또는 원래 `null`로 표시한다. 원본 PDF가 묶음에 없으면 포함 여부를 표시하고 저장된 검색 발췌와 위치만 보여준다. 화면의 성공은 문서 검토와 모의 전달의 성공이며, 실제 용접 적용·설비 실행 승인으로 해석하지 않는다. 이 도구에는 재추론·수정·승인·재전송 기능이 없다.

이 도구의 범위는 문서 실행 한 건의 최소 조회다. A/B 재촬영 재생, 실제 설비 제어, 전체 데모 완료는 포함하지 않는다.

> 2026-10-10 갱신: 여러 실행을 한 패키지로 묶는 일은 이후 [오프라인 관리자 패키지](ADMIN_DASHBOARD.md)가 맡는다. 그 패키지도 이 exporter를 그대로 호출해 단건 화면을 함께 넣는다. 아래의 "범위 밖" 서술은 이 도구 하나의 범위를 말한다.

검증:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_document_review_export.py'
```

테스트는 정상·누락·관측 충돌, 원본 불변, 해시 및 의미 위변조 거절, 출력 덮어쓰기 거절, HTML 주입 방지, 원본 이미지 바이트 포함, 실제 loopback 요청·ACK 표시를 확인한다. 테스트 중 모의 수신기를 여는 항목이 있지만 exporter와 생성된 HTML은 네트워크 요청을 하지 않는다.

2026-10-10 저장된 실제 실행 묶음의 내보내기 확인 결과:

| 사례 | 실행 결과 | 모의 전달 | 이슈 | 검증 파일 | 사건 |
| --- | --- | --- | ---: | ---: | ---: |
| `document-normal-server-01` | `succeeded` | `received` | 0 | 196 | 9 |
| `document-missing-server-01` | `needs_review` | `blocked` | 1 | 193 | 7 |
| `document-observation-conflict-server-01` | `needs_review` | `blocked` | 10 | 193 | 7 |

세 묶음의 모든 원본 파일 SHA-256이 생성 전후 일치했다. HTML과 확인 기록은 Git 제외 `output/document-review-20261010/`에 보관한다. 신규 테스트 6개가 통과했다. 이는 저장된 기록 내보내기와 표시 내용 검사 결과이며, 원문 문서의 현장 적용 승인을 뜻하지 않는다.

[확인 필요] 자동 브라우저의 로컬 파일 URL 제한으로 이번 실행에서 화면 렌더링의 시각 검수는 수행하지 못했다. 위 결과는 묶음 검증·HTML 구조·표시 내용·이미지 바이트 검사이며 브라우저 시각 검수를 대신하지 않는다.

## 명시적 재검토 묶음 조회 (2026-10-10 추가)

[명시적 재검토](EXPLICIT_REVIEW.md)의 `review-bundle.v1`도 같은 명령으로 내보낸다. exporter는 manifest의 스키마를 보고 `inspect_document_bundle` 또는 `inspect_review_bundle`을 생성 전후에 호출하며, 검증에 실패하면 HTML을 저장하지 않는다. 기존 문서 실행 HTML의 내용과 동작은 그대로다.

```bash
python3 scripts/export/export_document_review.py \
  output/explicit-review-20261010/run_review-20261010-voltage-deliver-01 \
  --output output/explicit-review-20261010/html/review-20261010-voltage-deliver-01.html
```

재검토 HTML은 출처를 표시로 구분한다: `원본 · model`(원래 인식 실행의 프레임·OCR/VLM 원문·관측 선택), `수정 · user` 또는 `수정 · demo_fixture (사람 검수 아님)`(수정 전후 값·작성 주체·사유·대상 실행/결과 해시), `재판단 · rule`(적용 식별자·적용 순서·작업지시 연결·새 명세·해결/잔존 이슈), `문서 · document`(정확 조회한 WPS 값과 원문 위치·복구 수정 ID). 명시적 재검토 요청(요청 ID·요청자·사유·선택 순서·`delivery_requested`), 실행 계보, 실제 모의 요청·ACK·수신기 원본 또는 전달 실패 기록, 전송 기록이 없다는 안내도 표시한다.

2026-10-10 서버의 실제 재검토 묶음 4개(재검토만 `succeeded`, 전달 `received`, 문제 잔존 `blocked`, 결함 주입 `failed`)와 다른 디렉토리로 옮긴 전달 묶음 사본 1개를 내보냈다. 모든 HTML 머리말은 `시연 fixture 수정 (사람 검수 아님)`으로 표시되고 결함 주입 실행에는 `시연용 결함 주입: receiver_unavailable` 표시가 붙는다. 파일은 Git 제외 `output/explicit-review-20261010/html/`에 있다. 신규 테스트 3개(`tests/test_review_export.py`)가 이동 사본 조회·출처 표시·이스케이프·내보낸 뒤 전달 시 원본 불변을 확인한다.

재검토 HTML도 JavaScript·폼·외부 자원이 없고 같은 CSP와 이스케이프를 사용한다. HTML을 열거나 섹션을 펼쳐도 모델 호출·수정 저장·재검토·전송이 일어나지 않는다. 여러 실행을 묶는 화면은 이 도구가 아니라 [오프라인 관리자 패키지](ADMIN_DASHBOARD.md)에 있다.
