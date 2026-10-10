"""관리자 대시보드 CLI.

    python -m contextweld_dashboard export --output <새 폴더> [--zip <새 zip>] [--add <묶음 폴더> ...]
    python -m contextweld_dashboard verify <패키지 폴더>

``export``는 원본 묶음을 읽기만 하고 새 폴더에만 쓴다(기존 출력 덮어쓰기 금지). ``verify``는 패키지 파일 해시와
함께, 패키지 안 실행 묶음 사본을 저장소의 스키마별 기존 검증기로 다시 검증한다(옮긴 사본의 동일성 확인).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from . import integrity  # noqa: E402
from .catalog import added_source, default_sources  # noqa: E402
from .package import REPO, ExportError, build_package  # noqa: E402
from .package_tools.verify_package import verify as verify_files  # noqa: E402


def export(args: argparse.Namespace) -> int:
    sources = default_sources(REPO)
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {source.key for source in sources}
        if unknown:
            print(f"알 수 없는 key: {sorted(unknown)}", file=sys.stderr)
            return 2
        sources = [source for source in sources if source.key in wanted]
    taken = {source.key for source in sources}
    for item in args.add or []:
        path = Path(item)
        if not path.is_dir():
            print(f"묶음 폴더가 아닙니다: {item}", file=sys.stderr)
            return 2
        source = added_source(path.resolve(), taken, display=item)
        taken.add(source.key)
        sources.append(source)
    missing = [source.display_path for source in sources if not source.path.exists()]
    if missing:
        print("원본 자료가 없습니다(경로 확인): " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        report = build_package(Path(args.output), sources, zip_path=Path(args.zip) if args.zip else None,
                               viewer_html=not args.no_viewer_html,
                               export_info={"command": "export_admin_dashboard"})
    except ExportError as exc:
        print(f"내보내기 실패: {exc}", file=sys.stderr)
        return 1
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    summary = {key: {"original": (value["original"] or {}).get("state"), "copy": (value["copy"] or {}).get("state"),
                     "copy_matches_original": value["copy_matches_original"], "files": value["copied_files"]}
               for key, value in report["sources"].items()}
    print(json.dumps({"package": report["package"], "files": report["files"], "zip": report.get("zip"),
                      "originals_unchanged": report["originals_unchanged"], "forbidden_calls": report["forbidden_calls"],
                      "model_problems": report["model_problems"], "sources": summary},
                     ensure_ascii=False, indent=2))
    return 0 if not report["model_problems"] else 1


def verify(args: argparse.Namespace) -> int:
    package = Path(args.package)
    files = verify_files(package)
    manifest = json.loads((package / "MANIFEST.json").read_text("utf-8")) if (package / "MANIFEST.json").is_file() else {}
    bundles = []
    for root in manifest.get("roots", []):
        if root.get("group") == "reference":
            continue
        result = integrity.inspect(package / root["package_dir"])
        bundles.append({"key": root["key"], "state": result["state"], "verifier": result["verifier"],
                        "message": result["message"]})
    print(json.dumps({"files": files, "bundles": bundles}, ensure_ascii=False, indent=2))
    expected_failures = {"rec-batch-01-incomplete"}
    ok = files["ok"] and all(item["state"] in ("verified", "partial") or item["key"] in expected_failures
                             for item in bundles)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contextweld_dashboard", description="ContextWeld 관리자 대시보드 오프라인 패키지")
    sub = parser.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export", help="저장된 묶음으로 오프라인 패키지 생성")
    p_export.add_argument("--output", required=True, help="새 패키지 폴더(없어야 함)")
    p_export.add_argument("--zip", help="함께 만들 zip 경로(없어야 함)")
    p_export.add_argument("--add", action="append", help="추가할 새 실행 묶음 폴더(반복 가능)")
    p_export.add_argument("--only", help="기본 자료 중 일부 key만 포함(쉼표 구분)")
    p_export.add_argument("--no-viewer-html", action="store_true", help="기존 단건 HTML 조회기 사본 생략")
    p_export.add_argument("--report", help="상세 보고서 JSON 경로(없어야 함)")
    p_export.set_defaults(func=export)
    p_verify = sub.add_parser("verify", help="패키지 파일·묶음 사본 재검증")
    p_verify.add_argument("package")
    p_verify.set_defaults(func=verify)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
