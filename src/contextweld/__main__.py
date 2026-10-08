"""JSON 후보와 작업지시를 읽는 간단한 CLI."""

import argparse
import json
from pathlib import Path
import sys

from .matching import WorkOrder, match_orders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부재번호 후보와 유효한 작업지시 연결 (사진 OCR 미포함)")
    parser.add_argument("input", type=Path, help="작업지시와 사례가 있는 JSON 파일")
    parser.add_argument("--case", required=True, help="조회할 사례 ID")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != 1):
            raise ValueError("schema_version: 1인 JSON 객체가 필요합니다.")
        for field in ("dataset_kind", "provenance"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError(f"{field}에 데이터 출처를 기록해야 합니다.")
        if not isinstance(payload["cases"], list) or not isinstance(payload["orders"], list):
            raise ValueError("cases와 orders는 배열이어야 합니다.")
        cases = [case for case in payload["cases"] if case["id"] == args.case]
        if len(cases) != 1:
            raise ValueError("사례 ID가 없거나 중복됩니다.")
        case = cases[0]
        if not isinstance(case.get("candidate_source"), str) or not case["candidate_source"].strip():
            raise ValueError("candidate_source에 후보의 출처가 필요합니다.")
        orders = [WorkOrder.from_dict(row) for row in payload["orders"]]
        result = match_orders(case["candidates"], orders, project_id=case["project_id"],
                              block_id=case["block_id"], as_of=case["as_of"])
        result.update({"case_id": args.case, "dataset_kind": payload["dataset_kind"],
                       "provenance": payload["provenance"], "candidate_source": case["candidate_source"]})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
