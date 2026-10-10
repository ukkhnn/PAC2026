"""문서 검토·명시적 재검토 묶음 공통 표시(WPS 표, 전달 단계, 사건 상태 분류, 원래 관측 프레임)."""
from __future__ import annotations

from typing import Any

from ..bundle_io import BundleReader
from ..model import ABSENT, block, derived, notice, overlay_bbox, overlay_polygon, row
from .common import ExportContext, status

SUCCESS = {"received", "retrieved", "matched", "ready_for_mock", "succeeded", "complete", "resolved", "verified", "passed"}
UNDETERMINED = {"needs_review", "blocked", "ambiguous", "unresolved", "conflict", "missing", "hold", "not_matched",
                "no_match", "revision_mismatch"}
FAILURE = {"failed", "error", "rejected"}
ACK_NOTICE = "모의 ACK는 수신·형식 검사 결과입니다. 용접 완료·현장 적용 승인·실행 승인이 아닙니다."


def classify_status(value: dict[str, Any], what: str) -> dict[str, Any]:
    v = value.get("v")
    if value.get("absent"):
        return status("recorded", f"{what}: 상태 필드 없음", value)
    if v in SUCCESS:
        return status("success", f"{what}={v}", value)
    if v in UNDETERMINED:
        return status("undetermined", f"{what}={v}", value)
    if v in FAILURE:
        return status("failure", f"{what}={v}", value)
    return status("recorded", f"{what}={v}", value)


def event_classifier(reader: BundleReader, events_ref: str = "events.jsonl"):
    """사건 상태는 사건 type 또는 payload의 저장 상태 필드에서만 정한다."""
    def classify(event: dict[str, Any], index: int) -> dict[str, Any]:
        type_ = event.get("type")
        if type_ in ("run_failed", "delivery_failed"):
            return status("failure", f"type={type_}", reader.value(events_ref, index, "type"))
        ref = event.get("payload_ref")
        if not isinstance(ref, str) or not reader.exists(ref) or not ref.endswith(".json"):
            return status("recorded", "판정할 상태 필드 없음")
        try:
            document = reader.json(ref)
        except ValueError:
            return status("recorded", "payload JSON 아님")
        if ref == "manifest.json":
            return classify_status(reader.value(ref, "run_outcome"), "run_outcome")
        if isinstance(document, dict) and isinstance(document.get("validation"), dict):
            return classify_status(reader.value(ref, "validation", "status"), "validation.status")
        if isinstance(document, dict) and isinstance(document.get("ack"), dict):
            return classify_status(reader.value(ref, "ack", "status"), "ack.status")
        if isinstance(document, dict) and "status" in document:
            return classify_status(reader.value(ref, "status"), "status")
        if isinstance(document, dict) and isinstance(document.get("issues"), list):
            value = reader.value(ref, "issues")
            return status("undetermined" if document["issues"] else "success",
                          f"issues {len(document['issues'])}건", value)
        return status("recorded", "판정할 상태 필드 없음")
    return classify


def payload_seq(reader: BundleReader, events_ref: str = "events.jsonl") -> dict[str, int]:
    seqs: dict[str, int] = {}
    for event in reader.jsonl(events_ref):
        ref = event.get("payload_ref")
        if isinstance(ref, str):
            seqs[ref] = event["seq"]
    return seqs


def flags(reader: BundleReader, names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [row(name, reader.value("manifest.json", name)) for name in names]


def wps_table(reader: BundleReader, ref: str, seq: int | None, *, origin_of=None) -> dict[str, Any]:
    params = reader.get(ref, "parameters")
    rows = []
    if isinstance(params, dict):
        for name in params:
            def p(*tokens: Any) -> dict[str, Any]:
                return reader.value(ref, "parameters", name, *tokens)
            item = params[name] if isinstance(params[name], dict) else {}
            origin = origin_of(name, item) if origin_of else "document"
            rows.append({"id": f"param-{name}", "seq": seq, "origin": origin, "cells": {
                "name": derived(name, "parameters의 키 이름"),
                "value": p("value"), "unit": p("unit"), "raw": p("raw_value"),
                "doc": p("evidence", "document_id"), "rev": p("evidence", "revision"),
                "page": p("evidence", "locator", "page"), "bbox": p("evidence", "locator", "bbox"),
                "coord": p("evidence", "locator", "coordinate_system"),
                "restored": p("restored_by_correction_id"),
            }})
    return block("table", "wps-params", "WPS 필드 · 값 · 단위 · 원문 위치", seq=seq, columns=[
        {"key": "name", "label": "필드"}, {"key": "value", "label": "값 (범위는 {min,max})"}, {"key": "unit", "label": "단위"},
        {"key": "raw", "label": "원문값"}, {"key": "doc", "label": "문서"}, {"key": "rev", "label": "개정"},
        {"key": "page", "label": "PDF 쪽"}, {"key": "bbox", "label": "bbox"}, {"key": "coord", "label": "좌표계"},
        {"key": "restored", "label": "복구 수정"}],
        rows=rows, empty_text="저장된 WPS 필드 없음",
        note="범위값은 문서 전사값이며 특정 운전값을 고른 결과가 아닙니다. 전사 검수·JSON 통과는 현장 적용 승인이 아닙니다.")


def documents_table(reader: BundleReader, ref: str, seq: int | None) -> dict[str, Any]:
    docs = reader.get(ref, "documents")
    rows = []
    for i, _doc in enumerate(docs if isinstance(docs, list) else []):
        def d(*tokens: Any) -> dict[str, Any]:
            return reader.value(ref, "documents", i, *tokens)
        rows.append({"seq": seq, "origin": "document", "cells": {
            "id": d("document_id"), "rev": d("revision"), "kind": d("source_kind"), "origin": d("document_origin"),
            "loc": d("locator"), "hash": d("source_hash")}})
    return block("table", "documents", "연결 문서 (fixture·synthetic_demo는 시연 설정)", seq=seq, columns=[
        {"key": "id", "label": "문서 ID"}, {"key": "rev", "label": "개정"}, {"key": "kind", "label": "source_kind"},
        {"key": "origin", "label": "document_origin"}, {"key": "loc", "label": "위치"}, {"key": "hash", "label": "원문 SHA-256"}],
        rows=rows, empty_text="연결 문서 기록 없음")


def retrieval_blocks(reader: BundleReader, ref: str, seq: int | None, prefix: str) -> list[dict[str, Any]]:
    if not reader.exists(ref):
        return [notice(f"{prefix}-none", "info", f"검색 근거 파일({ref}) 없음")]
    def r(*tokens: Any) -> dict[str, Any]:
        return reader.value(ref, *tokens)
    hits = reader.get(ref, "hits")
    rows = []
    for i, _hit in enumerate(hits if isinstance(hits, list) else []):
        def h(*tokens: Any) -> dict[str, Any]:
            return reader.value(ref, "hits", i, *tokens)
        rows.append({"seq": seq, "origin": "document", "cells": {
            "doc": h("document_id"), "chunk": h("chunk_id"), "rev": h("revision"), "loc": h("locator"),
            "text": h("text"), "score": h("score"), "rank": h("rank"), "hash": h("source_hash")}})
    return [
        block("fields", f"{prefix}-query", "문서 검색 조건 (조회 방식·필터·질의)", seq=seq, rows=[
            row("retriever", r("retriever")), row("질의(query)", r("query")), row("필터(filters)", r("filters")),
            row("top_k", r("top_k")), row("status", r("status")), row("reason", r("reason")),
            row("반환 근거 ID", r("returned_evidence_ids")), row("실제 사용 근거 ID", r("used_evidence_ids")),
            row("개정 처리", r("revision_resolution")), row("used_for", r("used_for")),
            row("원문 대조 여부(raw_sources_verified)", r("raw_sources_verified"))]),
        block("table", f"{prefix}-hits", "반환 근거 (발췌·위치)", seq=seq, columns=[
            {"key": "doc", "label": "문서"}, {"key": "chunk", "label": "chunk"}, {"key": "rev", "label": "개정"},
            {"key": "loc", "label": "위치"}, {"key": "text", "label": "발췌"}, {"key": "score", "label": "검색 점수"},
            {"key": "rank", "label": "순위"}, {"key": "hash", "label": "원문 해시"}], rows=rows,
            empty_text="반환 근거 없음", note="검색 점수는 순위용이며 적합성·승인 근거가 아닙니다."),
    ]


def delivery_stages(reader: BundleReader, seqs: dict[str, int]) -> dict[str, Any]:
    """명령 생성 → 실제 전송 → ACK 확인 → 수신기 수신. 저장 파일이 없으면 '기록 없음'(만들지 않음)."""
    stages = []
    has_cmd = reader.exists("commands/command.json")
    has_tr = reader.exists("commands/transport.json")
    has_err = reader.exists("commands/transport-error.json")
    has_rx = reader.exists("commands/receiver.jsonl") and bool(reader.jsonl("commands/receiver.jsonl"))
    cmd_rows = []
    if has_cmd:
        cmd_rows = [row("command_id", reader.value("commands/command.json", "command_id")),
                    row("purpose", reader.value("commands/command.json", "purpose"))]
    elif has_tr:
        cmd_rows = [row("command_id (전송 본문)", reader.value("commands/transport.json", "request", "command_id"))]
    stages.append({"key": "command", "label": "명령 생성", "state": "done" if (has_cmd or has_tr or has_err) else "absent",
                   "state_label": "명령 기록 있음" if (has_cmd or has_tr or has_err) else "명령 기록 없음 (만들지 않음)",
                   "rows": cmd_rows, "seq": seqs.get("commands/command.json")})
    if has_tr:
        t = "commands/transport.json"
        stages.append({"key": "send", "label": "실제 전송", "state": "done", "state_label": "loopback HTTP 전송 기록",
                       "rows": [row("endpoint", reader.value(t, "endpoint")), row("sent_at_utc", reader.value(t, "sent_at_utc")),
                                row("http_status", reader.value(t, "http_status")),
                                row("request_sha256", reader.value(t, "request_sha256"))],
                       "seq": seqs.get(t)})
        stages.append({"key": "ack", "label": "ACK 확인", "state": "done", "state_label": "모의 ACK 수신 (용접 완료 아님)",
                       "rows": [row("ack.status", reader.value(t, "ack", "status")), row("ack_id", reader.value(t, "ack", "ack_id")),
                                row("ack.command_id", reader.value(t, "ack", "command_id")),
                                row("duplicate", reader.value(t, "ack", "duplicate")),
                                row("validation_errors", reader.value(t, "ack", "validation_errors"))],
                       "seq": seqs.get(t)})
    elif has_err:
        t = "commands/transport-error.json"
        stages.append({"key": "send", "label": "실제 전송", "state": "failed", "state_label": "전송 실패 기록",
                       "rows": [row("error_type", reader.value(t, "error_type")), row("error", reader.value(t, "error")),
                                row("endpoint", reader.value(t, "endpoint")), row("http_status", reader.value(t, "http_status")),
                                row("fault_injection", reader.value(t, "fault_injection")), row("note", reader.value(t, "note"))],
                       "seq": seqs.get(t)})
        stages.append({"key": "ack", "label": "ACK 확인", "state": "failed", "state_label": "성공 ACK 없음",
                       "rows": [row("ack", reader.value(t, "ack")),
                                row("client_ack_confirmed", reader.value(t, "client_ack_confirmed")),
                                row("receiver_side", reader.value(t, "receiver_side"))], "seq": seqs.get(t)})
    else:
        for key, label in (("send", "실제 전송"), ("ack", "ACK 확인")):
            stages.append({"key": key, "label": label, "state": "absent", "state_label": "기록 없음 (만들지 않음)", "rows": []})
    if has_rx:
        rx = reader.jsonl("commands/receiver.jsonl")
        stages.append({"key": "receiver", "label": "수신기 수신", "state": "done", "state_label": f"수신기 기록 {len(rx)}줄",
                       "rows": [row("seq", reader.value("commands/receiver.jsonl", 0, "seq")),
                                row("request_sha256", reader.value("commands/receiver.jsonl", 0, "request_sha256"))],
                       "seq": seqs.get("commands/transport.json") or seqs.get("commands/transport-error.json")})
    else:
        stages.append({"key": "receiver", "label": "수신기 수신", "state": "absent", "state_label": "수신기 기록 없음", "rows": []})
    return block("stages", "delivery-stages", "전달 단계 (명령 생성 · 실제 전송 · ACK · 수신기)", stages=stages,
                 note=ACK_NOTICE)


def delivery_tab_blocks(reader: BundleReader, seqs: dict[str, int], final_seq: int | None) -> list[dict[str, Any]]:
    blocks = [notice("ack-notice", "warning", ACK_NOTICE), delivery_stages(reader, seqs)]
    if reader.exists("results/delivery.json"):
        blocks.append(block("json", "delivery-json", "results/delivery.json (전달 결과 원문)",
                            value=reader.value("results/delivery.json"), collapsed=False,
                            seq=seqs.get("results/delivery.json", final_seq)))
    for ref, title in (("commands/command.json", "생성한 명령(command.json)"),
                       ("commands/transport.json", "전송 기록(request·ack 포함)"),
                       ("commands/transport-error.json", "전송 실패 기록")):
        if reader.exists(ref):
            blocks.append(block("json", "j-" + ref.replace("/", "-").replace(".", "-"), title, value=reader.value(ref),
                                collapsed=True, seq=seqs.get(ref, seqs.get("commands/transport.json"))))
    if reader.exists("commands/receiver.jsonl"):
        blocks.append(block("raw_files", "rx-raw", "수신기 원본 기록", files=[{"root": reader.key,
                                                                            "path": "commands/receiver.jsonl"}]))
    return blocks


def frame_block(reader: BundleReader, ctx: ExportContext, rec_ref: str, frame_id: Any, prefix: str,
                title: str) -> list[dict[str, Any]]:
    """원래 인식 실행 결과(입력 사본)의 프레임·OCR/VLM 영역. 이 실행 이전 기록이므로 seq 없음."""
    if not isinstance(frame_id, str) or not reader.exists(f"{rec_ref}/manifest.json"):
        return [notice(f"{prefix}-noframe", "info", "원래 프레임 기록을 찾지 못했습니다.")]
    frames = reader.get(f"{rec_ref}/manifest.json", "frames")
    image = None
    for f in frames if isinstance(frames, list) else []:
        if f.get("frame_id") == frame_id:
            image = ctx.image(reader, f"{rec_ref}/{f['image_ref']}", label=frame_id)
    overlays = []
    ocr = f"{rec_ref}/results/{frame_id}-ocr.json"
    obs = f"{rec_ref}/results/{frame_id}-observation.json"
    if reader.exists(ocr):
        for j, t in enumerate(reader.get(ocr, "text_observations") or []):
            overlays.append(overlay_polygon(t["observation_id"], "ocr_text", t["polygon"], str(t.get("raw_text", "")),
                                            "model", reader.src(ocr, "text_observations", j, "polygon"),
                                            value=reader.value(ocr, "text_observations", j, "raw_text")))
    if reader.exists(obs):
        for j, o in enumerate(reader.get(obs, "visual_objects") or []):
            label = o.get("visible_text") or o.get("model_observation_id") or ""
            overlays.append(overlay_bbox(o["observation_id"], f"vlm_{o.get('kind', 'other')}", o["bbox"], str(label),
                                         "model", reader.src(obs, "visual_objects", j, "bbox"),
                                         value=reader.value(obs, "visual_objects", j, "description")))
    if image is None:
        return [notice(f"{prefix}-noimg", "critical", "프레임 이미지 파일이 없습니다.")]
    return [block("image", f"{prefix}-img", title, image=image, overlays=overlays,
                  caption="원래 인식 실행(공개 사진)의 저장 결과. 이 실행에서 새로 추론하지 않았습니다.")]


__all__ = ["ABSENT", "ACK_NOTICE", "classify_status", "delivery_tab_blocks", "documents_table", "event_classifier",
           "flags", "frame_block", "payload_seq", "retrieval_blocks", "wps_table"]
