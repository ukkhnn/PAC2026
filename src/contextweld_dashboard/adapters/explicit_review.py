"""명시적 재검토 묶음(review-bundle.v1) 읽기 어댑터."""
from __future__ import annotations

from typing import Any

from ..model import block, notice, row, tab
from ._runs import delivery_tab_blocks, documents_table, event_classifier, flags, frame_block, payload_seq, wps_table
from .common import absent, base_summary, build_steps, delivery_row, export_row, outcome_row

RULE_NOTICE = ("document_rule_review · new_model_calls=0 — 문서 규칙 재검토입니다. 이미지 의미·시각 관계를 모델이 새로 "
               "해석하지 않았습니다.")
O07_NOTICE = ("수정 저장·명시적 재검토·모의 전달은 서버 CLI(JSON 요청)로 따로 실행된 기록입니다. 이 화면은 조회만 하며 "
              "자동 실행·승인·재추론·재전송 기능이 없습니다.")


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    m = reader.json("manifest.json")
    events = reader.jsonl("events.jsonl")
    final_seq = max(e["seq"] for e in events) if events else None
    seqs = payload_seq(reader)
    lineage = reader.json("results/lineage.json")
    summary = base_summary(source, reader, kind_label="명시적 재검토 실행", title=str(m.get("run_id")), final_seq=final_seq)
    summary["flags"] = flags(reader, ("review_scope", "new_model_calls", "relation_reinterpretation", "delivery_requested",
                                      "delivery_fault_injection", "correction_source_kinds", "execution_authorized",
                                      "application_authorized", "demo_complete"))
    summary["headline"] = [row("재검토 요청", reader.value("manifest.json", "review_request_id")),
                           row("선택 수정", reader.value("manifest.json", "correction_ids"))]
    summary["replay"] = {"enabled": True, "reason": None}
    nodes = []
    for i, anc in enumerate(lineage.get("ancestors", []) if isinstance(lineage, dict) else []):
        key = ctx.run_key_for(anc.get("run_id"), anc.get("manifest_sha256"))
        nodes.append({"role": "ancestor", "label": f"조상 {i + 1} ({anc.get('run_kind')})",
                      "run_id": reader.value("results/lineage.json", "ancestors", i, "run_id"),
                      "kind_label": str(anc.get("run_kind")), "run_key": key,
                      "rows": [row("manifest_sha256", reader.value("results/lineage.json", "ancestors", i, "manifest_sha256")),
                               row("bundle_ref", reader.value("results/lineage.json", "ancestors", i, "bundle_ref"))]})
    nodes.append({"role": "self", "label": "현재 재검토 실행", "run_id": reader.value("manifest.json", "run_id"),
                  "kind_label": "review", "run_key": None, "rows": []})
    summary["links"] = [{"relation": rel, "label": label, "run_id": reader.value("manifest.json", field),
                         "run_key": ctx.run_key_for(m.get(field)), "note": ""}
                        for rel, label, field in (("parent", "즉시 부모", "parent_run_id"),
                                                  ("origin", "원래 문서 실행", "origin_run_id"),
                                                  ("recognition", "원래 인식 실행", "recognition_run_id"))]
    steps = build_steps(reader, "events.jsonl", event_classifier(reader))
    fault = m.get("delivery_fault_injection")
    top = [notice("rule", "info", RULE_NOTICE)]
    if "demo_fixture" in (m.get("correction_source_kinds") or []):
        top.append(notice("fixture", "warning", "선택 수정의 작성 주체는 demo_fixture입니다. 자동 시연용 예시이며 사람이 검수한 기록이 아닙니다."))
    if fault:
        top.append(notice("fault", "serious", f"시연용 결함 주입: {fault} — 일부러 만든 전달 실패입니다. 성공 ACK를 만들지 않았습니다."))
    flow = block("flow", "flow", "흐름 요약", items=[
        {"key": "observe", "label": "무엇을 보았나", "state": "done", "summary": "원래 관측(model) 재사용 · 새 모델 호출 0", "tab": "capture"},
        {"key": "recapture", "label": "왜 재촬영", "state": "absent", "summary": "재촬영 기록 없음", "tab": "recapture"},
        {"key": "reread", "label": "다시 무엇을 읽었나", "state": "done", "summary": "선택 수정 적용 후 문서 규칙 재판단(rule)", "tab": "corrections"},
        {"key": "evidence", "label": "어떤 근거", "state": "done", "summary": "WPS 필드·복구 수정·이슈 해결", "tab": "evidence"},
        {"key": "delivery", "label": "무엇을 보냈나", "state": "done" if m.get("delivery_status") == "received" else
         ("failed" if m.get("delivery_status") == "failed" else "not_done"),
         "summary": f"delivery_status={m.get('delivery_status')}", "tab": "delivery"}])
    summary_blocks = top + [flow,
        block("fields", "status", "실행 상태 (저장값 그대로)", rows=[
            outcome_row(reader, seq=final_seq), export_row(reader, seq=final_seq), delivery_row(reader, seq=final_seq),
            row("시작 UTC", reader.value("manifest.json", "started_at_utc")),
            row("종료 UTC", reader.value("manifest.json", "finished_at_utc"), seq=final_seq),
            row("즉시 부모 실행", reader.value("manifest.json", "parent_run_id")),
            row("원래 문서 실행", reader.value("manifest.json", "origin_run_id")),
            row("원래 인식 실행", reader.value("manifest.json", "recognition_run_id")),
            row("프레임", reader.value("manifest.json", "frame_id"))]),
        block("lineage", "lineage", "실행 계보 (results/lineage.json)", nodes=nodes),
        block("json", "limitations", "기록된 한계 (limitations 원문)", value=reader.value("manifest.json", "limitations"))]
    origin_ref = lineage["ancestors"][0]["bundle_ref"] if lineage.get("ancestors") else "inputs/parent"
    origin_input = reader.get(f"{origin_ref}/manifest.json", "input_bundle_ref")
    rec_ref = f"{origin_ref}/{origin_input}" if isinstance(origin_input, str) else f"{origin_ref}/inputs/recognition"
    capture = tab("partial", top[:1] + [notice("ab", "warning", "A/B 없음 — 공개 사진 기반 재검토입니다.")]
                  + frame_block(reader, ctx, rec_ref, m.get("frame_id"), "frame", f"원래 관측 · {m.get('frame_id')} (model, 보존된 모델 출력)")
                  + [block("json", "effective", "재검토 후 유효 해석 (effective-interpretation, rule)",
                           value=reader.value("results/effective-interpretation.json"), collapsed=True,
                           seq=seqs.get("results/effective-interpretation.json"))],
                  "A/B 촬영 쌍이 없는 공개 사진 기반 재검토")
    ws = "results/work-spec.json"

    def origin_of(name: str, item: dict) -> str:
        return "document"

    evidence = tab("available", top[:1] + [
        notice("orig", "warning", "원문 PDF는 묶음에 포함되지 않았습니다. 저장된 발췌·위치만 보여 줍니다."),
        wps_table(reader, ws, seqs.get(ws), origin_of=origin_of),
        documents_table(reader, ws, seqs.get(ws)),
        block("fields", "validation", "검증·보류 상태", seq=seqs.get(ws), rows=[
            row("validation.status", reader.value(ws, "validation", "status")),
            row("issues", reader.value(ws, "validation", "issues")),
            row("application_authorized", reader.value(ws, "application_authorized")),
            row("execution_authorized", reader.value(ws, "execution_authorized"))]),
        block("json", "matching", "표기 → 대상 (matching)", value=reader.value("results/matching.json"), collapsed=True,
              seq=seqs.get("results/matching.json")),
        block("json", "issues", "이슈 해결 (해결·잔존·새 이슈, issue-resolution)", value=reader.value("results/issue-resolution.json"),
              collapsed=False, seq=seqs.get("results/issue-resolution.json"))])
    ca = "results/correction-application.json"
    entries = reader.get(ca, "entries")
    entry_rows = [{"seq": seqs.get(ca), "origin": str(e.get("source_kind")) if e.get("source_kind") in ("user", "demo_fixture") else "rule",
                   "cells": {"order": reader.value(ca, "entries", i, "order"), "cid": reader.value(ca, "entries", i, "correction_id"),
                             "stage": reader.value(ca, "entries", i, "stage"), "action": reader.value(ca, "entries", i, "action"),
                             "kind": reader.value(ca, "entries", i, "source_kind"), "status": reader.value(ca, "entries", i, "status"),
                             "effect": reader.value(ca, "entries", i, "effect")}}
                  for i, e in enumerate(entries if isinstance(entries, list) else [])]
    req = "inputs/review-request.json"
    corr_blocks = [notice("o07", "info", O07_NOTICE)] + top[1:] + [
        block("fields", "request", "명시적 재검토 요청 (inputs/review-request.json)", rows=[
            row(k, reader.value(req, k)) for k in ("review_request_id", "requested_by", "reason", "correction_ids",
                                                    "delivery_requested", "delivery_fault_injection", "parent_run_id",
                                                    "parent_manifest_sha256", "requested_at_utc", "request_sha256", "interface")]),
        block("table", "application", "수정 적용 순서 (correction-application)", seq=seqs.get(ca), columns=[
            {"key": "order", "label": "순서"}, {"key": "cid", "label": "수정 ID"}, {"key": "stage", "label": "단계"},
            {"key": "action", "label": "동작"}, {"key": "kind", "label": "작성 주체"}, {"key": "status", "label": "상태"},
            {"key": "effect", "label": "효과"}], rows=entry_rows, empty_text="적용 기록 없음")]
    for cid in m.get("correction_ids") or []:
        ref = f"inputs/corrections/{cid}.json"
        if not reader.exists(ref):
            continue
        corr_blocks.append(block("diff", f"diff-{cid}", f"수정 기록 {cid} (원래 값과 분리 저장)", items=[{
            "id": cid, "label": "수정 전 → 후", "before": reader.value(ref, "before"), "after": reader.value(ref, "after"),
            "origin_before": "model", "origin_after": str(reader.get(ref, "source_kind")),
            "rows": [row(k, reader.value(ref, k)) for k in ("action", "reason", "author", "source_kind", "recorded_at_utc", "target")]}]))
    tabs = {"summary": tab("available", summary_blocks), "capture": capture,
            "timeline": tab("available", [notice("rule-t", "info", RULE_NOTICE)]),
            "recapture": absent("재검토 실행에는 재촬영 요청·A/B 자세 기록이 없습니다."),
            "evidence": evidence, "delivery": tab("available", delivery_tab_blocks(reader, seqs, final_seq)),
            "corrections": tab("available", corr_blocks)}
    return {"summary": summary, "steps": steps, "tabs": tabs}
