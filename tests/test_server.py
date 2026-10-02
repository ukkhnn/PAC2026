"""실제 HTTP 경계에서 기록, 확인, 재사용과 입력 검증을 확인한다."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from contextweld.server import create_server


class APITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = create_server(0, database=Path(self.directory.name) / 'test.sqlite3')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, path, payload=None, headers=None):
        headers = {'Content-Type': 'application/json', **(headers or {})}
        req = Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def analyze(self, case, **kwargs):
        code, run = self.request('/api/analyze', {'scenario_id': case, **kwargs})
        self.assertEqual(code, 200, run)
        return run

    def test_review_then_memory_then_changed_revision(self):
        run = self.analyze('ambiguous')
        self.assertIsNone(run['baseline']['fields']['size_mm'])
        self.assertEqual(run['contextual']['fields']['size_mm'], 6)
        code, saved = self.request('/api/review', {'run_id': run['id'], 'revision': 0, 'action': 'approve', 'note': '시험 원본 재확인'})
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved['revision'], 1)
        next_run = self.analyze('memory')
        self.assertEqual(next_run['contextual']['memory_used']['run_id'], run['id'])
        context = copy.deepcopy(next_run['context'])
        context['plan_revision'] = 'PLAN-DEMO-v2'
        changed = self.analyze('memory', context=context)
        self.assertIsNone(changed['contextual']['memory_used'])
        self.assertEqual(changed['contextual']['status'], 'blocked')
        self.assertEqual(self.request('/api/runs/' + run['id'])[1]['reviews'], saved['reviews'])

    def test_export_download_preserves_stored_run(self):
        run = self.analyze('normal')
        with urlopen(self.base + '/api/runs/' + run['id'] + '/export', timeout=5) as response:
            self.assertIn('attachment;', response.headers['Content-Disposition'])
            exported = json.loads(response.read())
        self.assertEqual(exported['observations'], run['observations'])
        self.assertEqual(exported['contextual'], run['contextual'])
        self.assertEqual(exported['source']['image_sha256'], run['source']['image_sha256'])

    def test_conflict_cannot_be_approved_and_original_survives_correction(self):
        run = self.analyze('conflict')
        review = {'run_id': run['id'], 'revision': 0, 'action': 'approve', 'note': '시험 재확인'}
        self.assertEqual(self.request('/api/review', review)[0], 400)
        code, saved = self.request('/api/review', {**review, 'corrections': {'size_mm': 6}})
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved['observations'][3]['candidates'][0]['text'], 'SIZE: 8')
        self.assertEqual(saved['baseline']['fields']['size_mm'], 8)
        self.assertEqual(saved['contextual']['fields']['size_mm'], 6)
        self.assertEqual(self.request('/api/review', review)[0], 400)

    def test_wrong_plan_and_incomplete_work_never_yield_recipe(self):
        run = self.analyze('wrong-context')
        self.assertIsNone(run['contextual']['recipe'])
        context = copy.deepcopy(self.analyze('normal')['context'])
        context['preceding_complete'] = False
        self.assertIsNone(self.analyze('normal', context=context)['contextual']['recipe'])

    def test_external_origin_and_private_files_are_rejected(self):
        self.assertEqual(self.request('/api/analyze', {'scenario_id': 'normal'}, {'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('/api/health', headers={'Host': 'example.com'})[0], 403)
        for path in ['/.cowork/STATUS.md', '/.git/config', '/docs/references/idea-proposal.pdf', '/../README.md']:
            self.assertEqual(self.request(path)[0], 404)

    def test_invalid_image_and_malformed_context_create_no_record(self):
        self.assertEqual(self.request('/api/upload', {'image_base64': 'not-base64'})[0], 400)
        self.assertEqual(self.request('/api/upload', {'image_base64': 'aGVsbG8='})[0], 400)
        for context in [{'preceding_complete': 1}, {'thickness_mm': float('nan')}, {'expected_size_mm': True}]:
            self.assertEqual(self.request('/api/analyze', {'scenario_id': 'normal', 'context': context})[0], 400)
        self.assertEqual(self.request('/api/history')[1], [])


if __name__ == '__main__':
    unittest.main()
