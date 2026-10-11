# ContextWeld 관리자 대시보드 — 오프라인 패키지

이 폴더는 Runpod·인터넷 없이 저장된 실행 기록을 조회·재생하는 읽기 전용 화면이다.
화면은 추론·문서 재검색·카메라 이동·명령 전송·수정 저장·재검토를 실행하지 않는다.

## 여는 방법

1. 폴더 전체를 원하는 위치로 옮긴다(zip이면 먼저 압축을 푼다).
2. `index.html`을 더블클릭해 브라우저(Safari·Chrome·Firefox)로 연다.
3. 왼쪽 목록에서 실행을 고르고 위쪽 재생 막대로 단계를 이동한다.

브라우저 정책 때문에 파일로 열리지 않으면 선택 사항으로 이 컴퓨터 안에서만 동작하는 정적 서버를 쓴다.

```bash
python3 tools/serve_package.py        # http://127.0.0.1:8765/index.html
```

## 파일 동일성 확인 (선택)

```bash
shasum -a 256 -c SHA256SUMS           # macOS 기본 도구
python3 tools/verify_package.py       # MANIFEST·원본 묶음 해시 목록 대조
```

`verify_package.py`는 파일 동일성만 확인한다. 스키마별 의미 검증(재계산 대조)은 저장소에서
`python3 scripts/export/export_admin_dashboard.py verify <이 폴더>`로 다시 실행할 수 있다.

## 구성

| 경로 | 내용 |
|---|---|
| `index.html`, `assets/` | 화면(외부 CDN·글꼴·스크립트 없음, 네트워크 연결 차단 CSP) |
| `data/` | 원본 묶음에서 만든 화면 데이터와 원문 텍스트 사본(JS 파일) |
| `bundles/<key>/` | 원본 실행 묶음의 바이트 동일 사본 |
| `viewer/<key>.html` | 기존 단건 HTML 조회기로 만든 문서·재검토 묶음 화면 |
| `MANIFEST.json`, `SHA256SUMS` | 파일 목록과 해시 |
| `EXPORT_INFO.json` | 내보낸 도구·저장소 커밋 정보 |

## 표시 한계

- 공개 사진 인식·문서 검토·명시적 재검토 실행과 Isaac 장면 자료는 서로 연결되지 않은 별도 자료다.
- 저장된 팔 이동 영상은 현재 기록에 없다. 장면 자료는 정지 이미지(초기·A·B)만 있다.
- 모의 ACK는 수신·형식 검사 결과이며 용접 완료나 현장 적용 승인이 아니다.
- 문서 원문 PDF/HTML은 묶음에 포함되지 않은 경우가 있으며, 그 경우 저장된 발췌와 위치만 보여 준다.
