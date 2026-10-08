"""인식 후보를 동일 작업 범위의 유효한 지시에 정확히 연결한다."""

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value.strip()):
        raise ValueError("식별자는 1~64자의 영문·숫자·밑줄·하이픈이어야 합니다.")
    return value.strip().upper()


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("시각은 시간대가 있는 ISO 8601 문자열이어야 합니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("시각은 ISO 8601 형식이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("시각에 시간대가 필요합니다. 예: +09:00")
    return parsed


@dataclass(frozen=True)
class WorkOrder:
    project_id: str
    block_id: str
    order_id: str
    part_id: str
    revision: int
    valid_from: datetime
    valid_until: datetime | None
    state: str
    instruction: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkOrder":
        if not isinstance(data, dict):
            raise ValueError("작업지시는 객체여야 합니다.")
        revision = data["revision"]
        if type(revision) is not int or revision < 1:
            raise ValueError("revision은 1 이상의 정수여야 합니다.")
        state = data["state"]
        if state not in ("released", "cancelled", "on_hold"):
            raise ValueError("state는 released, cancelled, on_hold 중 하나여야 합니다.")
        start = timestamp(data["valid_from"])
        end = timestamp(data["valid_until"]) if data.get("valid_until") is not None else None
        if end is not None and end <= start:
            raise ValueError("valid_until은 valid_from보다 늦어야 합니다.")
        instruction = data["instruction"]
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("작업지시 내용이 필요합니다.")
        return cls(*(identifier(data[key]) for key in ("project_id", "block_id", "order_id", "part_id")),
                   revision, start, end, state, instruction)

    def evidence(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "block_id": self.block_id,
            "order_id": self.order_id, "part_id": self.part_id,
            "revision": self.revision, "state": self.state,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "instruction": self.instruction,
        }


def match_orders(candidates: list[str], orders: list[WorkOrder], *,
                 project_id: str, block_id: str, as_of: str) -> dict[str, Any]:
    """후보는 추정으로 교정하지 않으며 취소·만료 후 이전 버전으로 되돌아가지 않는다."""
    if not isinstance(candidates, list):
        raise ValueError("candidates는 부재번호 문자열의 배열이어야 합니다.")
    normalized = list(dict.fromkeys(identifier(value) for value in candidates))
    project, block = identifier(project_id), identifier(block_id)
    instant = timestamp(as_of)
    groups: dict[tuple[str, str, str], list[WorkOrder]] = {}
    for order in orders:
        groups.setdefault((order.project_id, order.block_id, order.order_id), []).append(order)
    for versions in groups.values():
        revisions = [item.revision for item in versions]
        if len(set(revisions)) != len(revisions):
            raise ValueError("같은 작업지시의 revision이 중복됩니다.")
        if len({item.part_id for item in versions}) != 1:
            raise ValueError("같은 작업지시의 부재가 버전마다 다릅니다.")
        ordered = sorted(versions, key=lambda item: item.revision)
        if any(a.valid_from > b.valid_from for a, b in zip(ordered, ordered[1:])):
            raise ValueError("작업지시의 revision과 적용 시점 순서가 역전됐습니다.")

    latest = {
        key: max((item.revision for item in versions if item.valid_from <= instant), default=0)
        for key, versions in groups.items()
    }
    matches, excluded = [], []
    for order in sorted(orders, key=lambda item: (item.project_id, item.block_id, item.order_id, item.revision)):
        key = (order.project_id, order.block_id, order.order_id)
        if (order.project_id, order.block_id) != (project, block):
            reason = "different_scope"
        elif order.valid_from > instant:
            reason = "not_yet_effective"
        elif order.revision != latest[key]:
            reason = "superseded"
        elif order.valid_until is not None and instant >= order.valid_until:
            reason = "expired"
        elif order.state != "released":
            reason = order.state
        elif order.part_id not in normalized:
            reason = "part_not_in_candidates"
        else:
            matches.append(order.evidence())
            continue
        excluded.append({**order.evidence(), "reason": reason})

    if not normalized:
        status, reason = "unreadable", "no_candidates"
    elif not matches:
        status, reason = "unmatched", "no_valid_order"
    elif len(normalized) > 1:
        status, reason = "review_required", "ambiguous_part"
    elif len(matches) > 1:
        status, reason = "review_required", "multiple_orders"
    else:
        status, reason = "matched", "unique_candidate_and_order"
    return {
        "status": status, "reason": reason,
        "context": {"project_id": project, "block_id": block, "as_of": instant.isoformat()},
        "observed_candidates": list(candidates), "normalized_candidates": normalized,
        "matches": matches, "excluded_orders": excluded,
        "execution_authorized": False,
    }
