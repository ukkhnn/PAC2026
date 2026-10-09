"""정답 문자열을 보지 않고 영역을 대응한 뒤 문자 오류를 계산한다."""

from typing import Any


def normalize(text: str) -> str:
    return text.strip().upper()


def distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def iou(a: list[float], b: list[float]) -> float:
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union if union > 0 else 0.0


def assign(boxes: list[list[float]], observations: list[dict[str, Any]], threshold: float = 0.3) -> dict[int, int]:
    pairs = sorted((-iou(box, obs["bbox"]), g, p)
                   for g, box in enumerate(boxes) for p, obs in enumerate(observations)
                   if iou(box, obs["bbox"]) >= threshold)
    matched: dict[int, int] = {}
    used: set[int] = set()
    for _, g, p in pairs:
        if g not in matched and p not in used:
            matched[g] = p
            used.add(p)
    return matched


def score_text(expected: str, observation: dict[str, Any] | None) -> dict[str, Any]:
    candidates = observation["candidates"] if observation else []
    prediction = candidates[0]["text"] if candidates else ""
    return {
        "prediction": prediction, "candidates": candidates,
        "localized": observation is not None,
        "raw_exact": expected == prediction,
        "normalized_exact": normalize(expected) == normalize(prediction),
        "top3_exact": any(normalize(expected) == normalize(c["text"]) for c in candidates),
        "edits": distance(normalize(expected), normalize(prediction)),
        "characters": len(normalize(expected)),
    }
