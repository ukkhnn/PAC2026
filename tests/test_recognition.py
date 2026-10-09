"""모델 원문 보존, 좌표·참조 거부, 중단/완료 묶음 계약을 검사한다."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from contextweld.recognition import (Bundle, infer_json, normalize_ocr, normalize_visual,
                                     parse_json, run_bootstrap, safe_path, sha256,
                                     validate_relations, verify_bundle)


class RecognitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_ocr_preserves_text_score_and_original_coordinates(self) -> None:
        polygon = [[1, 2], [60, 2], [60, 20], [1, 20]]
        raw = {"res": {"rec_texts": ["O-01?"], "rec_scores": [0.27], "rec_polys": [polygon]}}
        observation = normalize_ocr(raw, "f", 100, 40)[0]
        self.assertEqual(observation["raw_text"], "O-01?")
        self.assertEqual(observation["polygon"], polygon)
        self.assertEqual(observation["recognition_score"], 0.27)
        self.assertIsNone(observation["detection_score"])
        raw["res"]["rec_polys"][0][0][0] = -1
        with self.assertRaises(ValueError):
            normalize_ocr(raw, "f", 100, 40)

    def test_visual_coordinate_transform_and_duplicate_id_rejection(self) -> None:
        item = {"observation_id": "v1", "kind": "member", "bbox_1000": [100, 200, 500, 900],
                "description": "plate", "visible_text": None}
        parsed = {"scene_summary": "plate", "quality_issues": [], "visual_objects": [item]}
        result = normalize_visual(parsed, "frame-001", 960, 540)
        self.assertEqual(result[0]["bbox"], [96, 108, 480, 486])
        self.assertEqual(result[0]["observation_id"], "frame-001-vlm-v1")
        parsed["visual_objects"].append(item.copy())
        with self.assertRaises(ValueError):
            normalize_visual(parsed, "f", 960, 540)
        parsed["visual_objects"] = [{**item, "bbox_1000": [0, 0, 1001, 1000]}]
        with self.assertRaises(ValueError):
            normalize_visual(parsed, "f", 960, 540)

    def test_invalid_relation_reference_and_execution_are_rejected(self) -> None:
        item = {"relation_id": "r1", "source_observation_ids": ["o1"],
                "target_observation_candidates": ["v1"], "selected_target_observation_id": None,
                "document_refs": ["d1"], "interpretation": "uncertain", "reason_codes": ["uncertain"]}
        parsed = {"relations": [item], "unresolved": ["work order absent"]}
        self.assertEqual(validate_relations(parsed, {"o1", "v1"}, {"d1"}), [item])
        for changed in ({"document_refs": ["invented"]}, {"target_observation_candidates": ["invented"]},
                        {"selected_target_observation_id": "o1"}, {"execution_authorized": True},
                        {"wps_id": "invented"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_relations({"relations": [{**item, **changed}], "unresolved": []}, {"o1", "v1"}, {"d1"})

    def test_bundle_atomic_publish_and_tamper_detection(self) -> None:
        bundle = Bundle(self.root, "sample", {"labels_used": False})
        bundle.result("recognition_decision", "f1", {"action": "needs_review"}, producer="rule")
        self.assertFalse(bundle.final.exists())
        final = bundle.finish()
        self.assertFalse(bundle.root.exists())
        verify_bundle(final)
        manifest = json.loads((final / "manifest.json").read_text())
        self.assertFalse(manifest["delivery_requested"])
        self.assertFalse(manifest["execution_authorized"])
        self.assertFalse(manifest["demo_complete"])
        with self.assertRaises(FileExistsError):
            Bundle(self.root, "sample", {})
        (final / "results/f1-recognition_decision.json").write_text("tampered")
        with self.assertRaises(ValueError):
            verify_bundle(final)

    def test_incomplete_failure_keeps_raw_output(self) -> None:
        bundle = Bundle(self.root, "failed", {})
        raw = bundle.root / "results/model.raw.txt"
        raw.write_text("invalid model output")
        preserved = bundle.fail(ValueError("bad response"))
        self.assertEqual(raw.read_text(), "invalid model output")
        self.assertFalse(bundle.final.exists())
        manifest = json.loads((preserved / "manifest.json").read_text())
        self.assertEqual(manifest["export_status"], "incomplete")
        self.assertEqual(manifest["status"], "failed")
        with self.assertRaises(FileExistsError):
            Bundle(self.root, "failed", {})

    def test_event_parents_follow_inputs_instead_of_other_frame(self) -> None:
        bundle = Bundle(self.root, "parents", {})
        first = bundle.event("frame_ingest", "frames/f1.json", "system", ["f1"])
        second = bundle.event("frame_ingest", "frames/f2.json", "system", ["f2"])
        bundle.result("ocr", "f1", {})
        bundle.result("ocr", "f2", {})
        events = [json.loads(line) for line in (bundle.root / "events.jsonl").read_text().splitlines()]
        self.assertEqual(events[0]["parent_event_ids"], [])
        self.assertEqual(events[1]["parent_event_ids"], [])
        self.assertEqual(events[2]["parent_event_ids"], [first])
        self.assertEqual(events[3]["parent_event_ids"], [second])

    def test_one_syntax_retry_preserves_both_prompts_and_raws(self) -> None:
        class Engine:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, image: Path, prompt: str) -> str:
                self.calls += 1
                self.last_generation = {"output_tokens": 1800 if self.calls == 1 else 20,
                                        "hit_token_limit": self.calls == 1}
                return "broken{" if self.calls == 1 else '{"relations": [], "unresolved": []}'

        bundle = Bundle(self.root, "retry", {})
        engine = Engine()
        parsed, raw_ref, _ = infer_json(bundle, engine, Path("unused"), "stage", "original prompt")
        self.assertEqual(engine.calls, 2)
        self.assertEqual(parsed["relations"], [])
        self.assertEqual(raw_ref, "results/stage.retry.raw.txt")
        self.assertEqual((bundle.root / "results/stage.raw.txt").read_text(), "broken{")
        self.assertEqual((bundle.root / "results/stage.prompt.txt").read_text(), "original prompt")
        first_generation = json.loads((bundle.root / "results/stage.generation.json").read_text())
        retry_generation = json.loads((bundle.root / "results/stage.retry.generation.json").read_text())
        self.assertTrue(first_generation["hit_token_limit"])
        self.assertFalse(retry_generation["hit_token_limit"])
        self.assertEqual(first_generation["output_tokens"], 1800)

    def test_nonfinite_json_and_path_escape_are_rejected(self) -> None:
        for raw in ('{"x": NaN}', '{"x": Infinity}', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_json(raw)
        for path in ("../secret", "/absolute", "a/../../secret", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(self.root, path)
        outside = self.root.parent / "escape"
        (self.root / "link").symlink_to(outside)
        with self.assertRaises(ValueError):
            safe_path(self.root, "link/file")

    def test_pipeline_keeps_image_observation_separate_from_documents(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        from contextweld.documents import build_index
        original = self.root / "SECRET_ANSWER_123.png"
        Image.new("RGB", (100, 60), "white").save(original)
        document = self.root / "reference.md"
        document.write_text("# Weld symbols\n\nThe arrow identifies a joint.\n")
        sources = self.root / "sources.json"
        sources.write_text(json.dumps({"sources": [
            {"id": "steel-S01", "group": "steel-images", "relative_path": original.name, "sha256": sha256(original)},
            {"id": "reference", "group": "documents", "relative_path": document.name, "sha256": sha256(document),
             "url": "https://example.com/reference", "media_type": "text/plain"}]}))
        index = build_index(self.root, sources)
        prompts = []
        stages = []

        class OCR:
            def predict(self, image: Path) -> dict:
                stages.append("ocr")
                return {"rec_texts": ["O?"], "rec_scores": [0.1],
                        "rec_polys": [[[1, 2], [20, 2], [20, 10], [1, 10]]]}

            def close(self) -> None:
                stages.append("ocr_closed")

        class VLM:
            def generate(self, image: Path, prompt: str) -> str:
                prompts.append(prompt)
                stages.append("vlm")
                if len(prompts) == 1:
                    return json.dumps({"scene_summary": "white surface", "quality_issues": [], "visual_objects": []})
                return json.dumps({"relations": [], "unresolved": ["no visible relation"]})

            def close(self) -> None:
                stages.append("vlm_closed")

        result = run_bootstrap(data_root=self.root, sources_path=sources, output_root=self.root / "runs",
                               run_id="integration", image_ids=["steel-S01"], config={"test_fixture": True},
                               ocr_factory=OCR, vlm_factory=VLM, document_index=index,
                               document_ids=["reference"], query="arrow joint")
        verify_bundle(result)
        self.assertEqual(stages, ["ocr", "ocr_closed", "vlm", "vlm", "vlm_closed"])
        self.assertNotIn("The arrow identifies a joint.", prompts[0])
        self.assertIn("The arrow identifies a joint.", prompts[1])
        self.assertTrue(all("SECRET_ANSWER_123" not in prompt for prompt in prompts))
        retrieval = json.loads((result / "evidence/frame-001-retrieval.json").read_text())
        self.assertEqual(retrieval["returned_evidence_ids"], retrieval["used_evidence_ids"])
        self.assertEqual(retrieval["cited_evidence_ids"], [])
        candidate = json.loads((result / "results/frame-001-work_spec_candidate.json").read_text())
        self.assertEqual(candidate["fields"], {})
        self.assertFalse(candidate["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
