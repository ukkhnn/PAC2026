#!/usr/bin/env python3
"""PV2 실험 전후의 보호 대상(원본·기존 결과·코드·프로세스) 상태를 기록하고 비교한다.

표준 라이브러리만 사용한다. 실행 중인 Isaac 송출이 갱신하는 stream/과 이 실험·병렬 대시보드의
새 경로는 비교에서 제외하고, 제외 목록 자체를 기록한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
PROTECTED_ROOTS = ["data", "configs", "src", "scripts", "tests", "docs", "experiments", "output",
                   "README.md", ".gitignore"]
EXTERNAL_ROOTS = ["/workspace/pac-handoffs"]
# 이 실험의 새 경로와 병렬 대시보드 작업 경로는 보호 비교 대상이 아니다.
EXCLUDED_PREFIXES = ["experiments/pipeline_v2/", "output/pipeline-v2-20261010/",
                     "output/admin-dashboard-20261010/"]
LIVE_PARTS = {"stream"}  # 기존 송출 프로세스가 계속 갱신하는 디렉토리
PROCESS_KEYWORDS = ("isaacsim", "run_isaac", "serve_isaac", "foxglove_bridge", "ros2-daemon")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
    return result.stdout


def excluded(relative: str) -> bool:
    parts = relative.split("/")
    return (any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES)
            or bool(LIVE_PARTS & set(parts[:-1])) or "__pycache__" in parts
            or relative.endswith((".pyc", ".pyo")) or ".pytest_cache" in parts)


def walk(root: Path, label_base: Path | None) -> dict[str, dict]:
    files = {}
    paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink())
    for path in paths:
        relative = str(path.relative_to(label_base)) if label_base else str(path)
        if label_base and excluded(relative):
            continue
        if path.is_symlink():
            files[relative] = {"symlink": os.readlink(path)}
            continue
        stat = path.stat()
        files[relative] = {"bytes": stat.st_size, "sha256": sha256(path)}
    return files


def processes() -> list[dict]:
    rows = []
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            cmd = (pid_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            stat = (pid_dir / "stat").read_text().split()
        except OSError:
            continue
        if any(key in cmd for key in PROCESS_KEYWORDS) and "snapshot.py" not in cmd:
            rows.append({"pid": int(pid_dir.name), "start_ticks": int(stat[21]), "cmdline": cmd[:400]})
    return sorted(rows, key=lambda row: row["pid"])


def model_check(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    checked, mismatches = 0, []
    for model in manifest["models"]:
        for item in model["files"]:
            path = base / model["relative_path"] / item["path"]
            checked += 1
            if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                mismatches.append(str(path))
    return {"manifest": str(manifest_path), "manifest_sha256": sha256(manifest_path),
            "files_checked": checked, "mismatches": mismatches}


def capture(args: argparse.Namespace) -> int:
    snapshot = {
        "schema_version": "pv2-protection-snapshot.v1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repo": str(REPO), "label": args.label,
        "git": {"head": git("rev-parse", "HEAD").strip(), "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
                "status_porcelain": git("status", "--porcelain", "--untracked-files=all").splitlines(),
                "tracked_diff_sha256": hashlib.sha256(git("diff", "--binary").encode()).hexdigest()},
        "excluded_prefixes": EXCLUDED_PREFIXES, "live_dirs_excluded": sorted(LIVE_PARTS),
        "files": {}, "external_files": {}, "processes": processes(),
    }
    for root in PROTECTED_ROOTS:
        path = REPO / root
        if path.exists():
            snapshot["files"].update(walk(path, REPO))
    for root in EXTERNAL_ROOTS:
        path = Path(root)
        if path.exists():
            snapshot["external_files"].update(walk(path, None))
    if args.models:
        snapshot["models"] = model_check(Path(args.models))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": args.out, "files": len(snapshot["files"]),
                      "external_files": len(snapshot["external_files"]),
                      "processes": len(snapshot["processes"]),
                      "model_mismatches": len(snapshot.get("models", {}).get("mismatches", []))}))
    return 0


def compare(args: argparse.Namespace) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    report = {"schema_version": "pv2-protection-compare.v1", "before": args.before, "after": args.after}
    for key in ("files", "external_files"):
        old, new = before[key], after[key]
        report[key] = {"compared": len(old),
                       "changed": sorted(k for k in old if k in new and old[k] != new[k]),
                       "removed": sorted(k for k in old if k not in new),
                       "added": sorted(k for k in new if k not in old)}
    old_proc = {(p["pid"], p["start_ticks"]): p["cmdline"] for p in before["processes"]}
    new_proc = {(p["pid"], p["start_ticks"]): p["cmdline"] for p in after["processes"]}
    report["processes"] = {"before": len(old_proc), "after": len(new_proc),
                           "missing": [{"pid": k[0], "cmdline": v} for k, v in old_proc.items() if k not in new_proc],
                           "new": [{"pid": k[0], "cmdline": v} for k, v in new_proc.items() if k not in old_proc]}
    report["git"] = {"head_before": before["git"]["head"], "head_after": after["git"]["head"],
                     "tracked_diff_unchanged": before["git"]["tracked_diff_sha256"] == after["git"]["tracked_diff_sha256"]}
    if "models" in before and "models" in after:
        report["models"] = {"before_mismatches": before["models"]["mismatches"],
                            "after_mismatches": after["models"]["mismatches"]}
    report["protected_unchanged"] = (not report["files"]["changed"] and not report["files"]["removed"]
                                     and not report["external_files"]["changed"]
                                     and not report["external_files"]["removed"]
                                     and not report["processes"]["missing"])
    text = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["protected_unchanged"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--out", required=True)
    cap.add_argument("--label", default="")
    cap.add_argument("--models", help="model-manifest.json path; verifies every pinned model file hash")
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    cmp_.add_argument("--out")
    args = parser.parse_args(argv)
    return capture(args) if args.command == "capture" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
