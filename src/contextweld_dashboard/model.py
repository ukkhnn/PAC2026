"""관리자 대시보드 화면 모델(view-model)의 기본 요소와 계약.

화면에 나오는 모든 저장 값은 ``V()``로 감싼다. ``src``는 ``"<root>::<path>#<json-pointer>"`` 형식으로
그 값이 저장된 원본 파일과 위치를 가리킨다. 테스트는 ``src``를 다시 읽어 같은 값인지 대조하므로
어댑터는 원본에 없는 값을 저장 값처럼 만들 수 없다. 대시보드가 계산한 값(개수 등)은 ``src=None``,
``origin="dashboard"``와 계산 설명(``note``)을 함께 둔다.

계약 요약 (화면 JS ``app.js``와 같은 이름을 쓴다):

* 실행 데이터: ``{"schema", "key", "summary", "integrity", "files", "steps", "tabs", "roots"}``
* 탭 키: ``TAB_KEYS`` (실행 요약, 촬영 전후 비교, 단계 타임라인, 재촬영 설명, 해석·문서 근거, 전달 내역,
  수정·재검토 이력). 각 탭은 ``{"availability", "absent_reason", "blocks"}``.
* 블록 형식: ``BLOCK_TYPES``. 모든 블록·행·항목은 선택적으로 ``seq``를 가진다. 재생 커서가 그 ``seq``보다
  앞이면 화면은 그 값을 "아직 기록 전"으로 가린다. ``seq``가 ``None``이면 실행 식별 정보처럼 사건과 무관한
  정적 정보다. 실행 종료 때 확정되는 값(run_outcome 등)은 마지막 사건의 ``seq``를 준다.
* 단계(step): ``events.jsonl``의 사건 하나. ``seq`` 순서로 정렬하며 상태 분류는 저장 필드에서만 가져온다.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable

SCHEMA_INDEX = "contextweld-admin-dashboard.index.v1"
SCHEMA_RUN = "contextweld-admin-dashboard.run.v1"

TAB_KEYS = ("summary", "capture", "timeline", "recapture", "evidence", "delivery", "corrections")
TAB_LABELS = {
    "summary": "실행 요약",
    "capture": "촬영 전후 비교",
    "timeline": "단계 타임라인",
    "recapture": "재촬영 설명",
    "evidence": "해석·문서 근거",
    "delivery": "전달 내역",
    "corrections": "수정·재검토 이력",
}
AVAILABILITY = ("available", "partial", "absent")

BLOCK_TYPES = (
    "notice", "fields", "table", "image", "image_pair", "cards", "stages", "diff",
    "lineage", "text", "json", "raw_files", "flow", "group", "video",
)
NOTICE_LEVELS = ("info", "warning", "serious", "critical")
STAGE_STATES = ("done", "not_done", "failed", "absent", "unknown")
STEP_CLASSES = ("success", "undetermined", "failure", "recorded")
INTEGRITY_STATES = ("verified", "failed", "unverifiable", "partial")

# 출처 라벨. 기존 exporter(scripts/export_document_review.py KIND_TAGS)의 표기를 그대로 따르고
# 대시보드에서 새로 필요한 출처만 추가한다.
ORIGIN_LABELS = {
    "model": "원본 · model",
    "user": "수정 · user",
    "demo_fixture": "수정 · demo_fixture (사람 검수 아님)",
    "fixture": "시연 fixture",
    "rule": "재판단 · rule",
    "document": "문서 · document",
    "system": "system",
    "simulator": "시뮬레이터 · 평가/설계 정보 (모델 관측 아님)",
    "dataset": "공개 데이터셋 출처 정보 (모델 관측 아님)",
    "dashboard": "대시보드 계산 (원문 아님)",
}

OUTCOME_LABELS = {
    "succeeded": "성공",
    "needs_review": "검토 보류",
    "failed": "기술 실패",
    "aborted": "중단",
    "running": "실행 중 기록 (미완료)",
}
EXPORT_LABELS = {"complete": "묶음 완전", "incomplete": "묶음 불완전", "in_progress": "기록 중"}
DELIVERY_LABELS = {
    "received": "모의 수신 확인 (용접 완료 아님)",
    "blocked": "전달 차단 (검토 보류)",
    "not_requested": "전달 미요청",
    "failed": "전달 실패",
}
# 상태 색은 항상 라벨·기호와 함께 쓴다(색만으로 구분하지 않음).
OUTCOME_TONES = {"succeeded": "good", "needs_review": "warning", "failed": "critical", "aborted": "critical",
                 "running": "serious"}
EXPORT_TONES = {"complete": "good", "incomplete": "critical", "in_progress": "serious"}
DELIVERY_TONES = {"received": "good", "blocked": "serious", "not_requested": "neutral", "failed": "critical"}


class _Absent:
    """원본에 키 자체가 없음을 나타내는 표식."""

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        return "<absent>"


ABSENT = _Absent()


def escape_token(token: Any) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer(*tokens: Any) -> str:
    """RFC 6901 JSON pointer. ``pointer("a", 0, "b") == "/a/0/b"``."""
    return "".join("/" + escape_token(token) for token in tokens)


def ref(root: str, path: str, ptr: str = "") -> str:
    if "::" in root or "#" in path:
        raise ValueError(f"잘못된 출처 참조: {root!r} {path!r}")
    return f"{root}::{path}#{ptr}"


def split_ref(src: str) -> tuple[str, str, str]:
    root, rest = src.split("::", 1)
    path, _, ptr = rest.partition("#")
    return root, path, ptr


def resolve_pointer(document: Any, ptr: str) -> Any:
    """JSON pointer를 따라간다. 없는 키면 ``ABSENT``를 돌려준다."""
    if ptr == "":
        return document
    if not ptr.startswith("/"):
        raise ValueError(f"JSON pointer는 /로 시작해야 합니다: {ptr!r}")
    current = document
    for raw in ptr[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return ABSENT
            current = current[int(token)]
        elif isinstance(current, dict):
            if token not in current:
                return ABSENT
            current = current[token]
        else:
            return ABSENT
    return current


def V(value: Any, src: str | None, *, origin: str | None = None, note: str | None = None) -> dict[str, Any]:
    """저장 값 하나. ``value``가 ``ABSENT``이면 원본에 키가 없다는 뜻으로 ``absent: true``를 남긴다."""
    if origin is not None and origin not in ORIGIN_LABELS:
        raise ValueError(f"알 수 없는 출처: {origin}")
    if src is None and origin != "dashboard":
        raise ValueError("src가 없는 값은 origin='dashboard'와 계산 설명이 필요합니다.")
    if src is None and not note:
        raise ValueError("대시보드 계산 값에는 note가 필요합니다.")
    item: dict[str, Any] = {"v": None if value is ABSENT else value, "src": src}
    if value is ABSENT:
        item["absent"] = True
    if origin is not None:
        item["o"] = origin
    if note:
        item["n"] = note
    return item


def derived(value: Any, note: str) -> dict[str, Any]:
    """대시보드가 저장 값에서 계산한 값(예: 개수). 원문 값과 구분해 표시한다."""
    return V(value, None, origin="dashboard", note=note)


def row(label: str, value: dict[str, Any], *, unit: dict[str, Any] | None = None, origin: str | None = None,
        seq: int | None = None, help: str | None = None, tone: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"label": label, "value": value}
    if unit is not None:
        item["unit"] = unit
    if origin is not None:
        item["origin"] = origin
    if seq is not None:
        item["seq"] = seq
    if help:
        item["help"] = help
    if tone:
        item["tone"] = tone
    return item


def block(type_: str, id_: str, title: str | None = None, **fields: Any) -> dict[str, Any]:
    if type_ not in BLOCK_TYPES:
        raise ValueError(f"알 수 없는 블록 형식: {type_}")
    item: dict[str, Any] = {"type": type_, "id": id_}
    if title is not None:
        item["title"] = title
    item.update({key: value for key, value in fields.items() if value is not None})
    return item


def notice(id_: str, level: str, text: str, *, src: str | None = None, seq: int | None = None) -> dict[str, Any]:
    if level not in NOTICE_LEVELS:
        raise ValueError(level)
    return block("notice", id_, None, level=level, text=text, src=src, seq=seq)


def tab(availability: str, blocks: list[dict[str, Any]], absent_reason: str | None = None) -> dict[str, Any]:
    if availability not in AVAILABILITY:
        raise ValueError(availability)
    if availability != "available" and not absent_reason:
        raise ValueError("partial/absent 탭에는 이유가 필요합니다.")
    return {"availability": availability, "absent_reason": absent_reason, "blocks": blocks}


def image_ref(path: str, width: int | None, height: int | None, sha256: str | None, *,
              meta_src: str | None = None, label: str | None = None) -> dict[str, Any]:
    """패키지 안 이미지 파일. ``path``는 패키지 루트 기준 상대경로다."""
    return {"path": path, "width": width, "height": height, "sha256": sha256, "meta_src": meta_src, "label": label}


def overlay_polygon(id_: str, kind: str, points: list[list[float]], label: str, origin: str, src: str, *,
                    value: dict[str, Any] | None = None, seq: int | None = None) -> dict[str, Any]:
    return {"id": id_, "kind": kind, "shape": {"type": "polygon", "points": points}, "label": label,
            "origin": origin, "src": src, "value": value, "seq": seq}


def overlay_bbox(id_: str, kind: str, xyxy: list[float], label: str, origin: str, src: str, *,
                 value: dict[str, Any] | None = None, seq: int | None = None) -> dict[str, Any]:
    return {"id": id_, "kind": kind, "shape": {"type": "bbox", "xyxy": xyxy}, "label": label,
            "origin": origin, "src": src, "value": value, "seq": seq}


def enum_label(value: Any, labels: dict[str, str]) -> str:
    if value is None:
        return "null (미기록)"
    if isinstance(value, str) and value in labels:
        return f"{labels[value]} · {value}"
    return f"{value} (정의되지 않은 값)"


def canonical_json(value: Any) -> str:
    """결정적 직렬화. 같은 입력이면 같은 바이트가 나오도록 키를 정렬한다."""
    def check(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("NaN/Infinity는 화면 모델에 넣지 않습니다.")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("화면 모델의 키는 문자열이어야 합니다.")
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def iter_values(node: Any, path: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    """화면 모델 안의 모든 ``V()`` 값을 (모델 내 경로, 값) 쌍으로 순회한다."""
    if isinstance(node, dict):
        if "v" in node and "src" in node and set(node) <= {"v", "src", "o", "n", "absent"}:
            yield path, node
            return
        for key in sorted(node):
            yield from iter_values(node[key], f"{path}/{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from iter_values(child, f"{path}/{index}")


def validate_run_model(run: dict[str, Any]) -> list[str]:
    """화면 모델 형식 검사. 문제 목록을 돌려준다(빈 목록이면 통과)."""
    problems: list[str] = []
    for key in ("schema", "key", "summary", "integrity", "steps", "tabs", "roots"):
        if key not in run:
            problems.append(f"실행 모델에 {key} 없음")
    if run.get("schema") != SCHEMA_RUN:
        problems.append("실행 모델 schema 불일치")
    tabs = run.get("tabs", {})
    for key in TAB_KEYS:
        if key not in tabs:
            problems.append(f"탭 {key} 없음")
            continue
        item = tabs[key]
        if item.get("availability") not in AVAILABILITY:
            problems.append(f"탭 {key} availability 오류")
        if item.get("availability") != "available" and not item.get("absent_reason"):
            problems.append(f"탭 {key}에 없음/부분 사유 없음")
        for blk in item.get("blocks", []):
            problems.extend(_validate_block(blk, f"tabs/{key}"))
    seqs = [step.get("seq") for step in run.get("steps", [])]
    if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
        problems.append("단계가 seq 오름차순·유일하지 않음")
    for step in run.get("steps", []):
        status = step.get("status", {})
        if status.get("class") not in STEP_CLASSES:
            problems.append(f"단계 {step.get('seq')} 상태 분류 오류")
    for where, value in iter_values(run):
        if value["src"] is None and value.get("o") != "dashboard":
            problems.append(f"{where}: src 없는 저장 값")
        if value["src"] is not None and "::" not in value["src"]:
            problems.append(f"{where}: src 형식 오류")
    return problems


def _validate_block(blk: dict[str, Any], where: str) -> list[str]:
    problems: list[str] = []
    type_ = blk.get("type")
    if type_ not in BLOCK_TYPES:
        return [f"{where}: 알 수 없는 블록 {type_}"]
    if not blk.get("id"):
        problems.append(f"{where}: 블록 id 없음")
    if type_ == "notice" and blk.get("level") not in NOTICE_LEVELS:
        problems.append(f"{where}/{blk.get('id')}: notice level 오류")
    if type_ == "stages":
        for stage in blk.get("stages", []):
            if stage.get("state") not in STAGE_STATES:
                problems.append(f"{where}/{blk.get('id')}: stage state 오류")
    if type_ == "group":
        for item in blk.get("items", []):
            for child in item.get("blocks", []):
                problems.extend(_validate_block(child, f"{where}/{blk.get('id')}/{item.get('id')}"))
    return problems
