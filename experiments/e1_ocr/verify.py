"""보존한 출력으로 다시 채점하고 원본·코드·결과 해시를 검사한다. 네트워크 호출 없음."""

import json
from pathlib import Path

from run import ROOT, evaluate, sha
from score import assign, score_text


def main() -> None:
    results = ROOT / "results"
    checksums = json.loads((results / "checksums.json").read_text())
    for name, expected in checksums.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"보존 자료 해시 불일치: {name}")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    environment = json.loads((results / "environment.json").read_text())
    if sha(ROOT / "manifest.json") != environment["manifest_sha256"]:
        raise ValueError("실행 당시 manifest와 다릅니다.")
    for name, expected in environment["source_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"실행 당시 코드와 다릅니다: {name}")
    saved_cases = json.loads((results / "cases.json").read_text())
    targets = [{k: v for k, v in r.items() if k not in ("full", "crop", "full_iou", "crop_iou")} for r in saved_cases]
    raw = json.loads((results / "raw.json").read_text())
    summary, cases = evaluate(raw, targets, manifest)
    if summary != json.loads((results / "summary.json").read_text()) or cases != saved_cases:
        raise ValueError("재채점 결과와 보존 결과가 다릅니다.")
    control = json.loads((results / "control.json").read_text())
    provenance = control["provenance"]
    b = provenance["text_bbox"]
    w, h = provenance["size"]
    observations = json.loads((results / "control-raw.json").read_text())["results"][0]["observations"]
    matched = assign([[b[0] / w, b[1] / h, b[2] / w, b[3] / h]], observations)
    score = score_text(provenance["expected"], observations[matched[0]] if 0 in matched else None)
    if score != control["score"] or not score["raw_exact"]:
        raise ValueError("합성 제어 이미지의 인식·좌표 검사 실패")
    checked = 0
    for item in manifest["images"]:
        source = ROOT / "inputs" / item["source_path"]
        if source.exists():
            if sha(source) != item["sha256"]:
                raise ValueError(f"로컬 이미지 해시 불일치: {item['id']}")
            checked += 1
    print(f"PASS: {len(checksums)} preserved hashes, {len(cases)} rescored labels, synthetic control, {checked} local images")


if __name__ == "__main__":
    main()
