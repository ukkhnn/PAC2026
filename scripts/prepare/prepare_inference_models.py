#!/usr/bin/env python3
"""공개 모델의 고정 revision을 내려받고 파일 해시를 기록한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODELS = (
    {
        "role": "text_detection",
        "repo_id": "PaddlePaddle/PP-OCRv6_medium_det",
        "revision": "8e0f56fb2ef86b461d99cfc7ac5c137738985f61",
        "allow_patterns": ["README.md", "inference.json", "inference.pdiparams", "inference.yml"],
    },
    {
        "role": "text_recognition",
        "repo_id": "PaddlePaddle/PP-OCRv6_medium_rec",
        "revision": "e5a92bcbc5cc1b494628e458d267778f0704fd7c",
        "allow_patterns": ["README.md", "inference.json", "inference.pdiparams", "inference.yml"],
    },
    {
        "role": "vision_language",
        "repo_id": "Qwen/Qwen3-VL-8B-Instruct",
        "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "allow_patterns": ["README.md", "*.json", "*.txt", "*.safetensors"],
    },
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: dict[str, Any]) -> None:
    expected = {(item["role"], item["repo_id"], item["revision"]) for item in MODELS}
    actual = {(item["role"], item["repo_id"], item["revision"]) for item in manifest["models"]}
    if expected != actual:
        raise ValueError("모델 ID/revision이 이 스크립트의 고정 목록과 다름")
    for model in manifest["models"]:
        for entry in model["files"]:
            path = (root / model["relative_path"] / entry["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("모델 루트 밖의 경로")
            if path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
                raise ValueError(f"기존 모델 파일 해시 불일치: {path}")


def prepare(root: Path, verify_only: bool = False) -> dict[str, Any]:
    manifest_path = root / "model-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_manifest(root, manifest)
        return manifest
    if verify_only:
        raise FileNotFoundError(manifest_path)

    from huggingface_hub import snapshot_download

    root.mkdir(parents=True, exist_ok=True)
    models: list[dict[str, Any]] = []
    for spec in MODELS:
        relative_path = Path(spec["repo_id"].split("/")[1]) / spec["revision"]
        local_dir = root / relative_path
        print(f"download {spec['repo_id']} @ {spec['revision']}", flush=True)
        # 인증이 필요 없는 공개 파일만 받는다. 중단된 다운로드는 Hub cache로 이어받는다.
        snapshot_download(
            repo_id=spec["repo_id"], revision=spec["revision"],
            local_dir=local_dir, allow_patterns=spec["allow_patterns"],
            token=False, max_workers=4,
        )
        files = [
            {"path": str(path.relative_to(local_dir)), "bytes": path.stat().st_size,
             "sha256": sha256_file(path)}
            for path in sorted(local_dir.rglob("*"))
            if path.is_file() and ".cache" not in path.relative_to(local_dir).parts
        ]
        if not files:
            raise ValueError(f"받은 모델 파일이 없음: {spec['repo_id']}")
        models.append({
            "role": spec["role"], "repo_id": spec["repo_id"],
            "revision": spec["revision"], "relative_path": str(relative_path),
            "source_url": f"https://huggingface.co/{spec['repo_id']}/tree/{spec['revision']}",
            "files": files,
        })
        print(f"hashed {spec['repo_id']}: {len(files)} files", flush=True)
    manifest = {
        "schema_version": "inference-models.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }
    # 완성된 manifest가 있을 때는 검증만 하며 수정하거나 덮어쓰지 않는다.
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, default=Path("/workspace/models/contextweld"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = prepare(args.model_root.resolve(), args.verify_only)
    print(json.dumps({"model_count": len(manifest["models"]),
                      "manifest": str(args.model_root / "model-manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
