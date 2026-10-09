#!/usr/bin/env python3
"""선택한 수정만 사용해 새 재검토 실행을 만든다. --deliver를 줄 때만 검증 통과 후 loopback 모의 수신기로 보낸다."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from contextweld.corrections import CorrectionConflict, CorrectionError, write_rejection
from contextweld.review import DELIVERY_FAULTS, run_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-bundle', type=Path, required=True, help='즉시 부모 완료 묶음 (document-demo 또는 review)')
    parser.add_argument('--store', type=Path, required=True, help='record_correction.py로 기록한 수정 저장소')
    parser.add_argument('--correction', dest='corrections', action='append', required=True,
                        help='적용할 correction_id. 여러 번 지정할 수 있으며 지정 순서를 기록한다')
    parser.add_argument('--review-request-id', required=True,
                        help='명시적 재검토 요청 ID. <store>/review-requests/에 등록하며 같은 ID 재시도는 다시 실행·전송하지 않는다')
    parser.add_argument('--run-id', required=True, help='새 실행 ID. 기존 실행을 덮어쓰지 않는다')
    parser.add_argument('--output-root', type=Path, default=REPO / 'output/explicit-review')
    parser.add_argument('--requested-by', required=True, help='요청자 ID')
    parser.add_argument('--requester-kind', choices=['user', 'demo_fixture'], required=True,
                        help='실제 사용자 요청은 user, 자동 시연 요청은 demo_fixture')
    parser.add_argument('--reason', required=True, help='재검토 요청 사유')
    parser.add_argument('--deliver', action='store_true', help='검증 통과 시에만 127.0.0.1 모의 수신기로 전달')
    parser.add_argument('--delivery-fault', choices=list(DELIVERY_FAULTS),
                        help='시연용 전달 결함 주입. --deliver와 함께만 사용하며 요청 기록에 남는다')
    args = parser.parse_args()
    try:
        result = run_review(repo=REPO, parent_bundle=args.parent_bundle, store=args.store, correction_ids=args.corrections,
                            review_request_id=args.review_request_id, run_id=args.run_id, output_root=args.output_root,
                            requested_by={'kind': args.requester_kind, 'id': args.requested_by}, reason=args.reason,
                            deliver=args.deliver, delivery_fault=args.delivery_fault)
    except CorrectionError as exc:
        report = {'status': 'conflict' if isinstance(exc, CorrectionConflict) else 'rejected', 'code': exc.code,
                  'message': exc.message, 'details': exc.details, 'run_created': False}
        if exc.code != 'output_inside_bundle':
            report['rejection_log'] = str(write_rejection(args.output_root / 'rejected-requests', {
                'stage': 'run_review', **{k: report[k] for k in ('status', 'code', 'message', 'details')},
                'review_request_id': args.review_request_id, 'run_id': args.run_id,
                'parent_bundle_name': args.parent_bundle.name, 'correction_ids': args.corrections,
                'delivery_requested': args.deliver}))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str), file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'재검토 실행 실패: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
