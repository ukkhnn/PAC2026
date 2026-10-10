#!/usr/bin/env python3
"""완료된 채점 결과를 비교표와 독립 정적 그래프로 내보낸다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LABELS = {
    "A_ocr": "A · OCR", "B_crop": "B · VLM 재판독", "C_scene": "C · 주변 장면",
    "D_candidates": "D · 후보 목록", "E_context": "E · 작업 맥락",
    "F_context_only": "F · 이미지 제외", "RULE_D": "문자 거리 규칙",
}


def markdown(summary: dict) -> str:
    lines = ["# CTX-001 실제 실행 결과표", "", "이 표는 저장된 실제 응답의 독립 채점으로 생성했다.", "",
             "| 조건 | 판독 일치 | 올바른 확정 | 잘못된 확정 | 보류 | 모델 오류 | 사진별 평균 정답률 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for condition, label in LABELS.items():
        row = summary["per_condition"][condition]
        lines.append(f"| {label} | {row['text_exact']}/{row['n']} | {row['correct']}/{row['n']} | "
                     f"{row['wrong_accepted']} | {row['abstentions']} | {row['model_errors']} | "
                     f"{row['image_macro_accuracy_all']*100:.1f}% |")
    lines += ["", "판독 일치는 양끝 공백 제거·대문자화만 적용한다. 1/I·0/O·내부 공백은 보존한다. "
              "A/B/C의 확정값은 판독 문자열, D/E/F/규칙은 선택한 후보 ID다. "
              "A의 확정은 비어 있지 않은 OCR 출력이라는 뜻이며 신뢰성 검증을 뜻하지 않는다.", "",
              "| 조건 변화 | 틀림→맞음 | 보류→맞음 | 오류→맞음 | 맞음→틀림 | 맞음→보류 | 맞음→오류 | 정답 수 증감 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for pair, row in summary["transitions"].items():
        matrix = row['outcome_matrix']
        lines.append(f"| {pair} | {row['wrong_to_correct']} | {row['abstain_to_correct']} | "
                     f"{matrix.get('error_to_correct', 0)} | {row['correct_to_wrong']} | "
                     f"{row['correct_to_abstain']} | {matrix.get('correct_to_error', 0)} | {row['net_correct_change']:+d} |")
    lines += ["", "| 부정 맥락 | 정답 확정 | 잘못된 확정 | 보류 | 모델 오류 |",
              "|---|---:|---:|---:|---:|"]
    for condition, row in summary["negative_context"].items():
        lines.append(f"| {condition} | {row['correct']}/{row['n']} | {row['wrong_accepted']} | "
                     f"{row['abstentions']} | {row['model_errors']} |")
    lines += ["", "부정 맥락 4개씩은 정상 28개와 별도 분모다. 같은 사진의 표기들은 독립 사진이 아니다. "
              "ROI와 합성 문서는 공개 라벨에서 만든 진단 입력이며 현장 성능 평가가 아니다.", "",
              "## 개별 표기의 최종값", "", "| 표기 | 정답 | A | B | C | D | E | F | 규칙 |",
              "|---|---|---|---|---|---|---|---|---|"]
    cases = {(r["sample_id"], r["condition"]): r for r in summary["cases"]}
    for sid in sorted({r["sample_id"] for r in summary["cases"]}):
        row = [sid, cases[(sid, "A_ocr")]["truth"]]
        for condition in LABELS:
            case = cases[(sid, condition)]
            if case["model_error"]:
                cell = "모델 오류"
            elif case["accepted"]:
                value = case["visible_text"] if condition in {"A_ocr", "B_crop", "C_scene"} else case["selected_candidate_id"]
                cell = ("✓ " if case["correct"] else "✗ ") + str(value)
            else:
                cell = "보류"
            row.append(cell.replace("|", "\\|"))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def chart(summary: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = list(LABELS)
    short = ["OCR", "VLM crop", "+ scene", "+ candidates", "+ context", "No image", "Edit distance"]
    groups = [("Correct", "correct", "#227a6b"), ("Wrong", "wrong_accepted", "#c16c52"),
              ("Abstain", "abstentions", "#bec8d1"), ("Model error", "model_errors", "#705789")]
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    left = [0] * len(keys)
    for label, metric, color in groups:
        values = [summary["per_condition"][key][metric] for key in keys]
        ax.barh(short, values, left=left, color=color, label=label, height=.65)
        for i, count in enumerate(values):
            if count:
                ax.text(left[i] + count/2, i, str(count), ha="center", va="center", fontsize=11,
                        color="white" if metric in {"correct", "model_errors"} else "#1b2630")
        left = [a + b for a, b in zip(left, values)]
    ax.invert_yaxis()
    ax.set_xlim(0, summary["dataset"]["targets"])
    ax.set_xlabel("Markings (28 from 9 photographs)")
    ax.set_title("Fixed-image context experiment · actual model outputs", loc="left", fontweight="bold", pad=18)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.13), ncol=4, frameon=False)
    fig.text(.01, .012, "Given target ROIs; synthetic, label-derived context. Development diagnostic, not field accuracy.",
             fontsize=9, color="#536170")
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    if not summary["validation"]["valid"]:
        raise ValueError("채점 무결성 검증 실패: 보고서 생성을 중단합니다")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "tables.md").write_text(markdown(summary), encoding="utf-8")
    chart(summary, args.output / "comparison.png")


if __name__ == "__main__":
    main()
