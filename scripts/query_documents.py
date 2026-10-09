#!/usr/bin/env python3
"""명시한 문서와 개정 범위에서 검색하고 질의·점수·원문 위치를 기록한다."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contextweld.documents import load_index, search_documents, write_json_exclusive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True, help="검색 전 원문 해시를 재검증할 루트")
    parser.add_argument("--query", required=True)
    parser.add_argument("--document-id", action="append", required=True, dest="document_ids")
    parser.add_argument("--revision", help="정확 일치 개정; 미확인 개정은 일치하지 않음")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True, help="새 검색 JSON 경로; 기존 파일 덮어쓰기 금지")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("출력 파일이 이미 존재합니다. 새 실행 경로를 지정하세요.")
        index = load_index(args.index)
        result = search_documents(index, args.query, document_ids=args.document_ids,
                                  revision=args.revision, top_k=args.top_k, data_root=args.data_root)
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"문서 검색 오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "reason": result["reason"],
                      "hits": len(result["hits"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
