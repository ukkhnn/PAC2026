#!/usr/bin/env python3
"""확보한 문서의 원문 해시와 위치를 보존하는 검색 색인을 만든다."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from contextweld.documents import build_index, write_json_exclusive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/raw/demo-bootstrap-v1")
    parser.add_argument("--sources", type=Path, default=ROOT / "configs/demo_data_sources.json")
    parser.add_argument("--output", type=Path, required=True, help="새 색인 JSON 경로; 기존 파일 덮어쓰기 금지")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("출력 파일이 이미 존재합니다. 새 실행 경로를 지정하세요.")
        index = build_index(args.data_root, args.sources)
        write_json_exclusive(args.output, index)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"문서 추출 오류: {exc}", file=sys.stderr)
        return 2
    print(f"문서 {len(index['documents'])}개, 청크 {len(index['chunks'])}개: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
