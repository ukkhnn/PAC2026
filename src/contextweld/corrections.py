"""완료된 실행 묶음 밖에 사용자 수정·보류를 별도로 기록한다.

수정 기록은 저장만 한다. 저장만으로 재검토·모델 호출·모의 전송·학습·검색 색인 추가를 하지 않는다.
지원하는 수정은 좁게 고정한다. 원본 WPS 수치의 자유 입력이나 범용 JSON patch, 승인·검증·신뢰도 같은
내부 필드의 수정은 허용하지 않는다.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

from contextweld.matching import identifier
from contextweld.recognition import safe_path, sha256, utc_now

REQUEST_SCHEMA = "correction-request.v1"
RECORD_SCHEMA = "correction-record.v1"
DOCUMENT_BUNDLE = "document-demo-bundle.v1"
REVIEW_BUNDLE = "review-bundle.v1"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
MAX_REASON = 2000

SELECT = "select_observed_candidate"
RESTORE = "restore_document_parameter"
HOLD = "hold"
ACTIONS = (SELECT, RESTORE, HOLD)
# 작성 주체 → (source_kind, 사건 producer). 자동 시연 예시는 사람 검수로 표시하지 않는다.
AUTHOR_KINDS = {"user": ("user", "user"), "demo_fixture": ("demo_fixture", "fixture")}
RESULT_REFS = {
    DOCUMENT_BUNDLE: {"observation": "results/observation-selection.json", "spec": "results/work-spec.json"},
    REVIEW_BUNDLE: {"observation": "results/effective-interpretation.json", "spec": "results/work-spec.json"},
}
REQUEST_KEYS = {"schema_version", "correction_id", "action", "target", "before", "after", "reason", "author"}
TARGET_KEYS = {
    SELECT: {"run_id", "result_ref", "result_sha256", "field", "observation_id"},
    RESTORE: {"run_id", "result_ref", "result_sha256", "field"},
    HOLD: {"run_id", "result_ref", "result_sha256"},
}
AFTER_KEYS = {SELECT: {"part_id"}, RESTORE: {"document_id", "revision", "row_id"}, HOLD: {"decision"}}
RECORD_KEYS = {"schema_version", "correction_id", "action", "target", "before", "after", "reason", "author",
               "source_kind", "producer", "recorded_at_utc", "request_sha256", "request", "effects"}
EFFECTS = {"stored_only": True, "review_started": False, "delivery_requested": False,
           "model_called": False, "added_to_retrieval_or_memory": False}


class CorrectionError(ValueError):
    """거절 사유를 기계가 읽을 수 있는 code와 함께 전달한다."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.details = code, message, details


class CorrectionRejected(CorrectionError):
    pass


class CorrectionConflict(CorrectionError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value))


def _text(value: Any, limit: int = MAX_REASON) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _hash(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value))


def inspect_bundle(root: Path) -> dict[str, Any]:
    """스키마에 맞는 기존 검증기를 그대로 호출한다. 검증하지 못한 묶음은 수정 대상이 아니다."""
    from contextweld.review import inspect_review_bundle
    from contextweld.workflow import inspect_document_bundle
    schema = read_json(root / "manifest.json").get("schema_version")
    if schema == DOCUMENT_BUNDLE:
        return inspect_document_bundle(root)
    if schema == REVIEW_BUNDLE:
        return inspect_review_bundle(root)
    raise ValueError("수정 대상으로 지원하지 않는 묶음 스키마: " + str(schema))


BUNDLE_SCHEMAS = {"bootstrap-bundle.v1", DOCUMENT_BUNDLE, REVIEW_BUNDLE}


def enclosing_bundle(path: Path) -> Path | None:
    """경로 자신이나 상위 디렉토리가 실행 묶음(완료·미완료)이면 그 묶음 경로를 돌려준다."""
    for candidate in [Path(path).resolve(), *Path(path).resolve().parents]:
        manifest = candidate / "manifest.json"
        if candidate.name.endswith(".incomplete") and manifest.is_file():
            return candidate
        if manifest.is_file() and (candidate / "checksums.json").is_file():
            try:
                if read_json(manifest).get("schema_version") in BUNDLE_SCHEMAS:
                    return candidate
            except (ValueError, OSError):
                return candidate
    return None


def bundle_identity(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "manifest.json")
    return {"run_id": manifest["run_id"], "bundle_schema": manifest["schema_version"], "run_kind": manifest["run_kind"],
            "bundle_manifest_sha256": sha256(root / "manifest.json"),
            "bundle_checksums_sha256": sha256(root / "checksums.json")}


def observation_state(selection: dict[str, Any], observation_id: str) -> dict[str, Any] | None:
    """원 관측 선택과 재검토 해석에 공통인 관측 한 건의 상태. 수정 전 값 비교의 기준이다."""
    for row in selection["observations"]:
        if row["ocr"]["observation_id"] != observation_id:
            continue
        vlm = list(dict.fromkeys(identifier(item["raw_text"].strip()) for item in row["vlm"]))
        effective = row.get("effective_identifier")
        return {"observation_id": observation_id, "ocr_identifier": row["normalized_identifier"],
                "vlm_identifiers": vlm, "candidates": list(dict.fromkeys([row["normalized_identifier"], *vlm])),
                "open_issue_codes": sorted(item["code"] for item in selection["issues"]
                                           if item.get("field") == observation_id),
                "effective_identifier": None if effective is None else
                {"value": effective["value"], "correction_id": effective["correction_id"]}}
    return None


def parameter_state(spec: dict[str, Any], name: str) -> dict[str, Any]:
    field = f"parameters.{name}"
    return {"field": field, "present": name in spec["parameters"],
            "missing": field in spec["validation"]["missing_fields"]}


def hold_state(manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {"run_outcome": manifest["run_outcome"], "delivery_status": manifest.get("delivery_status"),
            "open_issue_count": len(spec["validation"]["issues"])}


def wps_location(spec: dict[str, Any], orders: dict[str, Any], wps: dict[str, Any]) -> dict[str, str] | None:
    """명세가 선택한 작업지시가 실제 참조하는 WPS 행. 다른 문서·행으로 대체하지 않는다."""
    target = spec.get("target") or {}
    if not target.get("work_order_id"):
        return None
    for order in orders["orders"]:
        if (identifier(order["order_id"]) == target["work_order_id"]
                and identifier(order["project_id"]) == target.get("project_id")
                and identifier(order["block_id"]) == target.get("block_id")):
            ref = order["wps_ref"]
            if ref["document_id"] == wps["document_id"] and ref["revision"] == wps["revision"]:
                return {"document_id": ref["document_id"], "revision": ref["revision"], "row_id": ref["row_id"]}
    return None


def reviewed_wps_field(wps: dict[str, Any], row_id: str, name: str) -> dict[str, Any] | None:
    row = next((item for item in wps["pass_rows"] if item["row_id"] == row_id), None)
    value = None if row is None else row["fields"].get(name)
    return value if isinstance(value, dict) and value.get("review_status") == "agent_transcription_checked" else None


def origin_documents(root: Path) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """묶음의 원래 document_demo 입력(작업지시·프로파일·WPS 전사)을 찾는다."""
    manifest = read_json(root / "manifest.json")
    if manifest["schema_version"] == REVIEW_BUNDLE:
        lineage = read_json(root / "results/lineage.json")
        origin = safe_path(root, lineage["ancestors"][0]["bundle_ref"])
    else:
        origin = root
    return (origin, read_json(origin / "inputs/effective-work-orders.json"),
            read_json(origin / "inputs/target_profile.json"), read_json(origin / "evidence/wps-reviewed.json"))


def validate_request(request: Any) -> None:
    """요청의 형태만 검사한다. 묶음과 대조하는 검사는 record_correction에서 한다."""
    def reject(code: str, message: str) -> None:
        raise CorrectionRejected(code, message)

    if not isinstance(request, dict) or request.get("schema_version") != REQUEST_SCHEMA:
        reject("invalid_request", "correction-request.v1 객체가 필요합니다.")
    extra = set(request) - REQUEST_KEYS
    if extra:
        reject("unsupported_field", "지원하지 않는 요청 필드: " + ", ".join(sorted(extra)))
    if not valid_id(request.get("correction_id")):
        reject("invalid_request", "correction_id는 1~64자 영문·숫자·_.- 이어야 합니다.")
    action = request.get("action")
    if action not in ACTIONS:
        reject("unsupported_action", "지원하는 수정 동작: " + ", ".join(ACTIONS))
    target, after = request.get("target"), request.get("after")
    if not isinstance(target, dict) or set(target) != TARGET_KEYS[action]:
        reject("unsupported_field", f"{action}의 target 필드는 {sorted(TARGET_KEYS[action])}만 허용합니다.")
    if not valid_id(target["run_id"]) or not isinstance(target["result_ref"], str) or not _hash(target["result_sha256"]):
        reject("invalid_request", "target.run_id/result_ref/result_sha256 형식이 올바르지 않습니다.")
    if action == SELECT and (target["field"] != "part_id" or not valid_id(target["observation_id"])):
        reject("unsupported_field", "관측 후보 선택은 part_id 필드와 관측 ID만 지원합니다.")
    if action == RESTORE and (not isinstance(target["field"], str)
                              or not re.fullmatch(r"parameters\.[a-z_]{1,32}", target["field"])):
        reject("unsupported_field", "문서 근거 복구는 parameters.<이름> 필드만 지원합니다.")
    if not isinstance(after, dict) or set(after) != AFTER_KEYS[action]:
        reject("unsupported_field", f"{action}의 after 필드는 {sorted(AFTER_KEYS[action])}만 허용합니다. "
                                    "수치·승인·검증 결과를 직접 입력할 수 없습니다.")
    if action == SELECT and not valid_id(after["part_id"]):
        reject("invalid_value", "선택한 식별자 형식이 올바르지 않습니다.")
    if action == RESTORE and not all(_text(after[key], 128) for key in AFTER_KEYS[RESTORE]):
        reject("invalid_value", "문서 위치(document_id, revision, row_id)는 비어 있지 않은 문자열이어야 합니다.")
    if action == HOLD and after["decision"] != "hold":
        reject("invalid_value", "보류 기록의 after.decision은 hold여야 합니다.")
    if not isinstance(request.get("before"), dict):
        reject("invalid_request", "화면에서 확인한 수정 전 값(before)이 필요합니다.")
    if not _text(request.get("reason")):
        reject("invalid_request", f"사유(reason)는 1~{MAX_REASON}자 문자열이어야 합니다.")
    author = request.get("author")
    if (not isinstance(author, dict) or set(author) != {"kind", "id"} or author["kind"] not in AUTHOR_KINDS
            or not valid_id(author["id"])):
        reject("invalid_request", "author는 {kind: user|demo_fixture, id}여야 합니다.")


def evaluate_target(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """검증된 묶음에서 대상 결과의 현재 값을 다시 읽고 요청과 대조한다. 조용히 덮어쓰지 않는다."""
    action, target = request["action"], request["target"]
    identity = bundle_identity(root)
    if target["run_id"] != identity["run_id"]:
        raise CorrectionRejected("target_run_mismatch", "요청의 run_id가 대상 묶음과 다릅니다.",
                                 requested=target["run_id"], bundle=identity["run_id"])
    refs = RESULT_REFS[identity["bundle_schema"]]
    allowed = {SELECT: {refs["observation"]}, RESTORE: {refs["spec"]}, HOLD: set(refs.values())}[action]
    if target["result_ref"] not in allowed:
        raise CorrectionRejected("unsupported_result_ref", "이 동작이 가리킬 수 없는 결과입니다: " + target["result_ref"])
    checksums = read_json(root / "checksums.json")
    actual_hash = checksums.get(target["result_ref"])
    if actual_hash != sha256(safe_path(root, target["result_ref"])) or actual_hash != target["result_sha256"]:
        raise CorrectionRejected("stale_result", "확인한 결과 해시가 현재 묶음의 결과와 다릅니다.",
                                 requested=target["result_sha256"], actual=actual_hash)
    result = read_json(safe_path(root, target["result_ref"]))
    manifest = read_json(root / "manifest.json")
    spec = read_json(root / refs["spec"])
    if action == SELECT:
        state = observation_state(result, target["observation_id"])
        if state is None:
            raise CorrectionRejected("observation_not_found", "대상 실행·프레임에 없는 관측 ID입니다.",
                                     observation_id=target["observation_id"], frame_id=manifest.get("frame_id"))
        if request["after"]["part_id"] not in state["candidates"]:
            raise CorrectionRejected("candidate_not_observed", "실제 OCR/VLM이 읽은 후보 중에서만 선택할 수 있습니다.",
                                     candidates=state["candidates"])
    elif action == RESTORE:
        _, orders, profile, wps = origin_documents(root)
        name = target["field"].split(".", 1)[1]
        if name not in profile["parameters"]:
            raise CorrectionRejected("unsupported_field", "프로파일에 없는 파라미터입니다: " + name)
        state = parameter_state(result, name)
        if state["present"] or not state["missing"]:
            raise CorrectionRejected("parameter_not_missing", "누락으로 기록된 파라미터만 문서 근거로 복구할 수 있습니다.")
        location = wps_location(result, orders, wps)
        if location is None:
            raise CorrectionRejected("no_document_reference", "선택된 작업지시가 확보한 WPS를 참조하지 않아 근거 위치가 없습니다.")
        if request["after"] != location:
            raise CorrectionRejected("document_reference_mismatch", "작업지시가 참조하는 WPS 행만 사용할 수 있습니다.",
                                     expected=location)
        if reviewed_wps_field(wps, location["row_id"], name) is None:
            raise CorrectionRejected("document_field_unavailable", "참조 WPS 행에 검수된 해당 필드가 없습니다.")
    else:
        state = hold_state(manifest, spec)
    if request["before"] != state:
        raise CorrectionRejected("stale_before_value", "확인한 수정 전 값이 현재 결과와 다릅니다. 최신 값을 다시 확인하세요.",
                                 requested=request["before"], actual=state)
    return {**identity, **deepcopy(target),
            "result_id": spec["spec_id"] if target["result_ref"] == refs["spec"] else
            result.get("result_id", f"{identity['run_id']}:observation-selection"),
            "frame_id": manifest.get("frame_id")}


def build_record(request: dict[str, Any], target: dict[str, Any], recorded_at: str) -> dict[str, Any]:
    source_kind, producer = AUTHOR_KINDS[request["author"]["kind"]]
    return {"schema_version": RECORD_SCHEMA, "correction_id": request["correction_id"], "action": request["action"],
            "target": target, "before": deepcopy(request["before"]), "after": deepcopy(request["after"]),
            "reason": request["reason"], "author": deepcopy(request["author"]), "source_kind": source_kind,
            "producer": producer, "recorded_at_utc": recorded_at, "request_sha256": digest(request),
            "request": deepcopy(request), "effects": dict(EFFECTS)}


def validate_record(record: Any) -> None:
    """저장소에서 읽은 기록의 구조와 내장 요청의 일치를 확인한다. 의미 대조는 재검토 단계에서 한다."""
    if not isinstance(record, dict) or record.get("schema_version") != RECORD_SCHEMA or set(record) != RECORD_KEYS:
        raise CorrectionRejected("invalid_correction_record", "correction-record.v1 형식이 아닙니다.")
    request = record["request"]
    validate_request(request)
    if record["request_sha256"] != digest(request):
        raise CorrectionRejected("invalid_correction_record", "기록의 요청 해시가 일치하지 않습니다.")
    for key in ("correction_id", "action", "before", "after", "reason", "author"):
        if record[key] != request[key]:
            raise CorrectionRejected("invalid_correction_record", "기록과 원 요청의 내용이 다릅니다: " + key)
    if any(record["target"].get(key) != value for key, value in request["target"].items()):
        raise CorrectionRejected("invalid_correction_record", "기록의 대상이 원 요청과 다릅니다.")
    if (record["source_kind"], record["producer"]) != AUTHOR_KINDS[request["author"]["kind"]] or record["effects"] != EFFECTS:
        raise CorrectionRejected("invalid_correction_record", "작성 주체 또는 효과 표시가 올바르지 않습니다.")
    target = record["target"]
    if (target.get("bundle_schema") not in RESULT_REFS or not _hash(target.get("bundle_manifest_sha256"))
            or not _hash(target.get("bundle_checksums_sha256"))):
        raise CorrectionRejected("invalid_correction_record", "대상 묶음 식별 정보가 없습니다.")
    safe_path(Path("/"), target["result_ref"])


def _write_exclusive(path: Path, data: bytes) -> bool:
    """임시 파일을 완성한 뒤 hard link로 공개한다. 이미 있으면 False이며 기존 파일을 바꾸지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
        return True
    except FileExistsError:
        return False
    finally:
        temporary.unlink()


def record_path(store: Path, correction_id: str) -> Path:
    if not valid_id(correction_id):
        raise CorrectionRejected("invalid_request", "올바르지 않은 correction_id")
    return store / f"{correction_id}.json"


def _existing_outcome(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    try:
        existing = read_json(path)
    except (UnicodeDecodeError, ValueError):
        existing = {}
    same = (isinstance(existing, dict) and existing.get("request_sha256") == record["request_sha256"]
            and existing.get("target", {}).get("bundle_manifest_sha256") == record["target"]["bundle_manifest_sha256"])
    if not same:
        raise CorrectionConflict("correction_id_conflict", "같은 correction_id에 다른 내용이 이미 기록되어 있습니다. 새 ID를 사용하세요.",
                                 path=str(path), existing_request_sha256=existing.get("request_sha256"))
    return {"status": "duplicate_retry", "correction_id": record["correction_id"], "path": str(path),
            "record_sha256": sha256(path), "recorded_at_utc": existing["recorded_at_utc"],
            "effects": "no_new_record_no_review_no_delivery"}


def record_correction(bundle: Path, request: Any, store: Path) -> dict[str, Any]:
    """검증한 완료 묶음을 대상으로 수정·보류를 저장한다. 원 묶음은 읽기만 한다."""
    validate_request(request)
    root, store = Path(bundle), Path(store)
    if store.resolve().is_relative_to(root.resolve()) or enclosing_bundle(store) is not None:
        raise CorrectionRejected("store_inside_bundle", "실행 묶음 안에는 수정 기록을 저장할 수 없습니다.")
    before_checksums = (root / "checksums.json").read_bytes()
    try:
        inspect_bundle(root)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise CorrectionRejected("target_bundle_unverified", "대상 묶음을 검증하지 못했습니다: " + str(exc)) from exc
    target = evaluate_target(root, request)
    record = build_record(request, target, utc_now())
    if (root / "checksums.json").read_bytes() != before_checksums:
        raise CorrectionRejected("target_bundle_changed", "검사 도중 대상 묶음이 변경되었습니다.")
    path = record_path(store, request["correction_id"])
    data = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    if path.exists() or not _write_exclusive(path, data):
        return _existing_outcome(path, record)
    return {"status": "recorded", "correction_id": record["correction_id"], "path": str(path),
            "record_sha256": sha256(path), "recorded_at_utc": record["recorded_at_utc"],
            "effects": "stored_only_no_review_no_delivery"}


def load_selected(store: Path, correction_ids: list[str]) -> list[tuple[dict[str, Any], bytes]]:
    """명시적으로 선택한 ID의 파일만 연다. 저장소 목록을 훑거나 다른 기록을 자동 적용하지 않는다."""
    if not isinstance(correction_ids, list) or not correction_ids:
        raise CorrectionRejected("invalid_request", "재검토에 사용할 correction_id를 하나 이상 선택해야 합니다.")
    if len(set(correction_ids)) != len(correction_ids):
        raise CorrectionRejected("duplicate_selection", "같은 correction_id를 두 번 선택했습니다.")
    loaded = []
    for correction_id in correction_ids:
        path = record_path(Path(store), correction_id)
        if not path.is_file() or path.is_symlink():
            raise CorrectionRejected("correction_not_found", "선택한 수정 기록이 없습니다: " + correction_id)
        raw = path.read_bytes()
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CorrectionRejected("invalid_correction_record", "수정 기록 JSON을 읽지 못했습니다: " + correction_id) from exc
        validate_record(record)
        if record["correction_id"] != correction_id:
            raise CorrectionRejected("invalid_correction_record", "파일 이름과 correction_id가 다릅니다.")
        loaded.append((record, raw))
    return loaded


def describe_targets(bundle: Path) -> dict[str, Any]:
    """검증된 묶음에서 수정 가능한 대상과 수정 전 값·해시를 요청 서식으로 출력한다. 아무것도 저장하지 않는다."""
    root = Path(bundle)
    inspect_bundle(root)
    identity = bundle_identity(root)
    refs = RESULT_REFS[identity["bundle_schema"]]
    checksums = read_json(root / "checksums.json")
    manifest = read_json(root / "manifest.json")
    observation, spec = read_json(root / refs["observation"]), read_json(root / refs["spec"])
    author = {"kind": "user", "id": "<작성자 ID>"}
    base = {"schema_version": REQUEST_SCHEMA, "correction_id": "<새 correction ID>", "reason": "<사유>", "author": author}
    templates = []
    for row in observation["observations"]:
        state = observation_state(observation, row["ocr"]["observation_id"])
        templates.append({"allowed_after_values": state["candidates"], "request": {
            **base, "action": SELECT,
            "target": {"run_id": identity["run_id"], "result_ref": refs["observation"],
                       "result_sha256": checksums[refs["observation"]], "field": "part_id",
                       "observation_id": state["observation_id"]},
            "before": state, "after": {"part_id": "<allowed_after_values 중 하나>"}}})
    _, orders, profile, wps = origin_documents(root)
    location = wps_location(spec, orders, wps)
    for name in profile["parameters"]:
        state = parameter_state(spec, name)
        if state["present"] or not state["missing"]:
            continue
        available = location is not None and reviewed_wps_field(wps, location["row_id"], name) is not None
        note = (None if available else "선택된 작업지시가 확보한 WPS 행을 참조하지 않아 복구할 근거 위치가 없습니다. 저장 시 거절됩니다."
                if location is None else "참조 WPS 행에 검수 값이 없어 저장 시 거절됩니다.")
        templates.append({"restorable": available, "note": note,
                          "request": {**base, "action": RESTORE,
                                      "target": {"run_id": identity["run_id"], "result_ref": refs["spec"],
                                                 "result_sha256": checksums[refs["spec"]], "field": state["field"]},
                                      "before": state, "after": location or {"document_id": None, "revision": None, "row_id": None}}})
    templates.append({"request": {**base, "action": HOLD,
                                  "target": {"run_id": identity["run_id"], "result_ref": refs["spec"],
                                             "result_sha256": checksums[refs["spec"]]},
                                  "before": hold_state(manifest, spec), "after": {"decision": "hold"}}})
    return {"bundle": identity, "frame_id": manifest.get("frame_id"), "templates": templates,
            "note": "읽기 전용 출력입니다. request를 파일로 저장해 correction_id·after·reason·author를 채운 뒤 record로 저장하세요."}


def write_rejection(directory: Path, payload: dict[str, Any]) -> Path:
    """거절된 요청도 감사용으로 새 파일에 남긴다. 기존 기록은 바꾸지 않는다."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("-", "").replace(".", "")
    path = directory / f"{stamp}-{uuid.uuid4().hex[:8]}.json"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({"recorded_at_utc": utc_now(), **payload}, ensure_ascii=False, indent=2, default=str) + "\n")
    return path
