"""고정 사진·정답·합성 문서를 분리하고 불변 실험 입력을 준비한다."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA = "context-ablation-inputs.v1"
NEGATIVE_TARGETS = ("S01-R00", "S03-R00", "S06-R00", "S08-R00")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def bbox(points: list[list[int]]) -> list[int]:
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def center(annotation: dict[str, Any]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox(annotation["points"])
    return (x0 + x1) / 2, (y0 + y1) / 2


def placement(annotation: dict[str, Any], size: tuple[int, int]) -> dict[str, str]:
    x, y = center(annotation)
    return {
        "horizontal": ("left", "middle", "right")[min(2, int(x * 3 / size[0]))],
        "vertical": ("upper", "middle", "lower")[min(2, int(y * 3 / size[1]))],
    }


def neighbors(annotation: dict[str, Any], others: list[dict[str, Any]]) -> list[dict[str, str]]:
    x, y = center(annotation)
    ranked = sorted((row for row in others if row is not annotation),
                    key=lambda row: ((center(row)[0] - x) ** 2 + (center(row)[1] - y) ** 2,
                                     row["transcription"]))
    anchors = []
    for row in ranked[:1]:
        nx, ny = center(row)
        direction = ("right" if nx > x else "left") if abs(nx - x) >= abs(ny - y) else ("below" if ny > y else "above")
        anchors.append({"marking": row["transcription"], "relative_to_candidate": direction})
    return anchors


def shifted(position: dict[str, str]) -> dict[str, str]:
    cycle = {"left": "middle", "middle": "right", "right": "left"}
    vertical = {"upper": "middle", "middle": "lower", "lower": "upper"}
    return {"horizontal": cycle[position["horizontal"]], "vertical": vertical[position["vertical"]]}


def roster(text: str, annotations: list[dict[str, Any]], target: dict[str, Any], sample_id: str) -> tuple[list[str], str]:
    # OCR 출력과 무관한 고정 혼동 문자 및 같은 사진의 주변 라벨로만 작성한다.
    twin = text.replace("1", "I", 1)
    pool = [text, twin, text.replace("0", "O", 1)]
    x, y = center(target)
    nearby = sorted((row for row in annotations if row is not target),
                    key=lambda row: ((center(row)[0] - x) ** 2 + (center(row)[1] - y) ** 2,
                                     row["transcription"]))
    pool.extend(row["transcription"] for row in nearby[:2])
    match = re.fullmatch(r"(.+-)(\d+)([A-Za-z]*)", text)
    if not match:
        raise ValueError(f"Unsupported source label format: {sample_id}")
    prefix, number, suffix = match.groups()
    for delta in (1, -1, 2, -2, 3, -3):
        pool.append(f"{prefix}{int(number) + delta}{suffix}")
    unique = list(dict.fromkeys(pool))[:6]
    if len(unique) != 6 or twin == text:
        raise ValueError(f"Cannot construct six candidates: {sample_id}")
    return sorted(unique, key=lambda value: stable_key(f"context-v1|{sample_id}|{value}")), twin


def make_variant(candidate_ids: list[str], rows: list[dict[str, Any]], image_id: str) -> dict[str, Any]:
    indexed = {row["candidate_id"]: row for row in rows}
    return {
        "candidate_ids": candidate_ids,
        "work_context": {
            "document_id": f"DEMO-LAYOUT-{image_id}",
            "source_kind": "synthetic_demo",
            "placement_basis": "annotation_derived_coarse_image_layout",
            "real_work_order": False,
            "instruction": (
                "Identify the target marking by comparing its visible text and image surroundings "
                "with this provisional staging list. The list may be incomplete or inconsistent. "
                "Positions are coarse image-relative hints, not surveyed physical coordinates. "
                "Some entries share a staging position. Do not choose a candidate solely because "
                "it is listed. Do not assert a unique identity when evidence conflicts or remains ambiguous. "
                "No welding operation or material specification is authorized by this document."
            ),
            "candidate_rows": [indexed[value] for value in candidate_ids],
        },
    }


def build_assets(data_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = ROOT / "experiments/e1_ocr/manifest.json"
    sources_path = ROOT / "configs/demo_data_sources.json"
    manifest, source_config = read_json(manifest_path), read_json(sources_path)
    sources = {row["id"]: row for row in source_config["sources"]}
    inputs: dict[str, Any] = {
        "schema_version": SCHEMA,
        "experiment_id": "CTX-001",
        "purpose": "fixed_image_diagnostic_context_ablation",
        "roi_source": "public_dataset_annotation_given_target_not_detector_output",
        "source_manifest_sha256": sha256(manifest_path),
        "source_config_sha256": sha256(sources_path),
        "dataset": manifest["dataset"], "dataset_revision": manifest["revision"],
        "license_declared": manifest["license_declared"],
        "image_count": 10,
        "scorable_image_count": 9,
        "crop_policy": {"method": "axis_aligned_bbox", "padding_fraction_per_axis": 0.08,
                        "padding_min_pixels": 4, "rotate": False, "rectify": False,
                        "resize": False, "output_format": "PNG"},
        "images": [], "samples": [],
    }
    truth: dict[str, Any] = {
        "schema_version": "context-ablation-ground-truth.v1", "experiment_id": "CTX-001",
        "usage": "scoring_and_fixture_freeze_only_never_model_prompt",
        "label_provenance": "public_dataset_not_independently_human_reannotated",
        "normalization": {"text_exact": "strip_outer_whitespace_and_uppercase",
                          "text_exact_case_sensitive": "strip_outer_whitespace_only",
                          "member_id": "strip_outer_whitespace_and_uppercase",
                          "character_substitutions": False},
        "source_manifest_sha256": sha256(manifest_path), "targets": {}, "excluded": [],
    }
    fixtures: dict[str, Any] = {
        "schema_version": "context-ablation-fixtures.v1", "experiment_id": "CTX-001",
        "source_kind": "synthetic_demo", "generated_from_model_outputs": False,
        "construction": "label_derived_candidates_and_coarse_placements_frozen_before_new_inference",
        "candidate_count": 6, "negative_sample_ids": list(NEGATIVE_TARGETS), "fixtures": {},
    }
    for image in manifest["images"]:
        image_id = image["id"]
        source = sources[f"steel-{image_id}"]
        path = data_root / source["relative_path"]
        if sha256(path) != image["sha256"] or source["sha256"] != image["sha256"]:
            raise ValueError(f"Source image hash mismatch: {image_id}")
        with Image.open(path) as loaded:
            size = loaded.size
        inputs["images"].append({"image_id": image_id, "image_path": source["relative_path"],
                                 "image_sha256": image["sha256"], "image_size": list(size),
                                 "source_url": source["url"]})
        valid = [row for row in image["annotations"] if not row["difficult"]]
        by_text = {row["transcription"]: row for row in valid}
        for roi_index, annotation in enumerate(image["annotations"]):
            sample_id = f"{image_id}-R{roi_index:02d}"
            if annotation["difficult"]:
                truth["excluded"].append({"sample_id": sample_id, "image_id": image_id,
                                           "reason": "dataset_difficult_true"})
                continue
            text = annotation["transcription"]
            inputs["samples"].append({
                "sample_id": sample_id, "image_id": image_id, "image_path": source["relative_path"],
                "image_sha256": image["sha256"], "image_size": list(size),
                "target_polygon": annotation["points"], "target_bbox": bbox(annotation["points"]),
                "fixture_id": sample_id,
            })
            candidates, twin = roster(text, valid, annotation, sample_id)
            rows = []
            for candidate in candidates:
                if len(valid) == 1:
                    position = {"horizontal": "unspecified", "vertical": "unspecified"}
                    anchors: list[dict[str, str]] = []
                elif candidate in (text, twin):
                    position, anchors = placement(annotation, size), neighbors(annotation, valid)
                elif candidate in by_text:
                    item = by_text[candidate]
                    position, anchors = placement(item, size), neighbors(item, valid)
                else:
                    position, anchors = shifted(placement(annotation, size)), []
                rows.append({"candidate_id": candidate, "position": position,
                             "nearby_markings": anchors, "task": "marking_identity_review"})
            variants = {"normal": make_variant(candidates, rows, image_id)}
            expectations = {"normal": {"target_in_roster": True, "preferred_outcome": "correct_or_needs_review"}}
            if sample_id in NEGATIVE_TARGETS:
                # 목록 길이와 순서를 유지한 채 정답 후보 및 문서 내부 참조를 제거한다.
                number_match = re.fullmatch(r"(.+-)(\d+)([A-Za-z]*)", text)
                if number_match is None:
                    raise ValueError(f"Unsupported negative fixture label: {sample_id}")
                prefix, number, suffix = number_match.groups()
                absent_id = f"{prefix}{int(number) + 17}{suffix}"
                if absent_id in candidates:
                    raise ValueError(f"Duplicate negative fixture candidate: {sample_id}")
                absent_candidates = [absent_id if item == text else item for item in candidates]
                absent_rows = copy.deepcopy(rows)
                for row in absent_rows:
                    if row["candidate_id"] == text:
                        row["candidate_id"] = absent_id
                    row["nearby_markings"] = [anchor for anchor in row["nearby_markings"] if anchor["marking"] != text]
                variants["absent"] = make_variant(absent_candidates, absent_rows, image_id)
                # 정답 후보의 배치만 다른 위치로 바꾸고 비슷한 후보는 원래 배치를 유지한다.
                # 단일 표기 사진에도 거짓 위치 힌트를 추가하며 별도 강건성 조건으로만 채점한다.
                wrong_rows = copy.deepcopy(rows)
                for row in wrong_rows:
                    if row["candidate_id"] == text:
                        row["position"] = shifted(placement(annotation, size))
                        row["nearby_markings"] = []
                    elif row["candidate_id"] == twin:
                        row["position"] = placement(annotation, size)
                        row["nearby_markings"] = neighbors(annotation, valid)
                variants["wrong_context"] = make_variant(candidates, wrong_rows, image_id)
                expectations["absent"] = {"target_in_roster": False, "preferred_outcome": "out_of_roster_or_needs_review"}
                expectations["wrong_context"] = {"target_in_roster": True, "preferred_outcome": "correct_with_conflict_or_needs_review"}
            fixtures["fixtures"][sample_id] = {"variants": variants}
            truth["targets"][sample_id] = {
                "text": text, "image_id": image_id, "roi_index": roi_index, "difficult": False,
                "indistinguishable_context_candidate": twin, "variant_expectations": expectations,
            }
    if len(inputs["samples"]) != 28 or len(truth["excluded"]) != 1:
        raise ValueError("Unexpected scoring population; protocol must be reviewed before running")
    return inputs, fixtures, truth


def freeze(data_root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    paths = [destination / name for name in ("inputs.json", "fixtures.json", "ground_truth.json")]
    if any(path.exists() for path in paths):
        raise FileExistsError("Refusing to overwrite frozen experiment definitions")
    for path, value in zip(paths, build_assets(data_root)):
        write_new(path, value)


def verify_definitions(definition_dir: Path, data_root: Path) -> dict[str, Any]:
    rebuilt = build_assets(data_root)
    for name, expected in zip(("inputs.json", "fixtures.json", "ground_truth.json"), rebuilt):
        if read_json(definition_dir / name) != expected:
            raise ValueError(f"Frozen definition mismatch: {name}")
    return {"definition_sha256": {name: sha256(definition_dir / name)
                                  for name in ("inputs.json", "fixtures.json", "ground_truth.json")},
            "verified_images": 10, "scorable_images": 9, "scorable_targets": 28,
            "negative_targets": len(NEGATIVE_TARGETS)}


def prepare(definition_dir: Path, data_root: Path, output_dir: Path) -> dict[str, Any]:
    verification = verify_definitions(definition_dir, data_root)
    output_dir.mkdir(parents=True, exist_ok=False)
    crop_dir = output_dir / "crops"
    crop_dir.mkdir()
    prepared: dict[str, Any] = {"schema_version": "context-ablation-prepared.v1", **verification, "samples": []}
    inputs = read_json(definition_dir / "inputs.json")
    for sample in inputs["samples"]:
        path = data_root / sample["image_path"]
        bounds = crop_bounds(sample)
        crop_path = crop_dir / f"{sample['sample_id']}.png"
        with Image.open(path) as loaded:
            loaded.convert("RGB").crop(bounds).save(crop_path, format="PNG")
        prepared["samples"].append({**sample, "whole_path": str(path.resolve()),
                                     "crop_path": str(crop_path.resolve()), "crop_sha256": sha256(crop_path),
                                     "crop_bbox": bounds})
    write_new(output_dir / "prepared.json", prepared)
    return prepared


def crop_bounds(sample: dict[str, Any]) -> list[int]:
    """runner에서도 동일한 ROI·padding을 사용할 수 있는 공개 도우미다."""
    x0, y0, x1, y1 = sample["target_bbox"]
    px, py = max(4, math.ceil((x1 - x0) * .08)), max(4, math.ceil((y1 - y0) * .08))
    width, height = sample["image_size"]
    return [max(0, x0 - px), max(0, y0 - py), min(width, x1 + px), min(height, y1 + py)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/raw/demo-bootstrap-v1")
    parser.add_argument("--definition-dir", type=Path, default=HERE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.freeze:
        freeze(args.data_root, args.definition_dir)
        result = verify_definitions(args.definition_dir, args.data_root)
    elif args.verify_only:
        result = verify_definitions(args.definition_dir, args.data_root)
    else:
        result = prepare(args.definition_dir, args.data_root, args.output_dir)
        result = {key: value for key, value in result.items() if key != "samples"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
