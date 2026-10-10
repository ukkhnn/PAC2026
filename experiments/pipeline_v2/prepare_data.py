#!/usr/bin/env python3
"""PV2 평가 자료를 고정 revision의 공개 Steel OCR 960 데이터셋에서 격리된 실험 경로로 준비한다.

- 모델 입력 경로(data/root/)에는 내용 해시 순서의 중립 이름 사본만 둔다. 원래 파일명에는 정답 문자열이
  들어간 경우가 있어(예: ..._B15b30N-20_...) 모델 쪽 입력·출처 목록에 남기지 않는다.
- 정답(eval/ground_truth.json)은 평가 전용 디렉토리에 분리한다.
- 원본 저장소의 data/raw/는 읽기만 한다. 이미 받은 10장은 같은 해시인지 확인하고 사본을 만든다.
표준 라이브러리만 사용한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[2]
DATASET = "iput-tk230215/steel-ocr-dataset-960"
REVISION = "37725284f40deeaccbdeb3734be7b0e90e974305"
RESOLVE = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/"
PATHS_INFO = f"https://huggingface.co/api/datasets/{DATASET}/paths-info/{REVISION}"
LOCAL_RAW = REPO / "data/raw/demo-bootstrap-v1"
LOCAL_SOURCES = REPO / "configs/demo_data_sources.json"
DOCUMENT_INDEX = REPO / "output/document-rag/server-v1/index.json"
LABEL_FILES = {"train": "train_data/det/train.txt", "val": "train_data/det/val.txt"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fetch(url: str, *, data: bytes | None = None, attempts: int = 4) -> bytes:
    headers = {"User-Agent": "contextweld-pv2/1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def paths_info(paths: list[str]) -> dict[str, dict]:
    info = {}
    for start in range(0, len(paths), 50):
        body = json.dumps({"paths": paths[start:start + 50], "expand": False}).encode()
        for item in json.loads(fetch(PATHS_INFO, data=body)):
            info[item["path"]] = item
    return info


def parse_labels(text: str) -> list[tuple[str, list[dict]]]:
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        path, annotation = line.split("\t", 1)
        instances = json.loads(annotation)
        if not isinstance(instances, list) or not instances:
            raise ValueError(f"label line {number}: empty or invalid annotation")
        rows.append((path, instances))
    return rows


def write_exclusive(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "output/pipeline-v2-20261010/data")
    args = parser.parse_args(argv)
    out: Path = args.out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    root, evaluation, labels_dir = out / "root", out / "eval", out / "labels"
    for directory in (root / "images", evaluation, labels_dir):
        directory.mkdir(parents=True, exist_ok=True)
    started = now()

    # 1) 라벨 파일: 원격 고정 revision에서 받고, 로컬 train.txt와 해시를 대조한다.
    label_info = paths_info(list(LABEL_FILES.values()))
    labels, label_records = {}, {}
    for split, remote in LABEL_FILES.items():
        data = fetch(RESOLVE + remote)
        (labels_dir / Path(remote).name).write_bytes(data)
        local = LOCAL_RAW / "steel_ocr" / remote
        label_records[split] = {"remote_path": remote, "url": RESOLVE + remote, "sha256": sha256_bytes(data),
                                "bytes": len(data), "git_oid": label_info[remote]["oid"],
                                "last_commit": label_info[remote].get("lastCommit"),
                                "local_copy": str(local.relative_to(REPO)) if local.is_file() else None,
                                "local_copy_identical": (sha256_file(local) == sha256_bytes(data)) if local.is_file() else None}
        labels[split] = parse_labels(data.decode("utf-8"))

    # 2) 이전 파일럿·제품 bootstrap이 사용한 10장(해시)을 '이미 본 자료'로 표시한다.
    registry = json.loads(LOCAL_SOURCES.read_text(encoding="utf-8"))
    seen_hashes = {item["sha256"]: item["id"] for item in registry["sources"] if item["group"] == "steel-images"}

    # 3) 라벨이 있는 모든 이미지를 받고 LFS sha256과 대조한다.
    image_paths = sorted({"train_data/det/" + path for split in labels for path, _ in labels[split]})
    info = paths_info(image_paths)
    downloaded: dict[str, dict] = {}
    for remote in image_paths:
        meta = info.get(remote)
        if meta is None or "lfs" not in meta:
            raise ValueError(f"no LFS metadata for {remote}")
        expected = meta["lfs"]["oid"]
        local = LOCAL_RAW / "steel_ocr" / remote
        if local.is_file() and sha256_file(local) == expected:
            data, origin = local.read_bytes(), "existing_local_copy"
        else:
            data, origin = fetch(RESOLVE + remote), "downloaded"
        if sha256_bytes(data) != expected or len(data) != meta["lfs"]["size"]:
            raise ValueError(f"hash/size mismatch for {remote}")
        downloaded[remote] = {"data": data, "sha256": expected, "origin": origin, "bytes": len(data)}

    # 4) 내용 해시 순서로 중립 ID를 부여한다(라벨·파일명과 무관).
    order = sorted(image_paths, key=lambda remote: downloaded[remote]["sha256"])
    neutral = {remote: f"pv2-img-{index:03d}" for index, remote in enumerate(order, 1)}
    split_of = {"train_data/det/" + path: split for split in labels for path, _ in labels[split]}
    instances_of = {"train_data/det/" + path: inst for split in labels for path, inst in labels[split]}
    if len(split_of) != sum(len(rows) for rows in labels.values()):
        raise ValueError("an image appears in more than one split or twice")

    sources, ground_truth, provenance = [], {}, []
    for remote in order:
        record = downloaded[remote]
        suffix = Path(remote).suffix.lower()
        relative = f"images/{neutral[remote]}{suffix}"
        target = root / relative
        with target.open("xb") as handle:
            handle.write(record["data"])
        sources.append({"id": neutral[remote], "group": "steel-images", "relative_path": relative,
                        "sha256": record["sha256"], "media_type": "image/jpeg",
                        "source_kind": "public_dataset", "dataset": DATASET, "revision": REVISION,
                        "note": "neutral copy; original path kept only in evaluation records"})
        seen = seen_hashes.get(record["sha256"])
        ground_truth[neutral[remote]] = {
            "split": split_of[remote], "original_path": remote, "contributor": Path(remote).name.split("_")[0],
            "seen_in_previous_pilots": seen is not None, "previous_source_id": seen,
            "instances": [{"transcription": item["transcription"], "points": item["points"],
                           "difficult": bool(item.get("difficult", False))} for item in instances_of[remote]]}
        provenance.append({"id": neutral[remote], "original_path": remote, "url": RESOLVE + remote,
                           "sha256": record["sha256"], "bytes": record["bytes"], "origin": record["origin"]})

    # 5) 제품 문서 색인 검증에 필요한 원문 4개를 같은 상대경로로 복사한다(해시 대조).
    index = json.loads(DOCUMENT_INDEX.read_text(encoding="utf-8"))
    documents = []
    for document in index["documents"]:
        source = LOCAL_RAW / document["relative_path"]
        if sha256_file(source) != document["source_hash"]:
            raise ValueError(f"document hash mismatch: {document['document_id']}")
        target = root / document["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        documents.append({"document_id": document["document_id"], "relative_path": document["relative_path"],
                          "sha256": document["source_hash"]})

    write_exclusive(out / "sources.json", {
        "schema_version": registry["schema_version"],
        "description": "PV2 isolated registry for the unchanged product CLI. Neutral image names only; "
                       "labels and original file names are not part of model inputs.",
        "sources": sources})
    write_exclusive(evaluation / "ground_truth.json", {
        "schema_version": "pv2-ground-truth.v1", "use": "evaluation_only_never_model_input",
        "dataset": DATASET, "revision": REVISION, "label_files": label_records,
        "label_scope": "dataset authors' product-code boxes only (non-code boxes dropped upstream)",
        "images": ground_truth})
    counts = {split: {"images": sum(1 for gt in ground_truth.values() if gt["split"] == split),
                      "instances": sum(len(gt["instances"]) for gt in ground_truth.values() if gt["split"] == split)}
              for split in LABEL_FILES}
    write_exclusive(out / "data-manifest.json", {
        "schema_version": "pv2-data-manifest.v1", "started_at_utc": started, "finished_at_utc": now(),
        "dataset": DATASET, "revision": REVISION, "license_declared": "MIT (dataset card metadata)",
        "why_downloaded": "Only 10 labelled images existed on the server and all were used by earlier pilots; "
                          "the pinned public revision provides the remaining labelled images of the same domain.",
        "isolation": "written only under this directory; repository data/raw is read-only",
        "counts": counts, "seen_in_previous_pilots": sorted(n for n, gt in ground_truth.items() if gt["seen_in_previous_pilots"]),
        "images": provenance, "documents_copied_for_index_validation": documents,
        "local_sources_sha256": sha256_file(LOCAL_SOURCES), "document_index_sha256": sha256_file(DOCUMENT_INDEX)})
    print(json.dumps({"out": str(out), "counts": counts,
                      "seen": sum(1 for gt in ground_truth.values() if gt["seen_in_previous_pilots"]),
                      "downloaded": sum(1 for p in provenance if p["origin"] == "downloaded")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
