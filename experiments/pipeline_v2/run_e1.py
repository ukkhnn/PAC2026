#!/usr/bin/env python3
"""E1: 수정하지 않은 제품 CLI(scripts/run_recognition.py)를 10장 묶음으로 실행한다.

- 사용 이력 10장 묶음(pv2-e1-seen)을 먼저, 미사용 216장을 중립 ID 순서로 22묶음 실행한다.
- 실패한 묶음(run_*.incomplete)은 보존하고, 실패 프레임을 찾아 나머지를 새 run ID로 다시 실행하며
  실패 프레임은 단독 run으로 재확인한다(PROTOCOL 3절). 이미 완료된 run ID는 건너뛴다.
- 모든 결정과 시간은 ledger(JSON)에 기록한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "output/pipeline-v2-20261010"
DATA = OUT / "data"
RUNS = OUT / "runs/e1"
PY = "/workspace/venvs/contextweld-inference/bin/python"
MODELS = "/workspace/models/contextweld"
REV = {"det": "8e0f56fb2ef86b461d99cfc7ac5c137738985f61", "rec": "e5a92bcbc5cc1b494628e458d267778f0704fd7c",
       "vlm": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"}
DIRS = {"det": f"{MODELS}/PP-OCRv6_medium_det/{REV['det']}", "rec": f"{MODELS}/PP-OCRv6_medium_rec/{REV['rec']}",
        "vlm": f"{MODELS}/Qwen3-VL-8B-Instruct/{REV['vlm']}"}
INDEX = REPO / "output/document-rag/server-v1/index.json"
ENV = {"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
       "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True", "PV2_CUDA_FRACTION": "0.6", "PYTHONDONTWRITEBYTECODE": "1"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def plan() -> list[dict]:
    manifest = json.loads((DATA / "data-manifest.json").read_text(encoding="utf-8"))
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]
    seen = set(manifest["seen_in_previous_pilots"])
    ids = [item["id"] for item in sources]
    unseen = [identifier for identifier in ids if identifier not in seen]
    # 재현성 대조를 위해 기존 run_steel-batch-20261010-02와 같은 프레임 순서(steel-S01..S10)를 해시로 맞춘다.
    registry = json.loads((REPO / "configs/demo_data_sources.json").read_text(encoding="utf-8"))["sources"]
    by_hash = {item["sha256"]: item["id"] for item in sources}
    seen_order = [by_hash[item["sha256"]] for item in registry if item["group"] == "steel-images"]
    if set(seen_order) != seen:
        raise ValueError("seen images do not match the original registry")
    batches = [{"run_id": "pv2-e1-seen", "images": seen_order, "kind": "seen_reproducibility"}]
    for number, start in enumerate(range(0, len(unseen), 10), 1):
        batches.append({"run_id": f"pv2-e1-b{number:02d}", "images": unseen[start:start + 10], "kind": "unseen"})
    return batches


def command(run_id: str, images: list[str]) -> list[str]:
    argv = ["nice", "-n", "19", PY, "-u", str(REPO / "experiments/pipeline_v2/tools/cli_wrapper.py"),
            str(REPO / "scripts/run_recognition.py"),
            "--data-root", str(DATA / "root"), "--sources", str(DATA / "sources.json"),
            "--output-root", str(RUNS), "--run-id", run_id, "--image-ids", *images,
            "--document-index", str(INDEX), "--ocr-device", "cpu", "--max-new-tokens", "4096"]
    for component in ("det", "rec", "vlm"):
        argv += [f"--{component}-model-dir", DIRS[component], f"--{component}-revision", REV[component]]
    return argv


FRAME_ERRORS = {"JSONDecodeError", "ValueError"}  # 모델 출력 구문·스키마 실패만 프레임 실패로 본다.


def failing_image(run_id: str) -> tuple[str | None, str, str | None, str | None]:
    root = RUNS / f"run_{run_id}.incomplete"
    if not (root / "manifest.json").exists():
        return None, "no_bundle", None, None
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    error_type, error = manifest.get("error_type"), manifest.get("error")
    if error_type not in FRAME_ERRORS:
        return None, "infrastructure", error_type, error
    frames = manifest.get("frames", [])
    for frame in frames:
        if not (root / f"results/{frame['frame_id']}-ocr.json").exists():
            return frame["source_id"], "ocr", error_type, error
    for frame in frames:
        if not (root / f"results/{frame['frame_id']}-recognition_decision.json").exists():
            return frame["source_id"], "vlm", error_type, error
    return None, "unknown", error_type, error


def execute(run_id: str, images: list[str], ledger: dict, save) -> str:
    final, incomplete = RUNS / f"run_{run_id}", RUNS / f"run_{run_id}.incomplete"
    if final.exists():
        return "succeeded"
    if incomplete.exists():
        return "failed"
    logs = RUNS / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    argv = command(run_id, images)
    env = {**os.environ, **ENV, "PV2_WRAPPER_REPORT": str(logs / f"{run_id}.wrapper.json")}
    entry = {"run_id": run_id, "images": images, "argv": argv, "started_at_utc": now()}
    ledger["runs"].append(entry)
    save()
    started = time.monotonic()
    with (logs / f"{run_id}.log").open("w", encoding="utf-8") as handle:
        result = subprocess.run(argv, cwd=REPO, env=env, stdout=handle, stderr=subprocess.STDOUT, check=False)
    entry.update(finished_at_utc=now(), wall_seconds=round(time.monotonic() - started, 3), exit_code=result.returncode,
                 status="succeeded" if final.exists() and result.returncode == 0 else "failed")
    save()
    return entry["status"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="run only these planned run IDs")
    args = parser.parse_args(argv)
    RUNS.mkdir(parents=True, exist_ok=True)
    ledger_path = RUNS / "e1-ledger.json"
    ledger = (json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists()
              else {"schema_version": "pv2-e1-ledger.v1", "created_at_utc": now(), "plan": plan(),
                    "runs": [], "failures": [], "result_runs": {}})

    def save() -> None:
        ledger["updated_at_utc"] = now()
        tmp = ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(ledger_path)

    save()
    for batch in ledger["plan"]:
        if args.only and batch["run_id"] not in args.only:
            continue
        pending = [(batch["run_id"], list(batch["images"]))]
        attempt = 0
        while pending:
            run_id, images = pending.pop(0)
            status = execute(run_id, images, ledger, save)
            if status == "succeeded":
                for image in images:
                    ledger["result_runs"][image] = run_id
                save()
                continue
            bad, stage, error_type, error = failing_image(run_id)
            record = {"run_id": run_id, "images": images, "failing_image": bad, "stage": stage,
                      "error_type": error_type, "error": error, "recorded_at_utc": now()}
            if stage in {"no_bundle", "infrastructure", "unknown"}:
                # 모델 출력이 아닌 실행 환경 실패는 프레임 탓으로 돌리지 않고 즉시 멈춘다.
                ledger["failures"].append({**record, "final": True, "halted": True})
                save()
                print(json.dumps({"halted": record}, ensure_ascii=False))
                return 2
            if len(images) == 1:
                ledger["failures"].append({**record, "final": True})
                save()
                continue
            attempt += 1
            ledger["failures"].append({**record, "final": False})
            save()
            rest = [image for image in images if image != bad]
            pending.append((f"{batch['run_id']}-r{attempt}", rest))
            pending.append((f"{batch['run_id']}-solo-{bad}", [bad]))
    print(json.dumps({"ledger": str(ledger_path), "images_with_results": len(ledger["result_runs"]),
                      "failures": ledger["failures"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
