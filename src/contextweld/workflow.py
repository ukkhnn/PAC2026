"""저장된 실제 관측을 모사 문서·원문 범위값과 연결하는 검토용 실행."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any

from contextweld.documents import load_index, search_documents, source_path
from contextweld.matching import WorkOrder, identifier, match_orders
from contextweld.recognition import environment_record, safe_path, sha256, utc_now, verify_bundle, write_json

SCHEMA = "document-demo-bundle.v1"
SPEC_VERSION = "demo-1.4+ocr-1.2+documents-1.3"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def issue(code: str, field: str, *, kind: str = "conflict", **details: Any) -> dict[str, Any]:
    return {"code": code, "field": field, "kind": kind, **details}


def iou(a: list[float], b: list[float]) -> float:
    width, height = max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def observed_candidates(observation: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """문자열을 작업문서로 고치지 않고 겹치는 OCR/VLM의 불일치를 남긴다."""
    pattern = re.compile(policy["identifier_regex"])
    rows, errors, candidates = [], [], []
    for text in observation["text_observations"]:
        raw = text["raw_text"].strip()
        if not pattern.fullmatch(raw):
            continue
        normalized = identifier(raw)
        candidates.append(normalized)
        corroborating, alternatives = [], []
        for visual in observation["visual_objects"]:
            if visual.get("kind") != "text" or iou(text["bbox"], visual["bbox"]) < policy["vlm_text_iou_min"]:
                continue
            for line in (visual.get("visible_text") or "").splitlines():
                if pattern.fullmatch(line.strip()):
                    alternatives.append(identifier(line.strip()))
                    corroborating.append({"observation_id": visual["observation_id"], "raw_text": line,
                                          "bbox": visual["bbox"]})
        alternatives = list(dict.fromkeys(alternatives))
        if not alternatives:
            errors.append(issue("no_vlm_identifier_support", text["observation_id"], kind="missing"))
        elif alternatives != [normalized]:
            errors.append(issue("ocr_vlm_disagreement", text["observation_id"],
                                ocr=normalized, vlm=alternatives))
        candidates.extend(alternatives)
        rows.append({"ocr": deepcopy(text), "normalized_identifier": normalized,
                     "vlm": corroborating, "source_kind": "model"})
    if not rows:
        errors.append(issue("no_supported_marking", "part_id", kind="missing"))
    return {"policy": policy, "observations": rows, "candidates": list(dict.fromkeys(candidates)),
            "issues": errors, "normalization": "strip_and_uppercase_only",
            "physical_target_resolved": False}


def document_ref(document: dict[str, Any], path: Path, pointer: str) -> dict[str, Any]:
    return {"document_id": document["document_id"], "revision": str(document["revision"]),
            "source_hash": sha256(path), "locator": {"kind": "json_pointer", "pointer": pointer},
            "document_origin": document["document_origin"], "source_kind": "fixture"}


def apply_case(scenario: dict[str, Any], case: str, orders: dict[str, Any], drawing: dict[str, Any]) -> list[dict]:
    faults = deepcopy(scenario["cases"][case]["faults"])
    for fault in faults:
        if fault["op"] == "set_drawing_process":
            drawing["process"] = fault["value"]
        elif fault["op"] == "set_wps_revision":
            for order in orders["orders"]:
                order["wps_ref"]["revision"] = fault["value"]
        elif fault["op"] != "omit_parameter":
            raise ValueError("지원하지 않는 시연 결함 주입")
    return faults


def build_spec(*, run_id: str, observed: dict[str, Any], scenario: dict[str, Any],
               orders: dict[str, Any], drawing: dict[str, Any], wps: dict[str, Any],
               profile: dict[str, Any], order_path: Path, drawing_path: Path,
               faults: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """정확 ID 조회와 검수 필드 조회로 문서 검토용 명세를 만든다."""
    from contextweld.mock_delivery import validate_command
    errors = deepcopy(observed["issues"])
    matching = match_orders(observed["candidates"], [WorkOrder.from_dict(row) for row in orders["orders"]],
                            **scenario["context"])
    selected = None
    if matching["status"] == "matched":
        match = matching["matches"][0]
        selected = next(row for row in orders["orders"] if identifier(row["order_id"]) == match["order_id"]
                        and row["revision"] == match["revision"]
                        and identifier(row["project_id"]) == match["project_id"]
                        and identifier(row["block_id"]) == match["block_id"])
    else:
        errors.append(issue("work_order_" + matching["reason"], "work_order_id", kind="missing"))
    target = {**scenario["context"], "work_order_id": None, "part_id": None, "joint_id": None}
    target.pop("as_of")
    documents, fields, target_evidence = [], {}, {}
    if selected is not None:
        target.update(work_order_id=identifier(selected["order_id"]), part_id=identifier(selected["part_id"]),
                      joint_id=selected.get("joint_id"))
        index = orders["orders"].index(selected)
        order_ref = document_ref(orders, order_path, f"/orders/{index}")
        drawing_ref = document_ref(drawing, drawing_path, "/")
        documents.extend([order_ref, drawing_ref])
        target_evidence = {"part_id": {"source_kind": "model", "observations": observed["observations"]},
                           "work_order_id": order_ref,
                           "joint_id": {**drawing_ref, "locator": {"kind": "json_pointer", "pointer": "/joint_id"},
                                        "binding": "synthetic_document_reference_not_visual_joint_detection"}}
        for key in ("document_id", "revision"):
            if selected["drawing_ref"].get(key) != drawing.get(key):
                errors.append(issue("drawing_reference_mismatch", key, expected=selected["drawing_ref"].get(key), actual=drawing.get(key)))
        for key in ("part_id", "joint_id", "process", "material", "position", "thickness"):
            if selected.get(key) != drawing.get(key):
                errors.append(issue("work_order_drawing_conflict", key, work_order_value=selected.get(key),
                                    drawing_value=drawing.get(key), evidence=[order_ref, drawing_ref]))
        ref = selected["wps_ref"]
        if ref["document_id"] != wps["document_id"] or ref["revision"] != wps["revision"]:
            errors.append(issue("wps_reference_mismatch", "wps_ref", requested=ref,
                                available={"document_id": wps["document_id"], "revision": wps["revision"]}))
        else:
            documents.append({"document_id": wps["document_id"], "revision": wps["revision"],
                              "source_hash": wps["source_hash"], "locator": {"kind": "pdf_region", "page": 2,
                              "table": "weld_layer_conditions", "row": 1}, "document_origin": "public_document"})
            row = next((r for r in wps["pass_rows"] if r["row_id"] == ref["row_id"]), None)
            if row is None:
                errors.append(issue("wps_row_missing", "pass_row", kind="missing"))
            else:
                for key in profile["parameters"]:
                    value = row["fields"].get(key)
                    if value is not None and value.get("review_status") == "agent_transcription_checked":
                        fields[key] = {**deepcopy(value["normalized"]), "raw_value": value["raw_value"],
                                       "source_kind": "document", "evidence": deepcopy(value["evidence"])}
                        if "header" in value:
                            fields[key]["header_evidence"] = deepcopy(value["header"])
                expected_process = wps["applicability"]["process"]["normalized"]["value"]
                expected_material = wps["applicability"]["material_from"]["normalized"]["value"]
                for key, expected in (("process", expected_process), ("material", expected_material)):
                    if selected.get(key) != expected:
                        errors.append(issue("work_order_wps_conflict", key, work_order_value=selected.get(key),
                                            wps_value=expected, evidence=[order_ref, wps["applicability"]["process" if key == "process" else "material_from"]["evidence"]]))
    for fault in faults:
        if fault["op"] == "omit_parameter":
            fields.pop(fault["field"], None)
    spec = {"schema_version": "document-work-spec.v1", "spec_id": f"{run_id}-spec-001", "run_id": run_id,
            "purpose": "demo_mock", "evaluation_scope": "document_review", "target_profile": profile["profile_id"],
            "target": target, "target_evidence": target_evidence, "documents": documents, "parameters": fields,
            "source_row_id": selected["wps_ref"]["row_id"] if selected else None,
            "constraints": deepcopy(wps["constraints"]), "source_review": deepcopy(wps["review"]),
            "physical_applicability": "unverified", "range_combination_validated": False,
            "application_authorized": False, "execution_authorized": False,
            "application_missing": ["actual_photo_material_thickness_joint", "wps_thickness_unit",
                                    "GWS_WFP_and_project_approval", "operating_combination_and_robot_applicability"],
            "fault_injections": faults}
    prototype = command_from_spec(spec, profile)
    for validation in validate_command(prototype, profile):
        errors.append({**validation, "field": validation.get("path", "$"),
                       "kind": "missing" if validation["code"] in {"required_parameter_missing", "nonempty_string_required", "nonempty_reference_array_required"} else "invalid"})
    spec["validation"] = {"status": "ready_for_mock" if not errors else "needs_review",
                          "scope": "document_review_only", "issues": errors,
                          "missing_fields": [item.get("field") for item in errors if item.get("kind") == "missing"],
                          "checks": ["observation_consensus", "exact_work_order_scope_and_revision",
                                     "drawing_and_wps_references", "fixture_document_consistency",
                                     "transcribed_parameter_schema_units_and_evidence"],
                          "field_application_approved": False}
    return spec, matching


def command_from_spec(spec: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "demo-command.v1", "contract_version": profile["contract_version"],
            "command_id": f"{spec['run_id']}-command-001", "run_id": spec["run_id"], "spec_id": spec["spec_id"],
            "target_profile": profile["profile_id"], "purpose": "demo_mock", "evaluation_scope": "document_review",
            "execution_authorized": False, "application_authorized": False,
            "target": deepcopy(spec["target"]), "documents": deepcopy(spec["documents"]),
            "parameters": deepcopy(spec["parameters"]), "constraints": deepcopy(spec["constraints"]),
            "physical_applicability": "unverified", "range_combination_validated": False,
            "application_missing": deepcopy(spec["application_missing"])}


class ReviewBundle:
    """bootstrap 묶음을 수정하지 않고 별도 부분 실행의 사건·파일을 보존한다."""
    def __init__(self, output_root: Path, run_id: str, case: str, deliver: bool) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id):
            raise ValueError("유효하지 않은 run_id")
        output_root.mkdir(parents=True, exist_ok=True)
        self.final = output_root / f"run_{run_id}"
        self.root = output_root / f"run_{run_id}.incomplete"
        if self.final.exists() or self.root.exists():
            raise FileExistsError("기존 실행을 덮어쓸 수 없습니다. 새 run_id를 사용하세요.")
        self.root.mkdir()
        for name in ("inputs", "results", "evidence", "commands"):
            (self.root / name).mkdir()
        (self.root / "events.jsonl").touch()
        self.started, self.seq = time.monotonic(), 0
        self.manifest = {"schema_version": SCHEMA, "spec_version": SPEC_VERSION, "run_id": run_id,
                         "run_kind": "document_demo", "capture_mode": "public_dataset", "case": case,
                         "evaluation_scope": "document_review", "delivery_requested": deliver,
                         "execution_authorized": False, "application_authorized": False,
                         "demo_complete": False, "inference_reused": True, "new_model_calls": 0,
                         "started_at_utc": utc_now(), "export_status": "in_progress", "run_outcome": "running",
                         "input_bundle_ref": "inputs/recognition", "source_document_originals_included": False}
        write_json(self.root / "manifest.json", self.manifest)

    def event(self, stage: str, ref: str, *, command_id: str | None = None) -> None:
        self.seq += 1
        event = {"event_id": f"event-{self.seq:04d}", "seq": self.seq,
                 "run_id": self.manifest["run_id"], "stage": stage, "producer": "rule",
                 "recorded_at_utc": utc_now(), "elapsed_ms": round((time.monotonic() - self.started) * 1000),
                 "parent_event_ids": [f"event-{self.seq - 1:04d}"] if self.seq > 1 else [],
                 "payload_ref": ref, "command_id": command_id}
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def finish(self, outcome: str) -> Path:
        self.manifest.update(run_outcome=outcome, export_status="complete", finished_at_utc=utc_now(),
                             elapsed_seconds=round(time.monotonic() - self.started, 3))
        self.event("export", "manifest.json")
        self.manifest["files"] = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        write_json(self.root / "manifest.json", self.manifest)
        write_json(self.root / "checksums.json", {name: sha256(safe_path(self.root, name)) for name in self.manifest["files"]})
        inspect_document_bundle(self.root)
        self.root.rename(self.final)
        return self.final


def run_document_demo(*, repo: Path, scenario_path: Path, recognition_bundle: Path, document_index: Path,
                      data_root: Path, output_root: Path, run_id: str, case: str = "normal", deliver: bool = False) -> Path:
    from contextweld.mock_delivery import MockReceiver, send_command
    verify_bundle(recognition_bundle)
    source_manifest = read_json(recognition_bundle / "manifest.json")
    source_manifest_hash = sha256(recognition_bundle / "manifest.json")
    scenario = read_json(scenario_path)
    if case not in scenario["cases"]:
        raise ValueError("없는 시연 사례")
    if source_manifest["run_id"] != scenario["recognition_run_id"]:
        raise ValueError("시나리오가 가리키는 실제 인식 실행이 아닙니다.")
    frame_id = scenario["cases"][case].get("frame_id", scenario["frame_id"])
    frame = next((f for f in source_manifest["frames"] if f["frame_id"] == frame_id), None)
    if frame is None:
        raise ValueError("입력 프레임 없음")
    observation = next((read_json(safe_path(recognition_bundle, ref)) for ref in source_manifest["result_refs"]
                        if ref == f"results/{frame_id}-observation.json"), None)
    if observation is None or observation["run_id"] != source_manifest["run_id"] or observation["input_frame_ids"] != [frame_id]:
        raise ValueError("관측의 실행/프레임 불일치")
    wps_path = safe_path(repo, scenario["wps_file"])
    wps = read_json(wps_path)
    raw_wps = source_path(data_root, wps["source"]["relative_path"])
    if sha256(raw_wps) != wps["source_hash"] or not wps["review"]["transcription_checked"]:
        raise ValueError("WPS 원문 해시 또는 전사 검수 불일치")
    index = load_index(document_index, data_root)
    registered = next((d for d in index["documents"] if d["document_id"] == wps["document_id"]), None)
    if registered is None or registered["source_hash"] != wps["source_hash"]:
        raise ValueError("색인의 WPS와 검수한 원문이 다릅니다.")
    bundle = ReviewBundle(output_root, run_id, case, deliver)
    try:
        shutil.copytree(recognition_bundle, bundle.root / "inputs/recognition")
        write_json(bundle.root / "inputs/scenario.json", scenario)
        for key, name in scenario["files"].items():
            shutil.copyfile(safe_path(scenario_path.parent, name), bundle.root / "inputs" / Path(name).name)
        shutil.copyfile(wps_path, bundle.root / "evidence/wps-reviewed.json")
        orders = read_json(bundle.root / "inputs/work_orders.json")
        drawing = read_json(bundle.root / "inputs/drawing.json")
        profile = read_json(bundle.root / "inputs/target_profile.json")
        faults = apply_case(scenario, case, orders, drawing)
        write_json(bundle.root / "inputs/effective-work-orders.json", orders)
        write_json(bundle.root / "inputs/effective-drawing.json", drawing)
        write_json(bundle.root / "inputs/case.json", {"case": case, "faults": faults, "frame_id": frame_id,
                                                      "producer": "fixture" if faults else "system"})
        source_fingerprints = {str(p.relative_to(repo)): sha256(p) for p in
                               [repo / "src/contextweld/workflow.py", repo / "src/contextweld/mock_delivery.py",
                                repo / "src/contextweld/matching.py", repo / "src/contextweld/documents.py",
                                repo / "scripts/run/run_document_demo.py", repo / "scripts/verify/verify_document_demo.py"]}
        write_json(bundle.root / "inputs/environment.json", {"environment": environment_record(repo),
                   "code_hashes": source_fingerprints, "document_index_hash": index["index_hash"],
                   "source_manifest_hash": source_manifest_hash, "source_bundle_checksums_hash": sha256(recognition_bundle / "checksums.json")})
        bundle.manifest.update(scenario_id=scenario["scenario_id"], parent_run_id=source_manifest["run_id"],
                               source_manifest_hash=source_manifest_hash, frame_id=frame_id,
                               limitations=scenario["limitations"] + wps["limitations"])
        bundle.event("input_reuse", "inputs/environment.json")
        observed = observed_candidates(observation, scenario["observation_policy"])
        write_json(bundle.root / "results/observation-selection.json", observed)
        bundle.event("observation_selection", "results/observation-selection.json")
        retrieval = search_documents(index, scenario["retrieval_query"], document_ids=[wps["document_id"]], top_k=2)
        # 과거 색인의 미확인 개정을 고치지 않고 같은 원문 해시의 새 전사근거로 별도 해석한다.
        retrieval["revision_resolution"] = {"indexed_revision": registered["revision"], "transcribed_revision": wps["revision"],
                                             "source_hash_match": True, "evidence": wps["header"]["revision"]["evidence"]}
        retrieval["used_for"] = "supporting_source_context_not_model_generation"
        retrieval["used_evidence_ids"] = []
        write_json(bundle.root / "evidence/retrieval.json", retrieval)
        bundle.event("document_retrieval", "evidence/retrieval.json")
        spec, matching = build_spec(run_id=run_id, observed=observed, scenario=scenario, orders=orders, drawing=drawing,
                                   wps=wps, profile=profile, order_path=bundle.root / "inputs/effective-work-orders.json",
                                   drawing_path=bundle.root / "inputs/effective-drawing.json", faults=faults)
        write_json(bundle.root / "results/matching.json", matching)
        bundle.event("work_order_matching", "results/matching.json")
        write_json(bundle.root / "results/work-spec.json", spec)
        bundle.event("document_fields_and_validation", "results/work-spec.json")
        outcome = "needs_review" if spec["validation"]["issues"] else "succeeded"
        delivery = {"requested": deliver, "sent": False, "status": "blocked" if outcome == "needs_review" else "not_requested"}
        if deliver and outcome == "succeeded":
            command = command_from_spec(spec, profile)
            write_json(bundle.root / "commands/command.json", command)
            bundle.event("command_prepared", "commands/command.json", command_id=command["command_id"])
            with MockReceiver(profile, bundle.root / "commands/receiver.jsonl") as receiver:
                transport = send_command(receiver.url, command, timeout=5)
            write_json(bundle.root / "commands/transport.json", transport)
            bundle.event("mock_transport", "commands/transport.json", command_id=command["command_id"])
            delivery = {"requested": True, "sent": True, "transport_ref": "commands/transport.json", "transport": "loopback_http"}
            ack = transport.get("ack")
            if not isinstance(ack, dict) or ack.get("status") != "received" or ack.get("command_id") != command["command_id"]:
                outcome = "failed"
                delivery["status"] = "failed"
            else:
                delivery["status"] = "received"
        write_json(bundle.root / "results/delivery.json", delivery)
        bundle.event("delivery_result", "results/delivery.json")
        bundle.manifest["delivery_status"] = delivery["status"]
        return bundle.finish(outcome)
    except BaseException as exc:
        bundle.manifest.update(run_outcome="failed", export_status="incomplete", error_type=type(exc).__name__, error=str(exc))
        write_json(bundle.root / "manifest.json", bundle.manifest)
        raise


def inspect_document_bundle(root: Path) -> dict[str, Any]:
    """해시뿐 아니라 원관측·명세 재계산·명령·실수신 로그의 연결도 확인한다."""
    from contextweld.mock_delivery import validate_command
    manifest, checksums = read_json(root / "manifest.json"), read_json(root / "checksums.json")
    if manifest.get("schema_version") != SCHEMA or manifest.get("export_status") != "complete":
        raise ValueError("지원하지 않거나 불완전한 문서 실행 묶음")
    if manifest.get("execution_authorized") is not False or manifest.get("application_authorized") is not False:
        raise ValueError("문서 검토는 실행/적용을 승인할 수 없습니다.")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"checksums.json"}
    if actual != set(checksums) or actual != set(manifest["files"]):
        raise ValueError("묶음 파일 목록 불일치")
    for ref, digest in checksums.items():
        path = safe_path(root, ref)
        if path.is_symlink() or sha256(path) != digest:
            raise ValueError("묶음 파일 해시 불일치: " + ref)
    source = safe_path(root, manifest["input_bundle_ref"])
    verify_bundle(source)
    if sha256(source / "manifest.json") != manifest["source_manifest_hash"]:
        raise ValueError("원래 인식 실행 manifest 불일치")
    scenario, case_data = read_json(root / "inputs/scenario.json"), read_json(root / "inputs/case.json")
    source_manifest = read_json(source / "manifest.json")
    if (source_manifest["run_id"] != manifest["parent_run_id"] or source_manifest["run_id"] != scenario["recognition_run_id"]
            or manifest["run_kind"] != "document_demo" or manifest["capture_mode"] != "public_dataset"
            or manifest["new_model_calls"] != 0 or manifest["demo_complete"] is not False):
        raise ValueError("실행 종류 또는 원래 실행 연결 불일치")
    expected_frame = scenario["cases"][manifest["case"]].get("frame_id", scenario["frame_id"])
    if case_data["case"] != manifest["case"] or case_data["frame_id"] != expected_frame or manifest["frame_id"] != expected_frame:
        raise ValueError("시나리오 사례/프레임 불일치")
    original_orders, original_drawing = read_json(root / "inputs/work_orders.json"), read_json(root / "inputs/drawing.json")
    expected_faults = apply_case(scenario, manifest["case"], original_orders, original_drawing)
    if (expected_faults != case_data["faults"] or original_orders != read_json(root / "inputs/effective-work-orders.json")
            or original_drawing != read_json(root / "inputs/effective-drawing.json")):
        raise ValueError("원본 문서와 선언한 결함 주입 불일치")
    observation = read_json(source / f"results/{case_data['frame_id']}-observation.json")
    expected_observed = observed_candidates(observation, scenario["observation_policy"])
    if expected_observed != read_json(root / "results/observation-selection.json"):
        raise ValueError("원관측 선택 내용 불일치")
    profile, wps = read_json(root / "inputs/target_profile.json"), read_json(root / "evidence/wps-reviewed.json")
    spec, matching = build_spec(run_id=manifest["run_id"], observed=expected_observed, scenario=scenario,
                               orders=read_json(root / "inputs/effective-work-orders.json"),
                               drawing=read_json(root / "inputs/effective-drawing.json"), wps=wps, profile=profile,
                               order_path=root / "inputs/effective-work-orders.json", drawing_path=root / "inputs/effective-drawing.json",
                               faults=case_data["faults"])
    if spec != read_json(root / "results/work-spec.json") or matching != read_json(root / "results/matching.json"):
        raise ValueError("문서 명세/검증 재계산 불일치")
    delivery = read_json(root / "results/delivery.json")
    if (delivery["requested"] != manifest["delivery_requested"] or delivery["status"] != manifest["delivery_status"]
            or (not spec["validation"]["issues"] and manifest["delivery_requested"] and not delivery["sent"])):
        raise ValueError("전달 요청/결과 불일치")
    if delivery["sent"]:
        if spec["validation"]["issues"] or not manifest["delivery_requested"]:
            raise ValueError("검증 보류 또는 미요청 실행의 전송")
        command = read_json(root / "commands/command.json")
        if command != command_from_spec(spec, profile) or validate_command(command, profile):
            raise ValueError("명세와 모의 명령 불일치")
        transport = read_json(root / "commands/transport.json")
        ack = transport.get("ack")
        if transport.get("request") != command:
            raise ValueError("실제 전송 본문과 명령 불일치")
        canonical = json.dumps(command, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        if transport["request_sha256"] != digest:
            raise ValueError("전송 본문 해시 불일치")
        if delivery["status"] == "received":
            if (not ack or ack.get("status") != "received" or ack.get("command_id") != command["command_id"]
                    or ack.get("command_sha256") != digest or ack.get("validation_errors")
                    or ack.get("execution_authorized") is not False or ack.get("application_authorized") is not False
                    or transport["http_status"] != 200):
                raise ValueError("수신 응답 불일치")
            receipts = [json.loads(line) for line in (root / "commands/receiver.jsonl").read_text().splitlines()]
            if (len(receipts) != 1 or receipts[0]["command"] != command or receipts[0]["ack"] != ack
                    or receipts[0]["http_status"] != 200 or receipts[0]["request_sha256"] != digest
                    or json.loads(receipts[0]["raw_request"]) != command):
                raise ValueError("수신기 원본 요청/응답 불일치")
    # 빈 commands/는 복사·Git 정리 과정에서 사라질 수 있다. 없음과 빈 디렉토리만 같은 "명령 없음"으로 본다.
    elif (root / "commands").is_symlink() or ((root / "commands").exists() and not (root / "commands").is_dir()):
        raise ValueError("commands는 실제 디렉토리여야 합니다.")
    elif (root / "commands").is_dir() and any((root / "commands").iterdir()):
        raise ValueError("미전송 실행에 명령/수신 기록이 있습니다.")
    expected_outcome = "needs_review" if spec["validation"]["issues"] else ("failed" if delivery["status"] == "failed" else "succeeded")
    if manifest["run_outcome"] != expected_outcome:
        raise ValueError("요청 범위의 결과 상태 불일치")
    events = [json.loads(s) for s in (root / "events.jsonl").read_text().splitlines()]
    seen = set()
    for seq, event in enumerate(events, 1):
        if event["seq"] != seq or event["run_id"] != manifest["run_id"] or event["event_id"] in seen:
            raise ValueError("사건 실행/순서/ID 불일치")
        if not set(event["parent_event_ids"]) <= seen or not safe_path(root, event["payload_ref"]).is_file():
            raise ValueError("사건 원인/파일 참조 불일치")
        seen.add(event["event_id"])
    return {"verified": True, "run_id": manifest["run_id"], "case": manifest["case"],
            "run_outcome": manifest["run_outcome"], "delivery_status": delivery["status"],
            "issues": len(spec["validation"]["issues"]), "files": len(checksums), "events": len(events),
            "scope": "document_review_only", "demo_complete": False}
