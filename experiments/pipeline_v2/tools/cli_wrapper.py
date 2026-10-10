#!/usr/bin/env python3
"""제품 CLI를 코드 수정 없이 실행하면서 CUDA 메모리 상한과 최대 사용량만 기록한다.

사용: python cli_wrapper.py scripts/run_recognition.py <제품 CLI 인자...>
환경 변수 PV2_WRAPPER_REPORT(필수), PV2_CUDA_FRACTION(기본 0.6).
상한은 Isaac와 GPU를 공유할 때 이 프로세스만 OOM으로 실패하게 하는 보호 장치이며 출력값을 바꾸지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys
import time


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    report = Path(os.environ["PV2_WRAPPER_REPORT"])
    fraction = float(os.environ.get("PV2_CUDA_FRACTION", "0.6"))
    script, args = sys.argv[1], sys.argv[2:]
    import torch
    torch.cuda.set_per_process_memory_fraction(fraction, 0)
    record = {"schema_version": "pv2-cli-wrapper.v1", "script": script, "argv": args,
              "cuda_memory_fraction": fraction, "started_at_utc": now(), "pid": os.getpid(),
              "nice": os.nice(0), "env": {key: os.environ.get(key) for key in
                                          ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "HF_HUB_OFFLINE",
                                           "TRANSFORMERS_OFFLINE", "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK")}}
    started, code = time.monotonic(), 1
    sys.argv = [script, *args]
    try:
        runpy.run_path(script, run_name="__main__")
        code = 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException as exc:  # 기록 후 실패 코드로 끝낸다.
        record["wrapper_error"] = f"{type(exc).__name__}: {exc}"
        code = 1
    finally:
        record.update(exit_code=code, finished_at_utc=now(), wall_seconds=round(time.monotonic() - started, 3),
                      cuda_max_memory_allocated_bytes=torch.cuda.max_memory_allocated(0),
                      cuda_max_memory_reserved_bytes=torch.cuda.max_memory_reserved(0),
                      device_name=torch.cuda.get_device_name(0))
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
