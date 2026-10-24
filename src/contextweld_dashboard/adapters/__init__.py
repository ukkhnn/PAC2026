"""자료 종류별 읽기 어댑터 등록부. 종류 이름은 ``catalog.SCHEMA_KINDS``와 ``DEFAULT_REFERENCES``를 따른다."""
from __future__ import annotations

import importlib
from typing import Any, Callable

from ..bundle_io import BundleReader
from ..catalog import Source
from .common import ExportContext, diagnostic_model

Adapter = Callable[[Source, BundleReader, dict, ExportContext], dict]

KIND_LABELS = {
    "weld_pipeline": "통합 전달 실행",
    "recognition": "인식 bootstrap 실행",
    "document_review": "문서 검토 실행",
    "explicit_review": "명시적 재검토 실행",
    "recapture": "재촬영 루프 실행",
    "scene": "Isaac 장면 자료",
    "document_rag": "문서 검색 색인",
    "correction_store": "수정 저장소",
    "review_cli_log": "재검토 CLI 작업 기록",
    "demo_config": "문서 시연 설정 (fixture)",
    "knowledge": "WPS 전사 자료",
    "invalid": "알 수 없는 묶음",
}


def get_adapter(kind: str) -> Adapter | None:
    module = {"weld_pipeline": "weld_pipeline", "recognition": "recognition", "document_review": "document_review", "explicit_review": "explicit_review",
              "recapture": "recapture", "scene": "scene", "document_rag": "references",
              "correction_store": "references", "review_cli_log": "references", "demo_config": "references",
              "knowledge": "references"}.get(kind)
    if module is None:
        return None
    try:
        loaded = importlib.import_module(f"{__name__}.{module}")
    except ImportError:
        return None
    return getattr(loaded, "build", None)


def build_model(source: Source, reader: BundleReader, integrity: dict[str, Any], ctx: ExportContext) -> dict:
    """어댑터를 실행한다. 검증 실패 묶음과 어댑터 예외는 진단 화면으로 바꾼다(정상 재생 없음)."""
    label = KIND_LABELS.get(source.kind, source.kind)
    is_reference = source.group == "reference"
    if not is_reference and integrity.get("state") == "failed":
        return diagnostic_model(source, reader, integrity, kind_label=label)
    adapter = get_adapter(source.kind)
    if adapter is None:
        return diagnostic_model(source, reader, integrity, kind_label=label,
                                error=f"지원하지 않는 자료 종류: {source.kind}")
    try:
        return adapter(source, reader, integrity, ctx)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OSError) as exc:
        return diagnostic_model(source, reader, integrity, kind_label=label, error=f"{type(exc).__name__}: {exc}")
