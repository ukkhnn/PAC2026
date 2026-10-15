#!/usr/bin/env python3
"""독립 A/B 입력 준비, 실제 인식 재촬영 분기 실행, 불변 기록 검증 CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from contextweld.recognition import PaddleEngine, QwenEngine, environment_record, model_record, sha256
from contextweld.recapture_inputs import prepare_inputs, verify_inputs
from contextweld.recapture_inference import PipelineObserver
from contextweld.recapture_loop import run_recapture_loop, verify_recapture_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare", help="고정 A/B를 복사·검증한다. 추론/ROS 호출 없음")
    prepare.add_argument("--scene-root", type=Path, required=True)
    prepare.add_argument("--destination", type=Path, required=True)
    verify = commands.add_parser("verify", help="실행 묶음 해시·사건 인과 검증")
    verify.add_argument("--bundle", type=Path, required=True)
    verify_input = commands.add_parser("verify-inputs", help="추론 전 입력 자료만 검증")
    verify_input.add_argument("--inputs-root", type=Path, required=True)
    run = commands.add_parser("run", help="실제 모델 호출. 공유 GPU 사용 가능 시 별도 실행")
    run.add_argument("--inputs-root", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--data-root", type=Path, required=True)
    run.add_argument("--document-index", type=Path, required=True)
    run.add_argument("--document-ids", nargs="+", default=["twi-weld-symbols"])
    run.add_argument("--query", default="weld symbols arrow reference line fillet weld meaning")
    run.add_argument("--top-k", type=int, default=3)
    run.add_argument("--ocr-device", default="cpu")
    run.add_argument("--max-new-tokens", type=int, default=4096)
    run.add_argument("--max-pixels", type=int, default=802816)
    for component in ("det", "rec", "vlm"):
        run.add_argument(f"--{component}-model-dir", type=Path, required=True)
        run.add_argument(f"--{component}-revision", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare_inputs(args.scene_root, args.destination)
            print(json.dumps({"inputs": str(result), "inference_status": "not_run"}, ensure_ascii=False))
            return 0
        if args.action == "verify-inputs":
            result = verify_inputs(args.inputs_root)
            print(json.dumps({"verified": str(args.inputs_root), "schema_version": result["schema_version"]}))
            return 0
        if args.action == "verify":
            result = verify_recapture_bundle(args.bundle)
            print(json.dumps({"verified": str(args.bundle), "run_outcome": result["run_outcome"],
                              "export_status": result["export_status"]}))
            return 0
        if not 1 <= args.top_k <= 10 or args.max_new_tokens < 128 or args.max_pixels < 65536:
            raise ValueError("invalid retrieval or generation budget")
        verify_inputs(args.inputs_root)
        index = json.loads(args.document_index.read_text(encoding="utf-8"))
        config = {"schema_version": "recapture-inference-config.v1", "evidence_kind": "actual_model",
            "environment": environment_record(REPO), "labels_used": False,
            "implementation_sha256": {str(p.relative_to(REPO)): sha256(p) for p in [
                REPO / "src/contextweld/recapture_inputs.py", REPO / "src/contextweld/recapture_loop.py",
                REPO / "src/contextweld/recapture_inference.py", Path(__file__).resolve()]},
            "models": {
                "det": model_record(args.det_model_dir, "PaddlePaddle/PP-OCRv6_medium_det", args.det_revision),
                "rec": model_record(args.rec_model_dir, "PaddlePaddle/PP-OCRv6_medium_rec", args.rec_revision),
                "vlm": model_record(args.vlm_model_dir, "Qwen/Qwen3-VL-8B-Instruct", args.vlm_revision)},
            "document_index_sha256": sha256(args.document_index),
            "ocr": {"device": args.ocr_device, "doc_orientation": False, "unwarping": False,
                    "textline_orientation": False, "rec_score_threshold": 0.0, "input_channels": "BGR",
                    "enable_mkldnn": False, "cpu_threads": 4},
            "vlm": {"device": "cuda:0", "dtype": "bfloat16", "attention": "sdpa", "do_sample": False,
                    "max_new_tokens": args.max_new_tokens, "max_pixels": args.max_pixels, "min_pixels": 65536,
                    "json_syntax_retries": 1, "stages": ["observation", "relation", "capture_assessment"]},
            "retrieval": {"document_ids": args.document_ids, "query": args.query, "top_k": args.top_k}}
        observer = PipelineObserver(
            ocr_factory=lambda: PaddleEngine(args.det_model_dir, args.rec_model_dir, args.ocr_device),
            vlm_factory=lambda: QwenEngine(args.vlm_model_dir, args.max_new_tokens, args.max_pixels),
            document_index=index, data_root=args.data_root.resolve(), document_ids=args.document_ids,
            query=args.query, top_k=args.top_k)
        bundle = run_recapture_loop(inputs_root=args.inputs_root, output_root=args.output_root,
                                   run_id=args.run_id, observer=observer, config=config)
        result = verify_recapture_bundle(bundle)
        print(json.dumps({"bundle": str(bundle), "run_outcome": result["run_outcome"],
                          "visual_outcome": result["visual_outcome"], "recapture_outcome": result["recapture_outcome"],
                          "physical_movement_triggered": False, "export_status": result["export_status"]},
                         ensure_ascii=False))
        return 1 if result["run_outcome"] == "failed" else 0
    except Exception as exc:
        print(f"Recapture: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
