"""인쇄체 합성 PNG에서 실제 로컬 OCR과 해석 연결을 검증한다."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from contextweld.engine import decide
from contextweld.ocr import recognize

result = recognize(ROOT / 'data/examples/ocr-printed.png', ROOT)
knowledge = json.loads((ROOT / 'data/knowledge/demo-rules.json').read_text())
case = json.loads((ROOT / 'data/examples/scenarios.json').read_text())[0]
decision = decide(result['observations'], case['context'], knowledge)
expected = {'part_id': 'BLK-017', 'seam_id': 'S-04', 'weld_type': 'FILLET', 'size_mm': 6, 'position': 'FLAT'}
if decision['fields'] != expected or not decision['recipe'] or decision['recipe']['id'] != 'DEMO-FW6':
    print(json.dumps({'ocr': result, 'decision': decision}, ensure_ascii=False, indent=2))
    raise SystemExit('OCR 연결 확인 실패: 실제 출력을 확인해주세요.')
print(json.dumps({'provider': result['provider'], 'observation_count': len(result['observations']),
                  'fields': decision['fields'], 'recipe': decision['recipe']['id'],
                  'scope': 'synthetic_printed_image_smoke_test_not_field_accuracy'}, ensure_ascii=False, indent=2))
