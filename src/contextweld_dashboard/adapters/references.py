"""참조 자료(문서 색인·수정 저장소·재검토 CLI 기록·시연 설정·WPS 전사) 읽기 어댑터. 실행이 아니므로 재생하지 않는다."""
from __future__ import annotations

from typing import Any

from ..model import block, derived, notice, row, tab
from .common import absent, base_summary

TITLES = {
    "document_rag": ("문서 검색 색인 (server-v1)", "evidence"),
    "correction_store": ("수정 저장소 (correction-store)", "corrections"),
    "review_cli_log": ("재검토 서버 CLI 작업 기록", "corrections"),
    "demo_config": ("문서 시연 설정 (fixture · synthetic_demo)", "evidence"),
    "knowledge": ("WPS 검수 전사 (data/knowledge)", "evidence"),
}
NOTES = {
    "correction_store": "수정 기록은 원본 실행과 분리 저장됩니다. demo_fixture 작성 기록은 사람 검수가 아닙니다.",
    "review_cli_log": "O07: 수정 저장·명시적 재검토·모의 전달은 서버 CLI와 JSON 요청으로 실행됐습니다. 이 화면은 그 기록을 조회만 합니다.",
    "demo_config": "작업지시·도면은 시연용 fixture(synthetic_demo)이며 실제 작업지시나 정답이 아닙니다.",
    "knowledge": "전사 검수 범위는 현장 적용 승인이 아닙니다.",
    "document_rag": "검색 색인은 근거 후보를 찾는 자료이며 검색 점수는 적합성 판단이 아닙니다.",
}


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    title, tab_key = TITLES.get(source.kind, (source.kind, "evidence"))
    summary = base_summary(source, None, kind_label="참조 자료 (실행 아님)", title=title, final_seq=None)
    summary["replay"] = {"enabled": False, "reason": "참조 자료는 실행 기록이 아니어서 재생 대상이 아닙니다."}
    files = [item["path"] for item in reader.inventory() if not item.get("symlink")]
    summary["headline"] = [row("파일 수", derived(len(files), "복사한 파일 개수"))]
    blocks = [notice("ref", "info", NOTES.get(source.kind, "참조 자료입니다."))]
    for path in files:
        if path.endswith(".json"):
            blocks.append(block("json", "f-" + "".join(c if c.isalnum() else "-" for c in path)[:60], path,
                                value=reader.value(path), collapsed=len(files) > 3))
    blocks.append(block("raw_files", "raws", "원문 파일", files=[{"root": reader.key, "path": p} for p in files]))
    reason = "참조 자료 — 실행 기록이 아니므로 이 화면 요소가 없습니다."
    tabs = {key: absent(reason) for key in ("capture", "timeline", "recapture", "evidence", "delivery", "corrections")}
    tabs["summary"] = tab("available", [notice("ref-s", "info", f"{title}: {NOTES.get(source.kind, '')}"),
                                        block("raw_files", "raws-s", "파일", files=[{"root": reader.key, "path": p}
                                                                                    for p in files[:200]])])
    tabs[tab_key] = tab("available", blocks)
    return {"summary": summary, "steps": [], "tabs": tabs}
