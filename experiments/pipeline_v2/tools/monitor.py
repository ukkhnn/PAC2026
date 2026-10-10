#!/usr/bin/env python3
"""GPU·CPU(cgroup) 사용량을 주기적으로 기록한다. 읽기 전용 조회만 한다.

중지: --stop-file 경로에 파일이 생기거나 --max-hours가 지나면 끝난다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gpu() -> dict:
    query = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False)
    apps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True, check=False)
    used, total, util = (int(x.strip()) for x in query.stdout.strip().split(","))
    processes = {}
    for line in apps.stdout.strip().splitlines():
        pid, memory = (x.strip() for x in line.split(","))
        processes[pid] = int(memory)
    return {"memory_used_mib": used, "memory_total_mib": total, "utilization_pct": util, "processes_mib": processes}


def cpu() -> dict:
    stat = dict(line.split() for line in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines())
    return {key: int(stat[key]) for key in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec") if key in stat}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--max-hours", type=float, default=12.0)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_hours * 3600
    with args.out.open("a", encoding="utf-8") as handle:
        while not args.stop_file.exists() and time.monotonic() < deadline:
            row = {"t": now()}
            try:
                row["gpu"] = gpu()
            except Exception as exc:  # 조회 실패도 기록한다.
                row["gpu_error"] = str(exc)
            try:
                row["cpu"] = cpu()
            except Exception as exc:
                row["cpu_error"] = str(exc)
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
