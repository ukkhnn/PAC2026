"""표기 후보, 작업 맥락, 기준을 대조하는 시연 판단 엔진."""

from __future__ import annotations

import copy
import re
from typing import Any

FIELDS = ("part_id", "seam_id", "weld_type", "size_mm", "position")
LABELS = {"PART": "part_id", "SEAM": "seam_id", "WELD": "weld_type", "SIZE": "size_mm", "POS": "position"}
SCOPE_FIELDS = ("part_id", "seam_id", "material", "thickness_mm", "position", "plan_revision")


def normalize(field: str, value: Any) -> Any:
    if field == "size_mm":
        if isinstance(value, bool) or not re.fullmatch(r"\d{1,2}(?:\.0)?", str(value).strip()):
            raise ValueError("치수는 1~30 사이의 정수여야 합니다.")
        size = int(float(value))
        if not 1 <= size <= 30:
            raise ValueError("시연 치수 범위는 1~30 mm입니다.")
        return size
    text = str(value).strip().upper()
    if field == "weld_type":
        kinds = {"FW": "FILLET", "FILLET": "FILLET", "BW": "BUTT", "BUTT": "BUTT"}
        if text not in kinds:
            raise ValueError("시연 작업 종류는 FW/FILLET 또는 BW/BUTT입니다.")
        return kinds[text]
    if not re.fullmatch(r"[A-Z0-9_-]{1,64}", text):
        raise ValueError("식별자·자세는 영문, 숫자, 밑줄, 하이픈만 지원합니다.")
    return text


def parse_observations(observations: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    parsed: dict[str, list[dict[str, Any]]] = {field: [] for field in FIELDS}
    unparsed = []
    for observation in observations:
        recognized = False
        for candidate in observation.get("candidates", []):
            text = candidate.get("text", "")
            match = re.fullmatch(r"\s*(PART|SEAM|WELD|SIZE|POS)\s*[:=]\s*(.+?)\s*", text, re.I)
            if not match:
                continue
            field = LABELS[match[1].upper()]
            try:
                value = normalize(field, match[2])
            except ValueError:
                continue
            parsed[field].append({"value": value, "score": candidate.get("score"),
                                  "observation_id": observation["id"], "text": text})
            recognized = True
        if not recognized:
            unparsed.append(observation["id"])
    for field in FIELDS:
        unique: dict[Any, dict[str, Any]] = {}
        for candidate in parsed[field]:
            old = unique.get(candidate["value"])
            if old is None or float(candidate.get("score") or 0) > float(old.get("score") or 0):
                unique[candidate["value"]] = candidate
        parsed[field] = list(unique.values())
    return parsed, unparsed


def memory_scope(context: dict[str, Any], version: str) -> dict[str, Any]:
    return {**{key: context.get(key) for key in SCOPE_FIELDS}, "rules_version": version}


def search_evidence(fields: dict[str, Any], knowledge: dict[str, Any], uses_memory: bool) -> list[dict[str, Any]]:
    # 작은 문서 묶음에서 관련 태그를 조회한다. 임베딩 검색은 후속 교체 지점이다.
    tokens = {"PART", "SEAM", "SIZE", "CONFLICT", "RECIPE"}
    tokens.update(str(value) for value in fields.values() if value is not None)
    if uses_memory:
        tokens.add("MEMORY")
    results = []
    for doc in knowledge["documents"]:
        matches = sorted(tokens.intersection(doc["tags"]))
        if matches:
            results.append({**doc, "matched_tags": matches, "source_kind": knowledge["source_kind"],
                            "source_file": "data/knowledge/demo-rules.json", "version": knowledge["version"]})
    return results


def decide(observations: list[dict[str, Any]], context: dict[str, Any], knowledge: dict[str, Any],
           *, use_context: bool = True, memories: list[dict[str, Any]] | None = None,
           corrections: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed, unparsed = parse_observations(observations)
    fields: dict[str, Any] = {}
    origins: dict[str, str] = {}
    reasons: list[dict[str, str]] = []
    blockers: list[dict[str, str]] = []
    memory_used = None

    def reason(code: str, text: str, *, hard: bool = False) -> None:
        target = blockers if hard else reasons
        if not any(item["code"] == code for item in target):
            target.append({"code": code, "text": text})

    changes = corrections or {}
    if any(field not in FIELDS for field in changes):
        raise ValueError("알 수 없는 수정 필드입니다.")
    for field in FIELDS:
        candidates = parsed[field]
        if field in changes:
            fields[field] = normalize(field, changes[field])
            origins[field] = "operator_correction"
        elif len(candidates) == 1:
            fields[field] = candidates[0]["value"]
            origins[field] = "visual_candidate"
        else:
            fields[field] = None
            origins[field] = "unresolved"
            if not candidates:
                reason(f"missing-{field}", f"{field} 표기를 읽지 못했습니다.", hard=True)
            elif field != "size_mm":
                reason(f"ambiguous-{field}", f"{field} 후보가 여러 개입니다.", hard=True)

    trusted_identity = (fields["part_id"] == context.get("part_id") and
                        fields["seam_id"] == context.get("seam_id") and
                        fields["part_id"] is not None and fields["seam_id"] is not None)
    if use_context:
        for field in ("part_id", "seam_id"):
            if not context.get(field):
                reason(f"context-missing-{field}", f"작업계획에 {field}가 없습니다.", hard=True)
            elif fields[field] is not None and fields[field] != context[field]:
                reason(f"context-conflict-{field}", f"사진의 {field}와 작업계획이 다릅니다.", hard=True)
        for key in ("material", "thickness_mm", "position", "plan_revision"):
            if context.get(key) in (None, ""):
                reason(f"context-missing-{key}", f"기준 적용에 필요한 {key}가 없습니다.", hard=True)
        if context.get("preceding_complete") is not True:
            reason("preceding-incomplete", "선행작업 완료 여부를 확인해야 합니다.", hard=True)
        if fields["position"] is not None and context.get("position") not in (None, fields["position"]):
            reason("context-conflict-position", "사진의 자세와 작업계획이 다릅니다.", hard=True)
        if fields["weld_type"] is not None and context.get("weld_type") not in (None, fields["weld_type"]):
            reason("context-conflict-weld", "사진의 작업 종류와 작업계획이 다릅니다.", hard=True)

    size_candidates = [item["value"] for item in parsed["size_mm"]]
    if fields["size_mm"] is None and len(size_candidates) > 1:
        expected = context.get("expected_size_mm") if use_context and trusted_identity else None
        if expected in size_candidates:
            fields["size_mm"] = expected
            origins["size_mm"] = "plan_narrowed"
            reason("size-narrowed", "작업계획으로 치수 후보를 좁혔습니다. 원본 확인이 필요합니다.")
        elif use_context and trusted_identity and not blockers:
            scope = memory_scope(context, knowledge["version"])
            for memory in memories or []:
                size = memory.get("confirmed_fields", {}).get("size_mm")
                if memory.get("scope") == scope and size in size_candidates:
                    fields["size_mm"] = size
                    origins["size_mm"] = "operator_memory"
                    memory_used = {"review_id": memory["review_id"], "run_id": memory["run_id"],
                                   "scope": scope, "note": memory["note"], "confirmed_size_mm": size}
                    reason("memory-narrowed", "동일 작업 범위의 확인 이력으로 후보를 좁혔습니다. 새 사진은 다시 확인합니다.")
                    break
        if fields["size_mm"] is None:
            reason("ambiguous-size", "치수 6/8 등 복수 후보를 작업자가 확인해야 합니다.", hard=True)

    if use_context and fields["size_mm"] is not None:
        expected = context.get("expected_size_mm")
        if expected is not None and fields["size_mm"] != expected:
            reason("context-conflict-size", "사진 또는 수정 치수와 작업계획의 치수가 다릅니다.", hard=True)

    for field, candidates in parsed.items():
        if field not in changes and any(float(item.get("score") or 0) < 0.7 for item in candidates):
            reason("low-ocr-score", "낮은 OCR 점수의 표기가 있습니다. 점수는 정답 확률이 아닙니다.")
    if unparsed:
        reason("unparsed-text", "시연 문법 밖의 표기는 의미를 해석하지 못했습니다.")

    recipe = None
    if use_context and not blockers:
        thickness = context.get("thickness_mm")
        for candidate in knowledge["recipes"]:
            low, high = candidate["thickness_range_mm"]
            if (candidate["weld_type"] == fields["weld_type"] and candidate["size_mm"] == fields["size_mm"]
                    and candidate["material"] == context.get("material") and candidate["position"] == fields["position"]
                    and isinstance(thickness, (int, float)) and not isinstance(thickness, bool) and low <= thickness <= high):
                recipe = copy.deepcopy(candidate)
                break
        if recipe is None:
            reason("no-applicable-recipe", "재질·두께·자세·종류·치수에 맞는 시연 기준이 없습니다.", hard=True)
    if not use_context:
        reason("context-disabled", "표기만 해석했습니다. 작업계획과 적용 범위를 검증하지 않았습니다.")

    status = "blocked" if blockers else "review_required" if reasons else "candidate_ready"
    return {"status": status, "fields": fields, "field_origins": origins, "candidates": parsed,
            "reasons": reasons, "blockers": blockers, "recipe": recipe,
            "evidence": search_evidence(fields, knowledge, memory_used is not None), "memory_used": memory_used,
            "unparsed_observations": unparsed, "rules_version": knowledge["version"],
            "use_context": use_context, "disclaimer": knowledge["disclaimer"]}
