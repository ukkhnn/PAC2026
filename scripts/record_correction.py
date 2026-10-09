#!/usr/bin/env python3
"""완료된 실행 묶음 밖에 사용자 수정·보류를 별도로 기록한다. 재검토·모델 호출·모의 전송을 시작하지 않는다."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from contextweld.corrections import (CorrectionConflict, CorrectionError, describe_targets, record_correction,
                                     write_rejection)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    targets = commands.add_parser('targets', help='수정 가능한 대상·수정 전 값·결과 해시를 요청 서식으로 출력 (읽기 전용)')
    targets.add_argument('--bundle', type=Path, required=True, help='검증 가능한 완료 묶음 (document-demo 또는 review)')
    record = commands.add_parser('record', help='correction-request.v1 JSON 1건을 검사해 저장소에 새 파일로 기록')
    record.add_argument('--bundle', type=Path, required=True, help='수정 대상 완료 묶음. 읽기만 한다')
    record.add_argument('--request', type=Path, required=True, help='correction-request.v1 JSON 파일')
    record.add_argument('--store', type=Path, required=True, help='묶음 밖 수정 저장소 디렉토리')
    args = parser.parse_args()
    if args.command == 'targets':
        try:
            print(json.dumps(describe_targets(args.bundle), ensure_ascii=False, indent=2))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            print(f'대상 조회 실패: {exc}', file=sys.stderr)
            return 1
        return 0
    try:
        request = json.loads(args.request.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'요청 파일을 읽지 못했습니다: {exc}', file=sys.stderr)
        return 1
    try:
        result = record_correction(args.bundle, request, args.store)
    except CorrectionError as exc:
        report = {'status': 'conflict' if isinstance(exc, CorrectionConflict) else 'rejected', 'code': exc.code,
                  'message': exc.message, 'details': exc.details}
        # 저장소가 대상 묶음 안이면 거절 기록도 남기지 않는다. 완료 묶음은 바꾸지 않는다.
        if exc.code != 'store_inside_bundle':
            report['rejection_log'] = str(write_rejection(args.store / 'rejections', {
                'stage': 'record_correction', **{k: report[k] for k in ('status', 'code', 'message', 'details')},
                'bundle_name': args.bundle.name, 'request': request}))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str), file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'수정 저장 실패: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
