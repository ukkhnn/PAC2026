"""저장소 루트에서 `python3 -m pytest tests`가 바로 동작하도록 `src`를 경로에 올린다.

일부 테스트는 `python -m contextweld`를 하위 프로세스로 실행하므로 `PYTHONPATH`도 함께 넘긴다.
"""
from pathlib import Path
import os
import sys

SRC = str(Path(__file__).resolve().parent / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
existing = os.environ.get("PYTHONPATH", "")
if SRC not in existing.split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join([SRC, existing]) if existing else SRC
