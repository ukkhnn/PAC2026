"""묶음 검증. 스키마별 기존 검증기를 그대로 호출하고, 실패해도 무엇이 빠졌는지 보이도록 파일 목록을 따로 대조한다.

* ``bootstrap-bundle.v1`` → ``scripts/verify/verify_run_bundle.py`` 의 ``inspect_bundle`` (인식 bootstrap)
* ``document-demo-bundle.v1`` → ``contextweld.workflow.inspect_document_bundle``
* ``review-bundle.v1`` → ``contextweld.review.inspect_review_bundle``
* Isaac 장면 자료 → 전용 검증기 없음. manifest에 기록된 SHA-256만 대조하고 ``partial``로 표시한다.

검증기는 모두 읽기 전용이며 실패 시 ``ValueError`` 등 예외를 던진다. 이 모듈은 그 예외 문구를 그대로 보존한다.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable

from contextweld.recognition import safe_path

from .bundle_io import sha256_file

REPO = Path(__file__).resolve().parents[2]
SCENE_SCHEMAS = ("isaac-shipyard-capture.v1", "isaac-scene-capture.v1")
EXPECTED_ERRORS = (ValueError, KeyError, TypeError, OSError, IndexError, AttributeError, json.JSONDecodeError)

STATE_LABELS = {
    "verified": "묶음 검증 통과",
    "failed": "묶음 검증 실패",
    "partial": "부분 검증 (전용 검증기 없음)",
    "unverifiable": "검증 불가",
}


def _bootstrap_inspector() -> Callable[[Path], dict[str, Any]]:
    script = REPO / "scripts" / "verify" / "verify_run_bundle.py"
    spec = importlib.util.spec_from_file_location("contextweld_dashboard_verify_run_bundle", script)
    if spec is None or spec.loader is None:  # pragma: no cover - 저장소 구조가 깨진 경우
        raise RuntimeError("scripts/verify/verify_run_bundle.py를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect_bundle


def _document_inspector() -> Callable[[Path], dict[str, Any]]:
    from contextweld.workflow import inspect_document_bundle
    return inspect_document_bundle


def _review_inspector() -> Callable[[Path], dict[str, Any]]:
    from contextweld.review import inspect_review_bundle
    return inspect_review_bundle


def _recapture_inspector() -> Callable[[Path], dict[str, Any]]:
    from contextweld.recapture_loop import verify_recapture_bundle
    return verify_recapture_bundle


def _weld_inspector() -> Callable[[Path], dict[str, Any]]:
    from contextweld.weld_pipeline import verify_pipeline
    return verify_pipeline


VERIFIERS: dict[str, tuple[str, Callable[[], Callable[[Path], dict[str, Any]]]]] = {
    "weld-pipeline-bundle.v1": ("contextweld.weld_pipeline.verify_pipeline", _weld_inspector),
    "bootstrap-bundle.v1": ("scripts/verify/verify_run_bundle.py:inspect_bundle", _bootstrap_inspector),
    "document-demo-bundle.v1": ("contextweld.workflow.inspect_document_bundle", _document_inspector),
    "review-bundle.v1": ("contextweld.review.inspect_review_bundle", _review_inspector),
    "recapture-bundle.v1": ("contextweld.recapture_loop.verify_recapture_bundle", _recapture_inspector),
}


def _check(name: str, ok: bool | None, detail: str, items: list[str] | None = None) -> dict[str, Any]:
    state = "pass" if ok else ("fail" if ok is False else "not_applicable")
    entry: dict[str, Any] = {"name": name, "state": state, "detail": detail}
    if items:
        entry["items"] = items[:200]
        entry["item_count"] = len(items)
    return entry


def scan_tree(root: Path) -> dict[str, Any]:
    """symlink·파일 목록·해시를 직접 모은다(따라가지 않음)."""
    files: dict[str, str] = {}
    symlinks: list[str] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in list(dirnames):
            if (base / name).is_symlink():
                symlinks.append((base / name).relative_to(root).as_posix())
        for name in filenames:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            else:
                files[relative] = sha256_file(path)
    return {"files": files, "symlinks": sorted(symlinks)}


def _inventory_checks(root: Path, manifest: dict[str, Any] | None) -> tuple[list[dict[str, Any]], bool]:
    """checksums.json·manifest.files·실제 파일을 대조한다. 두 번째 값은 문제 여부."""
    checks: list[dict[str, Any]] = []
    problem = False
    tree = scan_tree(root)
    checks.append(_check("symlink 없음", not tree["symlinks"], "묶음 안 symlink는 허용하지 않습니다.", tree["symlinks"]))
    problem |= bool(tree["symlinks"])
    checksum_path = root / "checksums.json"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        checks.append(_check("checksums.json 존재", False, "해시 목록이 없어 파일 무결성을 확인할 수 없습니다."))
        return checks, True
    try:
        checksums = json.loads(checksum_path.read_text("utf-8"))
        if not isinstance(checksums, dict):
            raise ValueError("checksums.json은 객체여야 합니다.")
    except EXPECTED_ERRORS as exc:
        checks.append(_check("checksums.json 형식", False, f"읽기 실패: {exc}"))
        return checks, True
    escapes: list[str] = []
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, expected in sorted(checksums.items()):
        try:
            target = safe_path(root, relative)
        except ValueError as exc:
            escapes.append(f"{relative} ({exc})")
            continue
        if not target.is_file() or target.is_symlink():
            missing.append(relative)
        elif tree["files"].get(relative) != expected:
            mismatched.append(relative)
    unlisted = sorted(set(tree["files"]) - set(checksums) - {"checksums.json"})
    checks.append(_check("경로 이탈 없음", not escapes, "해시 목록의 경로가 묶음 밖을 가리키지 않아야 합니다.", escapes))
    checks.append(_check("누락 파일 없음", not missing, "해시 목록에 있는 파일이 모두 있어야 합니다.", missing))
    checks.append(_check("해시 일치", not mismatched, "파일 SHA-256이 checksums.json과 같아야 합니다.", mismatched))
    checks.append(_check("목록 밖 파일 없음", not unlisted, "해시 목록에 없는 파일이 없어야 합니다.", unlisted))
    problem |= bool(escapes or missing or mismatched or unlisted)
    if manifest is not None and isinstance(manifest.get("files"), list):
        listed = set(manifest["files"])
        diff = sorted(listed.symmetric_difference(set(checksums)))
        checks.append(_check("manifest.files와 해시 목록 일치", not diff, "두 목록이 같아야 합니다.", diff))
        problem |= bool(diff)
    return checks, problem


def _scene_checks(root: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """장면 manifest에 기록된 해시만 대조한다. 해시가 없는 파일은 '미기록'으로 센다."""
    checks: list[dict[str, Any]] = []
    recorded: list[tuple[str, str, str]] = []
    frames = manifest.get("frames") if isinstance(manifest.get("frames"), dict) else {}
    for view in sorted(frames):
        record = frames[view]
        if not isinstance(record, dict):
            continue
        for camera in ("wrist", "overview"):
            path = record.get(f"{camera}_saved_image")
            digest = record.get(f"{camera}_image_sha256")
            if isinstance(path, str) and isinstance(digest, str):
                recorded.append((path, digest, f"manifest.frames.{view}.{camera}_image_sha256"))
    if isinstance(manifest.get("config_sha256"), str):
        recorded.append(("config.json", manifest["config_sha256"], "manifest.config_sha256"))
    matched, failed = 0, []
    for relative, expected, where in recorded:
        try:
            target = safe_path(root, relative)
        except ValueError as exc:
            failed.append(f"{relative}: 경로 오류 ({exc})")
            continue
        if not target.is_file() or target.is_symlink():
            failed.append(f"{relative}: 파일 없음 ({where})")
        elif sha256_file(target) != expected:
            failed.append(f"{relative}: 해시 불일치 ({where})")
        else:
            matched += 1
    checks.append(_check("기록된 해시 대조", not failed if recorded else None,
                         f"manifest에 SHA-256이 기록된 파일 {len(recorded)}개 중 {matched}개 일치", failed))
    tree = scan_tree(root)
    checks.append(_check("symlink 없음", not tree["symlinks"], "장면 자료 사본 안 symlink는 허용하지 않습니다.",
                         tree["symlinks"]))
    recorded_paths = {item[0] for item in recorded}
    unrecorded = sorted(path for path in tree["files"] if path not in recorded_paths)
    checks.append(_check("해시 미기록 파일", None,
                         "원본 manifest에 해시가 없어 생성 시점 무결성을 확인할 수 없는 파일입니다. "
                         "패키지 MANIFEST의 내보내기 시점 해시만 있습니다.", unrecorded))
    counts = {"recorded": len(recorded), "matched": matched, "failed": len(failed) + len(tree["symlinks"]),
              "unrecorded": len(unrecorded)}
    return checks, counts


def inspect(root: Path) -> dict[str, Any]:
    """묶음 하나를 검증한다. 예외를 던지지 않고 결과 객체를 돌려준다.

    오류 문구 안의 서버 절대경로는 ``<묶음>``으로 바꿔 패키지에 서버 경로가 남지 않게 한다.
    """
    root = Path(root)
    result = _inspect(root)
    prefixes = sorted({str(root), str(root.resolve()), os.path.abspath(root)}, key=len, reverse=True)
    def clean(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        for prefix in prefixes:
            text = text.replace(prefix, "<묶음>")
        return text
    result["message"] = clean(result["message"])
    for check in result["checks"]:
        check["detail"] = clean(check["detail"])
        if "items" in check:
            check["items"] = [clean(item) for item in check["items"]]
    return result


def _inspect(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"state": "failed", "label": STATE_LABELS["failed"], "schema": None, "verifier": None,
                              "report": None, "message": None, "checks": []}
    manifest: dict[str, Any] | None = None
    manifest_path = root / "manifest.json"
    if not root.is_dir() or root.is_symlink():
        result["message"] = "묶음 디렉터리가 없거나 symlink입니다."
        return result
    if not manifest_path.is_file() or manifest_path.is_symlink():
        result["message"] = "manifest.json이 없습니다."
        result["checks"].append(_check("manifest.json 존재", False, result["message"]))
        return result
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest.json은 객체여야 합니다.")
    except EXPECTED_ERRORS as exc:
        result["message"] = f"manifest.json 읽기 실패: {exc}"
        result["checks"].append(_check("manifest.json 형식", False, result["message"]))
        return result
    schema = manifest.get("schema_version")
    result["schema"] = schema
    if schema in SCENE_SCHEMAS:
        checks, counts = _scene_checks(root, manifest)
        result["checks"] = checks
        result["counts"] = counts
        result["verifier"] = "contextweld_dashboard.integrity:_scene_checks (manifest 기록 해시 대조)"
        if counts["failed"]:
            result["message"] = "장면 자료의 기록 해시와 실제 파일이 다릅니다."
            return result
        result["state"] = "partial"
        result["label"] = (f"부분 검증 · 기록 해시 {counts['matched']}/{counts['recorded']} 일치 · "
                           f"해시 미기록 {counts['unrecorded']}개 (장면 자료 전용 검증기 없음)")
        return result
    inventory, inventory_problem = _inventory_checks(root, manifest)
    result["checks"] = inventory
    if schema not in VERIFIERS:
        result["message"] = f"지원하지 않는 묶음 스키마: {schema}"
        result["checks"].insert(0, _check("지원 스키마", False, result["message"]))
        return result
    name, loader = VERIFIERS[schema]
    result["verifier"] = name
    # 통합 v1은 export_status 대신 run_outcome·송수신·ACK를 전용 검증기가 검사한다.
    if schema != "weld-pipeline-bundle.v1" and manifest.get("export_status") != "complete":
        result["checks"].insert(0, _check("export_status=complete", False,
                                          f"export_status={manifest.get('export_status')!r}: 완료 묶음이 아닙니다."))
    before = _checksum_digest(root)
    try:
        report = loader()(root)
    except EXPECTED_ERRORS as exc:
        result["message"] = f"{type(exc).__name__}: {exc}"
        result["checks"].insert(0, _check("스키마별 검증기", False, result["message"]))
        return result
    if _checksum_digest(root) != before:
        result["message"] = "검증 도중 원본 묶음의 checksums.json이 바뀌었습니다."
        return result
    result["report"] = report
    result["checks"].insert(0, _check("스키마별 검증기", True, f"{name} 통과"))
    if inventory_problem:
        result["message"] = "검증기는 통과했지만 파일 목록 대조에서 문제가 발견됐습니다."
        return result
    result["state"] = "verified"
    result["label"] = f"{STATE_LABELS['verified']} · {name}"
    return result


def _checksum_digest(root: Path) -> str | None:
    path = root / "checksums.json"
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_verification(original: dict[str, Any], copy: dict[str, Any]) -> bool:
    """원본과 패키지 사본의 검증 결과가 같은지(상태·스키마·검증기 보고서) 비교한다."""
    return (original.get("state") == copy.get("state") and original.get("schema") == copy.get("schema")
            and original.get("report") == copy.get("report") and original.get("message") == copy.get("message"))
