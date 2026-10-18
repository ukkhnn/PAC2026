"""내보낼 원본 자료 목록. 기본값은 인계 문서 4절의 실제 자료이며, 새 묶음은 ``--add``로 더한다.

종류(kind)는 원본 manifest의 ``schema_version``으로 정한다. 같은 종류의 완료 실행으로 합치지 않도록
인식 bootstrap·문서 검토·명시적 재검토·장면 자료·참조 자료를 서로 다른 그룹으로 둔다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GROUPS = {
    "recognition": "인식 bootstrap (공개 사진)",
    "document": "문서 검토 실행",
    "review": "명시적 재검토 실행",
    "recapture": "재촬영 루프 실행",
    "scene": "Isaac 장면 자료 (예약 A/B 촬영)",
    "reference": "참조 자료 (실행 아님)",
}
SCHEMA_KINDS = {
    "bootstrap-bundle.v1": ("recognition", "recognition"),
    "document-demo-bundle.v1": ("document", "document_review"),
    "review-bundle.v1": ("review", "explicit_review"),
    "recapture-bundle.v1": ("recapture", "recapture"),
    "isaac-shipyard-capture.v1": ("scene", "scene"),
    "isaac-scene-capture.v1": ("scene", "scene"),
}
# 장면 자료는 정적 증거만 복사한다. stream/은 실행 중 프로세스가 계속 덮어쓰므로 고정 증거가 아니다.
SCENE_COPY = ("manifest.json", "config.json", "prediction.json", "frames/")
SCENE_EXCLUDED = (
    ("stream/", "실행 중 프로세스가 계속 덮어쓰는 최신 프레임(고정 증거 아님)"),
    ("assets/", "장면 설계용 텍스처 자산(화면 재생에 필요 없음, manifest에 해시만 기록)"),
    ("source/", "장면 실행 스크립트 사본(화면 재생에 필요 없음, manifest에 해시만 기록)"),
    ("scene.usda", "3D 장면 파일(로컬 3D 재렌더링은 요구 범위 아님)"),
)
EXCLUDED_BY_POLICY = (
    ("output/context-ablation-20261010", "CTX-001 후보 목록 실험: 사용자가 거부했으므로 성능 KPI·대표 성과로 쓰지 않음"),
    ("experiments/context_ablation", "CTX-001 실험 코드: 대시보드 범위 아님"),
)


@dataclass
class Source:
    key: str
    path: Path
    display_path: str
    group: str
    kind: str
    copy: tuple[str, ...] | None = None
    excluded: list[dict[str, str]] = field(default_factory=list)
    note: str | None = None


DEFAULT_SOURCES: tuple[tuple[str, str, str | None], ...] = (
    ("rec-batch-02", "output/recognition/run_steel-batch-20261010-02", None),
    ("rec-smoke-01", "output/recognition/run_steel-smoke-20261010-01", "1장짜리 초기 smoke 실행"),
    ("rec-batch-01-incomplete", "output/recognition/run_steel-batch-20261010-01.incomplete",
     "실제 중단·불완전 묶음(검증 실패 표시 확인용)"),
    ("doc-normal", "output/document-demo-20261010/server/run_document-normal-server-01", None),
    ("doc-missing", "output/document-demo-20261010/server/run_document-missing-server-01", None),
    ("doc-conflict", "output/document-demo-20261010/server/run_document-conflict-server-01", None),
    ("doc-revision-mismatch", "output/document-demo-20261010/server/run_document-revision-mismatch-server-01", None),
    ("doc-observation-conflict", "output/document-demo-20261010/server/run_document-observation-conflict-server-01", None),
    ("review-voltage-01", "output/explicit-review-20261010/run_review-20261010-voltage-01", None),
    ("review-voltage-deliver-01", "output/explicit-review-20261010/run_review-20261010-voltage-deliver-01", None),
    ("review-frame005-01", "output/explicit-review-20261010/run_review-20261010-frame005-01", None),
    ("review-receiver-down-01", "output/explicit-review-20261010/run_review-20261010-voltage-receiver-down-01", None),
    ("scene-shipyard-live-03", "output/isaac-shipyard-20261010/live-03", "사용자가 만족한 새 조선소 장면"),
    ("scene-night-live-01", "output/isaac-scene-20261010/live-01", "보존할 기존 야간 작업대 장면"),
)
# 참조 자료: (key, 경로, kind, 복사할 하위 항목 또는 None=전체)
DEFAULT_REFERENCES: tuple[tuple[str, str, str, tuple[str, ...] | None], ...] = (
    ("ref-document-rag", "output/document-rag/server-v1", "document_rag", None),
    ("ref-correction-store", "output/explicit-review-20261010/correction-store", "correction_store", None),
    ("ref-review-cli-log", "output/explicit-review-20261010", "review_cli_log",
     ("requests/", "rejected-requests/", "logs/", "results-summary.json", "steps-summary.json",
      "input-hashes-comparison.json")),
    ("ref-demo-config", "configs/document_demo", "demo_config", None),
    ("ref-knowledge", "data/knowledge", "knowledge", ("lanl-wps-3501-reviewed.json",)),
)

KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def classify(path: Path) -> tuple[str, str] | None:
    """manifest.json의 schema_version으로 (그룹, 어댑터 종류)를 정한다. 모르면 None."""
    manifest = path / "manifest.json"
    try:
        schema = json.loads(manifest.read_text("utf-8")).get("schema_version")
    except (OSError, ValueError, AttributeError):
        return None
    return SCHEMA_KINDS.get(schema)


def key_for(path: Path, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", path.name.lower().replace("run_", "")).strip("-")[:56] or "bundle"
    key = f"added-{base}"[:64]
    index = 2
    while key in taken:
        key = f"added-{base}-{index}"[:64]
        index += 1
    return key


def default_sources(repo: Path) -> list[Source]:
    sources: list[Source] = []
    for key, relative, note in DEFAULT_SOURCES:
        path = repo / relative
        group, kind = classify(path) or (_group_from_key(key), "invalid")
        source = Source(key, path, relative, group, kind, note=note)
        if group == "scene":
            source.copy = SCENE_COPY
            source.excluded = [{"item": item, "reason": reason} for item, reason in SCENE_EXCLUDED]
        sources.append(source)
    for key, relative, kind, subset in DEFAULT_REFERENCES:
        sources.append(Source(key, repo / relative, relative, "reference", kind, copy=subset))
    return sources


def added_source(path: Path, taken: set[str], display: str | None = None) -> Source:
    """사용자가 지정한 새 묶음. 스키마를 모르면 'invalid'로 남겨 오류 화면으로 보여 준다."""
    group, kind = classify(path) or ("recognition", "invalid")
    source = Source(key_for(path, taken), path, display or path.name, group, kind)
    if group == "scene":
        source.copy = SCENE_COPY
        source.excluded = [{"item": item, "reason": reason} for item, reason in SCENE_EXCLUDED]
    return source


def _group_from_key(key: str) -> str:
    return {"rec": "recognition", "doc": "document", "review": "review", "scene": "scene"}.get(key.split("-")[0],
                                                                                              "recognition")


def policy_exclusions() -> list[dict[str, Any]]:
    return [{"item": path, "reason": reason} for path, reason in EXCLUDED_BY_POLICY]
