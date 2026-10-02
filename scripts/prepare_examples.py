"""시연 문법·후보·작업 맥락과 SVG 입력을 생성한다. 현장 사진은 아니다."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cases = [
        ("normal", "정상 표기", "기준과 일치", "명확한 표기와 작업계획이 일치하는 경우", [6], 6, "BLK-017"),
        ("ambiguous", "모호한 수기", "맥락으로 후보 좁히기", "시연 인식 후보 6 / 8을 계획과 대조하는 경우", [6, 8], 6, "BLK-017"),
        ("conflict", "작업계획 충돌", "확정 보류", "사진의 치수 8이 계획의 치수 6과 충돌하는 경우", [8], 6, "BLK-017"),
        ("memory", "확인 이력 재사용", "같은 작업만 참조", "모호한 수기를 같은 작업의 확인 기록으로 좁히는 경우", [6, 8], None, "BLK-017"),
        ("wrong-context", "다른 부재의 계획", "맥락 오류 검출", "BLK-017 사진에 BLK-099 계획이 연결된 경우", [6], 6, "BLK-099"),
    ]
    directory = ROOT / "data/examples"
    directory.mkdir(parents=True, exist_ok=True)
    scenarios = []
    for case_id, title, tag, description, sizes, expected, part in cases:
        lines = ["PART: BLK-017", "SEAM: S-04", "WELD: FW", f"SIZE: {sizes[0]}", "POS: FLAT"]
        observations = []
        for index, line in enumerate(lines):
            texts = [f"SIZE: {size}" for size in sizes] if index == 3 else [line]
            observations.append({
                "id": f"mark-{index + 1}",
                "bbox": [0.10, 0.20 + index * 0.125, 0.62, 0.085],
                "candidates": [{"text": text, "score": 0.55 - n * 0.04 if len(texts) > 1 else 0.97} for n, text in enumerate(texts)],
            })
        text_nodes = []
        for index, line in enumerate(lines):
            transform = 'transform="rotate(-3 400 535)"' if index == 3 and len(sizes) > 1 else ""
            text_nodes.append(f'<text x="100" y="{235 + index * 112}" {transform}>{escape(line)}</text>')
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="900" viewBox="0 0 1000 900">
<defs><linearGradient id="steel" x2="1" y2="1"><stop stop-color="#303943"/><stop offset="1" stop-color="#141e28"/></linearGradient><pattern id="grain" width="80" height="60" patternUnits="userSpaceOnUse"><path d="M0 20L80 18M0 43L80 46" stroke="#738391" opacity=".09"/></pattern></defs>
<rect width="1000" height="900" fill="url(#steel)"/><rect width="1000" height="900" fill="url(#grain)"/>
<path d="M815 100V810" stroke="#73838f" stroke-width="18" opacity=".28"/><path d="M832 100V810" stroke="#0a1119" stroke-width="7"/>
<g fill="#edf0db" font-family="Menlo,monospace" font-size="53" font-weight="600">{''.join(text_nodes)}</g>
<text x="100" y="94" fill="#7c9bac" font-family="sans-serif" font-size="23">CONTEXTWELD / SYNTHETIC DEMO</text>
<text x="100" y="830" fill="#7c9bac" font-family="sans-serif" font-size="21">Demo marking grammar · Not a field photograph</text>
</svg>'''
        image = directory / f"{case_id}.svg"
        image.write_text(svg, encoding="utf-8")
        scenarios.append({
            "id": case_id, "title": title, "tag": tag, "description": description,
            "image_url": f"/examples/{case_id}.svg", "source_kind": "synthetic_demo",
            "provider": "fixture_candidates", "observations": observations,
            "context": {"part_id": part, "seam_id": "S-04", "expected_size_mm": expected,
                        "weld_type": "FILLET", "material": "DEMO-STEEL", "thickness_mm": 12,
                        "position": "FLAT", "plan_revision": "PLAN-DEMO-v1", "preceding_complete": True},
        })
    (directory / "scenarios.json").write_text(json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"시연 사례 {len(scenarios)}개 생성")


if __name__ == "__main__":
    main()
