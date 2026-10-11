#!/usr/bin/env python3
"""기존 관리자 패키지에 작업조건 자동 조회와 현대·두산 변환 토글을 추가한다."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from contextweld.robot_input import build_work_order_input_previews


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_assignment(path: Path) -> dict:
    """앱 스크립트 실행 없이 마지막 JSON 대입값만 읽는다."""
    text = path.read_text(encoding="utf-8")
    start = text.rfind(" = {")
    if start < 0:
        raise ValueError(f"JSON 대입 파일이 아님: {path.name}")
    return json.loads(text[start + 3:].strip().removesuffix(";"))


def write_assignment(path: Path, key: str, value: dict) -> None:
    preamble = "window.PAC_DASHBOARD_DATA = window.PAC_DASHBOARD_DATA || {runs: {}, raw: {}};\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(preamble + "window.PAC_DASHBOARD_DATA." + key + " = " + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(package: Path, run_key: str, wps_path: Path, profile_path: Path, *,
            doosan_profile_path: Path, work_orders_path: Path, recipes_path: Path, order_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", run_key):
        raise ValueError("잘못된 실행 키")
    run_file = package / "data/runs" / f"{run_key}.js"
    run = read_assignment(run_file)
    if run["summary"]["run_kind"]["v"] != "presentation_scenario":
        raise ValueError("저장된 실제 실행은 수정하지 않는다. presentation_scenario를 선택한다.")
    preview = build_work_order_input_previews(read_json(wps_path), read_json(work_orders_path), read_json(recipes_path),
                                             {"hyundai": read_json(profile_path), "doosan": read_json(doosan_profile_path)}, order_id=order_id)
    if preview["status"] != "preview_ready":
        raise ValueError("초기 선택값 변환 실패: " + json.dumps(preview, ensure_ascii=False))
    preview["source_files"] = {"wps_sha256": digest(wps_path), "hyundai_profile_sha256": digest(profile_path),
                               "doosan_profile_sha256": digest(doosan_profile_path), "recipes_sha256": digest(recipes_path),
                               "work_orders_sha256": digest(work_orders_path)}
    relative = "robot-input-preview.json"
    target = package / "bundles" / run_key / relative
    write_json(target, preview)
    # 기존 raw 식별자는 그대로 두고 새 파일에만 식별자를 할당한다.
    existing = next((f for f in run["files"] if f["path"] == relative), None)
    raw_id = existing["raw_id"] if existing else f"{run_key}/{max([int(f['raw_id'].rsplit('/', 1)[1]) for f in run['files'] if f.get('raw_id')] + [-1]) + 1:04d}"
    entry = {"path": relative, "media_type": "application/json", "raw_id": raw_id, "recorded_sha256": None,
             "sha256": digest(target), "size": target.stat().st_size, "state": "scenario_asset"}
    run["files"] = [f for f in run["files"] if f["path"] != relative] + [entry]
    write_assignment(package / "data/raw" / f"{raw_id}.js", f"raw[{json.dumps(raw_id)}]", {"text": target.read_text(encoding="utf-8")})

    def value(v: object, pointer: str = "") -> dict:
        return {"v": v, "src": f"{run_key}::{relative}#{pointer}"}

    event_id = "manufacturer-input-conversion"
    old = next((s for s in run["steps"] if s.get("event_id", {}).get("v") in (event_id, "hyundai-input-conversion")), None)
    seq = old["seq"] if old else max(s["seq"] for s in run["steps"]) + 1
    step = deepcopy(old or run["steps"][-1])
    step.update({"seq": seq, "label": "작업조건 조회 · 제조사 변환", "src": f"{run_key}::{relative}#",
                     "payload": {"root": run_key, "path": relative},
                     "status": {"class": "success", "label": "필드·단위 변환 완료", "basis": value("preview_ready", "/status"), "note": None}})
    parent = next(s for s in run["steps"] if s["seq"] == seq - 1)
    for name, v in {"event_id": event_id, "type": "input_conversion_preview", "stage": "manufacturer_mapping", "producer": "rule",
                        "recorded_at_utc": None, "elapsed_ms": None, "parent_event_ids": [parent["event_id"]["v"]],
                        "payload_ref": relative, "request_id": None, "command_id": None}.items():
        step[name] = value(v)
    run["steps"] = [s for s in run["steps"] if s["seq"] != seq] + [step]
    blocks = run["tabs"]["delivery"]["blocks"]
    blocks = [b for b in blocks if b.get("id") not in ("hyundai-hi6-input", "robot-manufacturer-input") and b.get("title") != "변환 근거"]
    for block in blocks:
        if block.get("title") == "전달 준비":
            block["title"] = "WPS 원문 조건"
    blocks.insert(0, {"id": "robot-manufacturer-input", "type": "robot_input", "title": "작업조건 · 제조사 입력 변환", "seq": seq, "preview": preview})
    blocks.append({"type": "raw_files", "title": "변환 근거", "seq": seq, "files": [{"root": run_key, "path": relative}]})
    run["tabs"]["delivery"]["blocks"] = blocks
    run["summary"]["final_seq"] = seq
    write_assignment(run_file, f"runs[{json.dumps(run_key)}]", run)
    index = read_assignment(package / "data/index.js")
    for item in index["runs"]:
        if item["key"] == run_key:
            item["steps"], item["summary"] = len(run["steps"]), deepcopy(run["summary"])
    write_assignment(package / "data/index.js", "index", index)

    assets = REPO / "src/contextweld/dashboard_assets"
    for filename in ("robot_input.js", "robot_input.css"):
        shutil.copyfile(assets / filename, package / "assets" / filename)
    app_path = package / "assets/app.js"
    app = app_path.read_text(encoding="utf-8")
    hook = 'robot_input: function (b, box) { window.PAC_ROBOT_INPUT.render(b, box); },'
    if hook not in app:
        marker = "var R = {"
        if app.count(marker) != 1:
            raise ValueError("대시보드 블록 렌더러 위치를 찾을 수 없음")
        app = app.replace(marker, marker + "\n    " + hook, 1)
    app_path.write_text(app, encoding="utf-8")
    html_path = package / "index.html"
    html = html_path.read_text(encoding="utf-8")
    if 'assets/robot_input.css' not in html:
        html = html.replace('</head>', '<link rel="stylesheet" href="assets/robot_input.css">\n</head>')
    if 'assets/robot_input.js' not in html:
        html = html.replace('<script src="assets/app.js">', '<script src="assets/robot_input.js"></script>\n<script src="assets/app.js">')
    html_path.write_text(html, encoding="utf-8")

    # 패키지 파일 목록을 갱신한다. 기존 실행 묶음의 checksums는 수정하지 않는다.
    manifest_path = package / "MANIFEST.json"
    manifest = read_json(manifest_path)
    excluded = set(manifest.get("volatile_files", [])) | {"MANIFEST.json", "SHA256SUMS"}
    manifest["files"] = [{"path": p.relative_to(package).as_posix(), "role": p.relative_to(package).parts[0] if len(p.relative_to(package).parts) > 1 else "app",
                          "size": p.stat().st_size, "sha256": digest(p)}
                         for p in sorted(package.rglob("*")) if p.is_file() and p.relative_to(package).as_posix() not in excluded]
    manifest.setdefault("local_preview", {})["manufacturer_input"] = ["hyundai-hi6", "doosan-drl"]
    write_json(manifest_path, manifest)
    (package / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(package).as_posix()}\n" for p in sorted(package.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")
    return preview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--run", default="shipyard-recapture")
    parser.add_argument("--wps", type=Path, default=REPO / "data/knowledge/lanl-wps-3501-reviewed.json")
    parser.add_argument("--profile", type=Path, default=REPO / "configs/robot_profiles/hyundai_hi6_current_voltage.json")
    parser.add_argument("--doosan-profile", type=Path, default=REPO / "configs/robot_profiles/doosan_drl_analog.json")
    parser.add_argument("--work-orders", type=Path, default=REPO / "configs/document_demo/work_orders.json")
    parser.add_argument("--recipes", type=Path, default=REPO / "configs/document_demo/weld_recipes.json")
    parser.add_argument("--order-id", default="WO-DEMO-015")
    args = parser.parse_args()
    result = install(args.package, args.run, args.wps, args.profile, doosan_profile_path=args.doosan_profile,
                     work_orders_path=args.work_orders, recipes_path=args.recipes, order_id=args.order_id)
    for manufacturer, preview in result["previews"].items():
        print(manufacturer + ": " + preview["command_preview"])


if __name__ == "__main__":
    main()
