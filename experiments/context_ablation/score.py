"""고정 이미지 맥락 실험의 원문 기록을 독립적으로 채점한다."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


NORMAL_CONDITIONS = (
    "A_ocr", "B_crop", "C_scene", "D_candidates", "E_context",
    "F_context_only", "RULE_D",
)
NEGATIVE_CONDITIONS = {"E_absent": "absent", "E_wrong": "wrong_context"}
TEXT_CONDITIONS = {"A_ocr", "B_crop", "C_scene"}
STATUSES = {"resolved", "unreadable", "ambiguous", "conflict"}


def normalize(value: str | None) -> str:
    """공백 양끝과 대소문자만 정규화한다. 1/I, 0/O, 내부 공백은 유지한다."""
    return (value or "").strip().upper()


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (char != other)))
        previous = current
    return previous[-1]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _outcome(row: dict[str, Any]) -> str:
    if row["missing"] or row["schema_errors"] or row["model_error"]:
        return "error"
    if row["accepted"]:
        return "correct" if row["correct"] else "wrong"
    return "abstain"


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    accepted = sum(row["accepted"] for row in rows)
    correct = sum(row["correct"] for row in rows)
    text_exact = sum(row["text_exact"] for row in rows)
    character_count = sum(row["truth_characters"] for row in rows)
    distances = sum(row["character_errors"] for row in rows)
    times = [row["elapsed_seconds"] for row in rows if row["elapsed_seconds"] is not None]
    by_image: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_image[row["image_id"]].append(row)
    images = {}
    for image_id, image_rows in sorted(by_image.items()):
        image_n = len(image_rows)
        images[image_id] = {
            "n": image_n,
            "correct": sum(row["correct"] for row in image_rows),
            "accuracy_all": sum(row["correct"] for row in image_rows) / image_n,
            "text_exact": sum(row["text_exact"] for row in image_rows),
            "text_exact_rate": sum(row["text_exact"] for row in image_rows) / image_n,
        }
    return {
        "n": n,
        "records_present": sum(not row["missing"] for row in rows),
        "text_exact": text_exact,
        "text_exact_rate": _ratio(text_exact, n),
        "text_exact_case_sensitive": sum(row["text_exact_case_sensitive"] for row in rows),
        "character_errors": distances,
        "truth_characters": character_count,
        "cer": _ratio(distances, character_count),
        "accepted": accepted,
        "correct": correct,
        "wrong_accepted": accepted - correct,
        "coverage": _ratio(accepted, n),
        "accuracy_all": _ratio(correct, n),
        "accuracy_accepted": _ratio(correct, accepted),
        "abstentions": sum(_outcome(row) == "abstain" for row in rows),
        "model_errors": sum(row["model_error"] for row in rows),
        "schema_errors": sum(bool(row["schema_errors"]) for row in rows),
        "missing_records": sum(row["missing"] for row in rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "elapsed_seconds_total": sum(times),
        "elapsed_seconds_mean": mean(times) if times else None,
        "image_count": len(images),
        "image_macro_accuracy_all": mean(item["accuracy_all"] for item in images.values()) if images else None,
        "image_macro_text_exact_rate": mean(item["text_exact_rate"] for item in images.values()) if images else None,
        "by_image": images,
    }


def _record_row(record: dict[str, Any] | None, job: dict[str, Any],
                target: dict[str, Any], sample: dict[str, Any],
                fixtures: dict[str, Any]) -> dict[str, Any]:
    truth = normalize(target["text"])
    row: dict[str, Any] = {
        "sample_id": job["sample_id"], "condition": job["condition"],
        "variant": job.get("variant", "normal"), "image_id": sample["image_id"],
        "truth": target["text"], "visible_text": None, "selected_candidate_id": None,
        "status": "missing", "accepted": False, "correct": False,
        "text_exact": False, "text_exact_case_sensitive": False,
        "truth_characters": len(truth), "character_errors": len(truth),
        "elapsed_seconds": None, "missing": record is None, "model_error": False,
        "schema_errors": [], "record_contract_errors": [], "selected_outside_candidates": False,
    }
    if record is None:
        return row
    errors: list[str] = row["schema_errors"]
    for field in ("sample_id", "condition"):
        if record.get(field) != job[field]:
            errors.append(f"{field} does not match plan")
    if record.get("variant") != row["variant"]:
        errors.append("variant does not match plan")
    images = record.get("input_image_refs")
    if not isinstance(images, list):
        errors.append("input_image_refs must be a list")
    elif job["condition"] == "F_context_only" and images:
        errors.append("F_context_only must not receive images")
    elapsed = record.get("elapsed_seconds")
    if isinstance(elapsed, (float, int)) and not isinstance(elapsed, bool) and math.isfinite(elapsed) and elapsed >= 0:
        row["elapsed_seconds"] = elapsed
    else:
        errors.append("elapsed_seconds must be finite and nonnegative")
    model_error = record.get("error")
    if model_error is not None and not isinstance(model_error, str):
        errors.append("error must be null or string")
    row["model_error"] = model_error is not None
    row["record_contract_errors"] = list(errors)
    parsed = record.get("parsed")
    if not isinstance(parsed, dict):
        if not row["model_error"]:
            errors.append("parsed must be an object for successful calls")
        row["status"] = "model_error" if row["model_error"] else "invalid"
        return row
    if set(parsed) != {"visible_text", "selected_candidate_id", "status", "reason", "evidence"}:
        errors.append("parsed keys differ from the frozen schema")
    text = parsed.get("visible_text")
    selected = parsed.get("selected_candidate_id")
    for field, value in (("visible_text", text), ("selected_candidate_id", selected)):
        if value is not None and not isinstance(value, str):
            errors.append(f"{field} must be null or string")
    status = parsed.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("unknown status")
    if not isinstance(parsed.get("reason"), str):
        errors.append("reason must be a string")
    evidence = parsed.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        errors.append("evidence must be a string list")
    condition = job["condition"]
    if condition in TEXT_CONDITIONS:
        if selected is not None:
            errors.append("text-only conditions cannot select a candidate")
        value = text
    else:
        value = selected
        variant = fixtures.get("fixtures", {}).get(job["sample_id"], {}).get("variants", {}).get(row["variant"])
        candidate_ids = variant.get("candidate_ids") if isinstance(variant, dict) else None
        if not isinstance(candidate_ids, list) or not candidate_ids or not all(isinstance(item, str) for item in candidate_ids):
            errors.append("fixture candidate_ids missing or invalid")
            row["record_contract_errors"].append("fixture candidate_ids missing or invalid")
        else:
            allowed = {normalize(item) for item in candidate_ids}
            if isinstance(selected, str) and normalize(selected) not in allowed:
                row["selected_outside_candidates"] = True
                errors.append("selected_candidate_id outside provided candidates")
            if row["variant"] == "absent" and truth in allowed:
                errors.append("absent fixture contains ground truth")
                row["record_contract_errors"].append("absent fixture contains ground truth")
    if status == "resolved" and (not isinstance(value, str) or not value.strip()):
        errors.append("resolved requires a nonempty final value")
    if status != "resolved" and selected is not None:
        errors.append("unresolved answer selected a candidate")
    row["status"] = status if isinstance(status, str) else "invalid"
    row["visible_text"] = text if isinstance(text, str) else None
    row["selected_candidate_id"] = selected if isinstance(selected, str) else None
    # 후보 선택이 잘못됐어도 원문 판독 자체는 별도 지표로 확인한다.
    if isinstance(text, str) and not row["model_error"]:
        row["text_exact"] = normalize(text) == truth
        row["text_exact_case_sensitive"] = text.strip() == target["text"].strip()
        row["character_errors"] = edit_distance(truth, normalize(text))
    if not errors and not row["model_error"] and status == "resolved":
        row["accepted"] = True
        row["correct"] = normalize(value) == truth
    return row


def score_run(run_dir: Path, truth: dict[str, Any], inputs: dict[str, Any],
              fixtures: dict[str, Any], *, asset_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """계획의 모든 항목을 분모로 사용하며 누락/보류를 정답에서 제외한다."""
    run_dir = Path(run_dir)
    plan = read_json(run_dir / "plan.json")
    jobs = plan.get("jobs", plan.get("planned_jobs"))
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("plan.json requires a nonempty jobs/planned_jobs list")
    samples_list = inputs.get("samples")
    targets = truth.get("targets")
    if not isinstance(samples_list, list) or not isinstance(targets, dict):
        raise ValueError("inputs.samples and ground_truth.targets are required")
    samples = {sample["sample_id"]: sample for sample in samples_list}
    errors: list[str] = []
    if len(samples) != len(samples_list):
        errors.append("duplicate sample_id in inputs")
    if set(samples) != set(targets):
        raise ValueError("ground truth targets must exactly match input sample IDs")
    image_count = len({sample["image_id"] for sample in samples.values()})
    if "scorable_image_count" in inputs and inputs["scorable_image_count"] != image_count:
        errors.append("scorable_image_count does not match sample image IDs")
    if "image_count" in inputs and inputs["image_count"] != len(inputs.get("images", [])):
        errors.append("image_count does not match image inventory")
    if "samples" in plan and plan["samples"] != len(samples):
        errors.append("plan sample count does not match inputs")
    for sample_id, target in targets.items():
        if not isinstance(target.get("text"), str) or not normalize(target["text"]):
            raise ValueError(f"empty or invalid truth: {sample_id}")
        if "image_id" in target and target["image_id"] != samples[sample_id]["image_id"]:
            errors.append(f"truth/input image ID mismatch: {sample_id}")
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for job in jobs:
        key = (job["sample_id"], job["condition"])
        if key in expected:
            errors.append(f"duplicate planned case: {key}")
            continue
        if key[0] not in samples:
            errors.append(f"unknown planned sample: {key[0]}")
            continue
        condition = key[1]
        if condition not in NORMAL_CONDITIONS and condition not in NEGATIVE_CONDITIONS:
            errors.append(f"unknown planned condition: {condition}")
            continue
        variant = NEGATIVE_CONDITIONS.get(condition, "normal")
        if job.get("variant", variant) != variant:
            errors.append(f"invalid planned variant: {key}")
        expected[key] = {**job, "variant": variant}
    for sample_id in samples:
        for condition in NORMAL_CONDITIONS:
            if (sample_id, condition) not in expected:
                errors.append(f"normal case missing from plan: {(sample_id, condition)}")
    negative_ids = fixtures.get("negative_sample_ids", inputs.get("negative_sample_ids"))
    if negative_ids is not None:
        if not isinstance(negative_ids, list) or len(set(negative_ids)) != len(negative_ids):
            errors.append("negative_sample_ids must be a unique list")
        else:
            for condition in NEGATIVE_CONDITIONS:
                actual = {sample_id for sample_id, case in expected if case == condition}
                if actual != set(negative_ids):
                    errors.append(f"negative plan sample IDs mismatch: {condition}")
    hashes = dict(plan.get("input_hashes", {}))
    if (run_dir / "config.json").exists():
        config = read_json(run_dir / "config.json")
        for name, digest in config.get("input_hashes", {}).items():
            if name in hashes and hashes[name] != digest:
                errors.append(f"plan/config input hash disagreement: {name}")
            hashes[name] = digest
    hash_checks: dict[str, str] = {}
    for name, declared in hashes.items():
        source_path = (asset_paths or {}).get(name)
        if source_path is None:
            source_path = next((path for path in (asset_paths or {}).values() if path.name == name), None)
        if source_path is None and Path(name).name == name and (run_dir / "inputs" / name).is_file():
            source_path = run_dir / "inputs" / name
        if source_path is None:
            errors.append(f"cannot verify declared input hash: {name}")
            continue
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        hash_checks[name] = digest
        if digest != declared:
            errors.append(f"input hash mismatch: {name}")
    artifact_hash_count = 0
    checksums_path = run_dir / "checksums.json"
    if checksums_path.exists():
        for relative, expected_hash in read_json(checksums_path).items():
            path = (run_dir / relative).resolve()
            if not path.is_relative_to(run_dir.resolve()):
                errors.append(f"artifact path escapes run directory: {relative}")
                continue
            if not path.is_file():
                errors.append(f"missing hashed artifact: {relative}")
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                errors.append(f"artifact hash mismatch: {relative}")
            artifact_hash_count += 1
    elif (run_dir / "completion.json").exists():
        errors.append("completed run is missing checksums.json")
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted((run_dir / "records").glob("*.json")):
        try:
            record = read_json(path)
            key = (record["sample_id"], record["condition"])
            if key in records:
                errors.append(f"duplicate record case: {key}")
                continue
            if key not in expected:
                errors.append(f"unplanned record case: {key}")
                continue
            if path.name != f"{key[0]}--{key[1]}.json":
                errors.append(f"record filename mismatch: {path.name}")
            records[key] = record
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f"invalid record {path.name}: {exc}")
    rows = []
    for key, job in sorted(expected.items()):
        sample_id = key[0]
        row = _record_row(records.get(key), job, targets[sample_id], samples[sample_id], fixtures)
        if row["missing"]:
            errors.append(f"missing record: {key}")
        integrity_issues = row["record_contract_errors"] if row["model_error"] else row["schema_errors"]
        for issue in integrity_issues:
            errors.append(f"invalid {key}: {issue}")
        rows.append(row)
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)
    row_map = {(row["sample_id"], row["condition"]): row for row in rows}
    transitions = {}
    for source, destination in (("A_ocr", "B_crop"), ("B_crop", "C_scene"),
                                ("C_scene", "D_candidates"), ("D_candidates", "E_context"),
                                ("F_context_only", "E_context"), ("A_ocr", "E_context"),
                                ("E_context", "E_absent"), ("E_context", "E_wrong")):
        pairs = [(row_map[(sample_id, source)], row_map[(sample_id, destination)])
                 for sample_id in samples
                 if (sample_id, source) in row_map and (sample_id, destination) in row_map]
        matrix = Counter(f"{_outcome(left)}_to_{_outcome(right)}" for left, right in pairs)
        transitions[f"{source}->{destination}"] = {
            "n": len(pairs), "outcome_matrix": dict(sorted(matrix.items())),
            "wrong_to_correct": matrix["wrong_to_correct"],
            "abstain_to_correct": matrix["abstain_to_correct"],
            "correct_to_wrong": matrix["correct_to_wrong"],
            "correct_to_abstain": matrix["correct_to_abstain"],
            "net_correct_change": sum(right["correct"] - left["correct"] for left, right in pairs),
            "changes": [{"sample_id": left["sample_id"], "image_id": left["image_id"],
                         "from": _outcome(left), "to": _outcome(right)}
                        for left, right in pairs if _outcome(left) != _outcome(right)],
        }
    negative = {}
    for condition in NEGATIVE_CONDITIONS:
        condition_rows = by_condition.get(condition, [])
        negative[condition] = {
            **_aggregate(condition_rows),
            "correct_literal_maintained": sum(row["text_exact"] for row in condition_rows),
            "selected_outside_candidates": sum(row["selected_outside_candidates"] for row in condition_rows),
            "interpretation": "separate stress test; excluded from normal-condition comparisons",
        }
    return {
        "schema_version": "context-ablation-score.v1",
        "validation": {"valid": not errors, "errors": errors, "input_hashes": hash_checks,
                       "artifact_hashes_checked": artifact_hash_count,
                       "planned_jobs": len(jobs), "unique_planned_jobs": len(expected),
                       "records_present": len(records)},
        "dataset": {"targets": len(samples), "images": image_count,
                    "source_images": inputs.get("image_count", image_count),
                    "excluded": truth.get("excluded", inputs.get("excluded", [])),
                    "independence_note": "multiple target regions from the same image are not independent photographs"},
        "metric_definitions": {
            "normalization": "strip().upper(); preserve internal whitespace, punctuation, 1/I and 0/O",
            "text_exact": "visible_text matches truth, independent of acceptance status; records with error are excluded from correct readings and remain in denominator",
            "text_exact_case_sensitive": "visible_text.strip() matches truth.strip()",
            "cer": "sum edit distance / sum truth characters; missing/model-error readings count as empty; candidate-choice violations retain visible-text diagnostics",
            "accepted": "valid, error-free, resolved, nonempty final value; candidate must be provided",
            "final_value": "A/B/C: visible_text; other conditions: selected_candidate_id",
            "accuracy_all": "correct accepted / all planned cases, including failures and abstentions",
            "accuracy_accepted": "correct accepted / accepted, null when no cases are accepted",
            "image_macro_accuracy_all": "mean of per-image accuracy_all; each image has equal weight",
            "ocr_acceptance": "A_ocr resolved means nonempty OCR text only; not a confidence or evidence review decision",
            "validation": "file/plan/hash/record-contract integrity; model schema failures recorded with error are valid failure observations",
        },
        "per_condition": {condition: _aggregate(by_condition.get(condition, [])) for condition in NORMAL_CONDITIONS},
        "transitions": transitions,
        "negative_context": negative,
        "no_image_control": {
            "condition": "F_context_only",
            "interpretation": "OCR reading + candidates + work context + supplied target ROI coordinates and scene size, without image bytes; not pure document-only",
            "n": len(by_condition.get("F_context_only", [])),
        },
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = score_run(args.run, read_json(args.truth), read_json(args.inputs), read_json(args.fixtures),
                            asset_paths={"truth": args.truth, "ground_truth": args.truth,
                                         "inputs": args.inputs, "fixtures": args.fixtures})
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"validation": summary["validation"],
                      "conditions": {key: {field: result[field] for field in
                          ("n", "correct", "accepted", "accuracy_all", "accuracy_accepted", "abstentions", "model_errors")}
                                     for key, result in summary["per_condition"].items()}}, ensure_ascii=False))
    return 0 if summary["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
