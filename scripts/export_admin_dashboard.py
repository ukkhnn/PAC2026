#!/usr/bin/env python3
"""저장된 실행 묶음으로 오프라인 관리자 대시보드 패키지를 만든다 (원본은 읽기만 함).

예: python3 scripts/export_admin_dashboard.py export --output output/admin-dashboard-20261010/package/pac-admin-dashboard
    python3 scripts/export_admin_dashboard.py verify output/admin-dashboard-20261010/package/pac-admin-dashboard
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contextweld_dashboard.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
