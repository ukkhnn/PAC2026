#!/usr/bin/env python3
"""발표용 사례 이미지: 원본 사진 사본에 OCR/VLM의 ID 판독 상자와 판정 요약을 그린다.

원본은 바꾸지 않고 output/pipeline-v2-20261010/slides/에 새 PNG를 쓴다. 상자·문자열은 저장된 실행 결과 그대로다.
글꼴 제약(서버에 한글 글꼴 없음)으로 이미지 안 문구는 영어로 쓴다.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "output/pipeline-v2-20261010/slides"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PATTERN = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$")
OCR_COLOR, VLM_COLOR = (0, 102, 204), (230, 110, 0)
NEW = REPO / "output/pipeline-v2-20261010/runs/e1/run_pv2-e1-quick-val01"
OLD = REPO / "output/recognition/run_steel-batch-20261010-02"
CASES = [
    ("case-1-high-score-ocr-misread", NEW, "frame-005", "M5Sb24-16",
     ["OCR only : M55624-16 (score 0.979) -> auto-confirms a WRONG ID",
      "VLM only : M5Sb24-16 -> correct",
      "ContextWeld gate : OCR != VLM -> HOLD, both candidates go to the worker"]),
    ("case-2-two-different-misreads", NEW, "frame-001", "B1Sb30N-8",
     ["OCR only : BISBON-8 -> WRONG ID      VLM only : BISB30N-8 -> WRONG ID",
      "ContextWeld gate : readers disagree -> HOLD (no wrong ID confirmed)"]),
    ("case-3-vlm-hallucination", NEW, "frame-007", "B1Sb40N-45",
     ["OCR only : no ID read      VLM only : B-1000 (invented reading of the faint code) -> WRONG ID",
      "ContextWeld gate : no OCR support -> HOLD"]),
    ("case-4-limit-shared-1-I-misread", OLD, "frame-007", "B1Sb30N-15",
     ["OCR : BISb30N-15   VLM : BISb30N-15  (both read the digit 1 as letter I)",
      "ContextWeld gate : readers agree -> PASSES a WRONG ID (limitation)",
      "Needs context: marking rules / target part list (not implemented yet)"]),
]


def label(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, color: tuple, font) -> None:
    x, y = xy
    box = draw.textbbox((x, y), text, font=font)
    draw.rectangle([box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3], fill=color)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    small, big = ImageFont.truetype(FONT, 22), ImageFont.truetype(FONT, 24)
    written = []
    for name, bundle, frame_id, truth, lines in CASES:
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        frame = next(f for f in manifest["frames"] if f["frame_id"] == frame_id)
        observation = json.loads((bundle / f"results/{frame_id}-observation.json").read_text(encoding="utf-8"))
        with Image.open(bundle / frame["image_ref"]) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for text in observation["text_observations"]:
            if PATTERN.fullmatch(text["raw_text"].strip()):
                x0, y0, x1, y1 = text["bbox"]
                draw.rectangle([x0, y0, x1, y1], outline=OCR_COLOR, width=5)
                label(draw, (x0 + 6, max(4, y0 - 34)), f"OCR: {text['raw_text']} ({text['recognition_score']:.3f})",
                      OCR_COLOR, small)
        for visual in observation["visual_objects"]:
            ids = [line for line in (visual.get("visible_text") or "").splitlines() if PATTERN.fullmatch(line.strip())]
            if visual.get("kind") == "text" and ids:
                x0, y0, x1, y1 = visual["bbox"]
                draw.rectangle([x0, y0, x1, y1], outline=VLM_COLOR, width=5)
                label(draw, (x0 + 6, min(image.height - 34, y1 + 8)), f"VLM: {', '.join(ids)}", VLM_COLOR, small)
        banner_height = 44 + 34 * (len(lines) + 1)
        width = max(image.width, 1080)
        canvas = Image.new("RGB", (width, image.height + banner_height), (255, 255, 255))
        canvas.paste(image, ((width - image.width) // 2, 0))
        text_draw = ImageDraw.Draw(canvas)
        y = image.height + 16
        text_draw.text((16, y), f"Label (evaluation only): {truth}", fill=(20, 20, 20), font=big)
        for line in lines:
            y += 34
            color = (170, 0, 0) if "WRONG" in line else (0, 110, 40) if "HOLD" in line else (20, 20, 20)
            text_draw.text((16, y), line, fill=color, font=small)
        path = OUT / f"{name}.png"
        canvas.save(path)
        written.append(str(path.relative_to(REPO)))
    print(json.dumps(written, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
