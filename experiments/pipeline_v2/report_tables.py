#!/usr/bin/env python3
"""채점 JSON에서 보고서용 표(마크다운)를 만든다."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    bundle = sys.argv[2]
    block = data["bundles"][bundle]
    summary, rows = block["summary"], block["rows"]
    out = [f"단일 코드 사진 {summary['single_code_images']}장(전체 {summary['images']}장).", "",
           "| 규칙 | 올바른 진행 | 잘못 진행 | 보류 |", "|---|---|---|---|"]
    for policy, label in (("D_gate", "D_gate(제품 합의 게이트)"), ("D_ocr", "D_ocr(OCR 단독)"), ("D_vlm", "D_vlm(VLM 단독)")):
        counts = summary["policies"][policy]
        out.append(f"| {label} | {counts.get('PROCEED-correct', 0)} | {counts.get('PROCEED-wrong', 0)} | {counts.get('HOLD', 0)} |")
    out += ["", f"- 판독기 정확 일치(사진 안 어느 위치든): OCR {summary['ocr_exact_any']}/{summary['single_code_images']}, "
            f"VLM {summary['vlm_exact_any']}/{summary['single_code_images']}. "
            f"`1/I`·`O/0` 혼동 허용 진단: OCR {summary['ocr_confusable_any']}, VLM {summary['vlm_confusable_any']}.",
            f"- 관계 단계: 관계가 나온 사진 {summary['frames_with_relations']}장, 문서 인용 {summary['document_refs_total']}건. "
            f"작업 명세 필드가 빈 사진 {summary['work_spec_fields_empty']}/{summary['images']}. "
            f"`quality_issues`가 비어 있지 않은 사진 {summary['quality_issues_nonempty']}장.", "",
            "| 사진 | 정답 | OCR 후보 | VLM text 후보 | 게이트 이슈 | D_gate | D_ocr | D_vlm |",
            "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        ocr = ", ".join(f"{item['text']}({item['score']:.3f})" for item in row["ocr_ids"]) or "—"
        vlm = ", ".join(row["vlm_text_ids"]) or "—"
        issues = ", ".join(row["gate_issues"]) or "없음"
        out.append(f"| {row['image']} | {', '.join(row['truth'])} | {ocr} | {vlm} | {issues} | "
                   f"{row['outcome']['D_gate']} | {row['outcome']['D_ocr']} | {row['outcome']['D_vlm']} |")
    seconds = [row["timing"][stage]["seconds"] for row in rows for stage in row["timing"]]
    out += ["", f"- VLM 호출 {len(seconds)}회, 합계 {sum(seconds):.1f}초, 최대 {max(seconds):.1f}초."]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
