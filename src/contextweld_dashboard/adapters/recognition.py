"""인식 bootstrap 묶음(bootstrap-bundle.v1) 읽기 어댑터."""
from __future__ import annotations

from typing import Any

from ..model import block, derived, notice, overlay_bbox, overlay_polygon, row, tab
from ._runs import event_classifier, payload_seq
from .common import absent, base_summary, build_steps, export_row, outcome_row


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    m = reader.json("manifest.json")
    events = reader.jsonl("events.jsonl")
    final_seq = max(e["seq"] for e in events) if events else None
    seqs = payload_seq(reader)
    frames = m.get("frames") or []
    by_id = {f.get("frame_id"): (i, f) for i, f in enumerate(frames)}
    summary = base_summary(source, reader, kind_label="인식 bootstrap 실행", title=str(m.get("run_id")), final_seq=final_seq)
    summary["flags"] = [row("inference_status", reader.value("manifest.json", "inference_status"), seq=final_seq),
                        row("delivery_requested", reader.value("manifest.json", "delivery_requested")),
                        row("execution_authorized", reader.value("manifest.json", "execution_authorized")),
                        row("application_authorized", reader.value("manifest.json", "application_authorized")),
                        row("demo_complete", reader.value("manifest.json", "demo_complete"))]
    summary["headline"] = [row("프레임 수", derived(len(frames), "manifest.frames 개수")),
                           row("사건 수", derived(len(events), "events.jsonl 줄 수"))]
    summary["replay"] = {"enabled": True, "reason": None}

    def frames_for(event: dict, index: int) -> list:
        out = []
        for fid in event.get("input_frame_ids") or []:
            if fid in by_id:
                image = ctx.image(reader, by_id[fid][1]["image_ref"], label=fid)
                if image:
                    out.append(image)
        return out

    steps = build_steps(reader, "events.jsonl", event_classifier(reader), frames_for=frames_for)
    groups, rel_rows, hit_rows, dec_rows, ret_rows = [], [], [], [], []
    for idx, f in enumerate(frames):
        fid = f["frame_id"]
        image = ctx.image(reader, f["image_ref"], label=fid)
        ocr, obs, rel = f"results/{fid}-ocr.json", f"results/{fid}-observation.json", f"results/{fid}-relation.json"
        dec, ret = f"results/{fid}-recognition_decision.json", f"evidence/{fid}-retrieval.json"
        overlays, ocr_rows, vlm_rows = [], [], []
        if reader.exists(ocr):
            sq = seqs.get(ocr)
            for j, t in enumerate(reader.get(ocr, "text_observations") or []):
                v = lambda k: reader.value(ocr, "text_observations", j, k)  # noqa: E731
                overlays.append(overlay_polygon(t["observation_id"], "ocr_text", t["polygon"], str(t.get("raw_text", "")),
                                                "model", reader.src(ocr, "text_observations", j, "polygon"),
                                                value=v("raw_text"), seq=sq))
                ocr_rows.append({"seq": sq, "origin": "model", "highlight": [t["observation_id"]], "cells": {
                    "id": v("observation_id"), "text": v("raw_text"), "score": v("recognition_score"),
                    "det": v("detection_score")}})
        if reader.exists(obs):
            sq = seqs.get(obs)
            for j, o in enumerate(reader.get(obs, "visual_objects") or []):
                v = lambda k: reader.value(obs, "visual_objects", j, k)  # noqa: E731
                label = o.get("visible_text") or o.get("model_observation_id") or ""
                overlays.append(overlay_bbox(o["observation_id"], f"vlm_{o.get('kind', 'other')}", o["bbox"], str(label),
                                             "model", reader.src(obs, "visual_objects", j, "bbox"),
                                             value=v("description"), seq=sq))
                vlm_rows.append({"seq": sq, "origin": "model", "highlight": [o["observation_id"]], "cells": {
                    "id": v("observation_id"), "kind": v("kind"), "text": v("visible_text"), "desc": v("description"),
                    "conf": v("confidence")}})
        if reader.exists(rel):
            sq = seqs.get(rel)
            for j, r in enumerate(reader.get(rel, "relations") or []):
                v = lambda k: reader.value(rel, "relations", j, k)  # noqa: E731
                rel_rows.append({"seq": sq, "origin": "model",
                                 "highlight": list(r.get("source_observation_ids") or []) + [r.get("selected_target_observation_id")],
                                 "cells": {"frame": derived(fid, "파일 이름의 프레임"), "id": v("relation_id"),
                                           "src": v("source_observation_ids"), "cands": v("target_observation_candidates"),
                                           "sel": v("selected_target_observation_id"), "interp": v("interpretation"),
                                           "reason": v("reason_codes"), "docs": v("document_refs")}})
        if reader.exists(dec):
            dec_rows.append({"seq": seqs.get(dec), "origin": "rule", "cells": {
                "frame": derived(fid, "파일 이름의 프레임"), "action": reader.value(dec, "action"),
                "reason": reader.value(dec, "reason_codes"), "recapture": reader.value(dec, "recapture_request")}})
        if reader.exists(ret):
            sq_ret, sq_rel = seqs.get(ret), seqs.get(rel)
            ret_rows.append({"seq": sq_ret, "origin": "document", "cells": {
                "frame": derived(fid, "파일 이름의 프레임"), "query": reader.value(ret, "query"),
                "filters": reader.value(ret, "filters"), "status": reader.value(ret, "status"),
                "returned": reader.value(ret, "returned_evidence_ids")}})
            ret_rows.append({"seq": sq_rel, "origin": "model", "cells": {
                "frame": derived(fid, "파일 이름의 프레임"), "query": derived("relation 단계에서 확정", "관계 해석 사건 때 같은 파일에 기록된 필드"),
                "filters": reader.value(ret, "used_evidence_ids"), "status": reader.value(ret, "cited_evidence_ids"),
                "returned": derived("used / cited", "모델에 제공한 근거와 모델이 인용한 근거")}})
            for j, _h in enumerate(reader.get(ret, "hits") or []):
                h = lambda k: reader.value(ret, "hits", j, k)  # noqa: E731
                hit_rows.append({"seq": sq_ret, "origin": "document", "cells": {
                    "frame": derived(fid, "파일 이름의 프레임"), "doc": h("document_id"), "chunk": h("chunk_id"),
                    "rev": h("revision"), "loc": h("locator"), "text": h("text"), "score": h("score"), "rank": h("rank")}})
        legend = [{"kind": "ocr_text", "label": "OCR 문자 영역 (다각형)"}, {"kind": "vlm_text", "label": "VLM 문자"},
                  {"kind": "vlm_member", "label": "VLM 부재"}, {"kind": "vlm_joint", "label": "VLM 이음"},
                  {"kind": "vlm_other", "label": "VLM 기타"}]
        blocks = [block("image", f"img-{fid}", f"{fid} 원본 + 저장 좌표 오버레이", image=image, overlays=overlays,
                        legend=legend, caption="저장된 화살표·기호 관측 0건이므로 그리지 않았습니다.") if image else
                  notice(f"noimg-{fid}", "critical", "프레임 이미지 파일 없음"),
                  block("table", f"ocr-{fid}", "OCR 관측 (model, confidence 대신 recognition_score)", rows=ocr_rows,
                        columns=[{"key": "id", "label": "관측 ID"}, {"key": "text", "label": "OCR 원문"},
                                 {"key": "score", "label": "recognition_score"}, {"key": "det", "label": "detection_score"}],
                        empty_text="OCR 관측 없음"),
                  block("table", f"vlm-{fid}", "VLM 시각 관측 (model, confidence=null)", rows=vlm_rows,
                        columns=[{"key": "id", "label": "관측 ID"}, {"key": "kind", "label": "종류"},
                                 {"key": "text", "label": "visible_text"}, {"key": "desc", "label": "설명"},
                                 {"key": "conf", "label": "confidence"}], empty_text="VLM 관측 없음"),
                  block("fields", f"src-{fid}", "공개 데이터셋 출처 (모델 관측 아님 · 정답으로 쓰지 않음)", rows=[
                      row("source_id", reader.value("manifest.json", "frames", idx, "source_id", origin="dataset")),
                      row("dataset", reader.value("manifest.json", "frames", idx, "source", "dataset", origin="dataset")),
                      row("license_declared", reader.value("manifest.json", "frames", idx, "source", "license_declared", origin="dataset")),
                      row("크기", reader.value("manifest.json", "frames", idx, "width")),
                      row("captured_at_utc", reader.value("manifest.json", "frames", idx, "captured_at_utc")),
                      row("camera_pose", reader.value("manifest.json", "frames", idx, "camera_pose"))]),
                  block("raw_files", f"raw-{fid}", "모델 원문·구조화 결과", files=[
                      {"root": reader.key, "path": p} for p in (f"results/{fid}-ocr.raw.json", f"results/{fid}-visual.raw.txt",
                                                                f"results/{fid}-relation.raw.txt", ocr, obs, rel)
                      if reader.exists(p)])]
        groups.append({"id": fid, "label": fid, "thumb": image, "blocks": blocks})
    summary_blocks = [
        notice("scope", "warning", "공개 사진 bootstrap입니다. A/B 시뮬레이션·전체 데모 완료가 아니며 작업 필드는 비운 채 needs_review로 남깁니다."),
        block("flow", "flow", "흐름 요약", items=[
            {"key": "observe", "label": "무엇을 보았나", "state": "done", "summary": f"공개 사진 {len(frames)}장 OCR·VLM 관측", "tab": "capture"},
            {"key": "recapture", "label": "왜 재촬영", "state": "absent", "summary": "재촬영 요청 없음 (recapture_request=null)", "tab": "recapture"},
            {"key": "reread", "label": "다시 무엇을 읽었나", "state": "absent", "summary": "재판독 기록 없음", "tab": "recapture"},
            {"key": "evidence", "label": "어떤 근거", "state": "done", "summary": "문서 검색 근거 반환 · 모델 인용 0건", "tab": "evidence"},
            {"key": "delivery", "label": "무엇을 보냈나", "state": "absent", "summary": "전달 미요청 (delivery_requested=false)", "tab": "delivery"}]),
        block("fields", "status", "실행 상태 (저장값 그대로)", rows=[
            outcome_row(reader, seq=final_seq), export_row(reader, seq=final_seq),
            row("시작 UTC", reader.value("manifest.json", "started_at_utc")),
            row("종료 UTC", reader.value("manifest.json", "finished_at_utc"), seq=final_seq),
            row("경과(초)", reader.value("manifest.json", "elapsed_seconds"), seq=final_seq)]),
        block("json", "models", "모델·설정 (results/inference-config.json)", value=reader.value("results/inference-config.json", "models")
              if reader.exists("results/inference-config.json") else derived(None, "설정 파일 없음"), collapsed=True),
        block("json", "limitations", "기록된 한계 (limitations 원문)", value=reader.value("manifest.json", "limitations")),
    ]
    tabs = {
        "summary": tab("available", summary_blocks),
        "capture": tab("partial", [notice("ab", "warning", "A/B 없음 — 공개 사진 bootstrap(capture_mode=public_dataset). 촬영 전후 쌍이 아닙니다."),
                                   block("group", "frames", "프레임별 원본과 관측", layout="gallery", items=groups)],
                       "A/B 촬영 쌍이 없는 공개 사진 실행"),
        "timeline": tab("available", [notice("t", "info", "결과 status=needs_review는 업무 판단 보류이며 단계 오류가 아닙니다.")]),
        "recapture": absent("재촬영 요청 기록 없음: 모든 recognition_decision의 recapture_request가 null입니다.", [
            block("table", "decisions", "프레임별 인식 판단 (rule)", rows=dec_rows, columns=[
                {"key": "frame", "label": "프레임"}, {"key": "action", "label": "action"},
                {"key": "reason", "label": "reason_codes"}, {"key": "recapture", "label": "recapture_request"}])]),
        "evidence": tab("available", [
            notice("orig", "warning", "문서 원문 HTML은 묶음에 포함되지 않았습니다(document_originals_included=false). 저장 발췌·위치만 표시합니다."),
            block("table", "relations", "관계 해석 (model 후보, 표기→대상)", rows=rel_rows, columns=[
                {"key": "frame", "label": "프레임"}, {"key": "id", "label": "relation"}, {"key": "src", "label": "출발 관측"},
                {"key": "cands", "label": "후보"}, {"key": "sel", "label": "선택"}, {"key": "interp", "label": "해석"},
                {"key": "reason", "label": "reason_codes"}, {"key": "docs", "label": "document_refs"}],
                empty_text="관계 해석 결과 없음"),
            block("table", "retrieval", "문서 검색 (반환) · 모델 제공(used) · 인용(cited)", rows=ret_rows, columns=[
                {"key": "frame", "label": "프레임"}, {"key": "query", "label": "질의"}, {"key": "filters", "label": "필터 / used"},
                {"key": "status", "label": "status / cited"}, {"key": "returned", "label": "반환 ID"}]),
            block("table", "hits", "반환 근거 발췌·위치", rows=hit_rows, columns=[
                {"key": "frame", "label": "프레임"}, {"key": "doc", "label": "문서"}, {"key": "chunk", "label": "chunk"},
                {"key": "rev", "label": "개정"}, {"key": "loc", "label": "위치"}, {"key": "text", "label": "발췌"},
                {"key": "score", "label": "검색 점수"}, {"key": "rank", "label": "순위"}],
                note="검색 점수는 순위용이며 적합성·승인 근거가 아닙니다.")]),
        "delivery": absent("전달 미요청(delivery_requested=false) — 명령·ACK 기록이 없습니다."),
        "corrections": absent("corrections.jsonl이 비어 있습니다 — 수정 기록 없음."),
    }
    return {"summary": summary, "steps": steps, "tabs": tabs}
