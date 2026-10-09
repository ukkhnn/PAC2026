#!/usr/bin/env python3
"""보존된 실제 인식 결과로 문서 연결과 선택적 모의 HTTP 전달을 실행한다."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from contextweld.workflow import run_document_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=REPO / 'configs/document_demo/scenario.json')
    parser.add_argument('--recognition-bundle', type=Path, required=True)
    parser.add_argument('--document-index', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=REPO / 'data/raw/demo-bootstrap-v1')
    parser.add_argument('--output-root', type=Path, default=REPO / 'output/document-demo')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--case', default='normal')
    parser.add_argument('--deliver', action='store_true', help='검증을 통과한 문서 검토값만 loopback 모의 수신기로 전달')
    args = parser.parse_args()
    try:
        bundle = run_document_demo(repo=REPO, scenario_path=args.scenario, recognition_bundle=args.recognition_bundle,
                                   document_index=args.document_index, data_root=args.data_root,
                                   output_root=args.output_root, run_id=args.run_id, case=args.case, deliver=args.deliver)
        manifest = json.loads((bundle / 'manifest.json').read_text())
        print(json.dumps({'bundle': str(bundle), 'run_outcome': manifest['run_outcome'],
                          'delivery_status': manifest['delivery_status'], 'demo_complete': False}, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'문서 연결 실행 실패: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
