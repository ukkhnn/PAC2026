# 참고 자료

프로젝트의 문제 정의와 요구사항을 뒷받침하는 자료와 확보 가능한 이미지·문서·코드를 정리한다. 공개 자료 재조사일은 2026-10-09다. 아래 대회 안내는 기존 2026-10-02 확인 기록이며 행사 일정은 이번에 재검증하지 않았다.

## 프로젝트 문서

| 자료 | 내용 |
|---|---|
| [제출 기획서](references/idea-proposal.pdf) | Static Duo의 ContextWeld 아이디어 요약서, 1쪽 |
| [미션 정의서](references/mission-03.pdf) | HD현대로보틱스 미션 03, 2쪽 |

PDF는 원본 내용을 유지하고 저장 위치와 파일명만 정리했다. 기획서는 제안 구조의 근거이며 구현 완료·성능의 근거가 아니다. 미션 정의서에는 예시 사진·영상·참고 링크가 제공되지 않았다.

## 대회 자료

| 출처 | 확인 범위 |
|---|---|
| [PAC 2026 공식 안내](https://ainnov.co.kr/pac2026) | 분과 성격, 본행사·멘토링·제출·심사 일정 |
| [PAC 2026 FAQ](https://ainnov.co.kr/pac2026/faq) | 분과 차이, 멘토링 참여, 행사 안내 |
| [공식 미션 03 PDF](https://ainnov.co.kr/public/assets/download/pac/pac2026_hd-hyundai-robotics_mission_3.pdf) | 검출·인식·해석·조건 판단·시각화·추적성 요구 |

일정은 공식 시간표를 기준으로 하며 변경될 수 있다. 사전 제작물 활용 범위, 본선 세부 배점과 제출 양식은 최신 개별 안내로 확인해야 한다.

## 도메인 자료

| 출처 | 활용 범위 | 한계 |
|---|---|---|
| [TWI Welding procedure](https://www.twi-global.com/technical-knowledge/job-knowledge/welding-procedure-039) | WPS 역할과 적용 변수 이해 | 대상 기업의 실제 승인 기준·설정값을 확정하지 않음 |
| [TWI Weld symbols](https://www.twi-global.com/technical-knowledge/job-knowledge/weld-symbols) | 용접 기호·치수·적용 표준의 구분 | 현장 수기 약어의 의미를 보장하지 않음 |

마일스톤과 구현 범위는 프로젝트의 개발 계획이며, 대회 주최 측의 공식 구현 명세와 구분한다.

## 확보 가능한 자료 요약 — 2026-10-09

공개 자료로 **철골 표기 인식, 용접기호 설명, 기준 문서 검색, WPS 항목 추출**을 개발할 수 있다. 이번 조사에서도 **현장 사진 → 표기 의미 → 같은 부재의 작업지시 → 적용 WPS → 최종 판단**이 연결된 공개 자료 묶음은 확보하지 못했다. 공개 자료가 전혀 없다는 뜻은 아니다.

| 구분 | 현재 확보·확인 범위 | 우선 활용 |
|---|---|---|
| 실제 철골 수기 이미지 | Steel OCR 960px 원본 10장과 배포 정답이 로컬에 있음 | 문자·영역 인식 비교 |
| 추가 산업 이미지 | Steel OCR 원본판, MPSC 배포 안내 확인 | 고해상도·다른 금속 표면으로 평가 확장 |
| 용접기호 그림·도면 | TWI 설명 그림, 공개 기호 검출 프로젝트·데이터 후보 | 기호 사전과 제한된 도면 인식 |
| 용접 지식·기준 | 한국선급 목록, TWI 해설, KOBELCO 표 확인 | 원문 근거 검색·맥락별 참고 자료 선택 |
| WPS·작업 문서 양식 | LANL WPS 예제와 WTS·검사·추적 양식 목록 확인 | 문서 구조·적용조건·이력 항목 설계 |
| 기업 작업 맥락 | 실제 부재대장·작업지시·변경이력·현장 표기사전 미확보 | 가상 자료임을 표시한 통합 시연 |

## 1. 이미지와 정답 데이터

수량은 별도 명시가 없으면 배포 페이지의 설명이다. 페이지 열람, 다운로드, 라벨 검수, 이용조건 확인은 서로 다른 단계다.

| 출처 | 얻을 수 있는 것 | 확보 상태·이용조건 | 적용 범위·한계 |
|---|---|---|---|
| [Steel OCR 원본판](https://huggingface.co/datasets/iput-tk230215/steel-ocr-dataset) | 철골 손글씨 제품코드 사진, 문자와 영역 정답. 카드상 학습·검증 319장, 테스트 14장, 인식용 crop 포함 | 카드 열람. 전체 원본 미다운로드. MIT 표기 | 현재 미션의 부재번호 인식에 가까운 후보. 조선 용접기호·작업 의미 정답은 없음 |
| [Steel OCR 960px](https://huggingface.co/datasets/iput-tk230215/steel-ocr-dataset-960) | 긴 변 960px 사진과 대응 좌표. 카드상 train 222장·val 95장, 약 182MB | 고정 버전에서 10장 확보·실험. MIT 메타데이터 표기; 기존 manifest에는 별도 LICENSE 파일 미확인 기록 | 이미 시작한 인식 실험의 입력. 원본판과 같은 계열이므로 별개 독립 데이터셋처럼 합산하지 않음 |
| [MPSC / SynthMPSC](https://github.com/TongkunGuan/RFN/blob/main/IndustrialTextDataset.md) | 금속 표면 문자 사진·영역·전사. 실제 train 2,555장·test 639장, 합성 98,962장 | 저자 안내의 Google Drive·Baidu 링크 확인. 압축파일 다운로드 미실시. CC BY-NC 4.0 및 학술 연구 한정 안내 | 부식·오염·반사·여러 방향의 보조 인식 평가. 대회 시연·재배포 범위는 [확인 필요]. 현장 수기 용접기호 정답은 아님 |
| [TWI 용접기호 그림](https://www.twi-global.com/technical-knowledge/job-knowledge/weld-symbols) | 화살표·기준선·이음·치수·보조 기호의 그림과 설명 | 본문·그림 링크 확인. 2020-04-27 재발행 해설. 그림 재배포 조건은 [확인 필요] | 기호 의미를 검토하고 제한된 예제를 설계하는 참고. 현장 사진 평가셋이나 최신 표준 전문을 대신하지 않음 |
| [Welded symbol — AriaCVBridge](https://universe.roboflow.com/ariacvbridge/welded-symbol) | 용접기호 검출 이미지 후보. 페이지 Images 606, 모델 v2 설명에는 640 images | 공개 페이지와 CC BY 4.0 표기 확인. 데이터 export·로그인 필요 여부는 [확인 필요] | 클래스 목록에 안내문 문장이 섞여 있음. [추론] 메타데이터 또는 라벨 품질 문제 가능성이 있어 채택 보류. 실제 파일의 분할·클래스·출처부터 검수 |

### 이미 가진 이미지

- [확보 manifest](../experiments/e1_ocr/manifest.json): 원본 URL, SHA-256, 배포 정답, 영역 좌표 기록.
- 고정 revision: `37725284f40deeaccbdeb3734be7b0e90e974305`. 로컬 `train.txt`는 실제 156행으로 카드의 222장 설명과 다르다. [확인 필요] 불일치 원인. 추가 수집 때 카드 숫자를 실제 확보량으로 쓰지 않는다.
- 로컬 이미지 10장 모두 manifest 해시와 일치함을 2026-10-09 재확인했다. 표기 29개 중 difficult 1개를 제외해 9장·28개 표기를 기존 실험에서 채점했다.
- 원본 위치: `experiments/e1_ocr/inputs/train_data/det/images/` — Git 제외. 예: `kanawa_IMG_0772.jpg`, `tsukimoto_IMG20250416160808.jpg`, `watanabe2_bundle_multi_005_yellow.JPG`.
- [기존 실험 결과](../experiments/REPORT-2026-10-09.md): 개발 표본으로 사용한 10장이므로 새 독립 평가셋으로 재사용하지 않는다.

## 2. 공개 문서와 작업 양식

| 출처 | 얻을 수 있는 것 | 이번 접근 확인 | 활용·주의점 |
|---|---|---|---|
| [한국선급 2026 규칙](https://www.krs.co.kr/KRRules/KRRules2026/KRRulesK.html) → 제2편 재료 및 용접 | 국문 규칙·적용지침. 별도 유효 회보 목록도 있음 | 공식 목록 확인. 이번 PDF 직접 열기는 도구 오류. 10/6에는 361쪽 다운로드·본문 추출 기록이 있으나 현재 프로젝트 안에 해당 PDF는 없음 | 국문 문서 검색의 우선 후보. 확보 시 판본·조항·회보·적용 시점을 기록. 실제 현장 승인 WPS와 구분 |
| [TWI Welding procedure](https://www.twi-global.com/technical-knowledge/job-knowledge/welding-procedure-039) | WPS의 역할과 절차 관련 설명 | 웹 본문 접근 확인 | 개념 설명과 질문·근거 구성. 특정 현장 설정값의 근거로 확대하지 않음 |
| [KOBELCO 조선용 용접재료 안내](https://www.kobelco-welding.jp/products/recommended-materials/index.html) | 조선 공정·부재/이음·자세·용접법·용접재료 대응표와 그림 | Shipbuilding 절과 표 본문 확인 | 작업 맥락이 달라지면 참고할 표 행도 달라지는 시연에 적합. 제조사 권장표이며 기업 승인 절차를 대신하지 않음 |
| [LANL WPS 3501-xxxx-1](https://engstandards.lanl.gov/esm/welding/welding_specs/3501-xxxx-1.pdf) | 기입된 WPS 예제, 2쪽 | 첫 열기에서 PDF·페이지 수 확인, 재열기는 오류. 10/6 본문 추출·시각 검수 기록 있음. 현재 프로젝트 안에 원문 PDF는 없음 | 표·단위·적용범위 추출 후보. 실제 파일 확보와 개정 확인 후 사용. 조선소 적용 기준으로 간주하지 않음 |
| [LANL Chapter 13](https://engstandards.lanl.gov/ESM_Ch13.shtml) | WPS, 작업별 WTS, Weld Tracking Chart, Weld Inspection Record 등 문서·양식 목록 | 공개 목록과 WTS 설명 확인. 개별 양식 파일은 이번에 전수 다운로드하지 않음 | 가상 작업지시·용접 추적·검사기록의 항목 설계 참고. 빈 양식·절차 문서는 실제 작업 이력이 아님. 일부 링크는 LANL 내부용 |

공개 열람 가능과 자유로운 원문·그림 재배포는 구분한다. 별도 라이선스를 확인하지 않은 문서는 원문 링크·필요한 요약·페이지/조항 참조를 중심으로 관리하고, 배포할 원문·그림의 이용조건은 [확인 필요]로 남긴다.

## 3. 공개 코드 후보

| 출처 | 참고할 내용 | 확인 상태 |
|---|---|---|
| [RFN](https://github.com/TongkunGuan/RFN) / [데이터 안내](https://github.com/TongkunGuan/RFN/blob/main/IndustrialTextDataset.md) | 산업 문자 검출 연구와 MPSC 수집·평가 안내 | 데이터 안내 확인. 코드 실행·가중치 검증 및 코드 라이선스는 [확인 필요]. 데이터의 CC BY-NC 조건과 코드 조건을 혼동하지 않음 |
| [weldCalloutIdentifier](https://github.com/RylanBosquez/weldCalloutIdentifier) | YOLOv8 기반 도면 용접기호 검출 코드·예시. 화살표, 꼬리, 필릿 등 | README·파일 목록·CC0-1.0 표기 확인. 전체 학습 데이터·가중치·실행성은 [확인 필요]. 도면 인식 예제이며 철판 위 수기 성능 근거는 아님 |
| [Steel OCR 연결 저장소](https://github.com/solution-futureindustry-2025-teamB/image-recog) | 데이터 카드가 안내하는 학습·전처리 코드 경로 | 카드의 링크만 확인. 이번 저장소 열기 실패로 실제 공개 접근·코드 확보는 [확인 필요] |

## 4. 당장 쓸 자료에서 제외하거나 보완할 것

| 자료 | 이유·대안 |
|---|---|
| [Shipyards process comparisons](https://zenodo.org/records/14591358) | 설명은 공개지만 파일은 Restricted. 확보된 작업 데이터로 세지 않음 |
| [LoHi-WELD](https://github.com/ssundxr/LoHi-Weld) 같은 용접 결함 데이터 | 용접 비드의 결함 검출이 대상. 부재번호·수기표기·용접기호 해석의 직접 평가셋으로 쓰지 않음 |
| 조선소 홍보 사진·영상 | 장면 이해에는 참고 가능하나 표기 정답·관련 작업지시가 확보되지 않으면 정확도 평가에 쓸 수 없음. 개별 사용조건 확인 필요 |
| 기업 표기사전·부재대장·작업지시·변경이력·승인 WPS | 현재 미확보. 공개 일반 문서에서 기업 고유 의미나 현재 작업 상태를 추정해 채우지 않음 |
| 자체 촬영·합성 자료 | 모사 표기·기호·오염·방향 변화의 통제된 기능 검증에 활용 가능. 실제 조선소 데이터와 분리하고 가상 작업지시는 같은 ID·버전·시점으로 연결해 작성 |

## 5. 우선 수집 순서

1. **Steel OCR 원본 이미지**: 기존 960px 사진에 대응하는 고해상도 원본과 다른 촬영 묶음의 개발 사진을 소량 확보한다. 대응 여부·중복·라벨부터 검수한다.
2. **TWI + KOBELCO + 한국선급 관련 절**: 지원할 기호와 질문에 필요한 부분을 선별하고 문서 ID·판본·원문 위치를 붙인다.
3. **LANL WPS 예제와 작업 양식**: WPS 표 추출과 가상 작업 묶음의 구조를 검토한다. 숫자·단위·표 행의 원문 대응을 확인한다.
4. **MPSC 또는 도면 기호 데이터**: 첫 장면에 필요한 경우에만 이용조건·다운로드·라벨 품질을 확인하고 추가한다.

[추론] 현재는 **실제 공개 사진 + 공개 지식 문서 + 명시적으로 구분한 가상 작업 맥락**이 구현 가능한 조합이다. 사진 인식과 문서 근거는 각각 검증할 수 있지만, 이 조합만으로 실제 기업의 작업·용접조건 판단 정확도를 입증할 수는 없다.

이번 갱신은 출처 조사와 기존 로컬 자료 확인이다. 신규 데이터셋 전체 다운로드·모델 설치·새 실험은 수행하지 않았다.
