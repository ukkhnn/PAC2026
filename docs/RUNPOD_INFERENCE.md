# Runpod 실제 인식과 문서 검색

기준일: **2026-10-10**. [자료 준비](RUNPOD_DATA_SETUP.md) 뒤에 수행하는 구현 단계다. 확보한 Steel OCR 사진을 실제 모델에 입력하고, 다운로드한 원문에서 검색한 근거를 별도 관계 해석 호출에 제공한다. 시뮬레이터 A/B·카메라 이동·모의 전달·관리자 화면을 완료했다는 뜻은 아니다.

## 이번 실행 계약

| 항목 | 선택 |
|---|---|
| 입력 | 해시가 고정된 공개 Steel OCR 사진. 배포 정답 라벨은 모델 입력에서 제외 |
| 문자 OCR | PP-OCRv6 medium 검출·인식, 원본 픽셀 좌표·원문·점수 보존 |
| 시각 해석 | Qwen3-VL-8B-Instruct. 이미지 관측과 문서 제공 관계 해석을 별도 호출 |
| 문서 | TWI HTML, LANL WTS/WPS PDF, 현대 arccond Markdown |
| 최소 검색 | 명시한 문서 ID 안의 BM25 검색. 원문 해시·페이지/절/줄/영역 참조 반환 |
| 결과 | 원본 사진, 호출별 프롬프트·원문·구조화 결과, 검색 근거, 사건·해시를 실행 묶음으로 저장 |
| 판단 | 공개 사진과 작업문서의 적용 관계는 미확정. 실제 작업·WPS나 용접조건을 임의 승인하지 않음 |

[데모 스펙](DEMO_SPEC.md)의 일반 저장 구조를 사용하며 부분 실행을 나타내는 `run_kind=bootstrap`, `capture_mode=public_dataset`, `delivery_requested=false`를 추가한다. 이 값은 전체 시나리오나 수정 재검토가 아니다. `run_outcome=needs_review`로 관측·검색은 확인했지만 작업 대상·조건은 미확정임을 나타낼 수 있다. 기술 실패는 `failed`다. `export_status=complete`는 저장 묶음의 완전성만 나타낸다.

문서의 미확인 개정은 `null`로 남긴다. 다운로드 시점이나 파일 해시를 문서 개정번호로 표시하지 않는다. WTS는 빈 양식이고, LANL WPS는 공개 참고 절차다. 검색 점수·모델 응답은 해당 철골 사진의 적용 WPS나 실제 로봇 실행 승인이 아니다.

## 서버 상태 보존

기존 변경을 최신 dev와 비교한 뒤 작업파일·원본·로그를 별도 백업하고 Git stash에도 보존했다. 기존 파일을 강제 초기화하지 않고 `577faa6`으로 fast-forward했다. 유일한 본문 차이는 자료 준비 안내의 과거 미커밋·미푸시 설명이었다. 최신 커밋의 이력형 설명을 채택했다.

| 검증 | 결과 |
|---|---|
| Git 기준 | `577faa671802919cfc70e3b5d334d655fd67b9ae` |
| 기존 작업파일 | 21개 보존 |
| 원본·manifest·기존 준비 로그 | 20개 해시 동일 |
| 구현 시작 시 상태 | dev 작업 트리 clean |

최초 실행은 `577faa6`에 미커밋 구현 변경을 적용한 상태에서 수행했다. 당시 Git 상태와 실제 실행 코드의 파일 해시는 실행 기록에 보존했다. 추론 환경은 기존 Isaac 환경과 분리하고, 실제 패키지 버전·모델 revision·파일 해시는 실행 기록에 남긴다. 원문·실행 산출물·모델 가중치는 일반 Git에 추가하지 않는다.

## 실행 환경과 모델

| 항목 | 실제 사용값 |
|---|---|
| 서버 | Python 3.12.3, NVIDIA L40S 46,068 MiB |
| Python | `/workspace/venvs/contextweld-inference/bin/python` |
| OCR | PaddleOCR 3.7.0, PaddleX 3.7.2, PaddlePaddle CPU 3.3.1, 4 threads, MKLDNN 끔 |
| VLM | Transformers 4.57.6, torch 2.8.0+cu128, BF16, SDPA, greedy, 출력 최대 4,096 tokens. 첫 실행의 1,800에서 잘림 확인 후 변경 |
| 관측 예산 | VLM에 중요 객체 최대 12개·짧은 설명·중복 금지를 요청. 초과 시 경고를 남기며 원문을 임의로 자르지 않음 |
| 이미지 예산 | 원본 보존, VLM processor min_pixels=65,536 / max_pixels=802,816 |
| PDF | pdfplumber 0.11.10 |
| 모델 확보 | 3모델·23파일·17,685,072,078 bytes, revision과 전체 파일 SHA-256 기록 |

| 모델 | 고정 revision |
|---|---|
| `PaddlePaddle/PP-OCRv6_medium_det` | `8e0f56fb2ef86b461d99cfc7ac5c137738985f61` |
| `PaddlePaddle/PP-OCRv6_medium_rec` | `e5a92bcbc5cc1b494628e458d267778f0704fd7c` |
| `Qwen/Qwen3-VL-8B-Instruct` | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |

[고정 요구사항](../configs/requirements-inference.txt)과 [모델 준비 도구](../scripts/prepare/prepare_inference_models.py)를 사용한다. 이번 서버는 새 venv가 기본 환경의 torch/torchvision을 읽어서 재사용한다. 기존 Isaac 환경은 변경하지 않았다. 새 서버에서 기본 CUDA torch가 없다면 위 torch/torchvision과 CUDA 조합을 먼저 준비해야 한다. CPU torch 설치 상태를 같은 실행환경으로 취급하지 않는다.

이번 환경의 `pip check`에는 기본 환경부터 존재하던 colcon-core와 setuptools 버전 경고가 남는다. 추론 실행과 테스트는 통과했으며 ROS 환경을 임의 변경하지 않았다. 전체 패키지 잠금과 경고는 `output/implementation-20261010/model-setup/`에 있다.

공식 사용법 확인일은 2026-10-10이다. [PP-OCR 검출 모델 카드](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det), [인식 모델 카드](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec), [Qwen 모델 카드](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)를 참고했다. 모델 공개 성능을 이 사진의 성능으로 인용하지 않는다.

## 다시 실행하기

서버 저장소 루트에서 실행한다. 모든 색인 파일과 run ID는 새 경로를 지정한다. 기존 산출물이 있으면 덮어쓰지 않고 오류를 반환한다.

새 환경에만 격리 런타임을 준비한다. 현재 서버에는 이미 설치돼 있다.

```bash
python3 -m venv --system-site-packages /workspace/venvs/contextweld-inference
/workspace/venvs/contextweld-inference/bin/python -m pip install -r configs/requirements-inference.txt
/workspace/venvs/contextweld-inference/bin/python scripts/prepare/prepare_inference_models.py
/workspace/venvs/contextweld-inference/bin/python scripts/prepare/prepare_inference_models.py --verify-only
```

원문 추출과 위치 검색:

```bash
/workspace/venvs/contextweld-inference/bin/python scripts/prepare/build_document_index.py \
  --output output/document-rag/new-run/index.json
/workspace/venvs/contextweld-inference/bin/python scripts/run/query_documents.py \
  --index output/document-rag/new-run/index.json \
  --data-root data/raw/demo-bootstrap-v1 \
  --document-id twi-weld-symbols --query "arrow reference line other side" \
  --output output/document-rag/new-run/twi.json
```

실제 인식과 근거 제공 해석:

```bash
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
/workspace/venvs/contextweld-inference/bin/python scripts/run/run_recognition.py \
  --data-root data/raw/demo-bootstrap-v1 \
  --output-root output/recognition --run-id steel-new-run --limit 10 \
  --det-model-dir /workspace/models/contextweld/PP-OCRv6_medium_det/8e0f56fb2ef86b461d99cfc7ac5c137738985f61 \
  --det-revision 8e0f56fb2ef86b461d99cfc7ac5c137738985f61 \
  --rec-model-dir /workspace/models/contextweld/PP-OCRv6_medium_rec/e5a92bcbc5cc1b494628e458d267778f0704fd7c \
  --rec-revision e5a92bcbc5cc1b494628e458d267778f0704fd7c \
  --vlm-model-dir /workspace/models/contextweld/Qwen3-VL-8B-Instruct/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b \
  --vlm-revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b \
  --document-index output/document-rag/new-run/index.json \
  --document-ids twi-weld-symbols --ocr-device cpu
python3 scripts/verify/verify_run_bundle.py output/recognition/run_steel-new-run
```

`--limit 1`로 첫 사진부터 확인하거나 `--image-ids steel-S01 steel-S10`처럼 고정 ID를 고를 수 있다. 모델에는 원본 파일명의 표기 정보나 배포 라벨을 제공하지 않는다. OCR은 배열, VLM은 이미지 객체를 받는다. OCR·VLM의 다른 판독은 별도 관측으로 보존하며 평균 점수나 임의 정답으로 합치지 않는다.

## 실제 문서 확인

| 확인 | 결과 |
|---|---|
| 추출 | 원문 4개, 청크 74개: TWI 60, WTS 1, WPS 2, 현대 11 |
| 위치 | HTML/MD 절·원문 줄, PDF 페이지·단어/줄 bbox |
| 실제 검색 | 네 원문 유형 각각 근거 반환. 없는 문서·없는 개정은 0건과 `needs_review` |
| TWI 예시 | `The Broken Reference Line`, HTML 3061줄 반환 |
| PDF 확인 | WTS 1쪽과 WPS 2쪽까지 렌더 검수. 페이지 전체 청크가 머리글·수치·주석을 함께 보존 |
| 개정 | 현재 등록은 4개 모두 `null`; 원문 개정을 자동 추정하지 않음 |
| 숫자·표 | WPS 무선 표의 패스별 셀 분리는 미완료. 페이지 검색 결과를 검수된 조건값으로 사용하지 않음 |

일부 PDF 글리프는 텍스트 추출에 경고가 있어 렌더 원문과 함께 확인한다. 검색 결과에는 반환 근거 `hits`, 모델에 제공한 `used_evidence_ids`, 실제 모델이 인용한 `cited_evidence_ids`를 분리한다. 근거 문단을 모델에 제공해도 해당 사진의 용접기호·대상·WPS가 확정되는 것은 아니다. 원문4개와 전체 색인은 Git 제외 자료이며, 실행 묶음에는 검색 발췌와 문서 메타데이터만 포함한다. 오프라인에서 전체 원문을 열었다고 표시하지 않는다.

## 실제 인식 확인

첫 실행 `steel-smoke-20261010-01`은 사진 1장, OCR과 VLM 관측·관계 호출을 완료했고 20개 파일의 묶음 해시·단계 참조를 확인했다. 추론 파이프라인 소요시간은 20.890초였고 모델 파일 해시 계산은 이 시간에 포함되지 않는다. 대상 관계는 미확정으로 남았다. 이후 여러 프레임 실행의 사건 원인을 각 프레임의 실제 입력에 연결하도록 보강했다. 첫 묶음은 수정하지 않았다.

첫 전체 실행 `steel-batch-20261010-01`은 OCR 10장과 관계 단계까지 7장을 저장했으나, 8번째 사진의 VLM JSON 파싱이 1회 재출력 뒤에도 실패했다. `run_steel-batch-20261010-01.incomplete`의 원문·중간 결과를 그대로 보존했다. 6번째 사진에서도 반복 객체 설명과 첫 출력 잘림이 확인됐다.

이에 관측 프롬프트에 중요 객체 최대 12개·중복 설명 금지를 요청하고 출력 예산을 4,096으로 늘렸다. 관측이 12개를 넘어도 원문을 임의로 자르지 않으며 경고를 기록한다. 새 실행은 호출별 토큰 수·상한 도달·EOS·생성시간을 기록한다. 시연을 막은 형식 오류 대응이며 정확도 향상 실험으로 보지 않는다.

보완한 `steel-batch-20261010-02`의 실제 결과:

| 확인 | 결과 |
|---|---|
| 입력·모델 호출 | 사진 10장, 실제 OCR 10회, VLM 관측·관계 각 10회 |
| 저장 관측 | OCR 영역 61개, VLM 객체 후보 66개. 정답 개수나 정확도 지표가 아님 |
| 구조화 | 프레임별 5단계, 총 50결과·71사건 |
| 생성 안정성 | VLM 20호출 모두 JSON 처리, 재출력 0회·토큰 상한 도달 0회. 최대 출력 2,404 tokens |
| 시간 | 350.940초. 초기 모델 파일 해시 계산 제외, 파이프라인 안의 모델 로드 포함 |
| 문서 연결 | 프레임마다 TWI 근거 3개 검색·모델 입력 제공, 원문 위치 기록 |
| 모델의 실제 근거 인용 | 0개. 문서 제공 자체를 사진의 기호·WPS 적용 근거 확정으로 표시하지 않음 |
| 관계 후보 | S08에서 15개, 나머지 사진은 0개. 자동 정답 판정 없음 |
| 결과 상태 | 추론 `succeeded`, 업무 판단 `needs_review`, 실행 승인·전달 없음 |
| 묶음 검증 | 서버와 로컬에서 175개 파일 해시·입력/근거 참조·프레임별 필수 단계 통과. checksums 자체 제외 |
| 자동 테스트 | 로컬 Python3.11·Runpod Python3.12에서 각각 41개 통과 |

실제 모델 판독 차이와 미확정 의미는 남아 있다. 첫 사진에서 OCR의 `B1Sb30N-56`과 VLM의 `BISb30N-56`처럼 문자열이 다를 수 있고, 문서로 이를 교정하지 않았다. 이번 검증은 모델과 검색·저장 흐름의 실행 확인이며 문서가 관계 정확도를 높였다는 증거는 아니다. S08의 일부 관계는 부재 관측을 source로, 문자 관측을 target으로 연결했다. 표기→대상 방향과 의미의 검증은 아직 완료되지 않았고 후보로만 저장한다. 모의 전달에 필요한 작업지시·도면·WPS 적용 연결은 다음 단계다.

## 결과 보관과 인계

서버와 로컬에 다음 Git 제외 자료를 보관했다.

| 경로 | 내용 |
|---|---|
| `output/recognition/run_steel-smoke-20261010-01/` | 첫 1장 실제 실행 |
| `output/recognition/run_steel-batch-20261010-01.incomplete/` | 출력 파싱 실패와 이전 단계 원문 |
| `output/recognition/run_steel-batch-20261010-02/` | 최종 10장·모델 원문·구조화·문서 발췌·해시 |
| `output/document-rag/server-v1/` | 74청크 색인, 검색 6건과 위치 검증 |
| `output/implementation-20261010/` | 실제 명령·로그·테스트·모델/환경 잠금·검증 요약 |
| `data/raw/demo-bootstrap-v1/` | 원본 사진·문서·배포 메타데이터와 확보 manifest |

서버의 이전 작업 백업은 `/workspace/pac-backups/before-sync-20261009T185726Z/`와 Git stash에 유지하며, 같은 백업의 로컬 사본은 `output/implementation-20261010/server-preservation/`에 있다. 로컬 협업 기록은 서버·공개 Git으로 보내지 않는다. 최초 실행 기록의 기반 커밋은 `577faa6`이며 당시 구현 변경은 미커밋 상태였다. 이후 커밋 여부와 무관하게 완료된 실행 기록은 수정하지 않는다.

후속 [문서 연결 실행](DOCUMENT_DEMO.md)에서 기존 관측→모사 작업지시/도면→WPS 대표층의 범위값·원문 위치→검증→모의 HTTP 수신을 연결했다. 위 bootstrap 기록과 모델 출력은 변경하지 않았다. 사진의 실제 물성·WPS 적용성, A/B RGB·재촬영·사용자 수정 재검토·관리자 화면은 후속 범위다.
