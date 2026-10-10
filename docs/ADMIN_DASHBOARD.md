# ContextWeld 관리자 대시보드 (오프라인 기록 재생)

작성 2026-10-10. 기준 저장소 `dev` HEAD `945132109b01ea7da38f6ebff68637b0c73fa9cd`(README·MILESTONES·OCR 명세·실험 README
미커밋 수정 포함 작업 트리). 인계 문서 `admin-dashboard-20261010`의 관리자 대시보드 작업 기록이다.

> 상태 요약 — 아래 [검증 결과](#7-검증-결과)와 [미구현·미기록](#9-미구현미기록-표시)을 함께 읽는다.
> <!-- STATUS-SUMMARY -->

## 1. 목적과 경계

화면은 “무엇을 보고, 왜 재촬영했고, 다시 무엇을 읽어, 어떤 근거로 어떤 파라미터를 보냈는가”를 **저장된 기록만으로**
설명한다(DEMO_SPEC 8절). 시뮬레이션·추론·파이프라인 실행·기록은 Runpod 담당이고, 이 대시보드는 내려받은 파일을
로컬 브라우저에서 읽고 반복 재생한다.

- 재생은 기록 읽기다. OCR/VLM, 문서 재검색, 카메라 이동, 명령 송신, 수정 저장, 명시적 재검토를 호출하지 않는다.
- Foxglove·ROS·GPU·Isaac은 실행 의존성이 아니다. 기존 Foxglove 설정·토픽·브리지와 실행 중 장면 프로세스는 건드리지 않았다.
- 기존 단건 HTML exporter(`scripts/export_document_review.py`)와 검증기(`verify_*.py`, `inspect_*`)는 바꾸지 않고
  그대로 호출한다. 패키지에는 기존 exporter로 만든 단건 화면도 함께 넣는다.
- 인식 bootstrap(공개 사진)·문서 검토·명시적 재검토·Isaac 장면 자료는 서로 다른 종류로 표시하고 합치지 않는다.
  장면 `J01`과 문서 `JOINT-DEMO-01`은 연결된 기록이 없으므로 미연결로 표시한다.
- CTX-001 후보 목록 실험(`output/context-ablation-20261010`)은 사용자가 거부했으므로 대시보드에 넣지 않았다.

## 2. 실행 방법

### 2.1 서버(또는 저장소가 있는 컴퓨터)에서 패키지 만들기

표준 라이브러리만 쓴다(추론 서버·GPU·네트워크 불필요). 출력 폴더는 없어야 하며 원본 묶음 밖이어야 한다.

```bash
cd /workspace/PAC2026
python3 scripts/export_admin_dashboard.py export \
  --output output/admin-dashboard-20261010/package/pac-admin-dashboard \
  --zip output/admin-dashboard-20261010/package/pac-admin-dashboard.zip \
  --report output/admin-dashboard-20261010/package/export-report.json
python3 scripts/export_admin_dashboard.py verify output/admin-dashboard-20261010/package/pac-admin-dashboard
```

새 묶음을 더할 때는 `--add <묶음 폴더>`(반복 가능), 기본 자료 일부만 넣을 때는 `--only <key,...>`.

### 2.2 로컬(Mac)에서 열기

1. zip을 풀거나 폴더를 옮긴다.
2. `index.html`을 더블클릭한다(Safari/Chrome/Firefox). 서버·인터넷 연결이 필요 없다.
3. 선택: `shasum -a 256 -c SHA256SUMS` 또는 `python3 tools/verify_package.py`로 사본 동일성 확인.
4. 파일 열기가 브라우저 정책으로 막히면 선택적으로 `python3 tools/serve_package.py` 후 `http://127.0.0.1:8765/index.html`.

Mac에서의 최종 확인 절차는 [10절](#10-mac-최종-확인-절차)에 따로 적었다. 서버에서 개발·검증했으며 Mac에서 실행했다고
주장하지 않는다.

## 3. 구성

| 경로 | 역할 |
|---|---|
| `src/contextweld_dashboard/model.py` | 화면 모델 계약: 모든 저장 값은 `{"v", "src"}`(원본 파일·JSON pointer)로 감싸고, 탭 7개·블록 형식·출처 라벨을 정의 |
| `src/contextweld_dashboard/bundle_io.py` | 읽기 전용 접근(`contextweld.recognition.safe_path`로 경로 가둠, symlink 거부, PNG/JPEG 크기 헤더 읽기) |
| `src/contextweld_dashboard/integrity.py` | 스키마별 기존 검증기 호출 + 파일 목록·해시·symlink·경로 이탈 대조, 장면 자료는 기록 해시만 대조(`partial`) |
| `src/contextweld_dashboard/catalog.py` | 기본 자료 목록(인계 4절), 종류 분류(schema_version), 제외 정책(CTX-001, 장면 `stream/` 등) |
| `src/contextweld_dashboard/adapters/` | 읽기 어댑터: `recognition`, `document_review`, `explicit_review`, `scene`, `references` |
| `src/contextweld_dashboard/package.py` | 패키지 생성(검증 → 바이트 동일 복사 → 사본 재검증 → 화면 모델 → 기존 HTML 조회기 → MANIFEST/SHA256SUMS) |
| `src/contextweld_dashboard/web/` | 화면(`index.html`, `app.css`, `app.js`): 바닐라 JS, 빌드 단계·외부 자원 없음 |
| `src/contextweld_dashboard/package_tools/` | 패키지에 들어가는 독립 도구(`verify_package.py`, `serve_package.py`, 안내문) |
| `scripts/export_admin_dashboard.py` | CLI(`export`, `verify`) |
| `scripts/check_admin_dashboard_browser.py` | 브라우저 검수 자동화(Playwright, UI 전용 격리 환경) |
| `tests/test_admin_dashboard_*.py`, `tests/admin_dashboard_*.py` | 단위·통합 테스트와 공통 도우미 |

### 3.1 데이터 흐름

```text
원본 묶음(output/…) ──읽기──▶ 기존 검증기(inspect_*) ──▶ 바이트 동일 복사(bundles/<key>/)
      │                                                        │
      └── 원본 해시 기록(전·후 비교) ◀─────────────────────────┤
                                                               ▼
                                   사본 재검증(원본과 같은 결과인지) ▶ 어댑터(사본에서 읽기)
                                                               ▼
                       data/index.js · data/runs/<key>.js · data/raw/<key>/<n>.js (화면 모델·원문 텍스트)
                                                               ▼
                         index.html + assets/ (CSP: 네트워크 연결 차단) ── 브라우저 file:// 로 열기
```

### 3.2 오프라인·무부작용 보장

- 화면 `index.html`의 CSP: `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self';
  font-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`.
  브라우저가 fetch·XHR·WebSocket 등 모든 연결을 막는다. 데이터는 `<script src>`로 패키지 안 파일만 읽는다.
- 화면 코드에는 네트워크 API·`innerHTML`·`eval`이 없다(정적 테스트). 원본 JSON/HTML/문서는 텍스트로만 표시한다.
- 내보내기는 `side_effect_guard` 안에서 실행한다. 전달(`send_command`, `MockReceiver`), 문서 검색·색인
  (`search_documents`, `build_index`), 수정 저장(`record_correction`), 재검토(`run_review`, `_deliver`), 문서 실행
  (`run_document_demo`), 추론(`run_bootstrap`, `infer_json`, 모델 엔진), 소켓 연결·바인드, 하위 프로세스 실행은 호출 즉시 실패하고
  보고서 `forbidden_calls`에 남는다. 정상 내보내기의 값은 빈 목록이어야 한다.
- 완료 묶음은 불변이다. 패키지·보고서·스크린샷은 모두 원본 밖 새 경로에만 쓴다. 기존 출력은 덮어쓰지 않는다.

## 4. 화면 구성 (DEMO_SPEC 8절 8개 요소)

<!-- SCREEN-SECTION -->

## 5. 표시 계약

<!-- CONTRACT-SECTION -->

## 6. 요구사항 대응표

<!-- REQUIREMENTS-TABLE -->

## 7. 검증 결과

<!-- VERIFICATION -->

## 8. 원본 보존 기록

<!-- PRESERVATION -->

## 9. 미구현·미기록 표시

<!-- GAPS -->

## 10. Mac 최종 확인 절차

<!-- MAC -->

## 11. 새 결과 연결 입력 계약

<!-- INPUT-CONTRACT -->
