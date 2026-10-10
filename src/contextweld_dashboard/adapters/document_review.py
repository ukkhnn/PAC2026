"""문서 검토 묶음(document-demo-bundle.v1) 읽기 어댑터."""
from __future__ import annotations

from typing import Any

from ..model import block, notice, row, tab
from ._runs import (delivery_tab_blocks, documents_table, event_classifier, flags, frame_block, payload_seq,
                    retrieval_blocks, wps_table)
from .common import absent, base_summary, build_steps, delivery_row, export_row, outcome_row


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    m = reader.json("manifest.json")
    events = reader.jsonl("events.jsonl")
    final_seq = max(e["seq"] for e in events) if events else None
    seqs = payload_seq(reader)
    summary = base_summary(source, reader, kind_label="문서 검토 실행", title=str(m.get("run_id")), final_seq=final_seq)
    summary["flags"] = flags(reader, ("case", "frame_id", "evaluation_scope", "delivery_requested", "new_model_calls",
                                      "execution_authorized", "application_authorized", "demo_complete"))
    summary["headline"] = [row("사례(case)", reader.value("manifest.json", "case")),
                           row("프레임", reader.value("manifest.json", "frame_id"))]
    rec_sha = reader.json("inputs/recognition/manifest.json") and None
    parent = m.get("parent_run_id")
    key = ctx.run_key_for(parent, m.get("source_manifest_hash"))
    summary["links"] = [{"relation": "recognition", "label": "원래 인식 실행", "run_id": reader.value("manifest.json", "parent_run_id"),
                         "run_key": key, "note": "manifest SHA-256 일치 시에만 연결" if key else "패키지 안 같은 묶음 확인 불가"}]
    summary["replay"] = {"enabled": True, "reason": None}
    steps = build_steps(reader, "events.jsonl", event_classifier(reader))
    ws = "results/work-spec.json"
    ws_seq = seqs.get(ws)
    flow = block("flow", "flow", "흐름 요약", items=[
        {"key": "observe", "label": "무엇을 보았나", "state": "done", "summary": "원래 인식 실행(공개 사진)의 저장 관측을 재사용", "tab": "capture"},
        {"key": "recapture", "label": "왜 재촬영", "state": "absent", "summary": "재촬영 기록 없음 (공개 사진)", "tab": "recapture"},
        {"key": "reread", "label": "다시 무엇을 읽었나", "state": "absent", "summary": "새 모델 호출 없음 (new_model_calls=0)", "tab": "evidence"},
        {"key": "evidence", "label": "어떤 근거", "state": "done", "summary": "작업지시·도면 fixture와 WPS 근거 연결", "tab": "evidence"},
        {"key": "delivery", "label": "무엇을 보냈나", "state": "done" if m.get("delivery_status") == "received" else "not_done",
         "summary": f"delivery_status={m.get('delivery_status')}", "tab": "delivery"}])
    summary_blocks = [
        notice("scope", "warning", "문서 검토용 부분 실행입니다. 실제 설비 실행·현장 적용은 승인되지 않았고 전체 데모 완료가 아닙니다."),
        flow,
        block("fields", "status", "실행 상태 (저장값 그대로)", rows=[
            outcome_row(reader, seq=final_seq), export_row(reader, seq=final_seq), delivery_row(reader, seq=final_seq),
            row("시작 UTC", reader.value("manifest.json", "started_at_utc")),
            row("종료 UTC", reader.value("manifest.json", "finished_at_utc"), seq=final_seq),
            row("원래 인식 실행", reader.value("manifest.json", "parent_run_id")),
            row("인식 묶음 manifest 해시", reader.value("manifest.json", "source_manifest_hash"))]),
        block("lineage", "lineage", "계보", nodes=[
            {"role": "recognition", "label": "원래 인식 실행", "run_id": reader.value("manifest.json", "parent_run_id"),
             "kind_label": "인식 bootstrap", "run_key": key, "rows": []},
            {"role": "self", "label": "현재 실행", "run_id": reader.value("manifest.json", "run_id"),
             "kind_label": "문서 검토 실행", "run_key": None, "rows": []}]),
        block("json", "limitations", "기록된 한계 (limitations 원문)", value=reader.value("manifest.json", "limitations"), collapsed=False),
        block("raw_files", "raws", "주요 원문 파일", files=[{"root": reader.key, "path": p} for p in
              ("manifest.json", "events.jsonl", "results/work-spec.json", "results/matching.json",
               "results/observation-selection.json", "evidence/retrieval.json", "results/delivery.json") if reader.exists(p)]),
    ]
    capture = tab("partial", [notice("ab", "warning", "A/B 없음 — 공개 사진 기반 문서 검토 실행입니다. 촬영 전후 쌍이 아닙니다.")]
                  + frame_block(reader, ctx, "inputs/recognition", m.get("frame_id"), "frame", f"선택 프레임 {m.get('frame_id')} · 원래 관측(model)")
                  + [block("json", "selection", "관측 선택·불일치 (results/observation-selection.json)",
                           value=reader.value("results/observation-selection.json"), collapsed=True,
                           seq=seqs.get("results/observation-selection.json"))],
                  "A/B 촬영 쌍이 없는 공개 사진 실행")
    timeline = tab("available", [notice("ev-keys", "info", "문서 검토 사건에는 type·input_frame_ids·input_result_ids·request_id 키가 "
                                        "저장되지 않았습니다. 해당 칸은 '기록 없음'으로 표시합니다.")])
    recapture = absent("문서 검토 실행에는 재촬영 요청·A/B 자세 기록이 없습니다(공개 사진 재사용).")
    evidence_blocks = [
        notice("orig", "warning", "원문 PDF는 묶음에 포함되지 않았습니다(source originals 미포함). 저장된 발췌·위치만 보여 줍니다."),
        block("json", "target", "표기 → 대상 (matching 결과)", value=reader.value("results/matching.json"), collapsed=True,
              seq=seqs.get("results/matching.json")),
        wps_table(reader, ws, ws_seq),
        documents_table(reader, ws, ws_seq),
        block("fields", "validation", "검증·보류 상태", seq=ws_seq, rows=[
            row("validation.status", reader.value(ws, "validation", "status")),
            row("issues", reader.value(ws, "validation", "issues")),
            row("missing_fields", reader.value(ws, "validation", "missing_fields")),
            row("application_missing", reader.value(ws, "application_missing")),
            row("physical_applicability", reader.value(ws, "physical_applicability")),
            row("range_combination_validated", reader.value(ws, "range_combination_validated")),
            row("application_authorized", reader.value(ws, "application_authorized")),
            row("execution_authorized", reader.value(ws, "execution_authorized")),
            row("fault_injections (시연 결함 주입)", reader.value(ws, "fault_injections"))]),
        block("json", "constraints", "제약·적용조건 (constraints)", value=reader.value(ws, "constraints"), collapsed=True, seq=ws_seq),
        block("json", "source-review", "전사 검수 범위 (현장 적용 승인과 구분)", value=reader.value(ws, "source_review"),
              collapsed=True, seq=ws_seq),
    ] + retrieval_blocks(reader, "evidence/retrieval.json", seqs.get("evidence/retrieval.json"), "ret")
    tabs = {"summary": tab("available", summary_blocks), "capture": capture, "timeline": timeline, "recapture": recapture,
            "evidence": tab("available", evidence_blocks),
            "delivery": tab("available", delivery_tab_blocks(reader, seqs, final_seq)),
            "corrections": absent("문서 검토 실행에는 수정 기록이 없습니다. 수정·재검토는 명시적 재검토 실행에서 확인합니다.")}
    del rec_sha
    return {"summary": summary, "steps": steps, "tabs": tabs}
