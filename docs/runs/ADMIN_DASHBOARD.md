# ContextWeld 관리자 대시보드 (오프라인 기록 재생)

작성 2026-10-10, 갱신 2026-10-11. 구현 당시 기준은 `dev` `9451321`의 작업 트리였고, 그때 미커밋이던 README·마일스톤·OCR 명세·실험 README 수정은 이후 커밋됐다. 인계 문서 `admin-dashboard-20261010`의 관리자 대시보드 작업 기록이다.

> **상태:** 패키지 생성기·화면·검증 연결은 구현했고 `scripts/export/export_admin_dashboard.py export|verify`로 실행한다.
> 아래 4·5절은 코드에서 확인한 구성이다. **6~11절의 실행 기록은 작성되지 않았다**([미작성 절](#6-11절-미작성) 참고).
> 빠진 내용을 구현 완료로 읽지 않는다.

## 1. 목적과 경계

화면은 “무엇을 보고, 왜 재촬영했고, 다시 무엇을 읽어, 어떤 근거로 어떤 파라미터를 보냈는가”를 **저장된 기록만으로**
설명한다(DEMO_SPEC 8절). 시뮬레이션·추론·파이프라인 실행·기록은 Runpod 담당이고, 이 대시보드는 내려받은 파일을
로컬 브라우저에서 읽고 반복 재생한다.

- 재생은 기록 읽기다. OCR/VLM, 문서 재검색, 카메라 이동, 명령 송신, 수정 저장, 명시적 재검토를 호출하지 않는다.
- Foxglove·ROS·GPU·Isaac은 실행 의존성이 아니다. 기존 Foxglove 설정·토픽·브리지와 실행 중 장면 프로세스는 건드리지 않았다.
- 기존 단건 HTML exporter(`scripts/export/export_document_review.py`)와 검증기(`verify_*.py`, `inspect_*`)는 바꾸지 않고
  그대로 호출한다. 패키지에는 기존 exporter로 만든 단건 화면도 함께 넣는다.
- 인식 bootstrap(공개 사진)·문서 검토·명시적 재검토·Isaac 장면 자료는 서로 다른 종류로 표시하고 합치지 않는다.
  기본 자료만 넣은 패키지에는 장면 `J01`과 문서 `JOINT-DEMO-01`을 잇는 기록이 없어 미연결로 표시한다.
  이후 [통합 파이프라인](WELD_PIPELINE.md) 실행이 시연 도면의 `joint_marking_map`으로 둘을 연결했고,
  그 묶음은 `scripts/export/export_weld_pipeline_dashboard.py`로 패키지에 추가한다.
- CTX-001 후보 목록 실험(`output/context-ablation-20261010`)은 대시보드에 넣지 않는다. 사용자가 거부했고, 후보 목록에
  정답이 들어 있어 평가 설계가 무효화된 상태다. 제외 규칙은 `catalog.py`의 `EXCLUDED_BY_POLICY`에 있다.

## 2. 실행 방법

### 2.1 서버(또는 저장소가 있는 컴퓨터)에서 패키지 만들기

표준 라이브러리만 쓴다(추론 서버·GPU·네트워크 불필요). 출력 폴더는 없어야 하며 원본 묶음 밖이어야 한다.

```bash
cd /workspace/PAC2026
python3 scripts/export/export_admin_dashboard.py export \
  --output output/admin-dashboard-20261010/package/pac-admin-dashboard \
  --zip output/admin-dashboard-20261010/package/pac-admin-dashboard.zip \
  --report output/admin-dashboard-20261010/package/export-report.json
python3 scripts/export/export_admin_dashboard.py verify output/admin-dashboard-20261010/package/pac-admin-dashboard
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
| `scripts/export/export_admin_dashboard.py` | CLI(`export`, `verify`) |
| `scripts/export/export_weld_pipeline_dashboard.py` | 검증한 통합 전달 실행을 기존 패키지에 새 실행으로 추가 |
| `scripts/export/add_robot_dashboard_preview.py` | 내보낸 사본에 [제조사 입력 변환 카드](ROBOT_INPUT_PREVIEW.md) 설치 |
| `tests/admin_dashboard_support.py` | 화면 모델의 모든 저장 값을 원본 파일에서 다시 읽어 대조하는 공통 도우미(`assert_linkage`) |

대시보드 전용 단위·통합 테스트 파일은 저장소에 없다. 위 도우미만 보존되어 있고 `python3 -m pytest tests`의 108개
테스트에는 대시보드 패키지 생성 경로가 포함되지 않는다.

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

## 4. 화면 구성

`model.py`의 `TAB_KEYS`가 실행 하나당 탭 7개를 정의한다. 각 탭은 `available`·`partial`·`absent` 중 하나이며,
`absent`일 때는 비운 이유(`absent_reason`)를 함께 표시한다.

| 탭 키 | 라벨 |
|---|---|
| `summary` | 실행 요약 |
| `capture` | 촬영 전후 비교 |
| `timeline` | 단계 타임라인 |
| `recapture` | 재촬영 설명 |
| `evidence` | 해석·문서 근거 |
| `delivery` | 전달 내역 |
| `corrections` | 수정·재검토 이력 |

블록 형식은 `notice`, `fields`, `table`, `image`, `image_pair`, `cards`, `stages`, `diff`, `lineage`, `text`,
`json`, `raw_files`, `flow`, `group`, `video`다. 알림 수준은 `info`·`warning`·`serious`·`critical`,
단계 상태는 `done`·`not_done`·`failed`·`absent`·`unknown`이다.

## 5. 표시 계약

- 화면에 보이는 모든 저장 값은 `{"v", "src"}`로 감싼다. `src`는 원본 파일 경로와 JSON pointer다.
- 대시보드가 계산한 값은 `src=None`이며 `origin=dashboard`와 설명을 함께 둬야 한다.
- `tests/admin_dashboard_support.py`의 `assert_linkage`가 이 계약을 검사한다. 모든 `{"v","src"}` 값을 원본
  파일에서 다시 읽어 같은지 대조하고, `src=None`인 값에 출처 표시가 있는지 확인한다.
- 기본 자료 목록과 종류 분류, 제외 정책은 `catalog.py`의 `DEFAULT_SOURCES`·`DEFAULT_REFERENCES`·
  `SCENE_EXCLUDED`·`EXCLUDED_BY_POLICY`에 있다.

## 6~11절 (미작성)

원래 계획했던 **요구사항 대응표, 검증 결과, 원본 보존 기록, 미구현·미기록 표시, Mac 최종 확인 절차,
새 결과 연결 입력 계약**은 작성되지 않았다. 빈 자리 표시만 남아 있던 것을 이 절로 대체한다.

지금 확인할 수 있는 것과 없는 것을 나눈다.

| 항목 | 상태 |
|---|---|
| 패키지 생성·검증 CLI | 구현됨. `export_admin_dashboard.py export`·`verify` |
| 사본 동일성 확인 | 패키지 안의 `SHA256SUMS`와 `tools/verify_package.py`로 확인 |
| 화면 모델 ↔ 원본 연결 검사 | `tests/admin_dashboard_support.py`의 도우미는 있으나 이를 호출하는 테스트 파일이 없음 |
| 실제 내보내기 실행 기록 | **미기록.** 어떤 묶음으로 언제 패키지를 만들었고 보고서의 `forbidden_calls`가 비어 있었는지 남아 있지 않음 |
| 원본 보존 전·후 해시 비교 | **미기록** |
| Mac 브라우저 시각 검수 | **미기록.** 2절의 열기 절차만 적혀 있고 실제 수행 결과는 없음 |
| 새 결과 연결 입력 계약 | **미작성.** 현재는 `--add <묶음 폴더>` 사용법만 2절에 있음 |

이 기록을 채우려면 2절의 명령을 실행하고 `export-report.json`과 사본 재검증 결과를 이 문서에 옮겨 적는다.

## 12. 목업·실제 실행 분리 표시 (2026-10-15 정정)

진단·처방 P2-2([지시서](../audit/INSTRUCTIONS/dashboard-mock-data.md)) 실행 기록이다. 재관측 시연
(`shipyard-recapture`)이 실제 반사 감지·재촬영 성공처럼 보이지 않도록 화면과 데이터에 목업 표시를 넣었다.

- `src/contextweld_dashboard/web/app.js`: `run_kind.v === "presentation_scenario"`인 실행은
  사이드바 카드에 `목업 · 실제 실행 아님`(warning) 칩을, 실행 화면 머리에 경고 배너를 표시한다. 배너에는
  "run_outcome·delivery_status·단계는 시나리오 정의값이며 모델 원문·추론 시간·전송 ACK가 없습니다"라는 문구와
  실제 종단 실행(`shipyard-connected-01`)을 여는 버튼을 함께 둔다. 실제 실행·기타 실행에는 영향이 없다.
- 로컬 사본 생성기 `output/dashboard-preview-20261010/add_recapture_scenario.py`(미추적): 시나리오 `mock_note`,
  `summary.note`, 요약 탭 첫 블록 notice, `data/index.js` 전역 안내(중복 방지 포함)를 추가했다. 재생성해도
  분리 표시가 유지된다. 생성기 안의 낡은 `scripts/add_robot_dashboard_preview.py` 경로를 `scripts/export/`로 고쳤다.
- 사본 재생성 뒤 `tools/verify_package.py` 통과(파일 4,892개, MANIFEST·해시 일치)를 확인했다.

**알려진 공백(이번 정정 범위 아님):** 통합 파이프라인·시연 시나리오 묶음은 MANIFEST `roots`에 등록되지 않는다
(두 exporter 모두 기존 동작). 파일 자체는 MANIFEST `files`·SHA256SUMS로 해시 검증되지만 묶음 단위
`checksums.json` 대조 대상에는 나타나지 않는다. 이 공백은 2026-10-16에 닫혔다([13절](#13-manifest-roots-등록-2026-10-16)).

## 13. MANIFEST roots 등록 (2026-10-16)

12절의 "알려진 공백"을 닫은 기록이다. 통합 파이프라인·시연 묶음 3개를 MANIFEST `roots`에 등록해
`verify` CLI가 묶음 단위로 추적하게 했다.

- `scripts/export/export_weld_pipeline_dashboard.py`: 실행 추가 뒤 패키지 `MANIFEST.json`의 `roots`에
  `{group:'connected', kind:'weld_pipeline', source:<묶음 경로>, package_dir:'bundles/<key>'}`를 등록한다.
  대상은 `shipyard-connected-01`(checksums 21)·`marking-delivery-02`(checksums 208)다.
- 로컬 사본 생성기 `output/dashboard-preview-20261010/add_recapture_scenario.py`(미추적):
  `shipyard-recapture`를 `{group:'presentation', kind:'presentation_scenario'}`로 등록하고, 격리 재빌드용
  대상 패키지 인자를 받는다.
- `src/contextweld_dashboard/__main__.py` `verify`: `expected_failures`를 갱신했다. 신규 3개는
  `weld-pipeline-bundle.v1` 전용 검증기 부재, 시나리오 묶음은 `manifest.json` 부재라는 기존
  `rec-batch-01-incomplete`와 같은 공백이다. 2026-10-10 생성 묶음 9개(doc 5 + review 4)는 P0 계보 정정
  ([RECOGNITION_AND_BINDING.md](RECOGNITION_AND_BINDING.md)) 뒤 강화된 검증기 재계산과 불일치하는데,
  P0 지시서대로 과거 기재를 재작성하지 않으므로 재실행 전까지 expected로 둔다.
- 주의: `marking-delivery-02`는 2026-10-10 생성 당시 검증기가 중첩 `checksums.json` 2개를 sums에서
  빠뜨렸던 공백(진단 71행, 2026-10-15 `8828c4b`로 닫힘)이 남아 현재 `verify_pipeline`을 통과하지 못한다.
  원본 묶음과 실제 사본은 수정하지 않았고, 격리 재빌드에서만 빌드 사본에 두 항목을 sums에 보충해
  내보냈다(기록 해시는 바꾸지 않음).

검증: 실제 사본과 격리 재빌드 모두 `tools/verify_package.py` "결과: 통과"(roots 22줄, 신규 3줄은
`shipyard-connected-01` pass·`marking-delivery-02` pass·`shipyard-recapture` no_checksums, 파일 4,892개)와
`export_admin_dashboard.py verify` exit 0(17묶음: verified 2 · partial 2 · expected failed 13)을 확인했다.
