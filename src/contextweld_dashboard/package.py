"""오프라인 패키지 생성기.

순서: 출력 경로 안전 확인 → 원본 해시 기록 → 원본 묶음 검증(기존 검증기) → 원본 바이트 그대로 복사 →
사본 재검증·원본과 비교 → 화면 모델 생성(사본에서 읽음) → 기존 HTML 조회기 생성(문서·재검토 묶음) →
웹 자산·도구 복사 → MANIFEST/SHA256SUMS → 원본 해시 재확인 → 임시 경로에서 최종 경로로 이동.

전 과정은 ``side_effect_guard`` 안에서 실행한다. 추론·문서 재검색·전달·수정 저장·재검토 실행 함수와 소켓 연결,
하위 프로세스 실행은 호출되는 즉시 실패하며 호출 횟수가 보고서에 남는다.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterator

from . import __version__, integrity
from .adapters import KIND_LABELS, build_model
from .adapters.common import ExportContext
from .bundle_io import BundleReader, TEXT_SUFFIXES, media_type, sha256_file
from .catalog import GROUPS, Source, policy_exclusions
from .model import SCHEMA_INDEX, SCHEMA_RUN, TAB_KEYS, canonical_json, validate_run_model

PACKAGE_SCHEMA = "contextweld-admin-dashboard.package.v1"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WEB_DIR = HERE / "web"
TOOLS_DIR = HERE / "package_tools"
RAW_TEXT_LIMIT = 5 * 1024 * 1024
VOLATILE_FILES = ("EXPORT_INFO.json", "data/export-info.js", "SHA256SUMS")

FORBIDDEN_CALLS = (
    ("contextweld.mock_delivery", "MockReceiver"),
    ("contextweld.mock_delivery", "send_command"),
    ("contextweld.documents", "search_documents"),
    ("contextweld.documents", "build_index"),
    ("contextweld.documents", "mark_context_used"),
    ("contextweld.documents", "write_json_exclusive"),
    ("contextweld.corrections", "record_correction"),
    ("contextweld.corrections", "write_rejection"),
    ("contextweld.review", "run_review"),
    ("contextweld.review", "_deliver"),
    ("contextweld.workflow", "run_document_demo"),
    ("contextweld.recognition", "run_bootstrap"),
    ("contextweld.recognition", "infer_json"),
    ("contextweld.recognition", "PaddleEngine"),
    ("contextweld.recognition", "QwenEngine"),
    ("contextweld.recognition", "write_json"),
)


class ExportError(RuntimeError):
    """패키지를 만들 수 없는 경우(출력 경로 위험, 원본 변경 등)."""


@contextlib.contextmanager
def side_effect_guard() -> Iterator[list[str]]:
    """금지 함수·네트워크·하위 프로세스 호출을 막고 시도를 기록한다."""
    calls: list[str] = []
    restore: list[tuple[Any, str, Any]] = []

    def deny(name: str) -> Any:
        def blocked(*_args: Any, **_kwargs: Any) -> Any:
            calls.append(name)
            raise RuntimeError(f"관리자 대시보드 내보내기에서 금지된 호출: {name}")
        return blocked

    targets: list[tuple[str, Any]] = []
    for module_name, attribute in FORBIDDEN_CALLS:
        module = importlib.import_module(module_name)
        if hasattr(module, attribute):
            targets.append((f"{module_name}.{attribute}", getattr(module, attribute)))
    for module_name, module in list(sys.modules.items()):
        if module is None or not (module_name == "contextweld" or module_name.startswith("contextweld.")
                                  or module_name.startswith("contextweld_dashboard_")):
            continue
        for attribute, value in list(vars(module).items()):
            for label, original in targets:
                if value is original:
                    restore.append((module, attribute, value))
                    setattr(module, attribute, deny(label))
    for owner, attribute in ((socket.socket, "connect"), (socket.socket, "connect_ex"), (socket.socket, "bind"),
                             (socket, "create_connection"), (subprocess, "Popen")):
        restore.append((owner, attribute, getattr(owner, attribute)))
        setattr(owner, attribute, deny(f"{getattr(owner, '__name__', owner)}.{attribute}"))
    try:
        yield calls
    finally:
        for owner, attribute, value in reversed(restore):
            setattr(owner, attribute, value)


def hash_tree(root: Path, subset: tuple[str, ...] | None = None) -> dict[str, str]:
    """원본 보존 확인용 해시 목록(symlink는 대상이 아닌 링크 문자열을 기록)."""
    result: dict[str, str] = {}
    for relative, path in iter_source_files(root, subset):
        result[relative] = "symlink:" + os.readlink(path) if path.is_symlink() else sha256_file(path)
    return result


def iter_source_files(root: Path, subset: tuple[str, ...] | None) -> Iterator[tuple[str, Path]]:
    entries = [""] if subset is None else list(subset)
    for entry in entries:
        start = root / entry if entry else root
        if entry and not entry.endswith("/"):
            if start.is_file() or start.is_symlink():
                yield entry, start
            continue
        if not start.is_dir() or start.is_symlink():
            continue
        for directory, dirnames, filenames in os.walk(start, followlinks=False):
            dirnames.sort()
            base = Path(directory)
            for name in sorted(dirnames):
                if (base / name).is_symlink():
                    yield (base / name).relative_to(root).as_posix(), base / name
            for name in sorted(filenames):
                yield (base / name).relative_to(root).as_posix(), base / name


def copy_source(source: Source, destination: Path) -> dict[str, Any]:
    """원본 바이트 그대로 복사한다. symlink는 따라가지도 복사하지도 않고 기록만 한다."""
    copied: list[str] = []
    skipped: list[dict[str, str]] = []
    destination.mkdir(parents=True, exist_ok=False)
    for relative, path in iter_source_files(source.path, source.copy):
        if path.is_symlink():
            skipped.append({"path": relative, "reason": "symlink (복사하지 않음)"})
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        if sha256_file(target) != hashlib.sha256(data).hexdigest():
            raise ExportError(f"복사본 해시 불일치: {source.key}/{relative}")
        copied.append(relative)
    missing_subset = []
    for entry in source.copy or ():
        if not (source.path / entry.rstrip("/")).exists():
            missing_subset.append(entry)
    return {"copied": copied, "skipped": skipped, "missing_requested": missing_subset}


def js_data(target: str, value: Any) -> str:
    text = canonical_json(value).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ("window.PAC_DASHBOARD_DATA = window.PAC_DASHBOARD_DATA || {runs: {}, raw: {}};\n"
            f"window.PAC_DASHBOARD_DATA.{target} = {text};\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def check_output_path(out_dir: Path, sources: list[Source]) -> None:
    out = out_dir.resolve()
    if out.exists() or out_dir.is_symlink():
        raise ExportError(f"기존 출력은 덮어쓰지 않습니다: {out_dir}")
    staging = out.parent / (out.name + ".partial")
    if staging.exists():
        raise ExportError(f"이전 임시 출력이 남아 있습니다. 확인 후 직접 정리하세요: {staging}")
    for source in sources:
        root = source.path.resolve()
        if out == root or out.is_relative_to(root) or root.is_relative_to(out):
            raise ExportError(f"원본 자료 안이나 원본을 포함하는 경로에는 쓰지 않습니다: {source.display_path}")
    try:
        from contextweld.corrections import enclosing_bundle
    except ImportError:  # pragma: no cover
        enclosing_bundle = None
    if enclosing_bundle is not None:
        probe = out.parent
        while not probe.exists():
            probe = probe.parent
        if enclosing_bundle(probe) is not None:
            raise ExportError("다른 실행 묶음 안에는 패키지를 쓰지 않습니다.")


def build_package(out_dir: Path, sources: list[Source], *, zip_path: Path | None = None,
                  viewer_html: bool = True, export_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """패키지를 만들고 보고서를 돌려준다. 실패하면 임시 출력을 남기고 ``ExportError``를 던진다."""
    out_dir = Path(out_dir)
    keys = [source.key for source in sources]
    if len(keys) != len(set(keys)):
        raise ExportError("자료 key가 중복됩니다.")
    check_output_path(out_dir, sources)
    staging = out_dir.resolve().parent / (out_dir.name + ".partial")
    before = {source.key: hash_tree(source.path, source.copy) for source in sources}
    report: dict[str, Any] = {"package": str(out_dir), "sources": {}, "forbidden_calls": [], "model_problems": {}}
    staging.mkdir(parents=True)
    try:
        _build_guarded(staging, sources, report, viewer_html)
    except RuntimeError as exc:
        if report["forbidden_calls"]:
            raise ExportError(f"금지된 호출이 시도되어 내보내기를 중단했습니다: {report['forbidden_calls']}") from exc
        raise
    if report["forbidden_calls"]:
        raise ExportError(f"금지된 호출이 시도되었습니다: {report['forbidden_calls']}")
    info = {"generated_by": f"contextweld_dashboard {__version__}", "python": sys.version.split()[0],
            "source_repo_head": _git("rev-parse", "HEAD"), "source_repo_dirty": bool(_git("status", "--porcelain")),
            **(export_info or {})}
    _write_text(staging / "EXPORT_INFO.json", json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text(staging / "data" / "export-info.js", js_data("exportInfo", info))
    manifest = _package_manifest(staging, sources)
    _write_text(staging / "MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    _write_sha256sums(staging)
    after = {source.key: hash_tree(source.path, source.copy) for source in sources}
    changed = {key: sorted(set(before[key].items()) ^ set(after[key].items())) for key in before}
    changed = {key: [item[0] for item in value] for key, value in changed.items() if value}
    report["originals_unchanged"] = not changed
    report["original_changes"] = changed
    if changed:
        raise ExportError(f"내보내기 중 원본이 바뀌었습니다: {changed}")
    os.replace(staging, out_dir.resolve())
    if zip_path is not None:
        report["zip"] = write_zip(out_dir, zip_path)
    report["files"] = len(manifest["files"])
    report["manifest_sha256"] = sha256_file(out_dir / "MANIFEST.json")
    return report


def _build_guarded(staging: Path, sources: list[Source], report: dict[str, Any], viewer_html: bool) -> None:
    """금지 호출 감시 안에서 검증·복사·화면 모델·정적 파일을 만든다. 시도된 금지 호출은 report에 남는다."""
    with side_effect_guard() as calls:
        report["forbidden_calls"] = calls
        original_checks: dict[str, dict[str, Any]] = {}
        copy_checks: dict[str, dict[str, Any]] = {}
        copy_logs: dict[str, dict[str, Any]] = {}
        for source in sources:
            if source.group != "reference":
                original_checks[source.key] = integrity.inspect(source.path)
            copy_logs[source.key] = copy_source(source, staging / "bundles" / source.key)
            if source.group != "reference":
                copy_checks[source.key] = integrity.inspect(staging / "bundles" / source.key)
        manifests: dict[str, dict[str, Any] | None] = {}
        manifest_sha: dict[str, str | None] = {}
        for source in sources:
            path = staging / "bundles" / source.key / "manifest.json"
            try:
                manifests[source.key] = json.loads(path.read_text("utf-8")) if path.is_file() else None
                manifest_sha[source.key] = sha256_file(path) if path.is_file() else None
            except (OSError, ValueError):
                manifests[source.key], manifest_sha[source.key] = None, None
        ctx = ExportContext(sources, manifests, manifest_sha)
        index_runs: list[dict[str, Any]] = []
        for source in sources:
            reader = BundleReader(staging / "bundles" / source.key, source.key)
            copy_check = copy_checks.get(source.key, {"state": "partial", "label": "참조 자료 (실행 묶음 검증 대상 아님)",
                                                      "checks": [], "message": None, "report": None,
                                                      "schema": None, "verifier": None})
            model = build_model(source, reader, copy_check, ctx)
            files, raw_entries = _file_entries(reader, source)
            same = (integrity.same_verification(original_checks[source.key], copy_check)
                    if source.key in original_checks else None)
            model_integrity = dict(copy_check)
            model_integrity["original"] = _brief(original_checks.get(source.key))
            model_integrity["copy_matches_original"] = same
            model_integrity["copy_log"] = copy_logs[source.key]
            model_integrity["excluded"] = source.excluded
            run = {"schema": SCHEMA_RUN, "key": source.key, "summary": model["summary"], "integrity": model_integrity,
                   "files": files, "steps": model["steps"], "tabs": model["tabs"],
                   "roots": {source.key: f"bundles/{source.key}"}}
            for extra in model.get("extra_roots", []):
                run["roots"][extra] = f"bundles/{extra}"
            problems = validate_run_model(run)
            if problems:
                report["model_problems"][source.key] = problems
            _write_text(staging / "data" / "runs" / f"{source.key}.js", js_data(f"runs[{json.dumps(source.key)}]", run))
            for raw_id, entry in raw_entries:
                _write_text(staging / "data" / "raw" / source.key / f"{raw_id.split('/')[-1]}.js",
                            js_data(f"raw[{json.dumps(raw_id)}]", entry))
            viewer = None
            if viewer_html and source.kind in ("document_review", "explicit_review") \
                    and copy_check.get("state") == "verified":
                viewer = _existing_viewer(staging / "bundles" / source.key, staging / "viewer" / f"{source.key}.html")
            index_runs.append(_index_entry(source, run, viewer))
            report["sources"][source.key] = {
                "group": source.group, "kind": source.kind, "display_path": source.display_path,
                "original": _brief(original_checks.get(source.key)), "copy": _brief(copy_check),
                "copy_matches_original": same, "copied_files": len(copy_logs[source.key]["copied"]),
                "skipped": copy_logs[source.key]["skipped"], "viewer_html": viewer,
            }
        index = {
            "schema": SCHEMA_INDEX,
            "package": {"title": "ContextWeld 관리자 대시보드", "tool": "contextweld_dashboard", "tool_version": __version__,
                        "tabs": list(TAB_KEYS),
                        "policy": "저장된 기록을 읽기만 합니다. 추론·문서 재검색·카메라 이동·명령 전송·수정 저장·재검토를 실행하지 않습니다."},
            "groups": [{"key": key, "label": label} for key, label in GROUPS.items()],
            "runs": index_runs,
            "exclusions": policy_exclusions(),
            "notices": _global_notices(),
        }
        _write_text(staging / "data" / "index.js", js_data("index", index))
        _copy_static(staging)
    report["forbidden_calls"] = list(calls)


def _brief(check: dict[str, Any] | None) -> dict[str, Any] | None:
    if check is None:
        return None
    return {key: check.get(key) for key in ("state", "label", "schema", "verifier", "message", "report")}


def _file_entries(reader: BundleReader, source: Source) -> tuple[list[dict[str, Any]], list[tuple[str, dict]]]:
    recorded: dict[str, str] = {}
    if reader.exists("checksums.json"):
        try:
            data = reader.json("checksums.json")
            recorded = data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            recorded = {}
    files: list[dict[str, Any]] = []
    raw_entries: list[tuple[str, dict[str, Any]]] = []
    counter = 0
    for item in reader.inventory():
        entry = dict(item)
        expected = recorded.get(item["path"])
        if item.get("symlink"):
            entry["state"] = "symlink"
        elif expected is None:
            entry["state"] = "unrecorded" if item["path"] != "checksums.json" else "self"
        else:
            entry["state"] = "match" if expected == item.get("sha256") else "mismatch"
        entry["recorded_sha256"] = expected
        suffix = os.path.splitext(item["path"])[1].lower()
        if not item.get("symlink") and suffix in TEXT_SUFFIXES and item["size"] <= RAW_TEXT_LIMIT:
            try:
                text = reader.text(item["path"])
            except (UnicodeDecodeError, ValueError):
                text = None
            if text is not None and text.encode("utf-8") == reader.bytes(item["path"]):
                counter += 1
                raw_id = f"{source.key}/{counter:04d}"
                entry["raw_id"] = raw_id
                raw_entries.append((raw_id, {"root": source.key, "path": item["path"], "sha256": item["sha256"],
                                             "recorded_sha256": expected, "media_type": media_type(item["path"]),
                                             "text": text}))
        files.append(entry)
    return files, raw_entries


def _existing_viewer(bundle: Path, output: Path) -> dict[str, Any] | None:
    """기존 단건 HTML 조회기(scripts/export/export_document_review.py)로 같은 사본을 내보낸다(대체·수정 없음)."""
    script = REPO / "scripts" / "export" / "export_document_review.py"
    spec = importlib.util.spec_from_file_location("contextweld_dashboard_existing_viewer", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.export_review(bundle, output)
    return {"path": output.relative_to(output.parents[1]).as_posix(), "bytes": result["bytes"],
            "sha256": sha256_file(output), "schema": result["schema"]}


def _index_entry(source: Source, run: dict[str, Any], viewer: dict[str, Any] | None) -> dict[str, Any]:
    integrity_info = run["integrity"]
    return {
        "key": source.key,
        "group": source.group,
        "kind": source.kind,
        "kind_label": KIND_LABELS.get(source.kind, source.kind),
        "summary": run["summary"],
        "integrity": {"state": integrity_info.get("state"), "label": integrity_info.get("label"),
                      "message": integrity_info.get("message"),
                      "copy_matches_original": integrity_info.get("copy_matches_original")},
        "steps": len(run["steps"]),
        "data_file": f"data/runs/{source.key}.js",
        "bundle_dir": f"bundles/{source.key}",
        "viewer_html": viewer["path"] if viewer else None,
        "tab_availability": {key: run["tabs"][key]["availability"] for key in TAB_KEYS},
    }


def _global_notices() -> list[dict[str, str]]:
    return [
        {"level": "info", "text": "이 화면은 저장된 기록을 읽기만 합니다. 새 추론·문서 재검색·카메라 이동·명령 전송·수정 저장·재검토를 실행하지 않습니다."},
        {"level": "warning", "text": "인식 bootstrap(공개 사진), 문서 검토, 명시적 재검토, Isaac 장면 자료는 서로 다른 자료입니다. 통합 실행의 J01→JOINT-DEMO-01 연결은 시연 도면의 명시 매핑이며 현장 이음 확인이 아닙니다."},
        {"level": "warning", "text": "모의 ACK는 수신·형식 검사 결과이며 용접 완료나 현장 적용 승인이 아닙니다."},
        {"level": "info", "text": "CTX-001 후보 목록 실험은 사용자가 거부한 실험이라 대시보드 성과·KPI로 포함하지 않았습니다."},
    ]


def _copy_static(staging: Path) -> None:
    for name in ("index.html",):
        _copy_file(WEB_DIR / name, staging / name)
    for name in ("app.css", "app.js"):
        _copy_file(WEB_DIR / name, staging / "assets" / name)
    for name in ("robot_input.js", "robot_input.css"):
        _copy_file(REPO / "src/contextweld/dashboard_assets" / name, staging / "assets" / name)
    for name in ("verify_package.py", "serve_package.py"):
        _copy_file(TOOLS_DIR / name, staging / "tools" / name)
    _copy_file(TOOLS_DIR / "README-offline.md", staging / "README-offline.md")


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(source.read_bytes())


def _package_manifest(staging: Path, sources: list[Source]) -> dict[str, Any]:
    files = []
    for path in sorted(staging.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(staging).as_posix()
        if relative in VOLATILE_FILES or relative == "MANIFEST.json":
            continue
        role = relative.split("/", 1)[0] if "/" in relative else "app"
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path), "role": role})
    return {
        "schema": PACKAGE_SCHEMA,
        "volatile_files": list(VOLATILE_FILES),
        "roots": [{"key": source.key, "group": source.group, "kind": source.kind, "source": source.display_path,
                   "package_dir": f"bundles/{source.key}", "copied_subset": list(source.copy) if source.copy else None,
                   "excluded": source.excluded} for source in sources],
        "files": files,
    }


def _write_sha256sums(staging: Path) -> None:
    lines = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            relative = path.relative_to(staging).as_posix()
            if relative != "SHA256SUMS":
                lines.append(f"{sha256_file(path)}  {relative}\n")
    _write_text(staging / "SHA256SUMS", "".join(lines))


def write_zip(package: Path, zip_path: Path) -> dict[str, Any]:
    """결정적 zip(고정 시각·정렬). 기존 파일은 덮어쓰지 않는다."""
    if zip_path.exists():
        raise ExportError(f"기존 zip은 덮어쓰지 않습니다: {zip_path}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(f"{package.name}/{path.relative_to(package).as_posix()}", (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    return {"path": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": sha256_file(zip_path)}


def copy_tree_exact(source: Path, target: Path) -> None:
    """테스트·이동 검증용: 패키지를 다른 위치로 그대로 복사한다."""
    shutil.copytree(source, target, symlinks=True)
