"""기존 A/B 자료를 실제 관측 판단으로 선택하고 불변 사건 묶음으로 보존한다."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

from contextweld.recognition import sha256, utc_now, write_json
from contextweld.recapture_inputs import verify_inputs
from contextweld.recapture_inference import validate_capture_assessment

SCHEMA = "recapture-bundle.v1"
RULE_VERSION = "recapture-visible-information.v1"
FIELDS = {"marking_text", "marking_target"}
QUALITY_CODES = {"glare", "occlusion", "blur", "out_of_frame", "small_text", "low_contrast", "unreadable"}


def decide_recapture(assessment: dict, attempts: int, max_attempts: int = 1) -> dict:
    """정답·A/B 이름 대신 관측된 필수정보와 시점 변경 가능성만 사용한다."""
    if type(attempts) is not int or attempts not in (0, 1) or max_attempts != 1:
        raise ValueError("this provider permits exactly one recapture attempt")
    checks = assessment.get("field_checks", [])
    if (len(checks) != 2 or {item.get("field") for item in checks} != FIELDS
            or any(item.get("status") not in {"observed", "unresolved"} for item in checks)):
        raise ValueError("validated required field checks are missing")
    missing = [item["field"] for item in checks if item["status"] == "unresolved"]
    evidence = assessment.get("quality_evidence", [])
    for item in evidence:
        if (item.get("code") not in QUALITY_CODES or type(item.get("viewpoint_change_may_help")) is not bool
                or not set(item.get("affected_fields", [])) <= FIELDS):
            raise ValueError("unsupported quality evidence")
    useful = [item for item in evidence if item["viewpoint_change_may_help"]
              and set(item["affected_fields"]) & set(missing)]
    if not missing:
        action, reasons = "continue", ["visible_information_observed"]
    elif not useful:
        action, reasons = "needs_review", ["no_supported_viewpoint_remedy"]
    elif attempts >= max_attempts:
        action, reasons = "needs_review", ["recapture_limit_reached"]
    else:
        action, reasons = "request_recapture", ["required_visual_information_unresolved", "viewpoint_change_may_help"]
    return {"action": action, "reason_codes": reasons, "affected_fields": missing,
            "quality_evidence": useful, "quality_evidence_source": "model_assessment",
            "roi_original_px": None, "rule_version": RULE_VERSION,
            "attempts_used": attempts, "max_attempts": max_attempts,
            "execution_authorized": False}


class LoopBundle:
    def __init__(self, output_root: Path, run_id: str, config: dict, inputs: dict) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_id):
            raise ValueError("invalid run_id")
        output_root.mkdir(parents=True, exist_ok=True)
        self.final = output_root / f"run_{run_id}"
        self.root = output_root / f"run_{run_id}.incomplete"
        if self.final.exists() or self.root.exists():
            raise FileExistsError("run already exists; refusing to overwrite")
        self.root.mkdir()
        for name in ("frames", "results", "evidence", "requests"):
            (self.root / name).mkdir()
        (self.root / "events.jsonl").touch()
        self.run_id, self.started, self.seq = run_id, time.monotonic(), 0
        self.frame_events: dict[str, str] = {}
        self.result_events: dict[str, str] = {}
        self.payload_events: dict[str, str] = {}
        self.active_request_id: str | None = None
        self.manifest = {
            "schema_version": SCHEMA, "run_id": run_id, "run_kind": "recapture_loop",
            "scenario_id": inputs["scenario_id"], "capture_mode": "pre_captured",
            "source_kind": "simulator", "started_at_utc": utc_now(), "status": "running",
            "run_outcome": "running", "export_status": "incomplete", "inference_status": "running",
            "config_ref": "results/inference-config.json", "inputs_ref": "inputs/inputs.json",
            "frames": [], "result_refs": [], "request_refs": [],
            "physical_movement_triggered": False, "recognition_feedback_enabled": False,
            "saved_frame_selection_enabled": True, "delivery_requested": False,
            "delivery_status": "not_requested", "application_authorized": False,
            "execution_authorized": False, "demo_complete": False,
            "evidence_kind": config.get("evidence_kind", "actual_model"),
            "limitations": [
                "A/B were captured before this run; a request selects saved B without moving a robot.",
                "Quality assessment is a model judgment, not a verified diagnosis of glare.",
                "Visual readiness is not transcription accuracy or work/WPS authorization.",
                "Document application, mock delivery and live camera control are not connected here."]}
        write_json(self.root / "results/inference-config.json", config)
        write_json(self.root / "manifest.json", self.manifest)

    def event(self, stage: str, payload_ref: str, producer: str, frame_ids: list[str],
              result_ids: list[str] | None = None, event_type: str = "stage_completed",
              parent_payload_refs: list[str] | None = None) -> str:
        self.seq += 1
        parents = [self.result_events[key] for key in result_ids or [] if key in self.result_events]
        parents += [self.frame_events[key] for key in frame_ids if key in self.frame_events]
        parents += [self.payload_events[key] for key in parent_payload_refs or [] if key in self.payload_events]
        record = {"run_id": self.run_id, "event_id": f"event-{self.seq:04d}", "seq": self.seq,
                  "type": event_type, "stage": stage, "producer": producer,
                  "recorded_at_utc": utc_now(), "elapsed_ms": round((time.monotonic() - self.started) * 1000),
                  "parent_event_ids": list(dict.fromkeys(parents)), "input_frame_ids": frame_ids,
                  "input_result_ids": result_ids or [], "request_id": self.active_request_id,
                  "command_id": None, "payload_ref": payload_ref}
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.payload_events[payload_ref] = record["event_id"]
        if stage == "frame_ingest":
            self.frame_events.update({key: record["event_id"] for key in frame_ids})
        return record["event_id"]

    def result(self, stage: str, frame_id: str, fields: dict, *, producer: str = "model",
               input_ids: list[str] | None = None, raw_ref: str | None = None) -> dict:
        identifier = f"{frame_id}-{stage}"
        result = {"schema_version": "recognition.v1", "result_id": identifier, "run_id": self.run_id,
                  "stage": stage, "input_frame_ids": [frame_id], "input_result_ids": input_ids or [],
                  "producer": producer, "status": "needs_review", "raw_output_ref": raw_ref,
                  "config_ref": "results/inference-config.json", **fields}
        ref = f"results/{identifier}.json"
        write_json(self.root / ref, result)
        self.manifest["result_refs"].append(ref)
        self.result_events[identifier] = self.event(stage, ref, producer, [frame_id], input_ids,
            parent_payload_refs=[fields["evidence_ref"]] if fields.get("evidence_ref") else [])
        return result

    def finish(self, *, visual_outcome: str, recapture_outcome: str, error: Exception | None = None) -> Path:
        failed = error is not None
        self.manifest.update(status="failed" if failed else "needs_review",
            run_outcome="failed" if failed else "needs_review", inference_status="failed" if failed else "succeeded",
            visual_outcome=visual_outcome, recapture_outcome=recapture_outcome, export_status="complete",
            finished_at_utc=utc_now(), elapsed_seconds=round(time.monotonic() - self.started, 3))
        if error:
            write_json(self.root / "results/error.json", {"error_type": type(error).__name__, "message": str(error)})
            self.manifest["error_ref"] = "results/error.json"
            self.event("failure", "results/error.json", "system", [], list(self.result_events), event_type="run_failed")
        self.event("export", "manifest.json", "system", [], list(self.result_events), event_type="run_exported")
        inventory = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        self.manifest["files"] = inventory
        write_json(self.root / "manifest.json", self.manifest)
        write_json(self.root / "checksums.json", {ref: sha256(self.root / ref) for ref in inventory})
        verify_recapture_bundle(self.root)
        self.root.rename(self.final)
        return self.final


def run_recapture_loop(*, inputs_root: Path, output_root: Path, run_id: str,
                       observer: Any, config: dict) -> Path:
    inputs_root, output_root = inputs_root.absolute(), output_root.absolute()
    if any(p.is_symlink() for base in (inputs_root, output_root) for p in (base, *base.parents)):
        raise ValueError("input/output roots cannot traverse a symlink")
    if output_root.is_relative_to(inputs_root) or inputs_root.is_relative_to(output_root):
        raise ValueError("input and output roots must be separate")
    inputs = verify_inputs(inputs_root)
    bundle = LoopBundle(output_root, run_id, {**config, "rule_version": RULE_VERSION,
        "max_recapture_attempts": 1, "input_checksums_sha256": sha256(inputs_root / "checksums.json")}, inputs)
    try:
        shutil.copytree(inputs_root, bundle.root / "inputs", symlinks=True)
        verify_inputs(bundle.root / "inputs")
        request_ref = None
        for attempts, source in enumerate(inputs["frames"]):
            frame = {**source, "image_ref": f"inputs/{source['image_ref']}",
                     "overview_ref": f"inputs/{source['overview_ref']}",
                     "source_capture_ref": f"inputs/{source['source_capture_ref']}",
                     "capture_mode": "pre_captured", "ingested_at_utc": utc_now(),
                     "capture_request_id": bundle.active_request_id, "origin_capture_request_id": None,
                     "request_link_semantics": "saved_frame_selection" if request_ref else "initial_saved_frame",
                     "coordinate_system": "original_pixels", "transforms": [], "labels_used": False}
            frame_ref = f"frames/{frame['frame_id']}.json"
            write_json(bundle.root / frame_ref, frame)
            bundle.manifest["frames"].append(frame)
            bundle.event("frame_ingest", frame_ref, "system", [frame["frame_id"]],
                         event_type="saved_frame_ingested", parent_payload_refs=[request_ref] if request_ref else [])
            observation, relation, assessment = observer.observe(bundle, frame)
            validate_capture_assessment(assessment, observation, relation)
            decision_fields = decide_recapture(assessment, attempts)
            decision = bundle.result("recognition_decision", frame["frame_id"], decision_fields,
                producer="rule", input_ids=[observation["result_id"], relation["result_id"], assessment["result_id"]])
            action = decision["action"]
            if action != "request_recapture":
                outcome = {"visual_outcome": "ready_for_document_review" if action == "continue" else "needs_review",
                           "recapture_outcome": ("resolved" if action == "continue" else "unresolved")
                           if attempts else "not_requested"}
                break
            bundle.active_request_id = f"{run_id}-recapture-01"
            request = {"schema_version": "recapture-request.v1", "request_id": bundle.active_request_id,
                       "run_id": run_id, "source_frame_ids": [frame["frame_id"]],
                       "source_result_ids": [decision["result_id"]],
                       "reason_codes": decision["reason_codes"], "affected_fields": decision["affected_fields"],
                       "quality_evidence": decision["quality_evidence"], "roi_original_px": None,
                       "suggested_adjustments": [{"kind": "viewpoint_change", "selection": "next_registered_view"}],
                       "attempt": attempts + 1, "max_attempts": 1, "capture_mode": "pre_captured",
                       "physical_movement_triggered": False, "requested_at_utc": utc_now()}
            request_ref = "requests/recapture-01.json"
            write_json(bundle.root / request_ref, request)
            bundle.manifest["request_refs"].append(request_ref)
            bundle.event("recapture_request", request_ref, "rule", [frame["frame_id"]],
                         [decision["result_id"]], event_type="recapture_requested")
        else:
            raise RuntimeError("recapture loop exhausted without a final decision")
    except Exception as exc:
        return bundle.finish(visual_outcome="failed", recapture_outcome="failed", error=exc)
    return bundle.finish(**outcome)


def _path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or Path(relative).is_absolute() or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise ValueError("unsafe bundle path")
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("symlinks are not bundle assets")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("missing or escaping bundle asset")
    return path


def verify_recapture_bundle(root: Path) -> dict:
    """파일 무결성과 사건의 인과·요청 연결을 함께 검사한다."""
    def read(ref: str) -> Any:
        return json.loads(_path(root, ref).read_text(encoding="utf-8"))
    if root.is_symlink() or any(p.is_symlink() for p in root.absolute().parents):
        raise ValueError("bundle root must not be a symlink")
    manifest, checksums = read("manifest.json"), read("checksums.json")
    if manifest.get("schema_version") != SCHEMA or manifest.get("export_status") != "complete":
        raise ValueError("unsupported or incomplete recapture bundle")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"checksums.json"}
    if any(p.is_symlink() for p in root.rglob("*")) or set(checksums) != actual or set(manifest["files"]) != actual:
        raise ValueError("bundle file inventory mismatch")
    for ref, digest in checksums.items():
        if sha256(_path(root, ref)) != digest:
            raise ValueError(f"bundle checksum mismatch: {ref}")
    if (manifest.get("capture_mode") != "pre_captured" or manifest.get("physical_movement_triggered") is not False
            or manifest.get("execution_authorized") is not False or manifest.get("delivery_status") != "not_requested"
            or manifest.get("demo_complete") is not False or manifest.get("application_authorized") is not False
            or manifest.get("delivery_requested") is not False or manifest.get("recognition_feedback_enabled") is not False
            or manifest.get("saved_frame_selection_enabled") is not True or manifest.get("run_kind") != "recapture_loop"):
        raise ValueError("unsupported live movement, delivery or authorization claim")
    if manifest["run_outcome"] not in {"needs_review", "failed"}:
        raise ValueError("partial recapture run cannot authorize a job")
    inputs = verify_inputs(root / "inputs") if (root / "inputs/checksums.json").is_file() else None
    if manifest["run_outcome"] != "failed" and inputs is None:
        raise ValueError("missing input package")
    results = {read(ref)["result_id"]: read(ref) for ref in manifest["result_refs"]}
    if len(results) != len(manifest["result_refs"]):
        raise ValueError("duplicate result IDs")
    frames = {f["frame_id"]: f for f in manifest["frames"]}
    if len(frames) != len(manifest["frames"]) or list(frames) not in (["frame-A"], ["frame-A", "frame-B"], []):
        raise ValueError("invalid saved-frame order")
    events = [json.loads(line) for line in _path(root, "events.jsonl").read_text().splitlines()]
    seen_events, seen_results, ingested = set(), set(), set()
    request_id, request_event, decision_seen = None, None, None
    result_events: dict[str, str] = {}
    frame_events: dict[str, str] = {}
    logged_request_refs = []
    for number, event in enumerate(events, 1):
        if (event["seq"] != number or event["event_id"] in seen_events or event["run_id"] != manifest["run_id"]
                or not set(event["parent_event_ids"]) <= seen_events
                or not set(event["input_result_ids"]) <= seen_results or event["command_id"] is not None):
            raise ValueError("invalid event ordering, lineage or command")
        payload = read(event["payload_ref"])
        if event["stage"] in {"movement_started", "movement_completed", "capture_completed"}:
            raise ValueError("saved input provider cannot record live camera movement")
        if event["stage"] == "frame_ingest":
            fid = payload["frame_id"]
            if fid in ingested or payload != frames[fid]:
                raise ValueError("duplicate or inconsistent ingested frame")
            if fid == "frame-B" and (not request_id or request_event not in event["parent_event_ids"]):
                raise ValueError("B ingestion must depend on a recapture request")
            if payload["capture_request_id"] != request_id or event["request_id"] != request_id:
                raise ValueError("frame/request link mismatch")
            if inputs is None:
                raise ValueError("ingested frame requires its input package")
            source = next(f for f in inputs["frames"] if f["frame_id"] == fid)
            for key, value in source.items():
                expected = f"inputs/{value}" if key in {"image_ref", "overview_ref", "source_capture_ref"} else value
                if payload.get(key) != expected:
                    raise ValueError("frame differs from saved capture provenance")
            if payload.get("origin_capture_request_id") is not None or payload.get("capture_mode") != "pre_captured":
                raise ValueError("stored capture cannot be attributed to this request")
            if sha256(_path(root, payload["image_ref"])) != payload["sha256"]:
                raise ValueError("frame image identity mismatch")
            ingested.add(fid)
            frame_events[fid] = event["event_id"]
        if not set(event["input_frame_ids"]) <= ingested:
            raise ValueError("event references a future frame")
        required_parents = {result_events[rid] for rid in event["input_result_ids"]}
        if event["stage"] != "frame_ingest":
            required_parents.update(frame_events[fid] for fid in event["input_frame_ids"])
        if not required_parents <= set(event["parent_event_ids"]):
            raise ValueError("event omits its input parents")
        if event["stage"] == "recapture_request":
            if (request_id or not decision_seen or decision_seen["action"] != "request_recapture"
                    or event["input_result_ids"] != [decision_seen["result_id"]]
                    or result_events[decision_seen["result_id"]] not in event["parent_event_ids"]
                    or payload["attempt"] != 1 or payload["max_attempts"] != 1
                    or payload["physical_movement_triggered"] is not False):
                raise ValueError("request not justified by a decision")
            expected_request = {"schema_version": "recapture-request.v1", "run_id": manifest["run_id"],
                "source_frame_ids": decision_seen["input_frame_ids"],
                "source_result_ids": [decision_seen["result_id"]],
                "reason_codes": decision_seen["reason_codes"], "affected_fields": decision_seen["affected_fields"],
                "quality_evidence": decision_seen["quality_evidence"], "roi_original_px": None,
                "capture_mode": "pre_captured"}
            if any(payload.get(key) != value for key, value in expected_request.items()):
                raise ValueError("request payload differs from its decision")
            request_id, request_event = payload["request_id"], event["event_id"]
            logged_request_refs.append(event["payload_ref"])
            if event["request_id"] != request_id:
                raise ValueError("request event identity mismatch")
        if event["request_id"] != request_id:
            raise ValueError("event/request identity mismatch")
        if payload.get("result_id") in results:
            rid = payload["result_id"]
            if (rid in seen_results or payload != results[rid] or payload["run_id"] != manifest["run_id"]
                    or payload["input_result_ids"] != event["input_result_ids"]
                    or payload["input_frame_ids"] != event["input_frame_ids"]
                    or payload["schema_version"] != "recognition.v1" or payload["stage"] != event["stage"]
                    or payload["producer"] != event["producer"]):
                raise ValueError("result/event mismatch")
            if any(results[key]["input_frame_ids"] != payload["input_frame_ids"] for key in payload["input_result_ids"]):
                raise ValueError("result cannot use another frame's observations")
            for ref_key in ("raw_output_ref", "config_ref", "evidence_ref"):
                if payload.get(ref_key):
                    _path(root, payload[ref_key])
            seen_results.add(rid)
            result_events[rid] = event["event_id"]
            if payload["stage"] == "capture_assessment":
                parents = [results[key] for key in payload["input_result_ids"]]
                observations = [item for item in parents if item["stage"] == "observation"]
                relations = [item for item in parents if item["stage"] == "relation"]
                if len(observations) != 1 or len(relations) != 1:
                    raise ValueError("assessment requires one observation and relation")
                validate_capture_assessment(payload, observations[0], relations[0])
            if payload["stage"] == "recognition_decision":
                assessment_ids = [i for i in payload["input_result_ids"] if results[i]["stage"] == "capture_assessment"]
                if len(assessment_ids) != 1:
                    raise ValueError("decision requires its capture assessment")
                expected = decide_recapture(results[assessment_ids[0]], len(ingested) - 1)
                if any(payload.get(key) != value for key, value in expected.items()):
                    raise ValueError("decision does not match recorded evidence")
                decision_seen = payload
        seen_events.add(event["event_id"])
    if seen_results != set(results) or ingested != set(frames) or not events or events[-1]["stage"] != "export":
        raise ValueError("unlogged data or absent export event")
    if manifest["request_refs"] != logged_request_refs:
        raise ValueError("request inventory mismatch")
    if manifest["run_outcome"] != "failed":
        if not decision_seen or decision_seen["action"] == "request_recapture":
            raise ValueError("missing terminal decision")
        expected_visual = "ready_for_document_review" if decision_seen["action"] == "continue" else "needs_review"
        if manifest["visual_outcome"] != expected_visual:
            raise ValueError("terminal visual outcome mismatch")
        expected_recapture = ("resolved" if decision_seen["action"] == "continue" else "unresolved") \
            if request_id else "not_requested"
        if manifest["recapture_outcome"] != expected_recapture or manifest["inference_status"] != "succeeded":
            raise ValueError("terminal recapture outcome mismatch")
    elif manifest.get("inference_status") != "failed" or not any(e["stage"] == "failure" for e in events):
        raise ValueError("failed run requires its failure record")
    return manifest
