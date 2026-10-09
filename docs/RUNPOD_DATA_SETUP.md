# Runpod 자료 준비

기준일: **2026-10-10**. 모델 추론·문서 처리·시뮬레이션은 Runpod에서 진행한다. 이 단계는 데모용 사진과 근거 원문을 서버에 준비하는 작업이며, 모델 설치·추론이나 RAG 구축 완료를 뜻하지 않는다.

아이디어 피칭이 목적이므로 이미 확보한 소량 사진부터 연결한다. 전체 데이터셋 다운로드나 독립 성능 평가를 선행 조건으로 두지 않는다. 환경 기준은 [Pod v1](POD_VER1.md), 전체 범위는 [데모 스펙](DEMO_SPEC.md)을 따른다.

## 1. 이번 준비 묶음

출처 목록은 [configs/demo_data_sources.json](../configs/demo_data_sources.json), 실행 도구는 [scripts/prepare_demo_data.py](../scripts/prepare_demo_data.py)다. Python 3.10 이상 표준 라이브러리만 사용한다.

| 묶음 | 내용 | 용도 |
|---|---|---|
| `steel-images` | 기존 고정 revision의 Steel OCR 960px 사진 10장 | 인식 연결·시연 입력 후보 |
| `steel-metadata` | 같은 revision의 배포 카드·train 라벨 | 출처·이용조건 표기와 사진의 문자/영역 확인 |
| `documents` | TWI 기호 해설 HTML, LANL WTS 양식·WPS PDF, 현대 `arccond` 원문 | 문서 추출·근거 연결을 시작할 원문 |

사진은 기존 [E1 manifest](../experiments/e1_ocr/manifest.json)의 URL과 SHA-256을 재사용한다. 원래 실험 파일은 변경하지 않는다. 배포 라벨에는 내려받지 않은 사진의 항목도 있으므로 이미지 목록은 새 출처 목록의 10개 항목을 기준으로 사용한다. 정답 라벨은 검토용이며 모델에 정답으로 주입하지 않는다.

문서는 우선 다운로드 가능성을 확인하는 선택 항목이다. 실패가 있어도 사진 준비는 진행할 수 있으며, 실패한 문서는 manifest에 남는다. 원문을 확보한 뒤에야 [문서 적용 계획](DOCUMENT_APPLICATION_PLAN.md)의 페이지·표·단위 검수를 진행한다. 공개 WPS는 현장 승인조건이 아니고, 제조사 설명의 예시도 실제 장비 등록값이 아니다.

## 2. 서버에서 직접 받기

Runpod의 `/workspace/PAC2026`에서 실행한다. 아래 스크립트·설정 파일이 포함된 `dev` 체크아웃이 필요하다. 기존 서버에 선별 전송한 작업 파일이 남아 있으면 변경 내용을 보존·확인한 뒤 Git 상태를 정합한다.

```bash
cd /workspace/PAC2026
python3 scripts/prepare_demo_data.py
python3 scripts/prepare_demo_data.py --verify-only
```

실행 출력을 파일로 남기려면 Bash에서 다음과 같이 실행한다. 로그 폴더는 스크립트가 자동으로 만들지 않는다.

```bash
set -o pipefail
mkdir -p output/data-setup
python3 scripts/prepare_demo_data.py 2>&1 | tee output/data-setup/bootstrap.log
python3 scripts/prepare_demo_data.py --verify-only 2>&1 | tee output/data-setup/verify.log
```

사진과 배포 메타데이터만 먼저 받을 수도 있다.

```bash
python3 scripts/prepare_demo_data.py \
  --group steel-images --group steel-metadata
```

기본 저장 경로는 다음과 같다. 원본과 실행 결과는 Git 제외 대상이다.

```text
/workspace/PAC2026/data/raw/demo-bootstrap-v1/
  asset-manifest.json
  steel_ocr/
    README.md
    train_data/det/train.txt
    train_data/det/images/       # 10장
  documents/
    twi/weld-symbols.html
    lanl/wts-rev1.pdf
    lanl/wps-3501-xxxx-1.pdf
    hyundai/arccond.md
```

이미 있는 파일은 해시·파일 형식을 확인해 재사용한다. 해시가 다른 파일을 조용히 덮어쓰지 않는다. 실패 시 해당 ID와 원인을 확인한다. 이번에 확보한 문서 4개의 실제 해시도 출처 목록에 고정했다. 원문이 이후 바뀌면 같은 자료로 조용히 교체하지 않고 불일치를 표시한다. 새 자료에 해시가 없으면 최초 확보 시 기록하고 이후 검사에서 사용한다. 최신 문서로 갱신할 때는 출처·개정과 새 저장 경로를 정한다.

`--verify-only`는 다운로드나 manifest 갱신 없이 파일을 검사한다. 이번 검증 결과는 콘솔 출력 또는 저장한 로그를 기준으로 확인하며, manifest에는 이전 준비 상태가 남는다. 선택 문서가 실패해도 프로세스 종료 코드는 성공일 수 있으므로 행별 성공·실패 출력을 함께 확인한다. 사진·메타데이터 등 필수 자료의 실패는 오류로 종료한다.

## 3. 기존 로컬 사진을 옮기는 대안

직접 다운로드가 되면 이 절은 생략한다. 아래 `runpod`은 Mac에 등록된 SSH 별칭이다. 다른 환경에서는 자신의 SSH 대상과 저장소 경로로 바꾼다.

Mac의 프로젝트 루트에서 다음 두 파일과 기존 입력만 옮긴다. 인증 파일·가상환경·다른 로컬 자료 전체를 복사하지 않는다.

```bash
ssh runpod 'mkdir -p /workspace/PAC2026/scripts /workspace/PAC2026/configs /workspace/data-import/steel-ocr'
scp scripts/prepare_demo_data.py runpod:/workspace/PAC2026/scripts/
scp configs/demo_data_sources.json runpod:/workspace/PAC2026/configs/
rsync -a experiments/e1_ocr/inputs/ runpod:/workspace/data-import/steel-ocr/
```

Runpod에서 전송한 파일을 검증해 준비 묶음으로 복사한다. 로컬 원본 경로는 손대지 않는다.

```bash
cd /workspace/PAC2026
python3 scripts/prepare_demo_data.py \
  --local-steel-root /workspace/data-import/steel-ocr \
  --group steel-images --group steel-metadata
```

## 4. AI Hub는 필요할 때 추가

[용접로봇 행동 생성 데이터 71939](https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=71939&topMenu=100)는 용접점·용접선·RGB-D/PCD 자료 후보다. 공개 명세에서 마킹 문자 전사나 마킹→부재 관계 정답은 확인하지 못했다. 현재 사진 준비의 필수 의존성이 아니다.

[공식 API·Shell 안내](https://aihub.or.kr/devsport/apishell/list.do?currMenu=403&topMenu=100)에 따르면 서버 직접 다운로드에는 사용자 API 키와 해당 데이터셋의 다운로드 승인이 필요하다. 로그인·키 발급·신청은 사용자가 진행한다. 키를 채팅·저장소·manifest에 넣지 않는다. 공식 도구의 목록 모드로 필요한 원천/라벨 파일과 크기를 먼저 고르고, 전체 다운로드를 기본값으로 실행하지 않는다.

승인 후 실제 확보 범위·파일키·해시를 따로 등록한다. 원천과 대응 라벨을 함께 선택하고, 압축 해제 공간도 확인한다. 이번 준비 스크립트는 AI Hub 계정에 로그인하거나 원본 다운로드를 시도하지 않는다.

## 5. 확인과 보존

- 실제 서버 실행 결과는 `output/data-setup/`에 남긴다. 서버의 명령 출력과 로컬 문서에 적힌 계획을 구분한다.
- 자료 다운로드 성공은 문서 내용 검수·모델 정확도·시뮬레이션 완료를 뜻하지 않는다.
- 일회성 Pod를 중지·삭제하기 전 새로 확보한 원문·manifest·필요 결과를 내려받는다. 코드·설정만 Git에 남겨서는 Git 제외 자료가 보존되지 않는다.
- 서버에서 직접 받은 원문은 서버에만 있다. 로컬에 같은 파일이 있다고 추정하지 않는다.

### 2026-10-10 실제 실행 결과

기존 Runpod의 `/workspace/PAC2026`에서 Python 3.12.3으로 실행했다. 최초 실행 당시 기반 커밋은 `faf0219bc5f953b82038f7694b8e860336913df6`이었고, 최신 공개 명세와 이번 도구·설정은 선별 전송한 작업 파일이었다. 이후 공개 코드·설정·안내는 Git으로 관리하며, 원본과 실행 로그는 Git 제외 경로에 별도 보관한다.

| 확인 | 결과 |
|---|---|
| 직접 다운로드 | 16/16 성공: 사진 10장, 카드·라벨 2개, 원문 4개 |
| 다운로드 파일 합계 | 3,089,515 bytes, 약 2.95 MiB. manifest·로그 제외 |
| 해시·형식 재검증 | `--verify-only` 16/16 성공. 사진·메타데이터는 기존 고정 SHA와 일치 |
| 문서 확인 수준 | TWI 페이지 제목·현대 `arccond` 제목·PDF 파일 서명 확인. 표 내용 검수는 미실시 |
| 도구 테스트 | 로컬과 Runpod에서 6개 통과: 로컬 복사, 무쓰기 검증, 해시 불일치·복구, 기존 파일 보존, 경로 탈출 등 |
| 기록 | 서버 `output/data-setup/tests.log`, `bootstrap.log`, `verify.log`, 원본 폴더의 `asset-manifest.json` |

로그 3개와 manifest 사본은 로컬 `output/data-setup/`에도 내려받았다. 원문 4개는 서버에 있으며 로컬에는 실행 기록만 가져왔다. 출처 목록은 16개 모두 SHA-256을 고정했다.

최초 manifest 기록 시각은 `2026-10-09T18:44:42Z`(한국 시각 2026-10-10 03:44)다. AI Hub 데이터·모델 가중치는 이번에 받지 않았다. OCR 추론·RAG·시뮬레이션 실행은 다음 단계다.

### 후속 구현 상태

2026-10-10 기존 작업파일·원본·로그 보존 후 서버 Git을 `577faa6`으로 정합했다. 원문4개와 사진·메타데이터를 로컬에도 복사해 해시와 원문 위치를 검토했다. 실제 OCR/VLM·문서 추출·검색 명령과 결과는 [Runpod 인식·검색 안내](RUNPOD_INFERENCE.md)를 따른다. 앞 절의 미실행 표시는 최초 자료 준비 당시 상태다.
