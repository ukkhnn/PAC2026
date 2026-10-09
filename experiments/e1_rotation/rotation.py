"""회전 관측을 원래 좌표로 되돌리고 정답 없이 후보를 모은다."""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1_ocr"))
from score import iou, normalize


def rotate_box(box: list[float], angle: int) -> list[float]:
    x0, y0, x1, y1 = box
    if angle == 0:
        return list(box)
    if angle == 90:
        return [y0, 1 - x1, y1, 1 - x0]
    if angle == 180:
        return [1 - x1, 1 - y1, 1 - x0, 1 - y0]
    if angle == 270:
        return [1 - y1, x0, 1 - y0, x1]
    raise ValueError("90도 단위만 지원합니다.")


def merge(rotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    for result in rotations:
        angle = result["angle"]
        for index, obs in enumerate(result["observations"]):
            if not obs["candidates"]:
                continue
            observations.append({"bbox": rotate_box(obs["bbox"], (360 - angle) % 360),
                "angle": angle, "observation_index": index,
                "candidates": [{**c, "angle": angle, "observation_index": index, "rank": rank}
                               for rank, c in enumerate(obs["candidates"])]})
    observations.sort(key=lambda o: (-o["candidates"][0]["confidence"], o["angle"], o["observation_index"]))
    groups = []
    for obs in observations:
        overlaps = [(iou(obs["bbox"], g["bbox"]), i) for i, g in enumerate(groups)]
        best = max(overlaps, default=(0, -1))
        if best[0] >= .3:
            groups[best[1]]["members"].append(obs)
        else:
            groups.append({"bbox": obs["bbox"], "members": [obs]})
    for group in groups:
        pool = sorted([c for obs in group["members"] for c in obs["candidates"]],
                      key=lambda c: (-c["confidence"], c["angle"], c["observation_index"], c["rank"]))
        seen = set()
        candidates = []
        for c in pool:
            key = normalize(c["text"])
            if key not in seen:
                seen.add(key)
                candidates.append(c)
        group["candidates"] = candidates
    return groups
