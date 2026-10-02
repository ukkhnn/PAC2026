"""판단과 확인 이력의 경계 동작을 검증한다. 현장 정확도 측정은 아니다."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contextweld.engine import decide, memory_scope
from contextweld.store import Store

KNOWLEDGE = json.loads((ROOT / "data/knowledge/demo-rules.json").read_text())
CASES = {item["id"]: item for item in json.loads((ROOT / "data/examples/scenarios.json").read_text())}


class EngineTests(unittest.TestCase):
    def run_case(self, name: str, **kwargs: object) -> dict:
        case = copy.deepcopy(CASES[name])
        return decide(case["observations"], case["context"], KNOWLEDGE, **kwargs)

    def test_normal_candidate_has_no_fabricated_settings(self) -> None:
        result = self.run_case("normal")
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(result["recipe"]["id"], "DEMO-FW6")
        self.assertTrue(all(value is None for value in result["recipe"]["settings"].values()))

    def test_context_narrows_visual_candidates_but_requests_review(self) -> None:
        before = self.run_case("ambiguous", use_context=False)
        after = self.run_case("ambiguous")
        self.assertIsNone(before["fields"]["size_mm"])
        self.assertEqual(after["fields"]["size_mm"], 6)
        self.assertEqual(after["status"], "review_required")
        self.assertEqual(len(after["candidates"]["size_mm"]), 2)

    def test_conflict_does_not_replace_visual_fact_with_plan(self) -> None:
        result = self.run_case("conflict")
        self.assertEqual(result["fields"]["size_mm"], 8)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["recipe"])

    def test_wrong_identity_never_uses_context_to_narrow(self) -> None:
        case = copy.deepcopy(CASES["ambiguous"])
        case["context"]["part_id"] = "BLK-099"
        result = decide(case["observations"], case["context"], KNOWLEDGE)
        self.assertIsNone(result["fields"]["size_mm"])
        self.assertEqual(result["status"], "blocked")

    def test_unread_size_cannot_be_invented_from_plan(self) -> None:
        case = copy.deepcopy(CASES["normal"])
        case["observations"] = [item for item in case["observations"] if item["id"] != "mark-4"]
        result = decide(case["observations"], case["context"], KNOWLEDGE)
        self.assertIsNone(result["fields"]["size_mm"])
        self.assertEqual(result["status"], "blocked")

    def test_memory_is_scoped_and_stays_within_visual_candidates(self) -> None:
        case = copy.deepcopy(CASES["memory"])
        memory = {"scope": memory_scope(case["context"], KNOWLEDGE["version"]),
                  "confirmed_fields": {"size_mm": 6}, "review_id": "review-1", "run_id": "run-1", "note": "원본 확인"}
        result = decide(case["observations"], case["context"], KNOWLEDGE, memories=[memory])
        self.assertEqual(result["fields"]["size_mm"], 6)
        self.assertEqual(result["memory_used"]["review_id"], "review-1")
        for key, value in [("seam_id", "S-99"), ("plan_revision", "v2"), ("material", "OTHER")]:
            changed = copy.deepcopy(memory)
            changed["scope"][key] = value
            self.assertIsNone(decide(case["observations"], case["context"], KNOWLEDGE, memories=[changed])["memory_used"])
        memory["confirmed_fields"]["size_mm"] = 10
        self.assertIsNone(decide(case["observations"], case["context"], KNOWLEDGE, memories=[memory])["memory_used"])

    def test_incomplete_preceding_work_and_wrong_thickness_block(self) -> None:
        for key, value in [("preceding_complete", False), ("thickness_mm", 25)]:
            case = copy.deepcopy(CASES["normal"])
            case["context"][key] = value
            result = decide(case["observations"], case["context"], KNOWLEDGE)
            self.assertEqual(result["status"], "blocked")
            self.assertIsNone(result["recipe"])


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "test.sqlite3")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def create(self, name: str) -> dict:
        case = copy.deepcopy(CASES[name])
        return self.store.create({"scenario_id": name}, case["observations"], case["context"], KNOWLEDGE)

    def test_correction_preserves_original_and_persists_audit(self) -> None:
        run = self.create("conflict")
        with self.assertRaises(ValueError):
            self.store.review(run["id"], "approve", "충돌 무시", {}, 0, KNOWLEDGE)
        approved = self.store.review(run["id"], "approve", "원본 치수 재확인", {"size_mm": 6}, 0, KNOWLEDGE)
        self.assertEqual(approved["observations"][3]["candidates"][0]["text"], "SIZE: 8")
        self.assertEqual(approved["baseline"]["fields"]["size_mm"], 8)
        self.assertEqual(approved["contextual"]["fields"]["size_mm"], 6)
        self.assertEqual(self.store.get(run["id"])["reviews"][0]["note"], "원본 치수 재확인")
        self.assertEqual(len(self.store.memories()), 1)

    def test_stale_review_is_rejected(self) -> None:
        run = self.create("normal")
        self.store.review(run["id"], "approve", "확인", {}, 0, KNOWLEDGE)
        with self.assertRaises(ValueError):
            self.store.review(run["id"], "hold", "오래된 화면", {}, 0, KNOWLEDGE)

    def test_hold_is_not_usable_memory(self) -> None:
        run = self.create("normal")
        self.store.review(run["id"], "hold", "보류", {}, 0, KNOWLEDGE)
        self.assertEqual(self.store.memories(), [])

    def test_approved_history_can_narrow_next_run(self) -> None:
        run = self.create("ambiguous")
        self.store.review(run["id"], "approve", "6으로 확인", {}, 0, KNOWLEDGE)
        next_run = self.create("memory")
        self.assertEqual(next_run["contextual"]["memory_used"]["run_id"], run["id"])
        self.assertIsNone(next_run["baseline"]["fields"]["size_mm"])


if __name__ == "__main__":
    unittest.main()
