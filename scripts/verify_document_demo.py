#!/usr/bin/env python3
"""추론·전송 없이 문서 연결 실행 묶음을 오프라인 검증한다."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from contextweld.workflow import inspect_document_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_document_bundle(args.bundle), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'문서 묶음 검증 실패: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
