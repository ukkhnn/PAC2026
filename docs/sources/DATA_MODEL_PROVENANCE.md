# 데이터·모델 출처 기록

확인일: **2026-10-10 (Asia/Seoul)**. 확인 당시 저장소 커밋: `945132109b01ea7da38f6ebff68637b0c73fa9cd`. 2026-10-11에 아래 표시한 항목만 갱신했고 해시·revision 재확인은 하지 않았다.

실제 확보 파일, 실행 설정, 결과에 남은 출처를 모았다. 원문 주소·고정 revision·파일 SHA-256·가공 과정·사용 실행·라이선스 확인 수준을 [기계 판독용 출처 목록](../../configs/data_model_provenance.json)에 함께 보존한다. 이 문서는 그 목록을 읽기 위한 안내다.

현재 데모 입력, 과거 실험, 설계가 무효화된 CTX-001, 검토만 한 후보를 구분한다. 과거 실험 결과는 현재 성능 근거에서 제외하며, 원본 기록은 출처 추적을 위해 보존한다. 확인일 시점에 진행 중이던 실험은 [PV2](../../experiments/pipeline_v2/REPORT.md)이며 그 입력·모델 manifest는 이 목록에 고정하지 않았다. PV2 자체의 기록은 `experiments/pipeline_v2/results/`에 있다. `[확인 필요]`는 확인하지 못한 사실이며, 빈 revision이나 해시를 추정해서 채우지 않는다.

## 1. 전체 구성

| 자료 | 원출처 / 생성 주체 | 실제 용도 | 추적 단위 |
|---|---|---|---|
| 공개 철골 사진 10장·배포자 정답 | Hugging Face `iput-tk230215/steel-ocr-dataset-960` | OCR/VLM 입력, 과거 개발 실험 | 고정 revision, 원본 파일·라벨 해시, S01–S10 |
| 공개 문서 4개 | TWI, LANL, Hyundai Robotics | 문서 추출·검색, WPS 원문 근거 | 원본 해시, 문서 ID, 페이지·영역 또는 문단 |
| 과거 ROI·회전 이미지·문항·가상 지시 | PAC2026에서 원본·정답·공개 글로부터 파생 | E1/E2/E4/E5 개발 실험 | 부모 원본, 좌표·변환, 작성 파일 |
| 현재 시연 작업지시·도면·등록조건 | PAC2026 작성 | 저장된 실제 인식 결과와 WPS 필드 연결, 제조사 입력 변환의 기본값 | fixture 해시, 원본 관측 ID |
| 제조사 입력 프로파일 2개 | 현대 Hyundai Robotics·두산 공식 문서에서 작성 | 공통 명세의 현대 Hi6·두산 DRL 변환 | 공식 문서 URL·확인일, 현대 원문 SHA-256 |
| Isaac 야간 작업장·조선소 장면 | PAC2026 생성 코드 + NVIDIA Isaac Sim 자산 | 반사·재촬영 흐름 시연용 합성 RGB | 장면 설정·생성기·seed·렌더 이미지 해시 |
| 실제 실행 모델 9개 | PaddlePaddle, Qwen, RapidAI 배포 모델, Apple Vision | 현재 3개 + 과거 6개 | 고정 checkpoint 또는 배포/OS 버전 |

사진의 `train`은 **배포자가 붙인 분할 이름**이다. 확인한 프로젝트 실행은 추론·개발 평가이며, 프로젝트가 이 자료로 모델을 학습하거나 미세 조정했다는 기록은 없다. 자체 작성 문항과 가상 작업지시는 독립적으로 수집한 현장 정답 자료가 아니다.

## 2. 실제 철골 사진과 정답

- 배포 페이지: [Steel OCR Dataset 960](https://huggingface.co/datasets/iput-tk230215/steel-ocr-dataset-960).
- 사용 revision: `37725284f40deeaccbdeb3734be7b0e90e974305`.
- 배포자 카드가 연결한 관련 코드: [image-recog](https://github.com/solution-futureindustry-2025-teamB/image-recog). 계정명만으로 원 촬영자·촬영 사업장·권리자를 확정하지 않는다.
- 선택 규칙: `train` 이미지 경로의 UTF-8 문자열을 SHA-256으로 정렬한 앞 10개. [원본 manifest](../../experiments/e1_ocr/manifest.json)와 [확보 설정](../../configs/demo_data_sources.json)에 기록되어 있다.
- 배포자 문자·다각형 정답을 사용한다. 과거 E1의 채점 대상은 28개 표기이며, `difficult=true`인 S10의 표기 1개는 제외했다. 독립 재라벨링은 하지 않았다.
- 고정 다운로드의 `train.txt`는 156행, 데이터 카드 설명은 학습 이미지 222장이다. `[확인 필요]` 이 차이를 전체 표본 수로 해석하지 않으며, 실제 사용 수는 manifest의 10장이다.

아래 파일의 원본 경로 앞에는 모두 `train_data/det/images/`가 붙는다. 원본 URL과 전체 64자리 SHA-256은 JSON의 `data_families → steel-ocr-960-subset → assets` 및 `acquired_assets`에 있다.

| ID | 원본 파일명 | SHA-256 앞 12자리 |
|---|---|---|
| S01 | `kanawa_IMG_0772.jpg` | `92dced68e6c58` |
| S02 | `kanawa_IMG_0770.jpg` | `56180af3d6a82` |
| S03 | `tsukimoto_IMG20250416160808.jpg` | `d245b46699ab9` |
| S04 | `kamijo_IMG_1560.jpg` | `5019aa229dab8` |
| S05 | `tsukimoto_IMG20250416152847.jpg` | `4ccda788e2a4f` |
| S06 | `watanabe2_bundle_multi_005_yellow.JPG` | `b32e563a74977` |
| S07 | `tsukimoto_IMG20250416152836.jpg` | `5c75e5b0db343` |
| S08 | `tsukimoto_IMG20250416160730.jpg` | `3055ff8b47bd2` |
| S09 | `tsukimoto_IMG20250416152830.jpg` | `b80718bc06102` |
| S10 | `watanabe2_solo_008_B15b30N-20_0deg_N_yellow.JPG` | `1a9494099122f` |

정답 파일 SHA-256은 `cff20945685ac20654313e58fb0d54fa99c7b559a10cbfc0d29964c7423c0fcb`, 고정 데이터 카드 SHA-256은 `b699ac6d6187055cc70dd6827ccfb802b713d039d4973c16b5e9b40af51c26c2`다. 현재 원본 사본은 `data/raw/demo-bootstrap-v1/`에 있다. 확보 시각은 자산별로 JSON에 UTC를 보존했으며, 서버 확보일은 한국 시간 2026-10-10이다. 초기 로컬 E1 확보일은 2026-10-09다.

**라이선스 확인 수준:** 고정 카드의 YAML과 현재 배포 페이지는 MIT를 선언한다. 고정 파일 목록에 별도 LICENSE 파일은 확인되지 않았고, 원 사진의 촬영자·촬영 위치·별도 권리 관계는 `[확인 필요]`다. 사진만으로 재질·두께·적용 WPS를 확정하지 않는다.

원본 크기 데이터셋 [steel-ocr-dataset](https://huggingface.co/datasets/iput-tk230215/steel-ocr-dataset)의 revision `cc1d729fc0e9e78945ee63463ee7f6e3e8d1b395`에서는 **test 파일명 14개 목록만** 확인했다. [분할 점검 기록](../../experiments/e1_ocr/split-audit.json)의 파일명 중복 확인에 사용했으며, 이 test 이미지로 평가한 기록은 없다. 파일명 중복이 없다는 사실이 시각적 독립성을 보장하지는 않는다.

## 3. 공개 문서와 원문 근거

확보 문서는 아래 4개다. `output/document-rag/server-v1/index.json`의 추출 인덱스에는 총 74개 조각이 있다. **다운로드·인덱싱된 문서와 개별 모델 호출에 제공·인용된 문서는 구분한다.** 실제 호출의 제공 근거 ID와 인용 ID가 사용 여부의 기준이다.

| 문서 ID / 발행 주체 | 원문 | 저장 내용·버전 | 확인된 용도 |
|---|---|---|---|
| `twi-weld-symbols` / TWI | [A review of the application of weld symbols on drawings](https://www.twi-global.com/technical-knowledge/job-knowledge/weld-symbols) | HTML, 의미 단위 60개. 고정 revision 없음 | bootstrap 관계 추론의 기본 검색 대상. 과거 E2 요약 자료의 원출처 |
| `lanl-wts` / Los Alamos National Laboratory | [WTS blank form](https://engstandards.lanl.gov/esm/welding/vol4/4-01-Att-1-R1.pdf) | 1쪽 PDF, 표제 Rev.1 / 2006-10-27, 인덱스 1개 | 추출·조회 확인. 빈 양식이며 실제 작업지시가 아님 |
| `lanl-wps-3501` / Los Alamos National Laboratory | [WPS 3501-xxxx-1](https://engstandards.lanl.gov/esm/welding/welding_specs/3501-xxxx-1.pdf) | 2쪽 PDF, 검수본 Rev.1, 인덱스 2개 | 선택한 적용성 필드·대표 layer 1의 전사와 페이지/영역 근거 연결 |
| `hyundai-arccond` / Hyundai Robotics | [arccond 명령 문서](https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/5_arccond.md) | Markdown `ko` 브랜치, 문단·표 11개 | 제조사 명령 참고·추출·검색. 이 문서로 실제 로봇을 구동한 기록은 없음 |

| 로컬 원본 경로 (`data/raw/demo-bootstrap-v1/` 아래) | SHA-256 |
|---|---|
| `documents/twi/weld-symbols.html` | `e1956080eb25e3b7b6f317807ff60dcf044309f90db97b8a1f8e6c4107121b94` |
| `documents/lanl/wts-rev1.pdf` | `d1dfdcf01435d55260783401edee7d42008d9d251a6ced5bf88caace2f9746a2` |
| `documents/lanl/wps-3501-xxxx-1.pdf` | `608db44080beab287dc1cd7e5a0b44744d63b0c51058e7ea159503af5b8dae10` |
| `documents/hyundai/arccond.md` | `bd47b532b6784d7d301e3ffe4e3befa5400e54940b55cd43133a6082a379d199` |

PDF는 `pdfplumber 0.11.10`으로 페이지·단어 좌표·표를 추출했다. 자동 표 분할은 전부 검수된 것이 아니다. TWI의 텍스트 추출에는 그림 속 기호가 포함되지 않는다. 일반 인덱스의 `revision=null`은 원래 값을 유지한다. 이후 확인한 WTS 표제와 WPS 검수본의 개정 정보를 별도 필드에 기록했다. Hyundai 자료는 원격 commit이 고정되지 않은 브랜치 URL이므로, 확보 당시 파일의 동일성은 위 해시로 구분한다.

WPS의 파생 검수본은 [lanl-wps-3501-reviewed.json](../../data/knowledge/lanl-wps-3501-reviewed.json)이다. 원문 SHA, 페이지, bounding box, 원문 값과 정규화 값을 연결한다. 텍스트·페이지 렌더를 대조한 선택 필드의 전사 검수이며, 사람의 도메인 검토나 현장 적용 승인을 뜻하지 않는다. 검수 범위 밖의 필드까지 검수된 것으로 확장하지 않는다.

4개 문서는 공식 원문 접근을 확인했다. 별도 재배포 라이선스는 `[확인 필요]`로 기록한다. 다운로드 당시의 `content_reviewed=false` 등은 JSON의 `acquisition_review_snapshot`에 보존하고, 이후 추출 및 선택 WPS 전사 검수와 구분한다.

## 4. 실행된 모델

### 현재 OCR/VLM

| 역할 | 공식 배포처 | 실제 실행 revision | 확인된 라이선스 근거 |
|---|---|---|---|
| 문자 검출 | [PaddlePaddle/PP-OCRv6_medium_det](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det) | `8e0f56fb2ef86b461d99cfc7ac5c137738985f61` | 현재 공식 카드의 Apache-2.0 선언 |
| 문자 인식 | [PaddlePaddle/PP-OCRv6_medium_rec](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec) | `e5a92bcbc5cc1b494628e458d267778f0704fd7c` | 현재 공식 카드의 Apache-2.0 선언 |
| 이미지·문자 관계 추론 | [Qwen/Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` | [실행 revision의 카드](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct/blob/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b/README.md)의 Apache-2.0 선언 |

`steel-smoke-20261010-01`, `steel-batch-20261010-02`의 실제 실행 기록에 연결한다. JSON에는 모델별 고정 트리 URL과 가중치·설정·토크나이저를 포함한 **23개 파일의 전체 해시**가 있다. 다운로드 manifest와 실행 `inference-config.json`의 파일 정보가 일치한다. 이번 출처 점검에서 서버의 대형 가중치 바이트를 다시 읽거나 모델을 다시 실행하지는 않았다.

Paddle의 고정 revision 카드 URL은 이번 웹 확인에서 표시되지 않아, 라이선스는 현재 공식 카드 선언 수준으로 기록했다. 확보한 23개 파일 목록에는 별도 LICENSE가 없다. 모델 카드의 선언과 실행 패키지 코드의 라이선스를 같은 근거로 취급하지 않는다.

확인된 실행 환경은 `paddleocr 3.7.0`, `paddlex 3.7.2`, CPU용 `paddlepaddle 3.3.1`, `torch 2.8.0+cu128`, `transformers 4.57.6`이다. 나머지 패키지 버전과 코드 라이선스 출처는 JSON의 `runtime`에 있다. 현행 문서 검색은 어휘/BM25 방식이며, **임베딩 모델을 사용했다는 실행 기록은 없다.**

### 과거 실험에서 실행한 모델

| 모델 / 배포자 | 고정 정보·원출처 | 실행 | 출처·라이선스 한계 |
|---|---|---|---|
| Apple Vision 문자 인식 / Apple | [VNRecognizeTextRequest](https://developer.apple.com/documentation/vision/vnrecognizetextrequest), request revision 3, macOS 26.5.1 / 25F80 | E1-001, E1-002 | OS 포함 모델. 별도 checkpoint/hash 없음. 공개 가중치 라이선스로 표시하지 않음 |
| `PP-OCRv6_det_small.onnx` / RapidAI 배포 | RapidOCR `v3.10.0`, [공식 모델 목록](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml) | E1-003 | 원 계열 PaddlePaddle, ONNX 변환·배포 RapidAI |
| `PP-OCRv6_rec_small.onnx` / RapidAI 배포 | 동일 배포 버전·공식 목록 | E1-003, E1-004 | E1-004는 인식기만 사용, 검출기·분류기 비활성 |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx` / RapidAI 배포 | 동일 배포 버전·공식 목록 | E1-003 | 위 ONNX 3개의 개별 배포 라이선스는 `[확인 필요]` |
| Qwen2.5-0.5B-Instruct / Qwen | [고정 배포본](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775), `7ae557604adf67be50417f59c2c2f167def9a775` | E2-001 | 고정 LICENSE의 Apache-2.0. CPU float32 |
| Qwen2.5-1.5B-Instruct / Qwen | [고정 배포본](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/tree/989aa7980e4cf806f80c7fef2b1adb7bc71aa306), `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | E2-002 | 고정 LICENSE의 Apache-2.0. Apple MPS float16 |

RapidOCR의 3개 ONNX는 로컬 바이트를 다시 해시하여 당시 실행 기록·공식 버전별 모델 목록과 일치함을 확인했다. 실제 ModelScope 다운로드 URL과 전체 해시는 JSON에 있다. [RapidOCR 코드](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/LICENSE)의 Apache-2.0 및 [ONNX Runtime 코드](https://github.com/microsoft/onnxruntime/blob/v1.30.0/LICENSE)의 MIT만으로 모든 배포 가중치의 조건을 확정하지 않는다. 과거 Qwen 2개는 보존한 파일 manifest를 사용했으며 대형 가중치를 이번에 다시 해시하지 않았다.

## 5. 파생·자체 작성 데이터

| 자료 ID | 생성 방법과 부모 자료 | 남긴 근거 / 해석 범위 |
|---|---|---|
| `e1-derived-roi-rotations` | 공개 정답 다각형에서 28개 ROI, 여백 5%·최소 2px, 회전 입력 생성 | JSON에 원본 ID·좌표·crop 해시. GT 위치를 사용하는 진단을 전체 검출 성능으로 해석하지 않음 |
| `e1-control-image` | `ABC123 B-108`을 Monaco 글꼴로 그린 제어 이미지 | 엔진 동작 확인용, 본 채점 제외. 실제 글꼴 버전·해시 미보존 |
| `e2-authored-corpus-questions` | TWI 글을 바탕으로 작성한 영문 요약 6개·140단어, 질문 9개·평가기준 | [corpus](../../experiments/e2_documents/corpus.json), [questions](../../experiments/e2_documents/questions.json), [rubric](../../experiments/e2_documents/rubric.json). 원문 전체나 독립 전문가 평가셋이 아님 |
| `e4-synthetic-orders` | 공개 사진의 정답 부재번호에서 가상 작업지시 작성 | [E4 자료](../../experiments/e4_linking). 실제 생산 지시와의 일치 정답이 아님. E5는 저장된 E2 출력·검사 fixture 사용 |
| `first-scene-fixture` | 수동 문자 후보·지시·revision을 작성 | [part-order-scene.json](../../data/examples/part-order-scene.json). 초기 동작 예시 |
| `document-demo-fixtures` | 저장된 S07 / `frame-007` 관측을 키로 시연 지시·도면 작성 | [work_orders](../../configs/document_demo/work_orders.json), [drawing](../../configs/document_demo/drawing.json), [SVG](../../configs/document_demo/drawing.svg), [scenario](../../configs/document_demo/scenario.json), [target_profile](../../configs/document_demo/target_profile.json) |
| `weld-recipe-fixtures` | 사용자가 허용한 시연 기본값. `WO-DEMO-015` 개정 1과 LANL WPS 개정 1 `layer-1`에 연결. WPS 범위의 중간값을 자동 선정한 값이 아님 | [weld_recipes](../../configs/document_demo/weld_recipes.json) |
| `shipyard-pipeline-fixtures` | 통합 실행용 시연 도면. `J01` 표기를 업무 ID `JOINT-DEMO-01`에 잇는 `joint_marking_map` 포함. 사진의 실제 형상 복원이 아님 | [drawing](../../configs/shipyard_pipeline/drawing.json) |
| `robot-input-profiles` | 현대·두산 공식 문서에서 작성한 입력 프로파일. 특정 로봇 본체·용접기 모델을 선정하지 않음 | [hyundai_hi6](../../configs/robot_profiles/hyundai_hi6_current_voltage.json), [doosan_drl](../../configs/robot_profiles/doosan_drl_analog.json) |
| `unit-test-fixtures` | 코드에서 작성한 이미지·관측·문서 조각·응답 | 테스트 입력. 실제 모델 추론 결과나 현장 표본으로 합산하지 않음 |

시연 문서의 `BISB30N-15`는 저장된 실제 인식 결과를 그대로 연결한 키다. 배포자 정답으로 교정한 값이라고 주장하지 않는다. 실제 라벨 표기는 `B1Sb30N-15`이며 저장된 인식 원문은 `BISb30N-15`(오독)로, 이를 대문자로 정규화한 `BISB30N-15`가 시연 키다(계보: [인식과 연결](../../runs/RECOGNITION_AND_BINDING.md)). `WO-DEMO-015`, `DRAWING-DEMO-015`, `JOINT-DEMO-01`과 FCAW/A36/flat 등의 조건은 작성한 시연 가정이다. 해당 사진에서 실측한 형상·재질·두께나 현장 승인 문서를 뜻하지 않는다.

**CTX-001은 설계 무효화 상태로 별도 보존한다.** 9장/28개 GT ROI와 정답 라벨에서 만든 6개 부재 목록·배치 맥락을 사용했다. ROI는 여백 8%·최소 4px로 별도 생성했으며, E1의 crop·회전물과 구분한다. 정답이 포함된 후보 선택을 파이프라인의 인식 개선으로 해석할 수 없으므로 현재 정확도나 발표의 모델 당위성 근거로 사용하지 않는다. 출처 목록의 `ctx001-invalidated-derived-inputs`는 이 계보를 남기기 위한 항목이다. 관련 입력·결과·정답 파일은 변경하지 않았다.

## 6. Isaac 장면·텍스처·로봇 자산

두 장면 모두 **NVIDIA Isaac Sim 6.1에서 생성한 합성 RGB**다. 실제 조선소 촬영 데이터로 분류하지 않는다. 저장된 장면은 미리 정한 A/B 시점과 시뮬레이션 관절 이동을 포함하지만, 추론 결과가 이동을 유발한 실시간 피드백 실행은 아니다.

| 장면 | 입력·생성 출처 | 보존 위치 |
|---|---|---|
| 기존 야간 작업장 `night-welding-glare-01` | [설정](../../configs/isaac_scene/night_welding.json), [생성 코드](../../scripts/isaac/run_isaac_welding_scene.py), DejaVuSansMono-Bold 텍스처 | `output/isaac-scene-20261010/live-01/manifest.json` 및 A/B wrist·overview PNG |
| 조선소 수기 `shipyard-handwriting-glare-01` | [설정](../../configs/isaac_scene/shipyard_handwriting.json), [장면 코드](../../scripts/isaac/run_isaac_shipyard_scene.py), [수기 생성 코드](../../scripts/isaac/isaac_shipyard_marking.py) | `output/context-ablation-20261010/isaac-live-03/manifest.json` 및 A/B wrist·overview PNG |

조선소 수기는 실제 사진의 문자를 베낀 것이 아니라 `shipyard-stroke-glyphs.v2`, seed `20261010`으로 생성한 획이다. 이 수기 생성에는 외부 글꼴을 사용하지 않는다. 패널·작업장 형상은 USD 기본 도형으로 작성했으며, 외부 로봇 모델은 [NVIDIA Isaac 6.1 자산 라이브러리의 UR10 USD](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.1/Isaac/Robots/UniversalRobots/ur10/ur10.usd)를 참조한다.

장면 manifest는 캡처 당시 소스 commit과 dirty 상태를 함께 기록한다. 현재 저장소 HEAD 하나만으로 렌더 입력을 재현했다고 볼 수 없으므로, JSON에 장면 설정·생성기·텍스처·PNG 해시를 보존했다. 이번에 대조한 장면 소스 5개 항목(두 장면의 공통 파일 포함)과 설정 2개는 캡처 기록·보존 사본·현재 코드의 해시가 일치했다. 캡처 당시 commit과 현재 commit이 다르다는 사실을 코드 바이트 불일치로 해석하지 않는다. 현재 조선소 입력의 wrist A/B 해시는 다음과 같다.

- A: `8ee7e159d0723b89592272958924edaf5aecb6cba52d0bcf24eee9ff8fdb3802`
- B: `2492583e4c354790765fef7f80aabcd8025edbfe8d020f13338942e6b34e70d8`

[공개 JPEG 미리보기 기록](../images/isaac_shipyard/README.json)은 이 PNG의 파생물이다. `output/recapture-handoff-20261010/inputs`도 같은 저장 프레임의 사본이며, 새로 수집한 데이터가 아니다. 2026-10-10 확인 시점에는 이 준비물에 모델 추론 기록이 없었으나, 이후 [통합 파이프라인](../runs/WELD_PIPELINE.md)이 `--capture-inputs`로 같은 경로를 입력 삼아 실제 판독을 수행했다.

Isaac 코드와 추가 구성 요소·자산·텍스처의 조건은 [공식 법적 고지](https://docs.isaacsim.omniverse.nvidia.com/latest/common/legal.html)와 [추가 소프트웨어·자료 라이선스](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)를 구분해 기록했다. UR10 본체·하위 자산의 정확한 파일 해시와 개별 조건은 `[확인 필요]`다. 기존 장면의 [DejaVu 라이선스](https://dejavu-fonts.github.io/License.html)는 확인했지만 실제 설치 글꼴 파일의 버전·해시는 남지 않았다. manifest의 marking 해시는 **생성 이미지의 해시**이며 글꼴 해시가 아니다.

## 7. 실행과 출처 연결

| 실행 | 입력 / 문서 | 모델 또는 처리 |
|---|---|---|
| steel smoke / batch-02 | 공개 사진, 호출별 검색·제공 문서 근거 | PP-OCRv6 medium det/rec + Qwen3-VL-8B |
| document-demo / explicit-review | 저장된 실제 관측 + 시연 작업지시·도면 + LANL WPS 검수본 | 기존 결과 재사용·필드 연결·검사. 새 모델 추론으로 합산하지 않음 |
| E1-001/002 | 공개 사진·GT crop·회전, 제어 이미지 | Apple Vision |
| E1-003 | 같은 공개 사진·GT crop | RapidOCR ONNX 3개 |
| E1-004 | GT crop·회전 | RapidOCR 인식기 1개 |
| E2-001/002 | TWI 기반 자체 요약·질문·rubric | 각각 Qwen2.5-0.5B / 1.5B |
| E4-001 / E5-001 | 저장된 E1 / E2 출력과 가상 fixture | 연결·검사 코드. 추가 모델 추론 없음 |
| CTX-001 | GT 파생 후보·맥락과 기존 사진 ROI | 현재 모델 3개 사용 이력은 보존, 평가 설계는 무효화 |
| Isaac live-01 / live-03 | 절차적 장면 + UR10 자산 | 시뮬레이터 렌더. OCR/VLM 실행의 근거가 아님 |

이 표의 식별자 연결은 JSON의 `run_source_mapping`에도 있다. 인덱싱됐다는 사실만으로 모든 문서를 모델에 제공했다고 표시하지 않는다. 원문 근거 ID가 있다는 사실만으로 모델 답변의 내용이 맞다고 표시하지 않는다.

## 8. 검토만 한 자원

실행 근거가 없는 모델은 `investigated_not_used`에 분리했다. Korean PP-OCRv5 recognizer, PaddleOCR-VL-1.6, Granite Docling, Qwen3-VL-4B, Grounding DINO, SAM2.1, RT-DETRv2, BGE-M3가 해당한다. Docling·YOLO도 조사 항목이며 사용 checkpoint가 확정된 실행으로 기록하지 않는다.

MPSC/RFN, KR Rules 2026, KOBELCO 자료, weldCalloutIdentifier, Zenodo shipyard 자료는 조사한 후보 출처다. 실제 사용 파일로 편입했다는 근거가 없어 다운로드·실행 목록에 합치지 않았다. 기존 후보 검토는 [오픈 자원·시나리오 문서](../plan/PIPELINE_OPEN_RESOURCES_AND_SCENARIO.md), 원출처 URL은 JSON에서 확인할 수 있다.

## 9. 이번 점검 결과와 남은 출처 정보

이번 점검에서는 원본 사진 10장·데이터 카드·정답·문서 4개, **총 16개 파일의 로컬 SHA-256이 확보 manifest와 일치**했다. 현재 모델 23개 파일은 다운로드·실행 메타데이터를 대조했고, 과거 RapidOCR 가중치 3개와 두 장면의 원본 PNG 8개는 실제 로컬 바이트를 다시 해시했다. 별도로 남은 Vision sandbox 실패와 bootstrap batch-01의 미완료 시도는 JSON의 `coverage.failed_attempts`에 구분했다. 원본 입력·정답·실행 결과를 수정하거나 새 추론을 실행하지 않았다.

다음 정보는 `[확인 필요]`로 남겼다.

1. [PV2](../../experiments/pipeline_v2/REPORT.md)에서 확정한 입력·모델·가공 manifest와 추가 자원. 현재는 실험 폴더에만 있고 이 목록에 고정하지 않았다.
2. 철골 사진의 원 촬영자·촬영 장소·별도 권리 관계, 카드와 라벨 파일의 표본 수 차이.
3. 공개 문서의 별도 재배포 조건, RapidOCR 배포 ONNX 가중치의 개별 라이선스.
4. Apple Vision 내부 checkpoint, UR10 하위 자산 및 기존 글꼴의 정확한 버전·해시.
5. Hyundai 문서의 확보 당시 upstream commit. 보존 파일은 SHA-256으로 식별 가능하다.

새 실행을 편입할 때는 실행 ID에서 이 목록의 자료·모델 ID를 참조하고, 원본 URL/배포자, 고정 revision, 확보 시각, 원본·가공 파일 해시, 부모 자료와 변환·seed, GT 생성 경로, 실제 제공·인용 근거를 추가한다. 미확인 값은 `null`과 사유로 남긴다. 이것은 출처 기록 규칙이며 새로운 실험 비교군·채점 설계를 정하는 문서는 아니다.

`output/`, `data/raw/`, 과거 모델 입력·실행 환경 등 Git 제외 자료의 경로는 보존된 로컬 실행물의 위치다. 새 clone에 자동으로 포함되지 않으므로, 공개 출처 목록의 URL·revision·해시와 원본 manifest를 함께 사용한다.
