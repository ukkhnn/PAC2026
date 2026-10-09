"""고정된 공개 개발 표본만 내려받고 원문·해시·출처를 보존한다."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
REPO = "iput-tk230215/steel-ocr-dataset-960"
REVISION = "37725284f40deeaccbdeb3734be7b0e90e974305"
ORIGINAL_REVISION = "cc1d729fc0e9e78945ee63463ee7f6e3e8d1b395"
COUNT = 10


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(path: str) -> tuple[bytes, str]:
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{path}"
    target = ROOT / "inputs" / path
    if target.exists():
        return target.read_bytes(), url
    with urlopen(url, timeout=60) as response:
        data = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return data, url


def main() -> None:
    card, card_url = fetch("README.md")
    labels, label_url = fetch("train_data/det/train.txt")
    entries = []
    for line in labels.decode().splitlines():
        path, annotations = line.split("\t", 1)
        entries.append((path, json.loads(annotations)))
    # 파일명의 SHA-256 순서로 고른다. OCR 출력이나 라벨 난도로 표본을 고르지 않는다.
    selected = sorted(entries, key=lambda x: digest(x[0].encode()))[:COUNT]
    manifest = {
        "experiment": "E1-001", "retrieved_date": "2026-10-09",
        "dataset": REPO, "revision": REVISION, "split": "train",
        "sample_rule": "first 10 train paths ordered by SHA256(UTF-8 path)",
        "dataset_kind": "public_steel_images", "purpose": "development_exploration",
        "license_declared": "MIT (dataset card metadata); no standalone LICENSE in file listing",
        "card_url": card_url, "card_sha256": digest(card),
        "labels_url": label_url, "labels_sha256": digest(labels),
        "train_rows_observed": len(entries),
        "original_test_listing_revision": ORIGINAL_REVISION,
        "images": [],
    }
    for index, (path, annotations) in enumerate(selected, 1):
        data, url = fetch("train_data/det/" + path)
        manifest["images"].append({
            "id": f"S{index:02d}", "source_path": "train_data/det/" + path,
            "url": url, "sha256": digest(data), "annotations": annotations,
        })
    destination = ROOT / "manifest.json"
    if destination.exists():
        if json.loads(destination.read_text()) != manifest:
            raise ValueError("기존 manifest와 자료가 다릅니다. 새 실험 ID를 사용하세요.")
    else:
        destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(selected)} images; {sum(len(a) for _, a in selected)} annotations; {len(entries)} train rows")


if __name__ == "__main__":
    main()
