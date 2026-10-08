"""후보 연결의 모호함·버전·범위·입력 오류를 검증한다."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from contextweld.matching import WorkOrder, match_orders

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "data/examples/part-order-scene.json"


def order(**changes: object) -> WorkOrder:
    row = dict(project_id="DEMO", block_id="BLK-01", order_id="WO-108", part_id="B-108",
               revision=1, valid_from="2026-10-01T09:00:00+09:00", valid_until=None,
               state="released", instruction="가상 작업지시")
    row.update(changes)
    return WorkOrder.from_dict(row)


def match(candidates: list[str], orders: list[WorkOrder], **context: str) -> dict:
    scope = dict(project_id="DEMO", block_id="BLK-01", as_of="2026-10-08T10:00:00+09:00")
    scope.update(context)
    return match_orders(candidates, orders, **scope)


class MatchingTests(unittest.TestCase):
    def test_normal_preserves_original_and_does_not_authorize_execution(self) -> None:
        candidates = [" b-108 ", "B-108"]
        result = match(candidates, [order()])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["observed_candidates"], candidates)
        self.assertEqual(result["normalized_candidates"], ["B-108"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(candidates, [" b-108 ", "B-108"])

    def test_context_does_not_resolve_ambiguous_observation(self) -> None:
        result = match(["B-108", "B-103"], [order()])
        self.assertEqual(result["reason"], "ambiguous_part")
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["observed_candidates"], ["B-108", "B-103"])

    def test_two_valid_orders_require_review(self) -> None:
        result = match(["B-108"], [order(), order(order_id="WO-OTHER")])
        self.assertEqual(result["reason"], "multiple_orders")

    def test_scope_and_part_must_match_exactly(self) -> None:
        for changed in ({"project_id": "OTHER"}, {"block_id": "BLK-02"}, {"part_id": "B-103"}):
            with self.subTest(changed=changed):
                result = match(["B-108"], [order(**changed)])
                self.assertEqual(result["status"], "unmatched")
                self.assertEqual(result["matches"], [])
                self.assertEqual(len(result["excluded_orders"]), 1)

    def test_latest_effective_revision_not_input_order(self) -> None:
        older = order()
        newer = order(revision=2, valid_from="2026-10-08T09:00:00+09:00")
        first = match(["B-108"], [older, newer])
        self.assertEqual(first, match(["B-108"], [newer, older]))
        self.assertEqual(first["matches"][0]["revision"], 2)
        self.assertEqual(first["excluded_orders"][0]["reason"], "superseded")

    def test_future_cancellation_does_not_change_past(self) -> None:
        future = order(revision=2, valid_from="2026-10-09T09:00:00+09:00", state="cancelled")
        result = match(["B-108"], [order(), future])
        self.assertEqual(result["matches"][0]["revision"], 1)
        self.assertEqual(result["excluded_orders"][0]["reason"], "not_yet_effective")

    def test_cancelled_held_or_expired_latest_never_revives_old(self) -> None:
        variants = [dict(state="cancelled"), dict(state="on_hold"),
                    dict(valid_until="2026-10-08T10:00:00+09:00")]
        for changes in variants:
            with self.subTest(changes=changes):
                latest = order(revision=2, valid_from="2026-10-08T09:00:00+09:00", **changes)
                result = match(["B-108"], [order(), latest])
                self.assertEqual(result["matches"], [])
                self.assertEqual(result["status"], "unmatched")
                self.assertEqual(result["excluded_orders"][0]["reason"], "superseded")

    def test_half_open_time_interval_and_timezone_equivalence(self) -> None:
        bounded = order(valid_from="2026-10-08T10:00:00+09:00", valid_until="2026-10-08T11:00:00+09:00")
        self.assertEqual(match(["B-108"], [bounded], as_of="2026-10-08T01:00:00Z")["status"], "matched")
        self.assertEqual(match(["B-108"], [bounded], as_of="2026-10-08T02:00:00Z")["status"], "unmatched")
        self.assertEqual(match(["B-108"], [bounded], as_of="2026-10-08T00:59:59Z")["status"], "unmatched")

    def test_no_candidate_does_not_invent_from_plan(self) -> None:
        result = match([], [order()])
        self.assertEqual(result["status"], "unreadable")
        self.assertEqual(result["matches"], [])

    def test_no_fuzzy_correction(self) -> None:
        self.assertEqual(match(["B-1O8"], [order()])["status"], "unmatched")

    def test_invalid_revision_histories_are_rejected(self) -> None:
        for second in [order(), order(revision=2, part_id="B-103"),
                       order(revision=2, valid_from="2026-09-01T09:00:00+09:00")]:
            with self.subTest(second=second):
                with self.assertRaises(ValueError):
                    match(["B-108"], [order(), second])

    def test_invalid_inputs_are_rejected(self) -> None:
        for changes in [dict(revision=True), dict(revision=0), dict(state="done"),
                        dict(valid_from="2026-10-08T09:00:00"),
                        dict(valid_until="2026-09-01T09:00:00+09:00")]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                order(**changes)
        for candidates in [[""], [None], "B-108"]:
            with self.subTest(candidates=candidates), self.assertRaises(ValueError):
                match(candidates, [order()])
        with self.assertRaises(ValueError):
            match(["B-108"], [order()], as_of="2026-10-08")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "contextweld", *args],
                              capture_output=True, text=True, cwd=ROOT)

    def test_example_cases_and_provenance(self) -> None:
        for case, status in {"normal": "matched", "ambiguous": "review_required",
                             "stale": "unmatched", "wrong-context": "unmatched"}.items():
            with self.subTest(case=case):
                run = self.run_cli(str(EXAMPLE), "--case", case)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["dataset_kind"], "synthetic")
                self.assertEqual(result["candidate_source"], "synthetic_manual")

    def test_missing_case_and_malformed_input_fail_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            for contents in ['{', '[]', '{"schema_version": 1}',
                             '{"schema_version": true}',
                             EXAMPLE.read_text().replace('"revision": 1', '"revision": false')]:
                bad.write_text(contents)
                run = self.run_cli(str(bad), "--case", "normal")
                self.assertEqual(run.returncode, 2)
                self.assertIn("입력 오류", run.stderr)
                self.assertNotIn("Traceback", run.stderr)
                self.assertEqual(run.stdout, "")
        self.assertEqual(self.run_cli(str(EXAMPLE), "--case", "absent").returncode, 2)


if __name__ == "__main__":
    unittest.main()
