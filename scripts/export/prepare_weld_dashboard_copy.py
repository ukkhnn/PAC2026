#!/usr/bin/env python3
"""기존 통합 묶음의 알려진 목록 누락만 별도 사본에 보충한다."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from contextweld_dashboard.preservation import prepare_weld_copy

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare_weld_copy(args.source,args.output,args.report),ensure_ascii=False,indent=2))
