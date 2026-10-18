"""어댑터 공통 도우미: 내보내기 문맥, 사건→단계 변환, 상태 분류 형식, 실패 묶음 진단 화면.

어댑터 계약::

    build(source: Source, reader: BundleReader, integrity: dict, ctx: ExportContext) -> dict

반환값은 ``{"summary", "steps", "tabs"}``를 가진 dict이며 패키지 생성기가 ``schema/key/integrity/files/roots``를
덧붙인다. 어댑터는 원본 파일을 쓰지 않고, 원본에 없는 값·연결·영역을 만들지 않는다. 키가 없으면
``ABSENT``(화면에서 "기록 없음"), 값이 ``null``이면 null 그대로 둔다.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from ..bundle_io import BundleReader
from ..catalog import GROUPS, Source
from ..model import (ABSENT, DELIVERY_LABELS, EXPORT_LABELS, OUTCOME_LABELS, V, block, derived, enum_label,
                     image_ref, notice, row, tab)

STAGE_LABELS = {
    # 인식 bootstrap
    "frame_ingest": "프레임 입력",
    "ocr": "OCR 문자 검출·인식",
    "observation": "VLM 시각 관측",
    "document_retrieval": "문서 검색",
    "relation": "관계 해석 (VLM)",
    "work_spec_candidate": "작업 명세 후보 (규칙)",
    "recognition_decision": "인식 판단 (규칙)",
    # 재촬영 루프
    "capture_assessment": "촬영 품질 평가 (model)",
    "recapture_request": "재촬영 요청 (규칙)",
    "export": "내보내기 완료",
    "failure": "실행 실패 기록",
    # 문서 검토
    "input_reuse": "기존 인식 결과 재사용",
    "observation_selection": "관측 선택",
    "work_order_matching": "작업지시·도면 매칭",
    "document_fields_and_validation": "문서 필드 추출·검증",
    "command_prepared": "전달 명령 생성",
    "mock_transport": "모의 전송",
    "delivery_result": "전달 결과 기록",
    # 명시적 재검토
    "review_request": "재검토 요청 접수",
    "input_snapshot": "입력 스냅샷",
    "lineage": "계보 확인",
    "correction_selected": "선택 수정 적용 대상",
    "observation_reselection": "관측 재선택",
    "correction_application": "수정 적용",
    "issue_resolution": "이슈 해결 판정",
}
STEP_CLASS_LABELS = {
    "success": "성공",
    "undetermined": "미확정·보류",
    "failure": "기술 실패",
    "recorded": "기록됨 (판정 필드 없음)",
}


class ExportContext:
    """패키지 안 다른 자료를 찾는 문맥. 실행 연결은 저장된 run_id와 manifest 해시가 있을 때만 만든다."""

    def __init__(self, sources: list[Source], manifests: dict[str, dict[str, Any] | None],
                 manifest_sha256: dict[str, str | None]):
        self.sources = {source.key: source for source in sources}
        self.manifests = manifests
        self.manifest_sha256 = manifest_sha256
        self._by_run_id: dict[str, list[str]] = {}
        for key, manifest in manifests.items():
            if self.sources[key].group in ("recognition", "document", "review") and isinstance(manifest, dict):
                run_id = manifest.get("run_id")
                if isinstance(run_id, str):
                    self._by_run_id.setdefault(run_id, []).append(key)

    def package_path(self, key: str, relative: str) -> str:
        return f"bundles/{key}/{relative}"

    def run_key_for(self, run_id: Any, manifest_sha256: str | None = None) -> str | None:
        """같은 run_id의 패키지 실행이 하나뿐이고(해시가 주어졌다면) manifest SHA-256도 같을 때만 연결한다."""
        if not isinstance(run_id, str):
            return None
        keys = self._by_run_id.get(run_id, [])
        if len(keys) != 1:
            return None
        if manifest_sha256 is not None and self.manifest_sha256.get(keys[0]) != manifest_sha256:
            return None
        return keys[0]

    def image(self, reader: BundleReader, relative: str, *, label: str | None = None,
              meta_src: str | None = None) -> dict[str, Any] | None:
        meta = reader.image_meta(relative)
        if meta is None:
            return None
        return image_ref(self.package_path(reader.key, relative), meta["width"], meta["height"], meta["sha256"],
                         meta_src=meta_src or reader.src(relative), label=label)


def status(class_: str, label: str | None = None, basis: dict[str, Any] | None = None,
           note: str | None = None) -> dict[str, Any]:
    if class_ not in STEP_CLASS_LABELS:
        raise ValueError(class_)
    return {"class": class_, "label": label or STEP_CLASS_LABELS[class_], "basis": basis, "note": note}


def build_steps(reader: BundleReader, events_ref: str, classify: Callable[[dict[str, Any], int], dict[str, Any]], *,
                frames_for: Callable[[dict[str, Any], int], list[dict[str, Any]]] | None = None,
                labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """``events.jsonl``을 ``seq`` 순서의 단계 목록으로 바꾼다. 키가 없는 사건 필드는 '기록 없음'으로 남긴다."""
    labels = labels or STAGE_LABELS
    events = reader.jsonl(events_ref)
    order = sorted(range(len(events)), key=lambda index: (events[index].get("seq"), index))
    steps: list[dict[str, Any]] = []
    for index in order:
        event = events[index]
        seq = event.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise ValueError(f"사건 {index}의 seq가 정수가 아닙니다.")

        def field(name: str) -> dict[str, Any]:
            return reader.value(events_ref, index, name)

        stage = event.get("stage")
        payload_ref = event.get("payload_ref")
        payload = None
        if isinstance(payload_ref, str) and reader.exists(payload_ref):
            payload = {"root": reader.key, "path": payload_ref}
        steps.append({
            "seq": seq,
            "src": reader.src(events_ref, index),
            "event_id": field("event_id"),
            "type": field("type"),
            "stage": field("stage"),
            "producer": field("producer"),
            "recorded_at_utc": field("recorded_at_utc"),
            "elapsed_ms": field("elapsed_ms"),
            "parent_event_ids": field("parent_event_ids"),
            "input_frame_ids": field("input_frame_ids"),
            "input_result_ids": field("input_result_ids"),
            "request_id": field("request_id"),
            "command_id": field("command_id"),
            "payload_ref": field("payload_ref"),
            "label": labels.get(stage, str(stage)) if stage is not None else "단계 이름 없음",
            "status": classify(event, index),
            "frames": frames_for(event, index) if frames_for else [],
            "payload": payload,
        })
    return steps


def outcome_row(reader: BundleReader, *, seq: int | None) -> dict[str, Any]:
    value = reader.value("manifest.json", "run_outcome")
    return row("실제 처리 결과 (run_outcome)", value, seq=seq, tone=_tone(value["v"], "outcome"),
               help=enum_label(value["v"], OUTCOME_LABELS))


def export_row(reader: BundleReader, *, seq: int | None) -> dict[str, Any]:
    value = reader.value("manifest.json", "export_status")
    return row("내보내기 상태 (export_status)", value, seq=seq, tone=_tone(value["v"], "export"),
               help=enum_label(value["v"], EXPORT_LABELS))


def delivery_row(reader: BundleReader, *, seq: int | None) -> dict[str, Any]:
    value = reader.value("manifest.json", "delivery_status")
    return row("모의 전달 상태 (delivery_status)", value, seq=seq, tone=_tone(value["v"], "delivery"),
               help=enum_label(value["v"], DELIVERY_LABELS) if not value.get("absent") else "이 묶음 종류에는 전달 상태 필드가 없음")


def _tone(value: Any, kind: str) -> str | None:
    from ..model import DELIVERY_TONES, EXPORT_TONES, OUTCOME_TONES
    table = {"outcome": OUTCOME_TONES, "export": EXPORT_TONES, "delivery": DELIVERY_TONES}[kind]
    return table.get(value) if isinstance(value, str) else None


def base_summary(source: Source, reader: BundleReader | None, *, kind_label: str, title: str,
                 final_seq: int | None) -> dict[str, Any]:
    """실행 목록·머리글에 쓰는 공통 요약. 원본 manifest의 값을 그대로 감싼다."""
    def m(name: str) -> dict[str, Any]:
        if reader is None or not reader.exists("manifest.json"):
            return derived(None, "manifest.json을 읽을 수 없음")
        return reader.value("manifest.json", name)

    return {
        "title": title,
        "group": source.group,
        "group_label": GROUPS[source.group],
        "kind_label": kind_label,
        "display_path": source.display_path,
        "note": source.note,
        "run_id": m("run_id"),
        "scenario_id": m("scenario_id"),
        "run_kind": m("run_kind"),
        "capture_mode": m("capture_mode"),
        "schema_version": m("schema_version"),
        "run_outcome": m("run_outcome"),
        "export_status": m("export_status"),
        "delivery_status": m("delivery_status"),
        "started_at_utc": m("started_at_utc"),
        "finished_at_utc": m("finished_at_utc"),
        "flags": [],
        "headline": [],
        "links": [],
        "final_seq": final_seq,
        "replay": {"enabled": False, "reason": "사건 기록이 없습니다."},
    }


def absent(reason: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return tab("absent", blocks or [], reason)


def diagnostic_model(source: Source, reader: BundleReader | None, integrity: dict[str, Any], *, kind_label: str,
                     error: str | None = None) -> dict[str, Any]:
    """검증 실패·불완전·화면 모델 생성 실패 묶음의 진단 화면. 정상 재생을 제공하지 않는다."""
    title = source.display_path.rsplit("/", 1)[-1]
    summary = base_summary(source, reader, kind_label=kind_label, title=title, final_seq=None)
    reason = "묶음 검증을 통과하지 못해 정상 재생을 제공하지 않습니다."
    if error:
        reason = f"화면 모델을 만들지 못했습니다: {error}"
    summary["replay"] = {"enabled": False, "reason": reason}
    blocks = [notice("diag-banner", "critical",
                     "이 묶음은 검증되지 않았습니다. 아래 내용은 진단용이며 완전한 성공 기록처럼 재생하지 않습니다.")]
    if error:
        blocks.append(notice("diag-adapter-error", "critical", f"화면 모델 생성 실패: {error}"))
    if reader is not None and reader.exists("manifest.json"):
        try:
            blocks.append(block("json", "diag-manifest", "manifest.json (검증되지 않은 원문)",
                                value=reader.value("manifest.json"), collapsed=False))
        except ValueError as exc:
            blocks.append(notice("diag-manifest-error", "critical", f"manifest.json 읽기 실패: {exc}"))
    reason_absent = "검증되지 않은 묶음이라 이 화면 요소를 정상 기록으로 표시하지 않습니다. 실행 요약의 진단을 확인하세요."
    tabs = {key: absent(reason_absent) for key in ("capture", "timeline", "recapture", "evidence", "delivery",
                                                     "corrections")}
    tabs["summary"] = tab("partial", blocks, "검증 실패 묶음: 진단 정보만 표시")
    return {"summary": summary, "steps": [], "tabs": tabs}


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "ABSENT", "ExportContext", "STAGE_LABELS", "STEP_CLASS_LABELS", "absent", "base_summary", "build_steps",
    "delivery_row", "diagnostic_model", "export_row", "outcome_row", "status", "V", "block", "derived", "notice",
    "row", "tab",
]
