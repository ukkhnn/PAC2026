"""재촬영 루프 묶음(recapture-bundle.v1) 읽기 어댑터.

저장된 A/B 중 관측 판단으로 실제 사용할 프레임을 고르고, 재촬영 요청이 있었을 때만 B를 추론에
사용한다. 이 어댑터는 ``verify_recapture_bundle()``(integrity 계층)이 통과한 묶음을 읽기만 한다.
원문 파일·저장 좌표·재촬영 사유(reason_codes)·A/B 차이를 화면에 보여 주며, 팔 이동·전달·문서 적용을
만들거나 암시하지 않는다.
"""
from __future__ import annotations

from typing import Any

from ..model import block, derived, notice, overlay_bbox, overlay_polygon, row, tab
from ._runs import classify_status, payload_seq, retrieval_blocks
from .common import absent, base_summary, build_steps, delivery_row, export_row, outcome_row, status

# 품질 코드는 모델의 관측 근거다. 'glare'여도 반사 원인 검증(causal_glare_verified)이 아니다.
QUALITY_LABELS = {
    "glare": "반사 의심 (모델)",
    "occlusion": "가림",
    "blur": "흐림",
    "out_of_frame": "화면 밖",
    "small_text": "작은 글자",
    "low_contrast": "저대비",
    "unreadable": "판독 어려움",
}
FIELD_LABELS = {"marking_text": "표기 텍스트", "marking_target": "표기 대상"}


def _recapture_classifier(reader):
    """사건 상태는 저장된 stage·action·field_checks에서만 정한다. 중간 관측·관계 결과는 '기록됨'으로 둔다."""
    def classify(event: dict[str, Any], index: int) -> dict[str, Any]:
        type_ = event.get("type")
        if type_ == "run_failed":
            return status("failure", "type=run_failed", reader.value("events.jsonl", index, "type"))
        stage = event.get("stage")
        ref = event.get("payload_ref")
        if not isinstance(ref, str) or not reader.exists(ref) or not ref.endswith(".json"):
            return status("recorded", "판정할 상태 필드 없음")
        if stage == "recognition_decision":
            action = reader.get(ref, "action")
            if action == "continue":
                return status("success", "action=continue (재관측 불필요)", reader.value(ref, "action"))
            if action == "request_recapture":
                return status("undetermined", "action=request_recapture (재촬영 요청)", reader.value(ref, "action"))
            if action == "needs_review":
                return status("undetermined", "action=needs_review", reader.value(ref, "action"))
            return status("recorded", "판정할 상태 필드 없음")
        if stage == "recapture_request":
            return status("undetermined", "재촬영 요청 접수", reader.value(ref, "reason_codes"))
        if stage == "capture_assessment":
            checks = reader.get(ref, "field_checks")
            checks = checks if isinstance(checks, list) else []
            unresolved = [item for item in checks if isinstance(item, dict) and item.get("status") == "unresolved"]
            if checks and not unresolved:
                return status("success", "필수 시각정보 관측됨", reader.value(ref, "field_checks"))
            return status("undetermined", f"미확정 필드 {len(unresolved)}개", reader.value(ref, "field_checks"))
        if stage == "document_retrieval":
            if isinstance(reader.get(ref, "status"), str):
                return classify_status(reader.value(ref, "status"), "status")
            return status("recorded", "검색 실행 기록")
        if stage == "frame_ingest":
            return status("recorded", "저장 프레임 입력", reader.value(ref, "frame_id"))
        if stage == "export":
            return classify_status(reader.value("manifest.json", "run_outcome"), "run_outcome")
        return status("recorded", "판정할 상태 필드 없음")
    return classify


def _frame_value(reader, frame_id: str, *tokens: Any, origin: str | None = None) -> dict[str, Any]:
    return reader.value(f"frames/{frame_id}.json", *tokens, origin=origin)


def _pair_items(ctx, reader, frames, camera: str, label: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for frame in frames:
        fid = frame["frame_id"]
        ref = frame["image_ref"] if camera == "wrist" else frame["overview_ref"]
        image = ctx.image(reader, ref, label=f"{fid} · {label}") if isinstance(ref, str) else None
        if image is None:
            continue
        items.append({"label": f"{fid} · {label}", "image": image, "rows": [
            row("captured_at_utc (원 촬영)", _frame_value(reader, fid, "captured_at_utc", origin="simulator")),
            row("ingested_at_utc (이번 입력)", _frame_value(reader, fid, "ingested_at_utc")),
            row("capture_request_id", _frame_value(reader, fid, "capture_request_id")),
            row("request_link_semantics", _frame_value(reader, fid, "request_link_semantics")),
            row("camera_id", _frame_value(reader, fid, "camera_id", origin="simulator")),
            row("camera position (m)", _frame_value(reader, fid, "camera_pose", "position", origin="simulator")),
            row("camera quaternion (wxyz)", _frame_value(reader, fid, "camera_pose", "quaternion_wxyz", origin="simulator")),
            row("기록 SHA-256", _frame_value(reader, fid, "sha256" if camera == "wrist" else "overview_sha256",
                                             origin="simulator"))]})
    return items


def _stored_preview(ctx, reader, frames) -> list[dict[str, Any]]:
    """입력 패키지에는 A/B가 모두 있지만, 요청이 없으면 B는 추론에 쓰지 않는다. 미사용 저장 프레임을 구분해 보여 준다."""
    if not reader.exists("inputs/inputs.json"):
        return []
    src_frames = reader.get("inputs/inputs.json", "frames")
    if not isinstance(src_frames, list):
        return []
    ingested = {frame.get("frame_id") for frame in frames}
    blocks: list[dict[str, Any]] = []
    for index, src in enumerate(src_frames):
        if not isinstance(src, dict) or src.get("frame_id") in ingested:
            continue
        fid = src.get("frame_id")
        items: list[dict[str, Any]] = []
        for camera, label in (("wrist", "손목"), ("overview", "전체")):
            key = "image_ref" if camera == "wrist" else "overview_ref"
            ref = src.get(key)
            image = ctx.image(reader, f"inputs/{ref}", label=f"{fid} · {label}") if isinstance(ref, str) else None
            if image is not None:
                items.append({"label": f"{label} (저장 자료)", "image": image, "rows": [
                    row("captured_at_utc (원 촬영)", reader.value("inputs/inputs.json", "frames", index,
                                                                  "captured_at_utc", origin="simulator"))]})
        if items:
            blocks.append(notice(f"preview-{fid}", "info",
                                 f"{fid}: 입력 패키지에 저장되어 있으나 이번 실행에서 추론에 사용하지 않았습니다."))
            blocks.append(block("image_pair", f"preview-{fid}-pair", f"저장 자료 미리보기 · {fid} (미사용)", items=items))
    return blocks


def _decision_table(reader, frames, seqs) -> dict[str, Any]:
    rows = []
    for frame in frames:
        fid = frame["frame_id"]
        ref = f"results/{fid}-recognition_decision.json"
        if not reader.exists(ref):
            continue
        rows.append({"seq": seqs.get(ref), "origin": "rule", "cells": {
            "frame": derived(fid, "파일 이름의 프레임"),
            "action": reader.value(ref, "action"),
            "reason": reader.value(ref, "reason_codes"),
            "affected": reader.value(ref, "affected_fields"),
            "attempt": reader.value(ref, "attempts_used")}})
    return block("table", "decisions", "인식 판단 (rule)", columns=[
        {"key": "frame", "label": "프레임"}, {"key": "action", "label": "action"},
        {"key": "reason", "label": "reason_codes"}, {"key": "affected", "label": "미확정 필드"},
        {"key": "attempt", "label": "attempts_used"}], rows=rows, empty_text="인식 판단 기록 없음")


def _assessment_table(reader, frames, seqs) -> dict[str, Any]:
    rows = []
    for frame in frames:
        fid = frame["frame_id"]
        ref = f"results/{fid}-capture_assessment.json"
        if not reader.exists(ref):
            continue
        checks = reader.get(ref, "field_checks")
        for j, check in enumerate(checks if isinstance(checks, list) else []):
            rows.append({"seq": seqs.get(ref), "origin": "model", "cells": {
                "frame": derived(fid, "파일 이름의 프레임"),
                "field": reader.value(ref, "field_checks", j, "field"),
                "status": reader.value(ref, "field_checks", j, "status"),
                "obs": reader.value(ref, "field_checks", j, "observation_ids"),
                "explanation": reader.value(ref, "field_checks", j, "explanation")}})
    return block("table", "assessments", "촬영 품질 평가 field_checks (model)", columns=[
        {"key": "frame", "label": "프레임"}, {"key": "field", "label": "필드"}, {"key": "status", "label": "상태"},
        {"key": "obs", "label": "관측 IDs"}, {"key": "explanation", "label": "설명"}], rows=rows,
        empty_text="품질 평가 기록 없음", note="상태는 모델의 관측 근거 판단이며 정답·정확도 판정이 아닙니다.")


def _request_blocks(reader, request_refs, seqs) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for ref in request_refs:
        if not reader.exists(ref):
            continue
        prefix = "req-" + ref.replace("/", "-").replace(".", "-")
        blocks.append(block("fields", prefix, f"재촬영 요청 원문 ({ref})", seq=seqs.get(ref), rows=[
            row("request_id", reader.value(ref, "request_id")),
            row("source_frame_ids", reader.value(ref, "source_frame_ids")),
            row("source_result_ids", reader.value(ref, "source_result_ids")),
            row("reason_codes", reader.value(ref, "reason_codes")),
            row("affected_fields", reader.value(ref, "affected_fields")),
            row("attempt", reader.value(ref, "attempt")),
            row("max_attempts", reader.value(ref, "max_attempts")),
            row("suggested_adjustments", reader.value(ref, "suggested_adjustments")),
            row("capture_mode", reader.value(ref, "capture_mode")),
            row("physical_movement_triggered", reader.value(ref, "physical_movement_triggered")),
            row("requested_at_utc", reader.value(ref, "requested_at_utc"))]))
        evidence = reader.get(ref, "quality_evidence")
        ev_rows = []
        for j, ev in enumerate(evidence if isinstance(evidence, list) else []):
            ev_rows.append({"seq": seqs.get(ref), "origin": "model", "cells": {
                "code": reader.value(ref, "quality_evidence", j, "code"),
                "fields": reader.value(ref, "quality_evidence", j, "affected_fields"),
                "obs": reader.value(ref, "quality_evidence", j, "observation_ids"),
                "viewpoint": reader.value(ref, "quality_evidence", j, "viewpoint_change_may_help"),
                "explanation": reader.value(ref, "quality_evidence", j, "explanation")}})
        blocks.append(block("table", f"{prefix}-evidence", "요청 근거 quality_evidence (model)", columns=[
            {"key": "code", "label": "code"}, {"key": "fields", "label": "영향 필드"},
            {"key": "obs", "label": "관측 IDs"}, {"key": "viewpoint", "label": "시점 변경 도움 가능"},
            {"key": "explanation", "label": "설명"}], rows=ev_rows, empty_text="근거 없음",
            note="code는 모델 판단입니다. 'glare'여도 반사 원인 검증(causal_glare_verified)이 아닙니다."))
    return blocks


def _frame_evidence(ctx, reader, frame, seqs) -> list[dict[str, Any]]:
    fid = frame["frame_id"]
    image = ctx.image(reader, frame["image_ref"], label=fid)
    obs_ref, rel_ref = f"results/{fid}-observation.json", f"results/{fid}-relation.json"
    overlays, ocr_rows, vlm_rows, rel_rows = [], [], [], []
    if reader.exists(obs_ref):
        sq = seqs.get(obs_ref)
        texts = reader.get(obs_ref, "text_observations")
        for j, t in enumerate(texts if isinstance(texts, list) else []):
            poly = t.get("polygon") if isinstance(t, dict) else None
            if isinstance(poly, list):
                overlays.append(overlay_polygon(t["observation_id"], "ocr_text", poly, str(t.get("raw_text", "")),
                                                "model", reader.src(obs_ref, "text_observations", j, "polygon"),
                                                value=reader.value(obs_ref, "text_observations", j, "raw_text"), seq=sq))
            ocr_rows.append({"seq": sq, "origin": "model", "highlight": [t["observation_id"]], "cells": {
                "id": reader.value(obs_ref, "text_observations", j, "observation_id"),
                "text": reader.value(obs_ref, "text_observations", j, "raw_text")}})
        visuals = reader.get(obs_ref, "visual_objects")
        for j, o in enumerate(visuals if isinstance(visuals, list) else []):
            bbox = o.get("bbox") if isinstance(o, dict) else None
            if isinstance(bbox, list):
                label = o.get("visible_text") or o.get("description") or ""
                overlays.append(overlay_bbox(o["observation_id"], f"vlm_{o.get('kind', 'other')}", bbox, str(label),
                                             "model", reader.src(obs_ref, "visual_objects", j, "bbox"),
                                             value=reader.value(obs_ref, "visual_objects", j, "description"), seq=sq))
            vlm_rows.append({"seq": sq, "origin": "model", "highlight": [o["observation_id"]], "cells": {
                "id": reader.value(obs_ref, "visual_objects", j, "observation_id"),
                "kind": reader.value(obs_ref, "visual_objects", j, "kind"),
                "text": reader.value(obs_ref, "visual_objects", j, "visible_text"),
                "desc": reader.value(obs_ref, "visual_objects", j, "description")}})
    if reader.exists(rel_ref):
        sq = seqs.get(rel_ref)
        relations = reader.get(rel_ref, "relations")
        for j, r in enumerate(relations if isinstance(relations, list) else []):
            rel_rows.append({"seq": sq, "origin": "model",
                             "highlight": list(r.get("source_observation_ids") or []) + [r.get("selected_target_observation_id")],
                             "cells": {"frame": derived(fid, "파일 이름의 프레임"),
                                       "id": reader.value(rel_ref, "relations", j, "relation_id"),
                                       "src": reader.value(rel_ref, "relations", j, "source_observation_ids"),
                                       "cands": reader.value(rel_ref, "relations", j, "target_observation_candidates"),
                                       "sel": reader.value(rel_ref, "relations", j, "selected_target_observation_id"),
                                       "interp": reader.value(rel_ref, "relations", j, "interpretation"),
                                       "reason": reader.value(rel_ref, "relations", j, "reason_codes"),
                                       "docs": reader.value(rel_ref, "relations", j, "document_refs")}})
    legend = [{"kind": "ocr_text", "label": "OCR 문자 영역 (다각형)"}, {"kind": "vlm_text", "label": "VLM 문자"},
              {"kind": "vlm_member", "label": "VLM 부재"}, {"kind": "vlm_joint", "label": "VLM 이음"},
              {"kind": "vlm_other", "label": "VLM 기타"}]
    ret_ref = f"evidence/{fid}-retrieval.json"
    return [block("image", f"img-{fid}", f"{fid} 원본 + 저장 좌표 오버레이", image=image, overlays=overlays,
                  legend=legend, caption="저장 좌표가 없으면 그리지 않았습니다.") if image else
            notice(f"noimg-{fid}", "critical", "프레임 이미지 파일 없음"),
            block("table", f"ocr-{fid}", "OCR 관측 (model)", rows=ocr_rows, columns=[
                {"key": "id", "label": "관측 ID"}, {"key": "text", "label": "OCR 원문"}], empty_text="OCR 관측 없음"),
            block("table", f"vlm-{fid}", "VLM 시각 관측 (model)", rows=vlm_rows, columns=[
                {"key": "id", "label": "관측 ID"}, {"key": "kind", "label": "종류"}, {"key": "text", "label": "visible_text"},
                {"key": "desc", "label": "설명"}], empty_text="VLM 관측 없음"),
            block("table", f"rel-{fid}", "관계 해석 (model, 표기→대상)", rows=rel_rows, columns=[
                {"key": "frame", "label": "프레임"}, {"key": "id", "label": "relation"}, {"key": "src", "label": "출발 관측"},
                {"key": "cands", "label": "후보"}, {"key": "sel", "label": "선택"}, {"key": "interp", "label": "해석"},
                {"key": "reason", "label": "reason_codes"}, {"key": "docs", "label": "document_refs"}],
                empty_text="관계 해석 결과 없음")] + retrieval_blocks(reader, ret_ref, seqs.get(ret_ref), f"ret-{fid}")


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    m = reader.json("manifest.json")
    events = reader.jsonl("events.jsonl")
    final_seq = max(e["seq"] for e in events) if events else None
    seqs = payload_seq(reader)
    frames = m.get("frames") or []
    request_refs = m.get("request_refs") or []
    evidence_kind = m.get("evidence_kind")

    summary = base_summary(source, reader, kind_label="재촬영 루프 실행", title=str(m.get("run_id")), final_seq=final_seq)
    summary["flags"] = [row("visual_outcome", reader.value("manifest.json", "visual_outcome")),
                        row("recapture_outcome", reader.value("manifest.json", "recapture_outcome")),
                        row("inference_status", reader.value("manifest.json", "inference_status")),
                        row("physical_movement_triggered", reader.value("manifest.json", "physical_movement_triggered")),
                        row("recognition_feedback_enabled", reader.value("manifest.json", "recognition_feedback_enabled")),
                        row("saved_frame_selection_enabled", reader.value("manifest.json", "saved_frame_selection_enabled")),
                        row("delivery_requested", reader.value("manifest.json", "delivery_requested")),
                        row("execution_authorized", reader.value("manifest.json", "execution_authorized")),
                        row("application_authorized", reader.value("manifest.json", "application_authorized")),
                        row("demo_complete", reader.value("manifest.json", "demo_complete"))]
    summary["headline"] = [row("프레임 수", derived(len(frames), "manifest.frames 개수")),
                           row("사건 수", derived(len(events), "events.jsonl 줄 수")),
                           row("재촬영 요청 수", derived(len(request_refs), "manifest.request_refs 개수"))]
    summary["replay"] = {"enabled": True, "reason": None}

    b_ingested = "frame-B" in {f.get("frame_id") for f in frames}
    requested = bool(request_refs)
    flow = block("flow", "flow", "흐름 요약", items=[
        {"key": "observe", "label": "무엇을 보았나", "state": "done",
         "summary": f"저장 프레임 {len(frames)}개 관측·품질 평가", "tab": "capture"},
        {"key": "recapture", "label": "왜 재촬영", "state": "done" if requested else "absent",
         "summary": ("재촬영 요청 1건 (저장 B 선택)" if requested else "재촬영 요청 없음"), "tab": "recapture"},
        {"key": "reread", "label": "다시 무엇을 읽었나", "state": "done" if b_ingested else "absent",
         "summary": ("저장 B 재추론" if b_ingested else "B 재추론 없음"), "tab": "capture"},
        {"key": "evidence", "label": "어떤 근거", "state": "done", "summary": "OCR·관계·품질 평가 근거", "tab": "evidence"},
        {"key": "delivery", "label": "무엇을 보냈나", "state": "absent",
         "summary": "전달 미요청 (delivery_status=not_requested)", "tab": "delivery"}])
    summary_blocks = [notice("scope", "warning",
                             "재촬영 루프 기록 실행입니다. 실제 팔 이동·문서 적용·모의 전달과 연결되지 않았습니다 "
                             "(physical_movement_triggered=false, delivery_requested=false, execution_authorized=false).")]
    if evidence_kind == "test_fixture":
        summary_blocks.append(notice("fixture", "warning",
                                     "evidence_kind=test_fixture: 모델 추론이 아니라 테스트 fixture 기록입니다."))
    summary_blocks += [flow, block("fields", "status", "실행 상태 (저장값 그대로)", rows=[
        outcome_row(reader, seq=final_seq), export_row(reader, seq=final_seq), delivery_row(reader, seq=final_seq),
        row("시각 판정 (visual_outcome)", reader.value("manifest.json", "visual_outcome"), seq=final_seq),
        row("재촬영 판정 (recapture_outcome)", reader.value("manifest.json", "recapture_outcome"), seq=final_seq),
        row("추론 상태 (inference_status)", reader.value("manifest.json", "inference_status"), seq=final_seq),
        row("시작 UTC", reader.value("manifest.json", "started_at_utc")),
        row("종료 UTC", reader.value("manifest.json", "finished_at_utc"), seq=final_seq),
        row("경과(초)", reader.value("manifest.json", "elapsed_seconds"), seq=final_seq)]),
        block("json", "limitations", "기록된 한계 (limitations 원문)", value=reader.value("manifest.json", "limitations")),
        block("raw_files", "raws", "주요 원문 파일", files=[{"root": reader.key, "path": p} for p in
              ("manifest.json", "events.jsonl", "results/inference-config.json", "inputs/inputs.json")
              if reader.exists(p)])]

    capture_blocks = [notice("ab", "info",
                             "저장 A/B 쌍. B는 재촬영 요청이 있었을 때만 추론에 사용합니다. 팔 이동은 없습니다 "
                             "(physical_movement_triggered=false).")]
    for camera, label in (("wrist", "손목 카메라"), ("overview", "전체 장면")):
        items = _pair_items(ctx, reader, frames, camera, label)
        if items:
            capture_blocks.append(block("image_pair", f"pair-{camera}", f"A/B 원본 비교 · {label}", items=items))
    capture_blocks += _stored_preview(ctx, reader, frames)

    def frames_for(event, index):
        out = []
        for fid in event.get("input_frame_ids") or []:
            frame = next((f for f in frames if f.get("frame_id") == fid), None)
            if frame:
                image = ctx.image(reader, frame["image_ref"], label=fid)
                if image:
                    out.append(image)
        return out

    steps = build_steps(reader, "events.jsonl", _recapture_classifier(reader), frames_for=frames_for)

    has_decision = any(reader.exists(f"results/{f['frame_id']}-recognition_decision.json") for f in frames)
    if has_decision:
        recap = [notice("judge", "info",
                        "재촬영 여부는 recognition_decision(rule)의 action·reason_codes와 capture_assessment(model)의 "
                        "field_checks로 읽습니다.")]
        recap.append(_decision_table(reader, frames, seqs))
        recap.append(_assessment_table(reader, frames, seqs))
        if requested:
            recap.insert(0, notice("saved", "warning",
                                   "이 요청은 저장된 B 프레임 선택 연결(saved_frame_selection)입니다. 물리 팔 이동을 "
                                   "실행하지 않았습니다(physical_movement_triggered=false)."))
            recap += _request_blocks(reader, request_refs, seqs)
        else:
            recap.append(notice("noreq", "info", "재촬영 요청 없음: 위 decision의 action·reason_codes가 사유입니다."))
        recapture_tab = tab("available", recap)
    else:
        recapture_tab = absent("재촬영 판단 기록 없음(실행 실패 등으로 판단에 도달하지 않았습니다).")

    evidence_blocks = []
    for frame in frames:
        evidence_blocks += _frame_evidence(ctx, reader, frame, seqs)
    if not frames:
        evidence_blocks = [notice("no-ev", "info", "관측·관계·근거 기록이 없습니다.")]

    tabs = {
        "summary": tab("available", summary_blocks),
        "capture": tab("available" if frames else "partial", capture_blocks,
                       None if frames else "사용된 프레임 기록이 없습니다."),
        "timeline": tab("available", [notice("keys", "info",
                                            "사건은 seq·parent_event_ids·input_result_ids로 인과를 표시합니다. "
                                            "B 관측 결과는 B 사건 이후에만 현재 값으로 표시합니다.")]),
        "recapture": recapture_tab,
        "evidence": tab("available", evidence_blocks),
        "delivery": absent("전달 미요청(delivery_requested=false, delivery_status=not_requested) — 문서 적용·모의 "
                           "전달은 이 실행과 연결되지 않았습니다."),
        "corrections": absent("재촬영 루프 실행에는 수정·재검토 기록이 없습니다."),
    }
    return {"summary": summary, "steps": steps, "tabs": tabs}
