"""문서 연결과 전송 보류를 합성 테스트 입력으로 검증한다. 정확도 실험이 아니다."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from contextweld.documents import build_index
from contextweld.recognition import Bundle, sha256, write_json
from contextweld.workflow import (apply_case, build_spec, inspect_document_bundle,
                                  observed_candidates, read_json, run_document_demo)

ROOT = Path(__file__).resolve().parents[1]


def observation(text: str = 'BISb30N-15', visible: str = 'BISb30N-15') -> dict:
    return {'text_observations': [{'observation_id': 'ocr-1', 'raw_text': text, 'bbox': [10, 10, 100, 40]}],
            'visual_objects': [{'observation_id': 'vlm-1', 'kind': 'text', 'visible_text': visible,
                                'bbox': [10, 10, 100, 40]}]}


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo, self.raw, self.output = self.root / 'repo', self.root / 'raw', self.root / 'output'
        self.config = self.repo / 'configs/document_demo'
        shutil.copytree(ROOT / 'configs/document_demo', self.config)
        self.raw.mkdir()
        (self.raw / 'wps.md').write_text('# Unit test fixture\nWelding current voltage travel speed\n')
        wps = read_json(ROOT / 'data/knowledge/lanl-wps-3501-reviewed.json')
        old, new = wps['source_hash'], sha256(self.raw / 'wps.md')
        wps = json.loads(json.dumps(wps).replace(old, new))
        wps['source']['relative_path'] = 'wps.md'
        wps['source']['url'] = 'https://example.invalid/unit-test'
        wp = self.repo / 'data/knowledge/lanl-wps-3501-reviewed.json'
        wp.parent.mkdir(parents=True)
        write_json(wp, wps)
        registry = self.root / 'sources.json'
        write_json(registry, {'sources': [{'id': wps['document_id'], 'group': 'documents', 'relative_path': 'wps.md',
                                          'sha256': new, 'media_type': 'text/plain', 'url': 'https://example.invalid/unit-test'}]})
        self.index = self.root / 'index.json'
        write_json(self.index, build_index(self.raw, registry))
        for relative in ['src/contextweld/workflow.py', 'src/contextweld/mock_delivery.py', 'src/contextweld/matching.py',
                         'src/contextweld/documents.py', 'scripts/run_document_demo.py', 'scripts/verify_document_demo.py']:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        bundle = Bundle(self.root / 'source', 'steel-batch-20261010-02', {'fixture': True})
        for frame_id, data in [('frame-007', observation()), ('frame-005', observation('BISb30N-29', 'B1Sb3ON-29'))]:
            image = bundle.root / 'frames' / f'{frame_id}.txt'
            image.write_text('Unit test placeholder, not an actual model image')
            bundle.manifest['frames'].append({'frame_id': frame_id, 'image_ref': f'frames/{frame_id}.txt', 'sha256': sha256(image)})
            bundle.result('observation', frame_id, data)
        self.source = bundle.finish()
        self.source_hash = sha256(self.source / 'checksums.json')
        self.kwargs = {'repo': self.repo, 'scenario_path': self.config / 'scenario.json', 'recognition_bundle': self.source,
                       'document_index': self.index, 'data_root': self.raw, 'output_root': self.output}

    def run_case(self, case: str, deliver: bool = True) -> Path:
        return run_document_demo(**self.kwargs, run_id='unit-' + case, case=case, deliver=deliver)

    def refresh_hashes(self, bundle: Path) -> None:
        manifest = read_json(bundle / 'manifest.json')
        write_json(bundle / 'checksums.json', {ref: sha256(bundle / ref) for ref in manifest['files']})

    def test_normal_actual_http_field_evidence_and_immutable_source(self) -> None:
        bundle = self.run_case('normal')
        report = inspect_document_bundle(bundle)
        self.assertEqual(report['run_outcome'], 'succeeded')
        self.assertEqual(report['delivery_status'], 'received')
        spec = read_json(bundle / 'results/work-spec.json')
        self.assertEqual(spec['parameters']['current']['min'], 130)
        self.assertEqual(spec['parameters']['current']['max'], 250)
        self.assertEqual(spec['parameters']['travel_speed']['unit'], 'in/min')
        self.assertEqual(spec['parameters']['voltage']['evidence']['locator']['page'], 2)
        self.assertEqual(spec['target_evidence']['joint_id']['source_kind'], 'fixture')
        self.assertFalse(spec['application_authorized'])
        self.assertEqual(spec['physical_applicability'], 'unverified')
        self.assertEqual(sha256(self.source / 'checksums.json'), self.source_hash)
        self.assertEqual(report, inspect_document_bundle(bundle))

    def test_missing_conflict_revision_and_observation_block_before_receiver(self) -> None:
        for case, code in [('missing', 'required_parameter_missing'), ('conflict', 'work_order_drawing_conflict'),
                           ('revision-mismatch', 'wps_reference_mismatch'), ('observation-conflict', 'ocr_vlm_disagreement')]:
            with self.subTest(case=case), patch('contextweld.mock_delivery.MockReceiver') as receiver:
                bundle = self.run_case(case)
                receiver.assert_not_called()
                spec = read_json(bundle / 'results/work-spec.json')
                self.assertIn(code, [item['code'] for item in spec['validation']['issues']])
                self.assertEqual(inspect_document_bundle(bundle)['run_outcome'], 'needs_review')
                self.assertEqual(list((bundle / 'commands').iterdir()), [])
                if case == 'missing':
                    self.assertIn('parameters.voltage', spec['validation']['missing_fields'])

    def test_no_delivery_request_never_starts_receiver(self) -> None:
        with patch('contextweld.mock_delivery.MockReceiver') as receiver:
            bundle = self.run_case('normal', deliver=False)
            receiver.assert_not_called()
        self.assertEqual(inspect_document_bundle(bundle)['delivery_status'], 'not_requested')

    def test_run_id_reuse_and_changed_original_are_rejected(self) -> None:
        self.run_case('normal', deliver=False)
        with self.assertRaises(FileExistsError):
            self.run_case('normal', deliver=False)
        (self.raw / 'wps.md').write_text('changed source')
        with self.assertRaisesRegex(ValueError, 'WPS 원문'):
            self.run_case('missing')

    def test_document_value_tampering_rejected_even_with_rehashed_bundle(self) -> None:
        bundle = self.run_case('normal', deliver=False)
        spec_path = bundle / 'results/work-spec.json'
        spec = read_json(spec_path)
        spec['parameters']['current']['max'] = 999
        write_json(spec_path, spec)
        self.refresh_hashes(bundle)
        with self.assertRaisesRegex(ValueError, '재계산'):
            inspect_document_bundle(bundle)

    def test_receipt_tampering_rejected_even_with_rehashed_bundle(self) -> None:
        bundle = self.run_case('normal')
        ledger = bundle / 'commands/receiver.jsonl'
        row = json.loads(ledger.read_text())
        row['command']['target']['part_id'] = 'DIFFERENT'
        ledger.write_text(json.dumps(row) + '\n')
        self.refresh_hashes(bundle)
        with self.assertRaisesRegex(ValueError, '수신기 원본'):
            inspect_document_bundle(bundle)

    def test_effective_document_cannot_change_without_declared_fault(self) -> None:
        bundle = self.run_case('normal', deliver=False)
        path = bundle / 'inputs/effective-drawing.json'
        drawing = read_json(path)
        drawing['process'] = 'GMAW'
        write_json(path, drawing)
        self.refresh_hashes(bundle)
        with self.assertRaisesRegex(ValueError, '결함 주입'):
            inspect_document_bundle(bundle)

    def test_same_order_id_in_another_project_cannot_override_selection(self) -> None:
        path = self.config / 'work_orders.json'
        orders = read_json(path)
        wrong = deepcopy(orders['orders'][0])
        wrong.update(project_id='OTHER', joint_id='WRONG-JOINT')
        orders['orders'].insert(0, wrong)
        write_json(path, orders)
        bundle = self.run_case('normal', deliver=False)
        self.assertEqual(read_json(bundle / 'results/work-spec.json')['target']['joint_id'], 'JOINT-DEMO-01')
        self.assertEqual(inspect_document_bundle(bundle)['run_outcome'], 'succeeded')

    def test_latest_cancelled_order_is_not_revived(self) -> None:
        path = self.config / 'work_orders.json'
        orders = read_json(path)
        newer = deepcopy(orders['orders'][0])
        newer.update(revision=2, state='cancelled', valid_from='2026-10-09T00:00:00Z')
        orders['orders'].append(newer)
        write_json(path, orders)
        bundle = self.run_case('normal')
        self.assertEqual(inspect_document_bundle(bundle)['run_outcome'], 'needs_review')
        self.assertFalse(read_json(bundle / 'results/delivery.json')['sent'])

    def test_disagreement_is_not_replaced_with_document_identifier(self) -> None:
        scenario = read_json(self.config / 'scenario.json')
        raw = observation('BISb30N-15', 'B1Sb30N-15')
        before = deepcopy(raw)
        result = observed_candidates(raw, scenario['observation_policy'])
        self.assertEqual(raw, before)
        self.assertEqual(result['candidates'], ['BISB30N-15', 'B1SB30N-15'])
        self.assertEqual(result['issues'][0]['code'], 'ocr_vlm_disagreement')

    def test_socket_failure_preserves_incomplete_run_without_false_ack(self) -> None:
        with patch('contextweld.mock_delivery.send_command', side_effect=TimeoutError('test timeout')):
            with self.assertRaises(TimeoutError):
                self.run_case('normal')
        bundle = self.output / 'run_unit-normal.incomplete'
        manifest = read_json(bundle / 'manifest.json')
        self.assertEqual(manifest['run_outcome'], 'failed')
        self.assertEqual(manifest['export_status'], 'incomplete')
        self.assertTrue((bundle / 'commands/command.json').is_file())
        self.assertFalse((bundle / 'commands/transport.json').exists())


if __name__ == '__main__':
    unittest.main()
