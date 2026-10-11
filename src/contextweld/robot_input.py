"""WPS와 작업 레시피를 제조사 입력 단위로 변환한다. 실행·통신은 제공하지 않는다."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json
from pathlib import Path
from typing import Any


# cur/vol의 물리량은 설치 용접기에 따라 달라진다. 이 변환기는 A/절대 V만 지원한다.
FIELDS = (
    ("current", "cur", "A", "A", "1"),
    ("voltage", "vol", "V", "V", "1"),
    ("travel_speed", "spd", "in/min", "cm/min", "2.54"),
)
SOURCE_URL = "https://github.com/hyundai-robotics/doc-arc-weld/blob/ko/2_Command/5_arccond.md"
DOOSAN_URL = "https://manual.doosanrobotics.com/ko/programming-manual/3.7.0/publish/app_weld_set_weld_cond_analog-flag_dry_run-0-v_tar"


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("유한한 숫자가 필요합니다.")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("유한한 숫자가 필요합니다.") from exc
    if (not number.is_finite() or number.adjusted() > 12
            or number.as_tuple().exponent < -30 or len(number.as_tuple().digits) > 30):
        raise ValueError("지원 범위의 유한한 숫자가 필요합니다.")
    return number


def _text(number: Decimal) -> str:
    value = format(number, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _multiply(number: Decimal, factor: Decimal) -> Decimal:
    # 이진 부동소수점과 기본 Decimal 정밀도로 인한 반올림을 피한다.
    with localcontext() as ctx:
        ctx.prec = 64
        return number * factor


def build_robot_input_preview(
    wps: dict[str, Any], profile: dict[str, Any], *, row_id: str = "layer-1",
    setpoints: dict[str, Any] | None = None, recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """명시된 원문 단위의 선택값만 변환한다. 누락값의 자동 선정은 하지 않는다.

    setpoints 예: {"current": "180", "voltage": "26", "travel_speed": "12"}.
    반환 숫자는 정확한 십진 문자열이다. blocked 결과에는 명령이 없다.
    """
    if profile.get("manufacturer") == "Doosan Robotics":
        return _build_doosan_preview(wps, profile, row_id=row_id, setpoints=setpoints, recipe=recipe)
    result: dict[str, Any] = {
        "schema_version": "robot-input-preview.v1", "manufacturer": "HD Hyundai Robotics",
        "controller": "Hi6", "profile_id": profile.get("profile_id"),
        "profile": deepcopy(profile), "source_row_id": row_id,
        "source_document": {key: deepcopy(wps.get(key)) for key in ("document_id", "revision", "source_hash")},
        "status": "needs_setpoints", "fields": [], "issues": [], "command_preview": None,
        "command_kind": "arccond D", "command_reference": SOURCE_URL,
        "hardware_verified": False, "physical_applicability": "unverified",
        "range_combination_validated": False, "application_authorized": False,
        "execution_authorized": False, "delivery_requested": False,
    }

    def issue(field: str, code: str, message: str) -> None:
        result["issues"].append({"field": field, "code": code, "message": message})

    if profile.get("manufacturer") != "HD Hyundai Robotics" or profile.get("controller") != "Hi6":
        issue("profile", "unsupported_profile", "현대 Hi6 프로파일이 필요합니다.")
    modes = profile.get("modes", {})
    if not isinstance(modes, dict) or modes.get("current") != "current_A":
        issue("profile.modes.current", "unsupported_current_mode", "cur를 전류 A로 사용하는 모드를 명시해야 합니다.")
    if not isinstance(modes, dict) or modes.get("voltage") != "absolute_V":
        issue("profile.modes.voltage", "unsupported_voltage_mode", "vol을 절대전압 V로 사용하는 모드를 명시해야 합니다.")
    rows = wps.get("pass_rows", [])
    matches = [row for row in rows if isinstance(row, dict) and row.get("row_id") == row_id] if isinstance(rows, list) else []
    if len(matches) != 1:
        issue("source_row_id", "missing_or_duplicate_row", "WPS 행을 하나로 선택할 수 없습니다.")
    source_fields = matches[0].get("fields", {}) if len(matches) == 1 else {}
    if not isinstance(source_fields, dict):
        source_fields = {}
    if setpoints is not None and not isinstance(setpoints, dict):
        issue("setpoints", "invalid_setpoints", "선택값은 필드별 객체여야 합니다.")
        setpoints = {}
    chosen = setpoints or {}
    for name in chosen:
        if name not in {field[0] for field in FIELDS}:
            issue(str(name), "unknown_setpoint", "지원하지 않는 선택값입니다.")
    for name, robot_field, source_unit, target_unit, factor_text in FIELDS:
        field = source_fields.get(name)
        if not isinstance(field, dict) or not isinstance(field.get("normalized"), dict):
            issue(name, "missing_source_field", "WPS 범위 필드가 없습니다.")
            continue
        normalized = field["normalized"]
        if normalized.get("unit") != source_unit:
            issue(name, "source_unit_mismatch", f"원문 단위는 {source_unit}여야 합니다.")
            continue
        try:
            low, high = _decimal(normalized.get("min")), _decimal(normalized.get("max"))
            if low <= 0 or low > high:
                raise ValueError("양수이며 순서가 맞는 범위가 필요합니다.")
        except ValueError as exc:
            issue(name, "invalid_source_range", str(exc))
            continue
        evidence = field.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("locator"):
            issue(name, "missing_evidence", "원문 위치 근거가 필요합니다.")
        elif any(not wps.get(key) or evidence.get(key) != wps.get(key)
                 for key in ("document_id", "revision", "source_hash")):
            issue(name, "evidence_mismatch", "근거 문서·개정·해시가 WPS와 일치하지 않습니다.")
        factor = Decimal(factor_text)
        target_low, target_high = _multiply(low, factor), _multiply(high, factor)
        if robot_field == "spd" and (target_low < 1 or target_high > 1000):
            issue(name, "controller_range_exceeded", "arccond spd의 문서 범위는 1–1000 cm/min입니다.")
        entry = {
            "name": name, "robot_field": robot_field,
            "source": {"min": _text(low), "max": _text(high), "unit": source_unit,
                       "raw_value": deepcopy(field.get("raw_value"))},
            "target": {"min": _text(target_low), "max": _text(target_high), "unit": target_unit},
            "factor": factor_text, "evidence": deepcopy(evidence), "selected": None,
        }
        result["fields"].append(entry)
        if name not in chosen:
            continue
        try:
            selected = _decimal(chosen[name])
        except ValueError as exc:
            issue(name, "invalid_setpoint", str(exc))
            continue
        if not low <= selected <= high:
            issue(name, "setpoint_out_of_range", "선택값이 WPS 범위를 벗어납니다.")
            continue
        entry["selected"] = {
            "source": {"value": _text(selected), "unit": source_unit},
            "target": {"value": _text(_multiply(selected, factor)), "unit": target_unit},
        }
    result["missing_setpoints"] = [name for name, *_ in FIELDS if name not in chosen]
    if result["issues"]:
        result["status"] = "blocked"
    elif not result["missing_setpoints"]:
        result["status"] = "preview_ready"
        # 공식 즉시변경 예제는 cnd 없이 cur/vol 또는 spd를 사용한다. arcon/모션은 생성하지 않는다.
        result["command_preview"] = "arccond D, " + ", ".join(
            f"{field['robot_field']}={field['selected']['target']['value']}" for field in result["fields"])
    return result


def _doosan_speed(value: Any) -> str:
    with localcontext() as ctx:
        ctx.prec = 64
        return _text((_decimal(value) * Decimal("25.4") / Decimal("60")).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _recipe_evidence(recipe: dict[str, Any], name: str) -> dict[str, Any]:
    evidence = deepcopy(recipe.get("evidence", {}))
    if not isinstance(evidence, dict):
        return {}
    locator = evidence.get("locator", {})
    if isinstance(locator, dict):
        locator["pointer"] = locator.get("pointer", "") + "/setpoints/" + name
        evidence["locator"] = locator
    return evidence


def _build_doosan_preview(wps: dict[str, Any], profile: dict[str, Any], *, row_id: str,
                          setpoints: dict[str, Any] | None, recipe: dict[str, Any] | None) -> dict[str, Any]:
    # 공통 WPS 검증을 재사용한 뒤 제조사 전용 필드와 단위만 대체한다.
    common = {"manufacturer": "HD Hyundai Robotics", "controller": "Hi6",
              "modes": {"current": "current_A", "voltage": "absolute_V"}}
    selected = {key: value for key, value in setpoints.items() if key != "wire_feed"} if isinstance(setpoints, dict) else setpoints
    result = build_robot_input_preview(wps, common, row_id=row_id, setpoints=selected)
    result.update({"manufacturer": "Doosan Robotics", "controller": "DRL", "profile_id": profile.get("profile_id"),
                   "profile": deepcopy(profile), "command_kind": "app_weld_set_weld_cond_analog",
                   "command_reference": DOOSAN_URL, "command_preview": None,
                   "command_parameters": None})
    result["issues"] = [issue for issue in result["issues"] if issue["code"] != "controller_range_exceeded"]

    def issue(field: str, code: str, message: str) -> None:
        result["issues"].append({"field": field, "code": code, "message": message})

    if (profile.get("controller") != "DRL" or profile.get("software_version") != "3.7.0"
            or profile.get("interface") != "analog"):
        issue("profile", "unsupported_profile", "두산 DRL 3.7.0 아날로그 프로파일이 필요합니다.")
    modes = profile.get("modes", {})
    if not isinstance(modes, dict) or modes.get("voltage") != "absolute_V" or modes.get("wire_feed") != "m/min":
        issue("profile.modes", "unsupported_mode", "절대전압 V와 송급 m/min 모드가 필요합니다.")
    for field in result["fields"]:
        if field["name"] == "current":
            field.update({"robot_field": None, "ref_only": True})
        elif field["name"] == "voltage":
            field["robot_field"] = "v_target"
        else:
            field.update({"robot_field": "vel_target", "factor": "25.4", "divisor": "60",
                          "precision": 6, "rounding": "ROUND_HALF_UP"})
            field["target"] = {"min": _doosan_speed(field["source"]["min"]),
                               "max": _doosan_speed(field["source"]["max"]), "unit": "mm/s"}
            if field["selected"]:
                field["selected"]["target"] = {"value": _doosan_speed(field["selected"]["source"]["value"]), "unit": "mm/s"}
    recipe = recipe if isinstance(recipe, dict) else {}
    points = recipe.get("setpoints", {})
    wire = points.get("wire_feed", {}) if isinstance(points, dict) else {}
    chosen = setpoints if isinstance(setpoints, dict) else {}
    if "wire_feed" not in chosen:
        result["missing_setpoints"].append("wire_feed")
    try:
        if not isinstance(wire, dict) or wire.get("unit") != "m/min":
            raise ValueError("송급속도 m/min의 독립 레시피 값이 필요합니다.")
        speed = _decimal(wire.get("value"))
        if speed <= 0:
            raise ValueError("송급속도는 양수여야 합니다.")
        evidence = _recipe_evidence(recipe, "wire_feed")
        if not evidence.get("document_id") or not evidence.get("locator"):
            raise ValueError("송급속도의 레시피 위치 근거가 필요합니다.")
        entry = {"name": "wire_feed", "robot_field": "f_target", "factor": "1",
                 "source": {"min": _text(speed), "max": _text(speed), "unit": "m/min", "raw_value": _text(speed)},
                 "target": {"min": _text(speed), "max": _text(speed), "unit": "m/min"},
                 "evidence": evidence, "source_kind": recipe.get("source_kind"), "selected": None}
        result["fields"].append(entry)
        if "wire_feed" in chosen:
            if _decimal(chosen["wire_feed"]) != speed:
                raise ValueError("송급속도는 이 레시피에 명시한 값과 같아야 합니다.")
            entry["selected"] = {"source": {"value": _text(speed), "unit": "m/min"},
                                 "target": {"value": _text(speed), "unit": "m/min"}}
    except ValueError as exc:
        issue("wire_feed", "invalid_wire_feed_recipe", str(exc))
    result["status"] = "blocked" if result["issues"] else "needs_setpoints"
    if not result["issues"] and not result["missing_setpoints"]:
        mapped = {field["robot_field"]: field["selected"]["target"]["value"]
                  for field in result["fields"] if field.get("robot_field")}
        speed = mapped["vel_target"]
        result["command_parameters"] = {"flag_dry_run": 1, "v_target": mapped["v_target"],
                                        "f_target": mapped["f_target"], "vel_target": speed,
                                        "vel_min": speed, "vel_max": speed}
        result["command_preview"] = ("app_weld_set_weld_cond_analog(flag_dry_run=1, "
            f"v_target={mapped['v_target']}, f_target={mapped['f_target']}, "
            f"vel_target={speed}, vel_min={speed}, vel_max={speed})")
        result["status"] = "preview_ready"
    return result


def build_work_order_input_previews(
    wps: dict[str, Any], work_orders: dict[str, Any], recipe_book: dict[str, Any],
    profiles: dict[str, dict[str, Any]], *, order_id: str,
) -> dict[str, Any]:
    """정확히 연결된 작업 레시피의 명시값으로 두 제조사의 입력을 자동 채운다."""
    result: dict[str, Any] = {"schema_version": "work-order-input-previews.v1", "order_id": order_id,
        "recipe_id": None, "selection_origin": "work_order_recipe", "selected_profile": "hyundai",
        "status": "blocked", "issues": [], "previews": {}, "execution_authorized": False,
        "application_authorized": False, "delivery_requested": False}
    common_spec: dict[str, Any] = {
        "schema_version": "common-weld-spec-preview.v1",
        "target": {"part_id": None, "joint_id": None, "observation_ref": None, "source_kind": "fixture"},
        "relation_origin": "scenario_mapping", "work_order": {"order_id": order_id, "revision": None},
        "wps_ref": None, "process": None, "material": None, "position": None, "parameters": {},
        "validation": {"status": "blocked", "scope": "document_fields_and_numeric_ranges_only",
                       "issues": result["issues"], "physical_applicable": False, "execution_authorized": False},
        "physical_applicable": False, "execution_authorized": False,
    }
    result["common_spec"] = common_spec

    def fail(code: str, message: str) -> dict[str, Any]:
        result["issues"].append({"field": "work_order_recipe", "code": code, "message": message})
        return result

    orders = work_orders.get("orders", [])
    if not isinstance(orders, list):
        return fail("order_not_unique", "작업지시 목록이 없습니다.")
    matches = [order for order in orders if isinstance(order, dict) and order.get("order_id") == order_id]
    if len(matches) != 1:
        return fail("order_not_unique", "작업지시가 없거나 중복되었습니다.")
    order = matches[0]
    common_spec["target"].update({key: order.get(key) for key in ("part_id", "joint_id")})
    common_spec["work_order"]["revision"] = order.get("revision")
    common_spec.update({key: order.get(key) for key in ("process", "material", "position")})
    common_spec["wps_ref"] = deepcopy(order.get("wps_ref"))
    for key in ("part_id", "joint_id", "process"):
        if not isinstance(order.get(key), str) or not order[key].strip():
            return fail("missing_work_requirement", f"작업지시 {key}가 필요합니다.")
    if order.get("state") != "released":
        return fail("work_order_not_released", "작업지시가 released 상태가 아닙니다.")
    applicability = wps.get("applicability", {})
    for order_key, wps_key in (("process", "process"), ("material", "material_from")):
        field = applicability.get(wps_key, {}) if isinstance(applicability, dict) else {}
        normalized = field.get("normalized", {}) if isinstance(field, dict) else {}
        expected = normalized.get("value") if isinstance(normalized, dict) else None
        if expected is not None and order.get(order_key) != expected:
            return fail("work_order_wps_conflict", f"작업지시 {order_key}가 WPS의 전사값과 다릅니다.")
    recipes = recipe_book.get("recipes", [])
    if not isinstance(recipes, list):
        return fail("recipe_not_unique", "작업 레시피 목록이 없습니다.")
    matched = [recipe for recipe in recipes if isinstance(recipe, dict)
               and recipe.get("order_ref") == {"order_id": order_id, "revision": order.get("revision")}]
    if len(matched) != 1:
        return fail("recipe_not_unique", "작업지시와 개정에 연결된 레시피가 없거나 중복되었습니다.")
    recipe = matched[0]
    reference = order.get("wps_ref")
    if (not isinstance(reference, dict) or recipe.get("wps_ref") != reference
            or reference.get("document_id") != wps.get("document_id")
            or reference.get("revision") != wps.get("revision")
            or not reference.get("row_id")):
        return fail("recipe_wps_mismatch", "작업지시·레시피·WPS의 문서, 개정, 행이 일치하지 않습니다.")
    evidence = recipe.get("evidence", {})
    if (not isinstance(evidence, dict) or evidence.get("document_id") != recipe_book.get("document_id")
            or evidence.get("revision") != recipe_book.get("revision") or not evidence.get("locator")):
        return fail("recipe_evidence_mismatch", "레시피의 문서 근거가 일치하지 않습니다.")
    points = recipe.get("setpoints", {})
    for name, unit in (("current", "A"), ("voltage", "V"), ("travel_speed", "in/min"), ("wire_feed", "m/min")):
        point = points.get(name) if isinstance(points, dict) else None
        if not isinstance(point, dict) or point.get("unit") != unit or "value" not in point:
            return fail("recipe_setpoint_missing_or_unit", f"레시피 {name}의 값과 {unit} 단위가 필요합니다.")
        try:
            value = _decimal(point["value"])
            if value <= 0:
                raise ValueError("양수 선택값이 필요합니다.")
        except ValueError as exc:
            return fail("invalid_recipe_setpoint", f"{name}: {exc}")
        common_spec["parameters"][name] = {
            "value": _text(value), "unit": unit, "origin": "fixture",
            "evidence": _recipe_evidence(recipe, name),
        }
    # 제조사별 필드 구성 전에 공통 작업명세의 원문 범위를 검토한다.
    rows = wps.get("pass_rows", [])
    selected_rows = [row for row in rows if isinstance(row, dict) and row.get("row_id") == reference["row_id"]] if isinstance(rows, list) else []
    if len(selected_rows) != 1:
        return fail("missing_or_duplicate_row", "공통 작업명세의 WPS 행이 없거나 중복되었습니다.")
    fields = selected_rows[0].get("fields", {})
    for name in ("current", "voltage", "travel_speed"):
        field = fields.get(name, {}) if isinstance(fields, dict) else {}
        normalized = field.get("normalized", {}) if isinstance(field, dict) else {}
        normalized = normalized if isinstance(normalized, dict) else {}
        parameter = common_spec["parameters"][name]
        try:
            if normalized.get("unit") != parameter["unit"]:
                raise ValueError("WPS 범위와 선택값의 단위가 다릅니다.")
            low, high, value = _decimal(normalized.get("min")), _decimal(normalized.get("max")), _decimal(parameter["value"])
            if low <= 0 or low > high or not low <= value <= high:
                raise ValueError("선택값이 유효한 WPS 범위 안에 있지 않습니다.")
        except ValueError as exc:
            return fail("common_parameter_invalid", f"{name}: {exc}")
    for key in ("hyundai", "doosan"):
        if not isinstance(profiles.get(key), dict):
            return fail("missing_profile", f"{key} 입력 프로파일이 없습니다.")
        expected = "HD Hyundai Robotics" if key == "hyundai" else "Doosan Robotics"
        if profiles[key].get("manufacturer") != expected:
            return fail("profile_key_mismatch", "제조사 선택 키와 프로파일이 다릅니다.")
    selected = {name: parameter["value"] for name, parameter in common_spec["parameters"].items()}
    for key in ("hyundai", "doosan"):
        selection = selected if key == "doosan" else {name: value for name, value in selected.items() if name != "wire_feed"}
        preview = build_robot_input_preview(wps, profiles[key], row_id=reference["row_id"],
                                            setpoints=selection, recipe=recipe)
        preview.update({"selection_origin": "work_order_recipe", "order_id": order_id,
                        "recipe_id": recipe.get("recipe_id"), "recipe_source_kind": recipe.get("source_kind")})
        for field in preview["fields"]:
            field["selection_evidence"] = _recipe_evidence(recipe, field["name"])
        result["previews"][key] = preview
    result.update({"recipe_id": recipe.get("recipe_id"), "source_kind": recipe.get("source_kind"),
                   "recipe": deepcopy(recipe), "work_order": deepcopy(order)})
    result["status"] = "preview_ready" if all(preview["status"] == "preview_ready" for preview in result["previews"].values()) else "blocked"
    for key, preview in result["previews"].items():
        result["issues"].extend({**issue, "profile": key} for issue in preview["issues"])
    common_spec["validation"]["status"] = "valid" if result["status"] == "preview_ready" else "blocked"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="현대 Hi6 입력 단위 미리보기. 로봇 전송 없음.")
    parser.add_argument("--wps", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--row-id", default="layer-1")
    parser.add_argument("--current", help="WPS 단위 A의 명시적 선택값")
    parser.add_argument("--voltage", help="WPS 단위 V의 명시적 선택값")
    parser.add_argument("--travel-speed", help="WPS 단위 in/min의 명시적 선택값")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    selected = {key: value for key, value in {
        "current": args.current, "voltage": args.voltage, "travel_speed": args.travel_speed,
    }.items() if value is not None}
    try:
        wps = json.loads(args.wps.read_text(encoding="utf-8"))
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        if not isinstance(wps, dict) or not isinstance(profile, dict):
            raise ValueError("WPS와 프로파일은 JSON 객체여야 합니다.")
        result = build_robot_input_preview(wps, profile, row_id=args.row_id, setpoints=selected)
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            protected = {args.wps.resolve(), args.profile.resolve()}
            if args.output.resolve() in protected:
                raise ValueError("원문이나 프로파일을 출력으로 덮어쓸 수 없습니다.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
