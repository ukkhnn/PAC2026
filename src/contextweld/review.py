"""명시적 요청으로만 시작하는 수정 후 문서 범위 재검토와 선택적 loopback 모의 전달.

원래 관측·문서 입력을 보존한 채 사용자가 선택한 수정만 적용해 관계/대상 해석 → 작업지시·도면 연결 →
WPS/개정 확인 → 새 명세 → 필수값·단위·충돌 검사를 규칙으로 다시 실행한다. 모델을 호출하지 않으며,
이미지 의미나 시각 관계의 재해석은 이 모듈의 범위가 아니다.
"""
from __future__ import annotations

from copy import deepcopy
from http.client import HTTPException
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any

from contextweld.corrections import (AUTHOR_KINDS, DOCUMENT_BUNDLE, HOLD, RESTORE, REVIEW_BUNDLE, SELECT,
                                     CorrectionConflict, CorrectionRejected, _write_exclusive, canonical, digest, enclosing_bundle,
                                     evaluate_target, inspect_bundle, load_selected, observation_state, parameter_state,
                                     read_json, reviewed_wps_field, valid_id, validate_record, wps_location)
from contextweld.matching import identifier
from contextweld.recognition import environment_record, safe_path, sha256, utc_now, write_json
from contextweld.workflow import build_spec, command_from_spec, inspect_document_bundle, observed_candidates

SCHEMA = REVIEW_BUNDLE
SPEC_VERSION = "demo-1.5+ocr-1.2+documents-1.3"
REQUEST_SCHEMA = "review-request.v1"
REQUEST_INTERFACE = "cli:scripts/run/run_review.py"
# 스크립트를 역할별 하위 폴더로 옮기기 전에 저장한 묶음은 옛 경로를 기록하고 있다.
# 요청 스냅샷 해시는 그 값으로 계산됐으므로 과거 기록도 그대로 검증한다.
ACCEPTED_REQUEST_INTERFACES = (REQUEST_INTERFACE, "cli:scripts/run_review.py")
PARENT_REF = "inputs/parent"
DELIVERY_FAULTS = ("receiver_unavailable",)
REQUEST_CONTENT_KEYS = {"schema_version", "review_request_id", "parent_run_id", "parent_schema_version",
                        "parent_manifest_sha256", "parent_checksums_sha256", "correction_ids",
                        "correction_record_sha256", "delivery_requested", "delivery_fault_injection",
                        "requested_by", "reason", "interface"}
COMMAND_FILES = {"command.json", "receiver.jsonl", "transport.json", "transport-error.json"}
LIMITATIONS = [
    "문서 범위 규칙 재검토다. 관측 후보 선택과 검수 WPS 행의 정확 조회만 다시 수행하며 이미지 의미·시각 관계의 모델 재해석은 하지 않았다.",
    "OCR/VLM 원문과 원래 관측 선택은 보존한다. 사람이 고른 식별자는 effective_identifier로만 표시한다.",
    "수정의 작성 주체 kind는 요청자가 선언한 값이며 신원 인증이 아니다. demo_fixture는 자동 시연용 예시이며 사람의 검수가 아니다.",
    "모의 ACK는 문서 범위값의 수신·형식 확인이며 현장 WPS 적용 승인이나 용접 실행 승인이 아니다.",
]


class ReviewRejected(CorrectionRejected):
    pass


class ReviewConflict(CorrectionConflict):
    pass


def _reject(code: str, message: str, **details: Any) -> ReviewRejected:
    return ReviewRejected(code, message, **details)


def lineage_for(parent: Path) -> list[dict[str, Any]]:
    """즉시 부모 묶음과 그 조상을 새 묶음 기준의 상대경로로 나열한다. 첫 항목이 원래 document_demo 실행이다."""
    manifest = read_json(parent / "manifest.json")
    if manifest.get("schema_version") == DOCUMENT_BUNDLE:
        ancestors = []
    elif manifest.get("schema_version") == REVIEW_BUNDLE:
        ancestors = [{**entry, "bundle_ref": f"{PARENT_REF}/{entry['bundle_ref']}"}
                     for entry in read_json(parent / "results/lineage.json")["ancestors"]]
    else:
        raise _reject("unsupported_parent", "재검토 부모로 지원하지 않는 묶음입니다.")
    return ancestors + [{"run_id": manifest["run_id"], "bundle_schema": manifest["schema_version"],
                         "run_kind": manifest["run_kind"], "manifest_sha256": sha256(parent / "manifest.json"),
                         "checksums_sha256": sha256(parent / "checksums.json"), "bundle_ref": PARENT_REF}]


def locate(parent: Path, bundle_ref: str) -> Path:
    if bundle_ref == PARENT_REF:
        return parent
    if not bundle_ref.startswith(PARENT_REF + "/"):
        raise ValueError("계보 경로가 부모 묶음 밖을 가리킵니다.")
    return safe_path(parent, bundle_ref[len(PARENT_REF) + 1:])


def effective_candidates(rows: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        selected = row.get("effective_identifier")
        if selected is not None:
            values.append(selected["value"])
        else:
            values.append(row["normalized_identifier"])
            values.extend(identifier(item["raw_text"].strip()) for item in row["vlm"])
    return list(dict.fromkeys(values))


def _issue_key(item: dict[str, Any]) -> tuple[Any, Any]:
    return item.get("code"), item.get("field")


def compare_issues(previous: list[dict], current: list[dict], applied: list[dict]) -> dict[str, Any]:
    """이전 이슈를 지우지 않고 재계산 결과와 대조한다. 해결은 수정 ID·근거와 연결한다."""
    current_keys = {_issue_key(item) for item in current}
    previous_keys = {_issue_key(item) for item in previous}
    rows = []
    for item in previous:
        if _issue_key(item) in current_keys:
            rows.append({"issue": item, "status": "open", "resolution": None, "correction_ids": [], "evidence": []})
            continue
        direct = [entry for entry in applied if entry["resolves_field"] == item.get("field")]
        rows.append({"issue": item, "status": "resolved",
                     "resolution": "direct_correction" if direct else "not_reproduced_after_recompute",
                     "correction_ids": [entry["correction_id"] for entry in direct or applied],
                     "evidence": [entry["effect"] for entry in direct]})
    new = [item for item in current if _issue_key(item) not in previous_keys]
    return {"entries": rows, "new_issues": new,
            "summary": {"previous": len(previous), "resolved": sum(row["status"] == "resolved" for row in rows),
                        "still_open": sum(row["status"] == "open" for row in rows), "new": len(new),
                        "current": len(current)}}


def compute_review(parent: Path, records: list[dict[str, Any]], *, run_id: str,
                   review_request_id: str) -> dict[str, Any]:
    """검증된 부모와 선택 수정만으로 재검토 결과를 결정적으로 계산한다. 시각·경로 정보를 넣지 않는다."""
    lineage = lineage_for(parent)
    if lineage[0]["bundle_schema"] != DOCUMENT_BUNDLE:
        raise _reject("unsupported_origin", "원래 실행은 document-demo-bundle.v1이어야 합니다.")
    origin_ref = lineage[0]["bundle_ref"]
    origin = locate(parent, origin_ref)
    for entry in lineage:
        location = locate(parent, entry["bundle_ref"])
        if (sha256(location / "manifest.json") != entry["manifest_sha256"]
                or sha256(location / "checksums.json") != entry["checksums_sha256"]):
            raise ValueError("계보의 조상 묶음 해시 불일치: " + entry["run_id"])
    origin_manifest = read_json(origin / "manifest.json")
    lineage_ids = [entry["run_id"] for entry in lineage]
    if len(set(lineage_ids)) != len(lineage_ids):
        raise ValueError("계보에 같은 run_id가 중복됩니다.")
    if run_id in set(lineage_ids) | {origin_manifest["parent_run_id"]}:
        raise _reject("run_id_reused", "재검토는 부모·조상·원래 인식 실행과 다른 새 run_id를 사용해야 합니다.", run_id=run_id)
    previous_requests = {read_json(locate(parent, entry["bundle_ref"]) / "manifest.json").get("review_request_id")
                         for entry in lineage if entry["bundle_schema"] == REVIEW_BUNDLE}
    if review_request_id in previous_requests:
        raise _reject("review_request_id_reused", "조상 재검토의 review_request_id를 다시 사용할 수 없습니다.")
    scenario, case = read_json(origin / "inputs/scenario.json"), read_json(origin / "inputs/case.json")
    orders, drawing = read_json(origin / "inputs/effective-work-orders.json"), read_json(origin / "inputs/effective-drawing.json")
    profile, wps = read_json(origin / "inputs/target_profile.json"), read_json(origin / "evidence/wps-reviewed.json")
    frame_id = case["frame_id"]
    observation = read_json(safe_path(origin, f"inputs/recognition/results/{frame_id}-observation.json"))
    base = observed_candidates(observation, scenario["observation_policy"])
    if base != read_json(origin / "results/observation-selection.json") or effective_candidates(base["observations"]) != base["candidates"]:
        raise ValueError("원래 관측 선택을 재현하지 못했습니다.")

    by_run = {entry["run_id"]: entry for entry in lineage}
    checked = []
    for record in records:
        validate_record(record)
        target = record["target"]
        if record["action"] == HOLD:
            raise _reject("hold_not_applicable", "보류 기록은 재검토에 적용할 수 없습니다. 보류는 후속 실행을 시작하지 않습니다.",
                          correction_id=record["correction_id"])
        entry = by_run.get(target["run_id"])
        if entry is None:
            raise _reject("unrelated_run", "선택한 수정이 이 재검토의 부모 계보에 없는 실행을 가리킵니다.",
                          correction_id=record["correction_id"], target_run_id=target["run_id"],
                          lineage=[item["run_id"] for item in lineage])
        if (entry["bundle_schema"], entry["manifest_sha256"], entry["checksums_sha256"]) != (
                target["bundle_schema"], target["bundle_manifest_sha256"], target["bundle_checksums_sha256"]):
            raise _reject("stale_target_bundle", "같은 run_id이지만 수정 당시와 다른 묶음입니다.",
                          correction_id=record["correction_id"])
        try:
            expected_target = evaluate_target(locate(parent, entry["bundle_ref"]), record["request"])
        except CorrectionRejected as exc:
            raise _reject(exc.code, "선택 수정을 계보의 원결과와 대조하지 못했습니다: " + exc.message,
                          correction_id=record["correction_id"], **exc.details) from exc
        if expected_target != target:
            raise _reject("invalid_correction_record", "수정 기록의 대상 정보가 원결과와 다릅니다.",
                          correction_id=record["correction_id"])
        checked.append((record, entry))

    interpretation = {"schema_version": "review-interpretation.v1", "result_id": f"{run_id}-effective-interpretation",
                      "run_id": run_id, "stage": "effective_interpretation", "producer": "rule",
                      "input_frame_ids": [frame_id],
                      "input_result_ids": [f"{origin_manifest['run_id']}:observation-selection"]
                      + [record["correction_id"] for record, _ in checked if record["action"] == SELECT],
                      "origin_run_id": origin_manifest["run_id"],
                      "original_observation_ref": f"{origin_ref}/results/observation-selection.json",
                      "original_observation_sha256": sha256(origin / "results/observation-selection.json"),
                      "policy": deepcopy(base["policy"]), "normalization": base["normalization"],
                      "observations": [{**deepcopy(row), "effective_identifier": None} for row in base["observations"]],
                      "original_candidates": list(base["candidates"]), "candidates": list(base["candidates"]),
                      "issues": deepcopy(base["issues"]), "resolved_issues": [],
                      "physical_target_resolved": False, "relation_reinterpretation": "not_performed",
                      "new_model_calls": 0, "model_outputs_reused": True}
    entries = []

    def entry_for(record: dict, lineage_entry: dict, stage: str, state: dict) -> dict[str, Any]:
        target = record["target"]
        return {"order": len(entries) + 1, "stage": stage, "correction_id": record["correction_id"],
                "action": record["action"], "source_kind": record["source_kind"], "producer": record["producer"],
                "author": deepcopy(record["author"]), "correction_reason": record["reason"],
                "target": {"run_id": target["run_id"], "bundle_ref": lineage_entry["bundle_ref"],
                           "relation_to_review": "immediate_parent" if lineage_entry is lineage[-1] else "ancestor",
                           "result_ref": target["result_ref"], "result_id": target["result_id"],
                           "result_sha256": target["result_sha256"], "field": target["field"],
                           "observation_id": target.get("observation_id")},
                "target_verified": True, "before_basis": "target_result_value_and_state_at_application",
                "before": deepcopy(record["before"]), "state_at_application": state, "after": deepcopy(record["after"])}

    # 단계 순서(관측 선택 → 문서 필드 복구)를 지키고 단계 안에서는 요청에 적은 순서로 적용한다.
    for record, lineage_entry in [item for item in checked if item[0]["action"] == SELECT]:
        observation_id = record["target"]["observation_id"]
        state = observation_state(interpretation, observation_id)
        if state is None:
            raise _reject("observation_not_in_review_frame", "재검토 프레임에 없는 관측입니다.", correction_id=record["correction_id"])
        if state != record["before"]:
            raise _reject("conflicting_or_stale_basis", "적용 시점의 값이 수정 전 값과 다릅니다. 같은 대상의 다른 수정과 충돌하거나 선행 수정을 선택하지 않았습니다.",
                          correction_id=record["correction_id"], state=state)
        selected = record["after"]["part_id"]
        row = next(item for item in interpretation["observations"] if item["ocr"]["observation_id"] == observation_id)
        chosen = ([{"observation_id": row["ocr"]["observation_id"], "engine": "ocr", "raw_text": row["ocr"]["raw_text"],
                    "producer": "model"}] if row["normalized_identifier"] == selected else [])
        chosen += [{"observation_id": item["observation_id"], "engine": "vlm", "raw_text": item["raw_text"], "producer": "model"}
                   for item in row["vlm"] if identifier(item["raw_text"].strip()) == selected]
        if not chosen:
            raise _reject("candidate_not_observed", "실제 관측 후보가 아닌 값입니다.", correction_id=record["correction_id"])
        row["effective_identifier"] = {"value": selected, "source_kind": record["source_kind"], "producer": record["producer"],
                                       "correction_id": record["correction_id"], "chosen_from": chosen,
                                       "ocr_raw_text_preserved": row["ocr"]["raw_text"]}
        moved = [item for item in interpretation["issues"] if item.get("field") == observation_id]
        interpretation["issues"] = [item for item in interpretation["issues"] if item.get("field") != observation_id]
        interpretation["resolved_issues"] += [{"issue": item, "resolved_by_correction_id": record["correction_id"],
                                               "resolution": "observed_candidate_selected_by_" + record["source_kind"],
                                               "evidence": chosen} for item in moved]
        interpretation["candidates"] = effective_candidates(interpretation["observations"])
        entries.append({**entry_for(record, lineage_entry, "observation", state), "status": "applied", "status_reason": None,
                        "resolves_field": observation_id,
                        "effect": {"effective_identifier": selected, "chosen_from": chosen,
                                   "moved_issue_codes": [item["code"] for item in moved]}})

    order_path, drawing_path = origin / "inputs/effective-work-orders.json", origin / "inputs/effective-drawing.json"

    def make(lifted: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        faults = [item for item in case["faults"] if not (item["op"] == "omit_parameter" and item["field"] in lifted)]
        spec, matching = build_spec(run_id=run_id, observed=interpretation, scenario=scenario, orders=deepcopy(orders),
                                    drawing=deepcopy(drawing), wps=wps, profile=profile, order_path=order_path,
                                    drawing_path=drawing_path, faults=faults)
        return deepcopy(spec), deepcopy(matching)

    lifted: list[str] = []
    restorations = []
    for record, lineage_entry in [item for item in checked if item[0]["action"] == RESTORE]:
        name = record["target"]["field"].split(".", 1)[1]
        current, _ = make(lifted)
        state = parameter_state(current, name)
        if state != record["before"]:
            raise _reject("conflicting_or_stale_basis", "적용 시점의 파라미터 상태가 수정 전 값과 다릅니다.",
                          correction_id=record["correction_id"], state=state)
        location = wps_location(current, orders, wps)
        status, reason, field = "applied", None, None
        if location is None or location != record["after"]:
            status, reason = "not_applied", "document_reference_unavailable_or_mismatch_in_current_review"
        elif reviewed_wps_field(wps, location["row_id"], name) is None:
            status, reason = "not_applied", "document_field_unavailable"
        else:
            trial, _ = make(lifted + [name])
            field = trial["parameters"].get(name)
            if field is None:
                status, reason = "not_applied", "document_field_not_produced"
            else:
                lifted.append(name)
        overridden = [item for item in case["faults"] if item["op"] == "omit_parameter" and item["field"] == name]
        effect = {"parameter": name, "value_source": "document_exact_lookup", "document": deepcopy(record["after"]),
                  "evidence": deepcopy(field["evidence"]) if field else None,
                  "restored_value": {key: field[key] for key in ("min", "max", "value", "unit", "raw_value") if key in field} if field else None,
                  "overrides_fault_injection": overridden if field else []}
        restorations.append({"correction_id": record["correction_id"], "parameter": name, "status": status, "reason": reason,
                             "requested_by_source_kind": record["source_kind"], "producer": "rule", **{k: effect[k] for k in
                             ("value_source", "document", "evidence", "overrides_fault_injection")}})
        entries.append({**entry_for(record, lineage_entry, "document_parameter", state), "status": status, "status_reason": reason,
                        "resolves_field": f"parameters.{name}", "effect": effect})

    spec, matching = make(lifted)
    for item in restorations:
        if item["status"] == "applied":
            spec["parameters"][item["parameter"]]["restored_by_correction_id"] = item["correction_id"]
            spec["parameters"][item["parameter"]]["restoration"] = {
                "value_source": "document_exact_lookup", "requested_by_source_kind": item["requested_by_source_kind"],
                "producer": "rule"}
    selections = [row["effective_identifier"] for row in interpretation["observations"] if row["effective_identifier"]]
    used = [item for item in selections if item["value"] == spec["target"].get("part_id")]
    if spec["target_evidence"] and used:
        kinds = sorted({item["source_kind"] for item in used})
        spec["target_evidence"]["part_id"] = {"source_kind": kinds[0] if len(kinds) == 1 else "mixed",
                                              "selected_by_correction_ids": [item["correction_id"] for item in used],
                                              "model_observations": deepcopy(interpretation["observations"])}
    spec.update(schema_version="review-work-spec.v1", base_schema_version="document-work-spec.v1",
                fault_injections=deepcopy(case["faults"]), parameter_restorations=restorations,
                review={"review_request_id": review_request_id, "parent_run_id": lineage[-1]["run_id"],
                        "origin_run_id": origin_manifest["run_id"],
                        "correction_ids": [record["correction_id"] for record, _ in checked],
                        "interpretation_ref": "results/effective-interpretation.json",
                        "scope": "document_rule_review", "relation_reinterpretation": "not_performed",
                        "new_model_calls": 0})
    matching["result_id"] = f"{run_id}-matching"
    applied = [entry for entry in entries if entry["status"] == "applied"]
    parent_spec = read_json(parent / "results/work-spec.json")
    origin_spec = read_json(origin / "results/work-spec.json")
    resolution = {"schema_version": "review-issue-resolution.v1", "result_id": f"{run_id}-issue-resolution",
                  "run_id": run_id, "producer": "rule", "current_spec_id": spec["spec_id"],
                  "against_parent": {"run_id": lineage[-1]["run_id"], "spec_id": parent_spec["spec_id"],
                                     **compare_issues(parent_spec["validation"]["issues"], spec["validation"]["issues"], applied)},
                  "against_origin": {"run_id": origin_manifest["run_id"], "spec_id": origin_spec["spec_id"],
                                     **compare_issues(origin_spec["validation"]["issues"], spec["validation"]["issues"], applied)},
                  "observation_issues_resolved": deepcopy(interpretation["resolved_issues"]),
                  "issues_cleared_without_recompute": 0}
    application = {"schema_version": "review-correction-application.v1", "result_id": f"{run_id}-correction-application",
                   "run_id": run_id, "producer": "rule", "selection_order": [record["correction_id"] for record, _ in checked],
                   "application_policy": "stage_order_observation_then_document_parameter; request_order_within_stage",
                   "entries": entries, "unselected_store_records_read": False}
    lineage_result = {"schema_version": "review-lineage.v1", "run_id": run_id, "parent_run_id": lineage[-1]["run_id"],
                      "origin_run_id": origin_manifest["run_id"], "recognition_run_id": origin_manifest["parent_run_id"],
                      "ancestors": lineage, "depth": len(lineage)}
    return {"lineage": lineage_result, "interpretation": interpretation, "application": application,
            "matching": matching, "spec": spec, "resolution": resolution, "profile": profile,
            "origin_manifest": origin_manifest}


RESULT_FILES = {"lineage": "results/lineage.json", "interpretation": "results/effective-interpretation.json",
                "application": "results/correction-application.json", "matching": "results/matching.json",
                "spec": "results/work-spec.json", "resolution": "results/issue-resolution.json"}


def request_content(*, review_request_id: str, parent: Path, records: list[dict], deliver: bool,
                    delivery_fault: str | None, requested_by: dict, reason: str) -> dict[str, Any]:
    manifest = read_json(parent / "manifest.json")
    return {"schema_version": REQUEST_SCHEMA, "review_request_id": review_request_id, "parent_run_id": manifest["run_id"],
            "parent_schema_version": manifest["schema_version"], "parent_manifest_sha256": sha256(parent / "manifest.json"),
            "parent_checksums_sha256": sha256(parent / "checksums.json"),
            "correction_ids": [record["correction_id"] for record in records],
            "correction_record_sha256": {record["correction_id"]: digest(record) for record in records},
            "delivery_requested": bool(deliver), "delivery_fault_injection": delivery_fault,
            "requested_by": deepcopy(requested_by), "reason": reason, "interface": REQUEST_INTERFACE}


class ReviewRun:
    """새 run_id의 재검토 묶음. 완료 경로에는 검증을 통과한 묶음만 원자적으로 공개한다."""

    def __init__(self, output_root: Path, run_id: str, manifest: dict[str, Any]) -> None:
        if not valid_id(run_id):
            raise ValueError("유효하지 않은 run_id")
        output_root.mkdir(parents=True, exist_ok=True)
        self.final = output_root / f"run_{run_id}"
        self.root = output_root / f"run_{run_id}.incomplete"
        if self.final.exists() or self.root.exists():
            raise FileExistsError("기존 실행을 덮어쓸 수 없습니다. 새 run_id를 사용하세요.")
        self.root.mkdir()
        for name in ("inputs", "inputs/corrections", "results", "commands"):
            (self.root / name).mkdir()
        (self.root / "events.jsonl").touch()
        (self.root / "corrections.jsonl").touch()
        self.started, self.seq = time.monotonic(), 0
        self.manifest = {**manifest, "started_at_utc": utc_now(), "export_status": "in_progress", "run_outcome": "running"}
        write_json(self.root / "manifest.json", self.manifest)

    def event(self, stage: str, ref: str, *, producer: str, event_type: str = "stage_completed",
              input_result_ids: list[str] | None = None, request_id: str | None = None,
              command_id: str | None = None) -> None:
        self.seq += 1
        event = {"run_id": self.manifest["run_id"], "event_id": f"event-{self.seq:04d}", "seq": self.seq,
                 "type": event_type, "stage": stage, "producer": producer, "recorded_at_utc": utc_now(),
                 "elapsed_ms": round((time.monotonic() - self.started) * 1000),
                 "parent_event_ids": [f"event-{self.seq - 1:04d}"] if self.seq > 1 else [],
                 "input_frame_ids": [self.manifest["frame_id"]], "input_result_ids": input_result_ids or [],
                 "request_id": request_id, "command_id": command_id, "payload_ref": ref}
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def finish(self, outcome: str) -> Path:
        self.manifest.update(run_outcome=outcome, export_status="complete", finished_at_utc=utc_now(),
                             elapsed_seconds=round(time.monotonic() - self.started, 3))
        self.event("export", "manifest.json", producer="system", event_type="export_completed")
        self.manifest["files"] = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        write_json(self.root / "manifest.json", self.manifest)
        write_json(self.root / "checksums.json", {name: sha256(safe_path(self.root, name)) for name in self.manifest["files"]})
        inspect_review_bundle(self.root)
        self.root.rename(self.final)
        return self.final

    def fail(self, exc: BaseException) -> None:
        self.manifest.update(run_outcome="failed", export_status="incomplete", finished_at_utc=utc_now(),
                             error_type=type(exc).__name__, error=str(exc))
        write_json(self.root / "manifest.json", self.manifest)
        try:
            self.event("failure", "manifest.json", producer="system", event_type="run_failed")
        except OSError:
            pass


def _receipt_summary(log: Path, command_id: str) -> dict[str, Any]:
    """수신기 원본 기록에서 이 명령의 수신 여부를 요약한다. 클라이언트 ACK 확인과 구분한다."""
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    mine = [row for row in rows if isinstance(row.get("ack"), dict) and row["ack"].get("command_id") == command_id]
    side = ("received" if any(row["ack"].get("status") == "received" for row in mine)
            else "rejected" if mine else "none")
    return {"receiver_side": side, "receiver_records": len(rows)}


def _deliver(run: ReviewRun, spec: dict[str, Any], profile: dict[str, Any], fault: str | None,
             timeout: float) -> dict[str, Any]:
    from contextweld.mock_delivery import MockReceiver, send_command
    command = command_from_spec(spec, profile)
    write_json(run.root / "commands/command.json", command)
    run.event("command_prepared", "commands/command.json", producer="rule", command_id=command["command_id"],
              input_result_ids=[spec["spec_id"]])
    log = run.root / "commands/receiver.jsonl"
    endpoint = None
    base = {"requested": True, "attempted": True, "command_id": command["command_id"], "transport": "loopback_http",
            "receiver_log_ref": "commands/receiver.jsonl", "fault_injection": fault}
    try:
        if fault == "receiver_unavailable":
            # 시연용 결함: 수신기를 연 뒤 닫아 실제 loopback 연결 실패를 만든다. 응답을 만들지 않는다.
            with MockReceiver(profile, log) as receiver:
                endpoint = receiver.url
            transport = send_command(endpoint, command, timeout=timeout)
        else:
            with MockReceiver(profile, log) as receiver:
                endpoint = receiver.url
                transport = send_command(endpoint, command, timeout=timeout)
    except (OSError, ValueError, HTTPException) as exc:
        receipts = _receipt_summary(log, command["command_id"])
        write_json(run.root / "commands/transport-error.json", {
            "schema_version": "review-delivery-error.v1", "command_id": command["command_id"], "endpoint": endpoint,
            "request_sha256": digest(command), "request": command, "error_type": type(exc).__name__, "error": str(exc),
            "http_status": getattr(exc, "http_status", None), "raw_response": getattr(exc, "raw_response", None),
            "ack": None, "client_ack_confirmed": False, **receipts, "fault_injection": fault,
            "note": ("수신기 기록에는 수신됐으나 클라이언트가 ACK를 확인하지 못했다. 성공으로 바꾸거나 같은 명령을 자동 재전송하지 않는다."
                     if receipts["receiver_side"] == "received" else None),
            "recorded_at_utc": utc_now()})
        run.event("mock_transport", "commands/transport-error.json", producer="system", event_type="delivery_failed",
                  command_id=command["command_id"])
        return {**base, "status": "failed", "transport_ref": None, "error_ref": "commands/transport-error.json",
                "client_ack_confirmed": False, "receiver_side": receipts["receiver_side"]}
    write_json(run.root / "commands/transport.json", transport)
    run.event("mock_transport", "commands/transport.json", producer="system", command_id=command["command_id"])
    ack = transport.get("ack") or {}
    received = (transport.get("http_status") == 200 and ack.get("status") == "received"
                and ack.get("command_id") == command["command_id"])
    return {**base, "status": "received" if received else "rejected", "transport_ref": "commands/transport.json",
            "error_ref": None, "client_ack_confirmed": received,
            "receiver_side": _receipt_summary(log, command["command_id"])["receiver_side"]}


def ledger_dir(store: Path) -> Path:
    """요청 ID 등록 위치. 출력 위치와 무관하게 수정 저장소마다 하나로 고정해 중복 실행·전송을 막는다."""
    return Path(store) / "review-requests"


def _ledger_outcome(path: Path, request_sha256: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    entry = read_json(path)
    if entry.get("request_sha256") != request_sha256:
        raise ReviewConflict("review_request_id_conflict", "같은 review_request_id에 다른 요청 내용이 이미 등록되어 있습니다.",
                             path=str(path))
    final = Path(entry["output_root"]) / f"run_{entry['run_id']}"
    incomplete = final.with_name(final.name + ".incomplete")
    result = {"status": "duplicate_request", "review_request_id": entry["review_request_id"], "run_id": entry["run_id"],
              "new_run_created": False, "delivery_attempted_again": False}
    for location in (final, incomplete):
        if not location.is_dir():
            continue
        manifest = read_json(location / "manifest.json")
        request = read_json(location / "inputs/review-request.json") if (location / "inputs/review-request.json").is_file() else {}
        # 등록된 실행이 실제로 이 요청의 실행인지 확인한다. 다른 요청의 ACK를 돌려주지 않는다.
        if manifest.get("review_request_id") != entry["review_request_id"] or request.get("request_sha256") != request_sha256:
            raise ReviewConflict("ledger_run_mismatch", "등록된 실행 경로에 다른 요청의 실행이 있습니다. 새 review_request_id를 사용하세요.",
                                 path=str(location))
        found = {**result, "bundle": str(location), "run_outcome": manifest["run_outcome"],
                 "delivery_status": manifest.get("delivery_status"), "export_status": manifest["export_status"]}
        if location == incomplete:
            found["note"] = "이전 시도는 미완료로 보존됨. 다시 실행하려면 새 review_request_id와 run_id를 사용하세요."
        return found
    return {**result, "bundle": None, "note": "등록된 실행 경로를 찾지 못했습니다(이동·삭제). 새 review_request_id를 사용하세요."}


def run_review(*, repo: Path, parent_bundle: Path, store: Path, correction_ids: list[str], review_request_id: str,
               run_id: str, output_root: Path, requested_by: dict[str, str], reason: str, deliver: bool = False,
               delivery_fault: str | None = None, timeout: float = 5) -> dict[str, Any]:
    """명시적 재검토 요청 1건을 실행한다. 전달은 deliver=True일 때만 새 실행 안에서 수행한다."""
    if not valid_id(review_request_id) or not valid_id(run_id):
        raise _reject("invalid_request", "review_request_id/run_id 형식이 올바르지 않습니다.")
    if (not isinstance(requested_by, dict) or set(requested_by) != {"kind", "id"}
            or requested_by["kind"] not in AUTHOR_KINDS or not valid_id(requested_by["id"])):
        raise _reject("invalid_request", "requested_by는 {kind: user|demo_fixture, id}여야 합니다.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise _reject("invalid_request", "재검토 요청 사유가 필요합니다.")
    if type(deliver) is not bool or (delivery_fault is not None and (delivery_fault not in DELIVERY_FAULTS or not deliver)):
        raise _reject("invalid_request", "전달 결함 주입은 --deliver와 함께 지원 값만 사용할 수 있습니다.")
    parent, output_root, store = Path(parent_bundle), Path(output_root), Path(store)
    for path in (output_root, store):
        inside = enclosing_bundle(path)
        if inside is not None or path.resolve().is_relative_to(parent.resolve()):
            raise _reject("output_inside_bundle", "실행 묶음 안에는 새 실행·요청 기록을 만들 수 없습니다.", bundle=str(inside or parent))
    try:
        inspect_bundle(parent)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise _reject("parent_unverified", "부모 묶음을 검증하지 못했습니다: " + str(exc)) from exc
    loaded = load_selected(store, list(correction_ids))
    records = [record for record, _ in loaded]
    content = request_content(review_request_id=review_request_id, parent=parent, records=records, deliver=deliver,
                              delivery_fault=delivery_fault, requested_by=requested_by, reason=reason)
    request_sha256 = digest(content)
    ledger_path = ledger_dir(store) / f"{review_request_id}.json"
    previous = _ledger_outcome(ledger_path, request_sha256)
    if previous is not None:
        return previous
    plan = compute_review(parent, records, run_id=run_id, review_request_id=review_request_id)
    origin = plan["origin_manifest"]
    manifest = {"schema_version": SCHEMA, "spec_version": SPEC_VERSION, "run_id": run_id, "run_kind": "review",
                "capture_mode": origin["capture_mode"], "evaluation_scope": "document_review",
                "review_scope": "document_rule_review", "scenario_id": origin["scenario_id"], "case": origin["case"],
                "frame_id": origin["frame_id"], "parent_run_id": content["parent_run_id"],
                "parent_schema_version": content["parent_schema_version"],
                "parent_manifest_sha256": content["parent_manifest_sha256"],
                "parent_checksums_sha256": content["parent_checksums_sha256"], "parent_bundle_ref": PARENT_REF,
                "origin_run_id": origin["run_id"], "recognition_run_id": origin["parent_run_id"],
                "lineage_ref": RESULT_FILES["lineage"], "review_request_id": review_request_id,
                "correction_ids": content["correction_ids"],
                "correction_source_kinds": sorted({record["source_kind"] for record in records}),
                "requested_by": deepcopy(requested_by), "delivery_requested": deliver,
                "delivery_fault_injection": delivery_fault, "execution_authorized": False,
                "application_authorized": False, "demo_complete": False, "inference_reused": True,
                "new_model_calls": 0, "relation_reinterpretation": "not_performed", "ocr_rewritten": False,
                "delivery_status": None, "source_document_originals_included": False,
                "limitations": LIMITATIONS + origin.get("limitations", [])}
    # 실행 디렉토리를 먼저 배타적으로 확보한 뒤 요청 ID를 등록한다.
    run = ReviewRun(output_root, run_id, manifest)
    ledger_entry = {"schema_version": "review-request-ledger.v1", "review_request_id": review_request_id,
                    "request_sha256": request_sha256, "run_id": run_id, "output_root": str(output_root.resolve()),
                    "registered_at_utc": utc_now()}
    if not _write_exclusive(ledger_path, json.dumps(ledger_entry, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"):
        conflict = ReviewConflict("review_request_race", "같은 review_request_id가 동시에 등록되어 이 시도는 실행하지 않았습니다.")
        run.fail(conflict)
        return _ledger_outcome(ledger_path, request_sha256) or {"status": "duplicate_request", "run_id": None}
    try:
        requester_producer = AUTHOR_KINDS[requested_by["kind"]][1]
        write_json(run.root / "inputs/review-request.json", {**content, "request_sha256": request_sha256,
                                                             "run_id": run_id, "requested_at_utc": run.manifest["started_at_utc"]})
        run.event("review_request", "inputs/review-request.json", producer=requester_producer,
                  event_type="review_requested", request_id=review_request_id)
        shutil.copytree(parent, run.root / PARENT_REF)
        for record, raw in loaded:
            (run.root / f"inputs/corrections/{record['correction_id']}.json").write_bytes(raw)
        with (run.root / "corrections.jsonl").open("w", encoding="utf-8") as stream:
            for record, _ in loaded:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        source_files = ["src/contextweld/review.py", "src/contextweld/corrections.py", "src/contextweld/workflow.py",
                        "src/contextweld/mock_delivery.py", "src/contextweld/matching.py", "scripts/run/run_review.py",
                        "scripts/run/record_correction.py", "scripts/verify/verify_review_bundle.py"]
        write_json(run.root / "inputs/environment.json", {
            "environment": environment_record(repo),
            "code_hashes": {name: sha256(repo / name) for name in source_files if (repo / name).is_file()},
            "parent_bundle_name": parent.name, "correction_store_read": "selected_ids_only"})
        run.event("input_snapshot", "inputs/environment.json", producer="system", request_id=review_request_id)
        copied = [read_json(run.root / f"inputs/corrections/{cid}.json") for cid in content["correction_ids"]]
        results = compute_review(run.root / PARENT_REF, copied, run_id=run_id, review_request_id=review_request_id)
        if {key: results[key] for key in RESULT_FILES} != {key: plan[key] for key in RESULT_FILES}:
            raise ValueError("부모 사본으로 재계산한 결과가 사전 계산과 다릅니다.")
        write_json(run.root / RESULT_FILES["lineage"], results["lineage"])
        run.event("lineage_verified", RESULT_FILES["lineage"], producer="rule", request_id=review_request_id)
        for record in copied:
            run.event("correction_selected", f"inputs/corrections/{record['correction_id']}.json", producer=record["producer"],
                      event_type="correction_selected", input_result_ids=[record["target"]["result_id"]],
                      request_id=review_request_id)
        for key, stage in RULE_STAGES:
            write_json(run.root / RESULT_FILES[key], results[key])
            run.event(stage, RESULT_FILES[key], producer="rule", request_id=review_request_id,
                      input_result_ids=[results[key]["result_id"]] if key in {"interpretation", "matching"} else [])
        spec = results["spec"]
        if spec["validation"]["issues"] or not deliver:
            delivery = expected_unsent_delivery(spec, deliver)
            outcome = "needs_review" if spec["validation"]["issues"] else "succeeded"
        else:
            delivery = _deliver(run, spec, results["profile"], delivery_fault, timeout)
            outcome = "succeeded" if delivery["status"] == "received" else "failed"
        write_json(run.root / "results/delivery.json", delivery)
        run.event("delivery_result", "results/delivery.json", producer="rule", request_id=review_request_id,
                  command_id=delivery.get("command_id"))
        run.manifest["delivery_status"] = delivery["status"]
        final = run.finish(outcome)
    except BaseException as exc:
        run.fail(exc)
        raise
    return {"status": "completed", "bundle": str(final), "run_id": run_id, "review_request_id": review_request_id,
            "run_outcome": outcome, "delivery_status": delivery["status"], "delivery_fault_injection": delivery_fault,
            "issues": len(spec["validation"]["issues"]), "demo_complete": False}


RULE_STAGES = (("interpretation", "observation_reselection"), ("application", "correction_application"),
               ("matching", "work_order_matching"), ("spec", "document_fields_and_validation"),
               ("resolution", "issue_resolution"))
MANIFEST_KEYS = {"schema_version", "spec_version", "run_id", "run_kind", "capture_mode", "evaluation_scope", "review_scope",
                 "scenario_id", "case", "frame_id", "parent_run_id", "parent_schema_version", "parent_manifest_sha256",
                 "parent_checksums_sha256", "parent_bundle_ref", "origin_run_id", "recognition_run_id", "lineage_ref",
                 "review_request_id", "correction_ids", "correction_source_kinds", "requested_by", "delivery_requested",
                 "delivery_fault_injection", "execution_authorized", "application_authorized", "demo_complete",
                 "inference_reused", "new_model_calls", "relation_reinterpretation", "ocr_rewritten", "delivery_status",
                 "source_document_originals_included", "limitations", "started_at_utc", "export_status", "run_outcome",
                 "finished_at_utc", "elapsed_seconds", "files"}
LOOPBACK = re.compile(r"http://127\.0\.0\.1:[0-9]{1,5}/commands")


def expected_unsent_delivery(spec: dict[str, Any], deliver: bool) -> dict[str, Any]:
    if spec["validation"]["issues"]:
        return {"requested": deliver, "attempted": False, "status": "blocked" if deliver else "not_requested",
                "reason": "validation_issues_remain"}
    return {"requested": False, "attempted": False, "status": "not_requested", "reason": None}


def _check_ack(ack: Any, command: dict[str, Any], body_sha: str) -> None:
    if (not isinstance(ack, dict) or ack.get("schema_version") != "demo-ack.v1" or ack.get("command_id") != command["command_id"]
            or ack.get("command_sha256") != body_sha or ack.get("purpose") != "demo_mock"
            or ack.get("evaluation_scope") != "document_review" or ack.get("execution_authorized") is not False
            or ack.get("application_authorized") is not False or ack.get("duplicate") is not False):
        raise ValueError("모의 ACK 계약 불일치")


def inspect_review_bundle(root: Path) -> dict[str, Any]:
    """해시뿐 아니라 부모 계보·선택 수정의 대상/원값/출처·재검토 재계산·요청/전달·사건 구조의 일치를 확인한다."""
    root = Path(root)
    manifest, checksums = read_json(root / "manifest.json"), read_json(root / "checksums.json")
    if manifest.get("schema_version") != SCHEMA or manifest.get("export_status") != "complete" or set(manifest) != MANIFEST_KEYS:
        raise ValueError("지원하지 않거나 불완전한 재검토 묶음")
    constants = {"spec_version": SPEC_VERSION, "run_kind": "review", "evaluation_scope": "document_review",
                 "review_scope": "document_rule_review", "parent_bundle_ref": PARENT_REF, "lineage_ref": RESULT_FILES["lineage"],
                 "execution_authorized": False, "application_authorized": False, "demo_complete": False,
                 "inference_reused": True, "new_model_calls": 0, "relation_reinterpretation": "not_performed",
                 "ocr_rewritten": False, "source_document_originals_included": False}
    if any(manifest[key] != value or type(manifest[key]) is not type(value) for key, value in constants.items()):
        raise ValueError("재검토 실행 범위·승인 표시 불일치")
    deliver, fault = manifest["delivery_requested"], manifest["delivery_fault_injection"]
    if type(deliver) is not bool or (fault is not None and (fault not in DELIVERY_FAULTS or deliver is not True)):
        raise ValueError("전달 요청·결함 주입 표시 불일치")
    if not manifest["started_at_utc"] <= manifest["finished_at_utc"]:
        raise ValueError("실행 시각 순서 불일치")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"checksums.json"}
    if actual != set(checksums) or actual != set(manifest["files"]):
        raise ValueError("묶음 파일 목록 불일치")
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("묶음 안의 symlink는 허용하지 않습니다.")
    for ref, value in checksums.items():
        if sha256(safe_path(root, ref)) != value:
            raise ValueError("묶음 파일 해시 불일치: " + ref)
    parent = safe_path(root, PARENT_REF)
    parent_manifest = read_json(parent / "manifest.json")
    if parent_manifest.get("schema_version") == DOCUMENT_BUNDLE:
        inspect_document_bundle(parent)
    elif parent_manifest.get("schema_version") == REVIEW_BUNDLE:
        inspect_review_bundle(parent)
    else:
        raise ValueError("지원하지 않는 부모 묶음")
    if (manifest["parent_run_id"] != parent_manifest["run_id"] or manifest["parent_schema_version"] != parent_manifest["schema_version"]
            or manifest["parent_manifest_sha256"] != sha256(parent / "manifest.json")
            or manifest["parent_checksums_sha256"] != sha256(parent / "checksums.json")):
        raise ValueError("즉시 부모 실행 연결 불일치")
    request = read_json(root / "inputs/review-request.json")
    content = {key: request.get(key) for key in REQUEST_CONTENT_KEYS}
    if (set(request) != REQUEST_CONTENT_KEYS | {"request_sha256", "run_id", "requested_at_utc"}
            or request["request_sha256"] != digest(content) or request["run_id"] != manifest["run_id"]
            or request["schema_version"] != REQUEST_SCHEMA or request["interface"] not in ACCEPTED_REQUEST_INTERFACES
            or request["requested_at_utc"] != manifest["started_at_utc"] or not isinstance(request["reason"], str)
            or not request["reason"].strip()):
        raise ValueError("재검토 요청 스냅샷 불일치")
    requested_by = manifest["requested_by"]
    if (not isinstance(requested_by, dict) or set(requested_by) != {"kind", "id"} or requested_by["kind"] not in AUTHOR_KINDS
            or not valid_id(requested_by["id"])):
        raise ValueError("요청자 표시 불일치")
    for key in ("review_request_id", "parent_run_id", "parent_schema_version", "parent_manifest_sha256",
                "parent_checksums_sha256", "correction_ids", "requested_by", "delivery_fault_injection"):
        if request[key] != manifest[key]:
            raise ValueError("요청과 manifest 불일치: " + key)
    if request["delivery_requested"] is not deliver:
        raise ValueError("요청과 manifest 불일치: delivery_requested")
    ids = request["correction_ids"]
    if not ids or len(set(ids)) != len(ids) or not all(valid_id(item) for item in ids):
        raise ValueError("선택 수정 ID 목록 불일치")
    records = [read_json(root / f"inputs/corrections/{item}.json") for item in ids]
    for item, record in zip(ids, records):
        validate_record(record)
        if record["correction_id"] != item or request["correction_record_sha256"].get(item) != digest(record):
            raise ValueError("수정 기록 스냅샷 불일치: " + item)
    if set(request["correction_record_sha256"]) != set(ids):
        raise ValueError("수정 기록 해시 목록 불일치")
    lines = [json.loads(line) for line in (root / "corrections.jsonl").read_text(encoding="utf-8").splitlines()]
    if lines != records:
        raise ValueError("corrections.jsonl 스냅샷 불일치")
    if manifest["correction_source_kinds"] != sorted({record["source_kind"] for record in records}):
        raise ValueError("수정 작성 주체 표시 불일치")
    try:
        results = compute_review(parent, records, run_id=manifest["run_id"], review_request_id=manifest["review_request_id"])
    except CorrectionRejected as exc:
        raise ValueError("선택 수정을 계보에 적용할 수 없습니다: " + str(exc)) from exc
    for key, ref in RESULT_FILES.items():
        if read_json(root / ref) != results[key]:
            raise ValueError("재검토 결과 재계산 불일치: " + ref)
    origin, lineage = results["origin_manifest"], results["lineage"]
    if ((manifest["origin_run_id"], manifest["recognition_run_id"], manifest["case"], manifest["frame_id"],
         manifest["scenario_id"], manifest["capture_mode"]) != (origin["run_id"], origin["parent_run_id"], origin["case"],
                                                                origin["frame_id"], origin["scenario_id"], origin["capture_mode"])
            or lineage["parent_run_id"] != manifest["parent_run_id"]
            or manifest["limitations"] != LIMITATIONS + origin.get("limitations", [])):
        raise ValueError("원래 실행·계보·한계 표시 불일치")
    spec, profile = results["spec"], results["profile"]
    delivery = read_json(root / "results/delivery.json")
    commands_dir = root / "commands"
    if commands_dir.exists() and not commands_dir.is_dir():
        raise ValueError("commands는 디렉토리여야 합니다.")
    # 빈 commands/는 복사 과정에서 사라질 수 있으므로 없음과 빈 디렉토리를 같게 본다.
    commands = sorted(p.name for p in commands_dir.iterdir()) if commands_dir.is_dir() else []
    sent = not spec["validation"]["issues"] and deliver
    if not sent:
        if delivery != expected_unsent_delivery(spec, deliver) or commands:
            raise ValueError("보류·미요청 실행에 전송 시도나 명령/수신 기록이 있습니다.")
    else:
        from contextweld.mock_delivery import validate_command
        command = read_json(root / "commands/command.json")
        body_sha = digest(command)
        if command != command_from_spec(spec, profile) or validate_command(command, profile):
            raise ValueError("명세와 모의 명령 불일치")
        receipts = [json.loads(line) for line in (root / "commands/receiver.jsonl").read_text(encoding="utf-8").splitlines()] \
            if "receiver.jsonl" in commands else []
        for row in receipts:
            if not isinstance(row, dict) or set(row) != {"seq", "request_sha256", "raw_request", "command", "body_read", "http_status", "ack"}:
                raise ValueError("수신기 원본 기록 형식 불일치")
        summary = _receipt_summary(root / "commands/receiver.jsonl", command["command_id"])
        base = {"requested": True, "attempted": True, "command_id": command["command_id"], "transport": "loopback_http",
                "receiver_log_ref": "commands/receiver.jsonl", "fault_injection": fault,
                "receiver_side": summary["receiver_side"]}
        if delivery.get("status") == "failed":
            error = read_json(root / "commands/transport-error.json")
            expected_files = {"command.json", "transport-error.json"} | ({"receiver.jsonl"} if "receiver.jsonl" in commands else set())
            if (set(commands) != expected_files
                    or delivery != {**base, "status": "failed", "transport_ref": None, "error_ref": "commands/transport-error.json",
                                    "client_ack_confirmed": False}
                    or error.get("ack") is not None or error.get("client_ack_confirmed") is not False
                    or error.get("command_id") != command["command_id"] or error.get("request") != command
                    or error.get("request_sha256") != body_sha or error.get("fault_injection") != fault
                    or error.get("receiver_side") != summary["receiver_side"]
                    or (error.get("endpoint") is not None and not LOOPBACK.fullmatch(error["endpoint"]))):
                raise ValueError("전달 실패 기록 불일치")
            if fault == "receiver_unavailable" and receipts:
                raise ValueError("수신기 미가동 결함인데 수신 기록이 있습니다.")
        else:
            if fault is not None:
                raise ValueError("결함 주입 실행이 정상 전달로 기록되어 있습니다.")
            transport = read_json(root / "commands/transport.json")
            ack = transport.get("ack")
            _check_ack(ack, command, body_sha)
            received = transport.get("http_status") == 200 and ack.get("status") == "received" and not ack.get("validation_errors")
            status = "received" if received else "rejected"
            if (set(commands) != {"command.json", "receiver.jsonl", "transport.json"} or transport.get("request") != command
                    or transport.get("request_sha256") != body_sha or transport.get("transport") != "http_loopback"
                    or transport.get("schema_version") != "demo-delivery.v1" or not LOOPBACK.fullmatch(str(transport.get("endpoint")))
                    or delivery != {**base, "status": status, "transport_ref": "commands/transport.json", "error_ref": None,
                                    "client_ack_confirmed": received}):
                raise ValueError("전송 본문·응답·전달 기록 불일치")
            if (len(receipts) != 1 or receipts[0]["command"] != command or receipts[0]["ack"] != ack
                    or receipts[0]["http_status"] != transport["http_status"] or json.loads(receipts[0]["raw_request"]) != command
                    or receipts[0]["request_sha256"] != body_sha):
                raise ValueError("수신기 원본 요청/응답 불일치")
    expected_outcome = ("needs_review" if spec["validation"]["issues"] else
                        "succeeded" if delivery["status"] in {"not_requested", "received"} else "failed")
    if manifest["run_outcome"] != expected_outcome or manifest["delivery_status"] != delivery["status"]:
        raise ValueError("요청 범위의 결과 상태 불일치")
    expected_files = ({"manifest.json", "events.jsonl", "corrections.jsonl", "inputs/review-request.json",
                       "inputs/environment.json", "results/delivery.json", *RESULT_FILES.values()}
                      | {f"inputs/corrections/{item}.json" for item in ids} | {f"commands/{name}" for name in commands}
                      | {f"{PARENT_REF}/{ref}" for ref in read_json(parent / "checksums.json")} | {f"{PARENT_REF}/checksums.json"})
    if actual != expected_files:
        raise ValueError("재검토 묶음에 예상하지 않은 파일이 있거나 필요한 파일이 없습니다.")
    events = [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    request_id, requester = manifest["review_request_id"], AUTHOR_KINDS[requested_by["kind"]][1]
    skeleton = [("review_requested", "review_request", requester, "inputs/review-request.json", None, request_id),
                ("stage_completed", "input_snapshot", "system", "inputs/environment.json", None, request_id),
                ("stage_completed", "lineage_verified", "rule", RESULT_FILES["lineage"], None, request_id)]
    skeleton += [("correction_selected", "correction_selected", record["producer"],
                  f"inputs/corrections/{record['correction_id']}.json", None, request_id) for record in records]
    skeleton += [("stage_completed", stage, "rule", RESULT_FILES[key], None, request_id) for key, stage in RULE_STAGES]
    if sent:
        command_id = delivery["command_id"]
        skeleton += [("stage_completed", "command_prepared", "rule", "commands/command.json", command_id, None),
                     ("delivery_failed", "mock_transport", "system", "commands/transport-error.json", command_id, None)
                     if delivery["status"] == "failed" else
                     ("stage_completed", "mock_transport", "system", "commands/transport.json", command_id, None)]
    skeleton += [("stage_completed", "delivery_result", "rule", "results/delivery.json", delivery.get("command_id"), request_id),
                 ("export_completed", "export", "system", "manifest.json", None, None)]
    observed = [(e.get("type"), e.get("stage"), e.get("producer"), e.get("payload_ref"), e.get("command_id"), e.get("request_id"))
                for e in events]
    if observed != skeleton:
        raise ValueError("사건 종류·생성 주체·순서 불일치")
    for seq, event in enumerate(events, 1):
        if (event["seq"] != seq or event["event_id"] != f"event-{seq:04d}" or event["run_id"] != manifest["run_id"]
                or event["parent_event_ids"] != ([f"event-{seq - 1:04d}"] if seq > 1 else [])
                or event["input_frame_ids"] != [manifest["frame_id"]]
                or (seq > 1 and event["recorded_at_utc"] < events[seq - 2]["recorded_at_utc"])):
            raise ValueError("사건 실행/순서/ID 불일치")
    resolution = results["resolution"]["against_parent"]["summary"]
    return {"verified": True, "schema": SCHEMA, "run_id": manifest["run_id"], "run_kind": "review",
            "parent_run_id": manifest["parent_run_id"], "origin_run_id": manifest["origin_run_id"],
            "review_request_id": manifest["review_request_id"], "correction_ids": ids,
            "correction_source_kinds": manifest["correction_source_kinds"], "run_outcome": manifest["run_outcome"],
            "delivery_requested": deliver, "delivery_fault_injection": fault, "delivery_status": delivery["status"],
            "receiver_side": delivery.get("receiver_side"),
            "issues": len(spec["validation"]["issues"]), "resolved_vs_parent": resolution["resolved"],
            "lineage_depth": lineage["depth"], "files": len(checksums), "events": len(events),
            "scope": "document_rule_review", "new_model_calls": 0, "demo_complete": False}
