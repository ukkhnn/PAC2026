# 지시서 보충 — 서버 유실물 복구 로컬 준비 (2026-10-16)

P1(server-artifact-recovery)은 서버(Runpod) 접근이 재개되기 전까지 실물 대조가 불가능하다. 이 문서는
로컬에서 미리 완결한 준비를 기록한다: 보존 사본 무결성 재계산, 서버 전용 후보 판정표, 기대 해시 출처
지도 v0.1, 서버 접속 시 명령 초안, 서버 스냅샷 분류. 서버 재개 시 4절의 명령 초안을 실행하고 3절의
해시 출처와 대조하면 된다. 모든 내용은 2026-10-16 로컬 HEAD `fb63ae3` 기준이며, 이 문서의 항목은
(claude 제안사항)이 아니라 사용자 확인을 거친 실행 기록이다.

## 1. 로컬 보존 사본 무결성 재계산 (전부 통과)

도구: `scripts/verify/recheck_preservation_copies.py` (신규, 표준 라이브러리만, 사본을 풀지 않고
스트리밍 해시). 전체 리포트: `output/p1-local-prep-recheck-20261016.json` (미추적).

| 대상 | 방식 | 기록 출처 | 결과 |
|---|---|---|---|
| document-demo `data-output-before.tar.gz` | tar-json | 같은 폴더 `data-output-before.json` | 365/365 일치 |
| isaac-scene `data-output-before.tar.gz` | tar-json | 같은 폴더 `data-output-before.json` | 1,339/1,339 일치 |
| implementation `working-files.tar.gz` | tar-working-files | 같은 폴더 `inventory.json`(working_files 21) | 21/21 일치 |
| `recapture-loop-handoff.zip` | zip-sha | 인계 기록 SHA `385bf4b3…`(HANDOFF.md·.cowork) | 일치 |
| pv2 `run-evidence.tar.gz` 내 `checksums.json` | tar-member-sha | `pipeline-v2-source.tar` 안 `e1-quick-bundle-checksums.sha256` `0ed5afe5…` | 일치 |
| pv2 `run-evidence.tar.gz` run 번들 | tar-internal-json | 내부 `checksums.json`(141항목) | 141/141 일치 |
| pv2 `run-evidence.tar.gz` ↔ 추출본 | tar-vs-dir | `output/pv2-read-review-20261010/source/` | 150/150 일치 |

결론: 로컬 보존 사본은 전부 기록 해시와 일치한다(무결). 서버 회수 파일과의 대조는 3절의 출처로 한다.

## 2. 서버 전용 후보 판정표 (서버 재개 시 최우선 확인 순서)

| 우선순위 | 서버 경로 | 서버 필수? | 로컬 보유 자료 | 판정 |
|---|---|---|---|---|
| 1 | `/workspace/pac-handoffs` | 실물 필수 | 없음(`output/handoffs-20261010/claude-parallel-prompts.json`은 서버 사본 아님) | 유일 사본 가능성 — 최우선 회수 |
| 2 | `/workspace/pac-backups` | 실물 필수 | 명명 규칙만(`before-<head>-<date>-<id>`) | 유일 사본 가능성 — 최우선 회수 |
| 3 | `output/explicit-review-20261010` | 실물 필수 | 동명 로컬 없음. 연관: `output/document-review-20261010/`(HTML 3종), `output/document-demo-20261010/server/`(5-run), provenance `run_source_mapping` 언급 | 재생성 불가 추정 — 우선 회수 |
| 4 | `/workspace/models/contextweld` | 실물 필수(로컬 가중치 없음) | `output/implementation-20261010/model-setup/model-manifest.json`(23파일 17,685,072,078B), `configs/data_model_provenance.json` models(9) | 재다운로드 가능 — HF 고정 revision 2026-10-16 생존 확인: PP-OCRv6_medium_det `8e0f56fb…`, Qwen3-VL-8B-Instruct `0c351dd0…`. 단 17.7GB라 회수가 재다운로드보다 빠르면 회수 |
| 5 | `/workspace/data-import/steel-ocr` | 범위 확인 필수 | 10장 사본(`data/raw/demo-bootstrap-v1/steel_ocr/` + `data-and-logs.tar.gz` 동일 10장) | 전체 범위·추가 파일 여부 확인 후 판정 |
| 6 | `output/context-ablation-20261010` | 실물 대조 | 로컬 전체 사본 + `final-local-verification.json`(서버=로컬 증명) | 서버 실물 ↔ 로컬 사본 대조 |
| 7 | `output/pipeline-v2-20261010` | 실물 대조 | `output/pv2-read-review-20261010/`(source.tar + run-evidence.tar.gz, 재계산 통과) | 서버 실물 ↔ 로컬 사본 대조 |
| 8 | `output/isaac-*` | 실물 대조 | `output/isaac-scene-20261010/server-preservation/`(1,339파일 재계산 통과) | 서버 실물 ↔ 로컬 사본 대조 |

## 3. 기대 해시 대조 목록 v0.1 — 출처 지도

목록은 출처 파일에서 파생한다(중복 사본을 만들지 않고 출처가 곧 목록). 서버 회수 파일을 대조할 때
각 출처의 스키마에 맞춰 경로→sha256을 추출해 `sha256sum` 형식으로 만든 뒤 비교한다.

| 출처 파일 | 내용 | 규모 |
|---|---|---|
| `configs/data_model_provenance.json` | 모델 9개(files[].sha256), acquired_assets 16, documents 4, data_families 12 | — |
| `output/implementation-20261010/model-setup/model-manifest.json` | 서버 모델 파일(repo_id·revision·relative_path) | 23파일, 17.7GB |
| `output/implementation-20261010/server-preservation/inventory.json` | working_files 21 + asset_hashes 20 | 41 |
| `output/context-ablation-20261010/preservation-before.json` | 서버 상태 스냅샷 해시 | 1,363파일 |
| `output/recapture-handoff-20261010/preservation-before.json` | 인계 시점 공개 파일 해시 | 40파일 |
| `output/provenance-audit-20261010/preservation-before.json`·`verification.json` | 공개 20·자산 16·장면 PNG 8·evidence-path 37 등 | — |
| `output/document-demo-20261010/verify_server_sources.py` | 서버 스냅샷 19파일(5절 분류 결과) | 19 |
| `output/recapture-handoff-20261010/recapture-loop-handoff.zip` | 전체 파일 SHA | 1 |
| `output/pv2-read-review-20261010/source/experiments/pipeline_v2/results/e1-quick-bundle-checksums.sha256` + `…/runs/e1/run_pv2-e1-quick-val01/checksums.json` | run 번들 해시 | 1+141 |

`scripts/verify/recheck_preservation_copies.py`의 각 모드(`--tar-json`, `--tar-working-files`,
`--zip-sha`, `--tar-internal-json` 등)가 위 출처별 대조 방식을 이미 구현한다. 서버에서 회수한 파일은
로컬 보존 사본(1절)과 바이트 동일한지 먼저 보고, 보존 사본이 없는 항목(판정표 1~5번)은 이 출처들과
대조한다.

## 4. 서버 접속 시 명령 초안

`/workspace/PAC2026`에서 실행한다. 기존 `preserve_server_git.py`의 절차(백업→해시→동기화→검증)와
`backup-summary.json` 스키마를 준용한다.

```bash
cd /workspace/PAC2026
git status --short && git rev-parse HEAD

# 1) 후보 8경로 존재·크기 확인
for p in /workspace/models/contextweld /workspace/data-import/steel-ocr \
         /workspace/pac-handoffs /workspace/pac-backups \
         output/pipeline-v2-20261010 output/context-ablation-20261010 \
         output/explicit-review-20261010 output/isaac-scene-20261010; do
  if [ -e "$p" ]; then du -sb "$p"; else echo "MISSING $p"; fi
done

# 2) 파일 해시 스냅샷(기존 pac-backups 하위에 기록)
mkdir -p /workspace/pac-backups/recheck-20261016
for p in /workspace/models/contextweld /workspace/data-import/steel-ocr \
         /workspace/pac-handoffs /workspace/pac-backups \
         output/pipeline-v2-20261010 output/context-ablation-20261010 \
         output/explicit-review-20261010 output/isaac-scene-20261010; do
  [ -e "$p" ] || continue
  find "$p" -type f -print0 | sort -z | xargs -0 sha256sum > \
    "/workspace/pac-backups/recheck-20261016/$(echo "$p" | tr '/' '_').sha256"
done
```

회수 순서는 2절 판정표 우선순위를 따른다(1~3번 먼저, 모델은 4번). 회수 후 로컬에서
`scripts/verify/recheck_preservation_copies.py`로 재검증하고, 결과를 본 문서에 갱신하며
`docs/sources/DATA_MODEL_PROVENANCE.md`·`configs/data_model_provenance.json`에 추가 기록한다.

## 5. 서버 스냅샷 분류 (verify_server_sources.py 재작성·재실행)

미추적 로컬 도구 `output/document-demo-20261010/verify_server_sources.py`(2026-10-10 작성, 서버
스냅샷 해시 19개)는 경로 재구성 이후 그대로 실행하면 실패했었다. 2026-10-16에 옛 경로→새 경로
매핑 8개를 넣고 분류형으로 재작성해 재실행했다. 산출물: 같은 폴더
`server-sources-recheck-20261016.json`.

- 결과: 19파일 중 **일치 4 / 변경 7 / 이동+변경 8 / 유실 0**.
- 이동 8개(매핑으로 전부 발견): `docs/` 6개(`DEMO_SPEC`·`DOCUMENT_APPLICATION_PLAN`·`MILESTONES`→
  `docs/plan/`, `DOCUMENT_DEMO`·`RUNPOD_INFERENCE`→`docs/runs/`, `OCR_PIPELINE_SPEC`→`docs/spec/`),
  `scripts/` 2개(`run_document_demo.py`→`scripts/run/`, `verify_document_demo.py`→`scripts/verify/`).
- 변경 15개는 모두 진단·처방(P0·P2) 및 문서 재구성의 추적 커밋으로 설명 가능하다. 유실 없음.
- 일치 4개: `configs/document_demo/scenario.json`, `configs/document_demo/target_profile.json`,
  `data/knowledge/lanl-wps-3501-reviewed.json`, `tests/test_mock_delivery.py`.

의미: 로컬 저장소는 서버 스냅샷(2026-10-10)에서 커밋 이력으로 진화했고, "서버에만 존재"하던 것의
정확한 유실 목록은 여전히 서버 접근 후에 확정된다(지시서 배경 그대로). 이 분류가 P1 재대조의
출발점이다.

## 완료 기준과의 관계

- "유실·복구 목록 문서화"의 로컬 선행분 완료: 후보 판정표(2절), 해시 출처 지도(3절), 명령
  초안(4절), 스냅샷 분류(5절)가 준비됐다.
- 남은 것: 서버 접근 재개 후 지시서의 1번(재대조)·2번(우선 회수)·3번(해시 대조 기록) 실행과
  본 문서 갱신. 실제 GPU 재촬영 루프 1회 실행은 같은 접근 재개 이후의 별도 작업이다.
