#!/usr/bin/env python3
"""고정 공개 사진으로 OCR/VLM과 원문 위치 검색을 실행하고 묶음을 보존한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contextweld.recognition import (PaddleEngine, QwenEngine, VISUAL_OBJECT_BUDGET, environment_record, model_record,
                                     run_bootstrap, sha256, verify_bundle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-bundle", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--sources", type=Path, default=REPO / "configs/demo_data_sources.json")
    parser.add_argument("--output-root", type=Path, default=REPO / "output/recognition")
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--image-ids", nargs="+")
    for component in ("det", "rec", "vlm"):
        parser.add_argument(f"--{component}-model-dir", type=Path)
        parser.add_argument(f"--{component}-revision")
    parser.add_argument("--ocr-device", default="cpu")
    parser.add_argument("--document-index", type=Path)
    parser.add_argument("--document-ids", nargs="+", default=["twi-weld-symbols"])
    parser.add_argument("--query", default="weld symbols arrow reference line fillet weld meaning")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--max-pixels", type=int, default=802816)
    args = parser.parse_args(argv)
    try:
        if args.verify_bundle:
            verify_bundle(args.verify_bundle)
            print(json.dumps({"verified": str(args.verify_bundle)}))
            return 0
        for required in ("data_root", "run_id", "document_index", "det_model_dir", "rec_model_dir", "vlm_model_dir",
                         "det_revision", "rec_revision", "vlm_revision"):
            if not getattr(args, required):
                parser.error(f"--{required.replace('_', '-')} is required")
        if not 1 <= args.limit <= 10 or not 1 <= args.top_k <= 10 or args.max_new_tokens < 128 or args.max_pixels < 65536:
            raise ValueError("invalid input or generation budget")
        sources = json.loads(args.sources.read_text(encoding="utf-8"))
        image_ids = args.image_ids or [source["id"] for source in sources["sources"]
                                       if source["group"] == "steel-images"][:args.limit]
        print("Hashing pinned model files...", flush=True)
        config = {"schema_version": "recognition-config.v1", "spec_version": "demo-1.3+ocr-1.2+documents-1.2",
                  "environment": environment_record(REPO),
                  "models": {
                      "det": model_record(args.det_model_dir, "PaddlePaddle/PP-OCRv6_medium_det", args.det_revision),
                      "rec": model_record(args.rec_model_dir, "PaddlePaddle/PP-OCRv6_medium_rec", args.rec_revision),
                      "vlm": model_record(args.vlm_model_dir, "Qwen/Qwen3-VL-8B-Instruct", args.vlm_revision)},
                  "sources_sha256": sha256(args.sources), "document_index_sha256": sha256(args.document_index),
                  "image_ids": image_ids, "ocr_device": args.ocr_device,
                  "ocr": {"doc_orientation": False, "unwarping": False, "textline_orientation": False,
                          "rec_score_threshold": 0.0, "input_channels": "BGR", "enable_mkldnn": False,
                          "cpu_threads": 4},
                  "vlm": {"device": "cuda:0", "dtype": "bfloat16", "attention": "sdpa", "do_sample": False,
                          "max_new_tokens": args.max_new_tokens, "min_pixels": 65536, "max_pixels": args.max_pixels,
                          "visual_object_budget": {"requested_max": VISUAL_OBJECT_BUDGET,
                                                   "enforcement": "prompt_only"},
                          "json_syntax_retries": 1},
                  "retrieval": {"document_ids": args.document_ids, "query": args.query, "top_k": args.top_k},
                  "labels_used": False, "delivery_requested": False}
        result = run_bootstrap(data_root=args.data_root.resolve(), sources_path=args.sources,
                               output_root=args.output_root, run_id=args.run_id, image_ids=image_ids,
                               config=config,
                               ocr_factory=lambda: PaddleEngine(args.det_model_dir, args.rec_model_dir, args.ocr_device),
                               vlm_factory=lambda: QwenEngine(args.vlm_model_dir, args.max_new_tokens, args.max_pixels),
                               document_index=json.loads(args.document_index.read_text(encoding="utf-8")),
                               document_ids=args.document_ids, query=args.query, top_k=args.top_k)
    except Exception as exc:
        print(f"Recognition failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"bundle": str(result), "status": "needs_review", "demo_complete": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
