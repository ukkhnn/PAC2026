"""관리자 대시보드 테스트 공통 도우미 (unittest 자동 수집 대상 아님).

핵심 검사 ``assert_linkage``: 화면 모델의 모든 저장 값 ``{"v", "src"}``를 원본 파일에서 다시 읽어 같은지 대조한다.
대시보드 계산 값(``src=None``)은 ``origin=dashboard``와 설명이 있어야 한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from contextweld_dashboard import integrity  # noqa: E402
from contextweld_dashboard.adapters import build_model  # noqa: E402
from contextweld_dashboard.adapters.common import ExportContext  # noqa: E402
from contextweld_dashboard.bundle_io import BundleReader, sha256_file  # noqa: E402
from contextweld_dashboard.catalog import Source, default_sources  # noqa: E402
from contextweld_dashboard.model import (ABSENT, SCHEMA_RUN, iter_values, resolve_pointer,  # noqa: E402
                                         split_ref, validate_run_model)


def real_sources() -> dict[str, Source]:
    return {source.key: source for source in default_sources(ROOT)}


def available(key: str) -> bool:
    source = real_sources().get(key)
    return source is not None and source.path.exists()


def context_for(sources: list[Source]) -> ExportContext:
    manifests: dict[str, Any] = {}
    digests: dict[str, Any] = {}
    for source in sources:
        path = source.path / "manifest.json"
        try:
            manifests[source.key] = json.loads(path.read_text("utf-8")) if path.is_file() else None
            digests[source.key] = sha256_file(path) if path.is_file() else None
        except (OSError, ValueError):
            manifests[source.key], digests[source.key] = None, None
    return ExportContext(sources, manifests, digests)


def build_real(key: str, *, all_sources: bool = True) -> tuple[dict[str, Any], dict[str, Path]]:
    """원본 묶음(읽기 전용)에서 화면 모델을 만든다. 패키지 생성기와 같은 순서·형식을 쓴다."""
    sources = real_sources()
    source = sources[key]
    ctx = context_for(list(sources.values()) if all_sources else [source])
    check = integrity.inspect(source.path) if source.group != "reference" else {
        "state": "partial", "label": "참조 자료", "checks": [], "message": None, "report": None, "schema": None,
        "verifier": None}
    reader = BundleReader(source.path, key)
    model = build_model(source, reader, check, ctx)
    run = {"schema": SCHEMA_RUN, "key": key, "summary": model["summary"], "integrity": check, "files": [],
           "steps": model["steps"], "tabs": model["tabs"], "roots": {key: str(source.path)}}
    roots = {key: source.path}
    for extra in model.get("extra_roots", []):
        roots[extra] = sources[extra].path
        run["roots"][extra] = str(sources[extra].path)
    return run, roots


def load_document(path: Path) -> Any:
    text = path.read_text("utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def resolve_src(roots: dict[str, Path], src: str) -> Any:
    root_key, relative, ptr = split_ref(src)
    if root_key not in roots:
        raise AssertionError(f"알 수 없는 출처 루트: {src}")
    path = roots[root_key] / relative
    if not path.is_file():
        return ABSENT
    return resolve_pointer(load_document(path), ptr)


def assert_linkage(test: Any, run: dict[str, Any], roots: dict[str, Path]) -> int:
    """모든 저장 값이 원본과 같은지 대조하고, 대조한 개수를 돌려준다."""
    checked = 0
    cache: dict[Path, Any] = {}
    for where, value in iter_values(run):
        src = value["src"]
        if src is None:
            test.assertEqual(value.get("o"), "dashboard", f"{where}: src 없는 값은 dashboard 출처여야 함")
            test.assertTrue(value.get("n"), f"{where}: 대시보드 계산 값 설명 없음")
            continue
        root_key, relative, ptr = split_ref(src)
        test.assertIn(root_key, roots, f"{where}: 알 수 없는 루트 {root_key}")
        path = roots[root_key] / relative
        if value.get("absent"):
            if path.is_file():
                if path not in cache:
                    cache[path] = load_document(path) if path.suffix in (".json", ".jsonl") else None
                if cache[path] is not None:
                    test.assertIs(resolve_pointer(cache[path], ptr), ABSENT, f"{where}: absent 표시인데 원본에 값이 있음 {src}")
            checked += 1
            continue
        test.assertTrue(path.is_file(), f"{where}: 원본 파일 없음 {src}")
        if path.suffix not in (".json", ".jsonl"):
            if ptr == "":
                test.assertEqual(value["v"], path.read_text("utf-8"), f"{where}: 원문 텍스트 불일치 {src}")
            checked += 1
            continue
        if path not in cache:
            cache[path] = load_document(path)
        actual = resolve_pointer(cache[path], ptr)
        test.assertIsNot(actual, ABSENT, f"{where}: 원본에 없는 위치 {src}")
        test.assertEqual(value["v"], actual, f"{where}: 원본 값과 다름 {src}")
        checked += 1
    return checked


def assert_valid(test: Any, run: dict[str, Any]) -> None:
    problems = validate_run_model(run)
    test.assertEqual(problems, [], "화면 모델 형식 문제")


def all_text(node: Any) -> str:
    """화면 모델 안 사람에게 보이는 문자열 전체(금지 문구 검사용)."""
    parts: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            for key, child in item.items():
                if key in ("src", "path", "meta_src", "sha256"):
                    continue
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(node)
    return "\n".join(parts)


def blocks_of(run: dict[str, Any], tab: str) -> list[dict[str, Any]]:
    """탭의 블록(그룹 안 블록 포함)을 평탄하게 돌려준다."""
    found: list[dict[str, Any]] = []

    def walk(blocks: list[dict[str, Any]]) -> None:
        for blk in blocks:
            found.append(blk)
            if blk.get("type") == "group":
                for item in blk.get("items", []):
                    walk(item.get("blocks", []))
    walk(run["tabs"][tab]["blocks"])
    return found


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for directory, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = "symlink" if path.is_symlink() else sha256_file(path)
    return result
