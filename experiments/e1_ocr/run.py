"""두 입력 조건의 실제 로컬 OCR과 채점을 실행하고 원본 출력을 보존한다."""

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from typing import Any

from PIL import Image, ImageDraw, __version__ as pillow_version

from score import assign, iou, score_text

ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def bounds(points: list[list[int]]) -> list[float]:
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def relative(box: list[float], width: int, height: int) -> list[float]:
    return [box[0] / width, box[1] / height, box[2] / width, box[3] / height]


def prepare(run: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    full_jobs, crop_jobs, targets = [], [], []
    crops = run / "crops"
    crops.mkdir()
    for item in manifest["images"]:
        source = ROOT / "inputs" / item["source_path"]
        if sha(source) != item["sha256"]:
            raise ValueError(f"자료 해시 불일치: {item['id']}")
        with Image.open(source) as image:
            if image.getexif().get(274, 1) != 1:
                raise ValueError("EXIF 회전과 라벨 좌표의 관계를 먼저 확인해야 합니다.")
            width, height = image.size
            full_jobs.append({"id": item["id"] + "-full", "path": str(source)})
            for index, annotation in enumerate(item["annotations"]):
                if annotation.get("difficult") or annotation["transcription"] == "###":
                    continue
                box = bounds(annotation["points"])
                if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                    raise ValueError(f"범위 밖 라벨: {item['id']}/{index}")
                padx, pady = max(2, (box[2] - box[0]) * .05), max(2, (box[3] - box[1]) * .05)
                crop = [max(0, math.floor(box[0] - padx)), max(0, math.floor(box[1] - pady)),
                        min(width, math.ceil(box[2] + padx)), min(height, math.ceil(box[3] + pady))]
                key = f"{item['id']}-R{index:02d}"
                path = crops / f"{key}.png"
                image.crop(tuple(crop)).convert("RGB").save(path)
                crop_jobs.append({"id": key + "-crop", "path": str(path)})
                local_box = [box[0] - crop[0], box[1] - crop[1], box[2] - crop[0], box[3] - crop[1]]
                targets.append({
                    "id": key, "image_id": item["id"], "expected": annotation["transcription"],
                    "source_path": item["source_path"], "image_size": [width, height],
                    "source_sha256": item["sha256"], "polygon": annotation["points"],
                    "full_bbox": relative(box, width, height), "crop_pixels": crop,
                    "crop_bbox": relative(local_box, crop[2] - crop[0], crop[3] - crop[1]),
                    "crop_sha256": sha(path),
                })
    return full_jobs + crop_jobs, targets


def evaluate(raw: dict[str, Any], targets: list[dict[str, Any]], manifest: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_id = {r["id"]: r for r in raw["results"]}
    expected_ids = {i["id"] + "-full" for i in manifest["images"]} | {t["id"] + "-crop" for t in targets}
    if len(by_id) != len(raw["results"]) or set(by_id) != expected_ids:
        raise ValueError("실행 결과 ID가 중복되거나 누락됐습니다.")
    failures = [r for r in raw["results"] if r.get("error")]
    if failures:
        raise RuntimeError(f"OCR 호출 오류 {len(failures)}건. raw.json을 확인하세요. 성능 계산은 중단합니다.")
    rows = []
    for item in manifest["images"]:
        labels = [t for t in targets if t["image_id"] == item["id"]]
        full_observations = by_id[item["id"] + "-full"]["observations"]
        mapping = assign([t["full_bbox"] for t in labels], full_observations)
        for index, target in enumerate(labels):
            full = full_observations[mapping[index]] if index in mapping else None
            crop_observations = by_id[target["id"] + "-crop"]["observations"]
            crop_mapping = assign([target["crop_bbox"]], crop_observations)
            crop = crop_observations[crop_mapping[0]] if 0 in crop_mapping else None
            rows.append({**target, "full": score_text(target["expected"], full),
                         "crop": score_text(target["expected"], crop),
                         "full_iou": iou(target["full_bbox"], full["bbox"]) if full else None,
                         "crop_iou": iou(target["crop_bbox"], crop["bbox"]) if crop else None})
    summary: dict[str, Any] = {"image_count": len(manifest["images"]), "label_count": len(rows),
        "excluded_labels": sum(len(i["annotations"]) for i in manifest["images"]) - len(rows),
        "engine": {k: v for k, v in raw.items() if k != "results"}, "conditions": {}}
    for condition in ("full", "crop"):
        scores = [row[condition] for row in rows]
        runs = [r for r in raw["results"] if r["id"].endswith("-" + condition)]
        times = [r["seconds"] for r in runs]
        chars = sum(s["characters"] for s in scores)
        edits = sum(s["edits"] for s in scores)
        summary["conditions"][condition] = {
            "localized": sum(s["localized"] for s in scores),
            "raw_exact": sum(s["raw_exact"] for s in scores),
            "normalized_exact": sum(s["normalized_exact"] for s in scores),
            "top3_exact": sum(s["top3_exact"] for s in scores),
            "edit_count": edits, "reference_characters": chars, "cer": edits / chars if chars else None,
            "ocr_calls": len(runs), "error_count": 0,
            "unassigned_observations": sum(len(r["observations"]) for r in runs) - sum(s["localized"] for s in scores),
            "ocr_seconds_total": sum(times), "ocr_seconds_median": statistics.median(times),
            "ocr_seconds_first": times[0],
            "per_image": {item["id"]: {"exact": sum(r[condition]["normalized_exact"] for r in rows if r["image_id"] == item["id"]),
                "labels": sum(r["image_id"] == item["id"] for r in rows)} for item in manifest["images"]},
        }
    return summary, rows


def contact_sheet(run: Path, targets: list[dict[str, Any]]) -> None:
    sheet = Image.new("RGB", (1000, math.ceil(len(targets) / 4) * 180), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for index, target in enumerate(targets):
        x, y = (index % 4) * 250, (index // 4) * 180
        with Image.open(run / "crops" / (target["id"] + ".png")) as crop:
            crop.thumbnail((240, 145))
            sheet.paste(crop, (x + 5, y + 25))
        draw.text((x + 5, y + 5), f"{target['id']}: {target['expected']}", fill="black")
    sheet.save(run / "contact-sheet.jpg")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", help="기존 결과를 덮어쓰지 않는 새 디렉토리 이름")
    args = parser.parse_args()
    if not args.run_id.replace("-", "").replace("_", "").isalnum():
        parser.error("run_id에는 문자·숫자·하이픈·밑줄만 사용하세요.")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    run = ROOT / "runs" / args.run_id
    run.mkdir(parents=True, exist_ok=False)
    jobs, targets = prepare(run, manifest)
    write_json(run / "jobs.json", jobs)
    write_json(run / "targets.json", targets)
    contact_sheet(run, targets)
    build = ROOT / ".build"
    build.mkdir(exist_ok=True)
    binary = build / "vision"
    subprocess.run(["swiftc", "-module-cache-path", str(build / "cache"), str(ROOT / "vision.swift"), "-o", str(binary)], check=True, timeout=180)
    metadata = {"run_id": args.run_id, "started_at": datetime.now().astimezone().isoformat(),
                "python": platform.python_version(), "pillow": pillow_version, "machine": platform.machine(),
                "macos": platform.mac_ver()[0], "manifest_sha256": sha(ROOT / "manifest.json"),
                "source_sha256": {name: sha(ROOT / name) for name in ("run.py", "score.py", "vision.swift", "PROTOCOL.md")},
                "binary_sha256": sha(binary),
                "swift_version": subprocess.check_output(["swiftc", "--version"], text=True).strip()}
    write_json(run / "environment.json", metadata)
    result = subprocess.run([str(binary), str(run / "jobs.json"), str(run / "raw.json")], text=True, capture_output=True, timeout=180)
    (run / "engine.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    raw = json.loads((run / "raw.json").read_text())
    summary, rows = evaluate(raw, targets, manifest)
    write_json(run / "summary.json", summary)
    write_json(run / "cases.json", rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
