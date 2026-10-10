#!/usr/bin/env python3
"""PV2 E1 채점기: 제품 묶음의 관측 결과에 진행 규칙(D_gate/D_ocr/D_vlm)을 적용하고 평가 전용 정답과 비교한다.

- D_gate는 제품 workflow.observed_candidates를 문서 데모 관측 정책 그대로 호출한다.
- 정답은 평가에만 쓴다. 모델 입력에는 들어가지 않았다.
사용: python -B score.py <bundle_dir> [<bundle_dir> ...] --out scores.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from contextweld.workflow import observed_candidates  # noqa: E402

GT_PATH = REPO / "output/pipeline-v2-20261010/data/eval/ground_truth.json"
SOURCES = REPO / "output/pipeline-v2-20261010/data/sources.json"
REGISTRY = REPO / "configs/demo_data_sources.json"
POLICY = json.loads((REPO / "configs/document_demo/scenario.json").read_text(encoding="utf-8"))["observation_policy"]
PATTERN = re.compile(POLICY["identifier_regex"])


def norm(text: str) -> str:
    return text.strip().upper()


def confusable(text: str) -> str:
    return norm(text).replace("I", "1").replace("L", "1").replace("|", "1").replace("O", "0")


def ocr_ids(observation: dict) -> list[dict]:
    return [{"text": norm(t["raw_text"]), "score": t["recognition_score"]} for t in observation["text_observations"]
            if PATTERN.fullmatch(t["raw_text"].strip())]


def vlm_ids(observation: dict, kinds: set[str] | None = {"text"}) -> list[str]:
    found = []
    for item in observation["visual_objects"]:
        if kinds is not None and item.get("kind") not in kinds:
            continue
        for line in (item.get("visible_text") or "").splitlines():
            if PATTERN.fullmatch(line.strip()):
                found.append(norm(line))
    return found


def outcome(decision: str | None, truth: list[str]) -> str:
    if decision is None:
        return "HOLD"
    if len(truth) == 1:
        return "PROCEED-correct" if decision == truth[0] else "PROCEED-wrong"
    return "PROCEED-in-set" if decision in truth else "PROCEED-not-in-set"


def unique_one(values: list[str]) -> str | None:
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else None


def gt_lookup() -> tuple[dict, dict]:
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))["images"]
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    by_hash = {item["sha256"]: item["id"] for item in sources}
    old = {item["id"]: by_hash[item["sha256"]] for item in
           json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"] if item["group"] == "steel-images"}
    return gt, old


def score_bundle(bundle: Path, gt: dict, old: dict) -> list[dict]:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for frame in manifest["frames"]:
        frame_id, source = frame["frame_id"], frame["source_id"]
        image = old.get(source, source)
        truth_items = gt[image]["instances"]
        truth = [norm(item["transcription"]) for item in truth_items]
        observation = json.loads((bundle / f"results/{frame_id}-observation.json").read_text(encoding="utf-8"))
        relation = json.loads((bundle / f"results/{frame_id}-relation.json").read_text(encoding="utf-8"))
        spec = json.loads((bundle / f"results/{frame_id}-work_spec_candidate.json").read_text(encoding="utf-8"))
        observed = observed_candidates(observation, POLICY)
        gate = unique_one(observed["candidates"]) if not observed["issues"] else None
        ocr = ocr_ids(observation)
        d_ocr = unique_one([item["text"] for item in ocr])
        vlm = vlm_ids(observation)
        d_vlm = unique_one(vlm)
        timing = {}
        for stage in ("visual", "relation"):
            path = bundle / f"results/{frame_id}-{stage}.generation.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                timing[stage] = {"seconds": data["generation_seconds"], "output_tokens": data["output_tokens"]}
        rows.append({
            "bundle": bundle.name, "frame_id": frame_id, "image": image, "split": gt[image]["split"],
            "seen_in_previous_pilots": gt[image]["seen_in_previous_pilots"], "truth": truth,
            "ocr_ids": ocr, "vlm_text_ids": vlm, "vlm_any_kind_ids": vlm_ids(observation, None),
            "gate_issues": [issue["code"] for issue in observed["issues"]], "gate_candidates": observed["candidates"],
            "decision": {"D_gate": gate, "D_ocr": d_ocr, "D_vlm": d_vlm},
            "outcome": {"D_gate": outcome(gate, truth), "D_ocr": outcome(d_ocr, truth), "D_vlm": outcome(d_vlm, truth)},
            "read_any": {"ocr_exact": any(item["text"] in truth for item in ocr),
                         "vlm_exact": any(value in truth for value in vlm),
                         "ocr_confusable": any(confusable(item["text"]) in {confusable(t) for t in truth} for item in ocr),
                         "vlm_confusable": any(confusable(value) in {confusable(t) for t in truth} for value in vlm)},
            "shared_wrong_agreement": bool(gate is not None and gate not in truth),
            "relations": len(relation["relations"]),
            "document_refs": sum(len(item["document_refs"]) for item in relation["relations"]),
            "work_spec_fields_empty": spec["fields"] == {} and spec["business_part_id"] is None and spec["wps_id"] is None,
            "quality_issues": observation.get("quality_issues", []), "timing": timing})
    return rows


def summarize(rows: list[dict]) -> dict:
    single = [row for row in rows if len(row["truth"]) == 1]
    summary = {"images": len(rows), "single_code_images": len(single), "policies": {}}
    for policy in ("D_gate", "D_ocr", "D_vlm"):
        counts: dict[str, int] = {}
        for row in single:
            counts[row["outcome"][policy]] = counts.get(row["outcome"][policy], 0) + 1
        summary["policies"][policy] = counts
    summary["ocr_exact_any"] = sum(row["read_any"]["ocr_exact"] for row in single)
    summary["vlm_exact_any"] = sum(row["read_any"]["vlm_exact"] for row in single)
    summary["ocr_confusable_any"] = sum(row["read_any"]["ocr_confusable"] for row in single)
    summary["vlm_confusable_any"] = sum(row["read_any"]["vlm_confusable"] for row in single)
    summary["document_refs_total"] = sum(row["document_refs"] for row in rows)
    summary["frames_with_relations"] = sum(1 for row in rows if row["relations"])
    summary["work_spec_fields_empty"] = sum(row["work_spec_fields_empty"] for row in rows)
    summary["quality_issues_nonempty"] = sum(1 for row in rows if row["quality_issues"])
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    gt, old = gt_lookup()
    report = {"schema_version": "pv2-e1-scores.v1", "policy": POLICY, "bundles": {}}
    for bundle in args.bundles:
        rows = score_bundle(bundle, gt, old)
        report["bundles"][bundle.name] = {"summary": summarize(rows), "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({name: value["summary"] for name, value in report["bundles"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
