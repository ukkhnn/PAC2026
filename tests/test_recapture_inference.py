"""촬영 판단의 실제 관측 참조, 기존 파이프라인 재사용과 실패 근거 보존."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from contextweld.documents import build_index
from contextweld.recognition import Bundle, OBSERVATION_PROMPT, sha256
from contextweld.recapture_inference import (
    CAPTURE_ASSESSMENT_PROMPT, PipelineObserver, capture_assessment_prompt,
    validate_capture_assessment,
)


def observations() -> dict:
    return {"scene_summary": "marked plate", "quality_issues": [],
            "text_observations": [{"observation_id": "frame-001-ocr-001", "raw_text": "M-17",
                                   "bbox": [10, 10, 30, 20]}],
            "visual_objects": [{"observation_id": "frame-001-vlm-joint", "kind": "joint",
                                "description": "plate joint", "visible_text": None,
                                "bbox": [40, 10, 50, 50]}]}


def relations() -> dict:
    return {"relations": [{"relation_id": "r1", "source_observation_ids": ["frame-001-ocr-001"],
                           "target_observation_candidates": ["frame-001-vlm-joint"],
                           "selected_target_observation_id": "frame-001-vlm-joint",
                           "document_refs": [], "interpretation": "marking beside joint", "reason_codes": []}],
            "unresolved": []}


def assessment() -> dict:
    return {"field_checks": [
        {"field": "marking_text", "status": "observed", "observation_ids": ["frame-001-ocr-001"],
         "relation_ids": [], "explanation": "The OCR records the marking."},
        {"field": "marking_target", "status": "observed", "observation_ids": ["frame-001-vlm-joint"],
         "relation_ids": ["r1"], "explanation": "The relation selects the visible joint."}],
        "quality_evidence": []}


def unresolved_assessment() -> dict:
    return {"field_checks": [
        {"field": field, "status": "unresolved", "observation_ids": [], "relation_ids": [],
         "explanation": "The required information is not visible."}
        for field in ("marking_text", "marking_target")],
        "quality_evidence": [{"code": "unreadable", "affected_fields": ["marking_text"],
                              "observation_ids": [], "explanation": "Bright region has no legible text.",
                              "viewpoint_change_may_help": True}]}


class CaptureAssessmentTests(unittest.TestCase):
    def test_valid_observed_fields_and_quality_do_not_imply_failure(self) -> None:
        value = assessment()
        value["quality_evidence"] = [{"code": "glare", "affected_fields": ["marking_text"],
                                      "observation_ids": ["frame-001-ocr-001"],
                                      "explanation": "Reflection beside the readable marking.",
                                      "viewpoint_change_may_help": False}]
        self.assertEqual(validate_capture_assessment(value, observations(), relations()), value)

    def test_unresolved_may_have_no_references_and_does_not_invent_them(self) -> None:
        value = unresolved_assessment()
        result = validate_capture_assessment(value, {"text_observations": [], "visual_objects": []}, {"relations": []})
        self.assertEqual(result, value)

    def test_unknown_and_duplicate_references_are_rejected(self) -> None:
        for key, value in (("observation_ids", ["invented"]),
                           ("observation_ids", ["frame-001-ocr-001", "frame-001-ocr-001"]),
                           ("relation_ids", ["invented"]), ("relation_ids", ["r1", "r1"])):
            changed = assessment()
            changed["field_checks"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_capture_assessment(changed, observations(), relations())

    def test_observed_text_needs_actual_referenced_text_not_a_description(self) -> None:
        for text in (None, "", "  "):
            source = observations()
            source["text_observations"][0]["raw_text"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_capture_assessment(assessment(), source, relations())
        value = assessment()
        value["field_checks"][0]["observation_ids"] = ["frame-001-vlm-joint"]
        source = observations()
        source["visual_objects"][0]["description"] = "This says M-17"
        source["visual_objects"][0]["raw_text"] = "injected unexpected visual field"
        with self.assertRaises(ValueError):
            validate_capture_assessment(value, source, relations())
        source["visual_objects"][0]["visible_text"] = "M-17"
        validate_capture_assessment(value, source, relations())

    def test_observed_target_needs_a_referenced_selected_actual_target(self) -> None:
        for selected, references in ((None, ["r1"]), ("invented", ["r1"]), ("frame-001-vlm-joint", [])):
            value, relation = assessment(), relations()
            relation["relations"][0]["selected_target_observation_id"] = selected
            value["field_checks"][1]["relation_ids"] = references
            with self.subTest(selected=selected, references=references), self.assertRaises(ValueError):
                validate_capture_assessment(value, observations(), relation)

    def test_exact_fields_status_and_nonempty_explanations_are_required(self) -> None:
        bad = []
        value = assessment()
        value["field_checks"].pop()
        bad.append(value)
        for change in ({"field": "marking_target"}, {"status": "certain"},
                       {"status": []}, {"explanation": " \n"}):
            value = assessment()
            value["field_checks"][0].update(change)
            bad.append(value)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_capture_assessment(value, observations(), relations())

    def test_quality_requires_supported_codes_fields_boolean_and_explanation(self) -> None:
        for change in ({"code": "missing_wps"}, {"code": []}, {"affected_fields": ["wps_id"]},
                       {"affected_fields": []}, {"observation_ids": ["imagined"]},
                       {"viewpoint_change_may_help": 1}, {"explanation": ""}):
            value = unresolved_assessment()
            value["quality_evidence"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_capture_assessment(value, observations(), relations())

    def test_quality_prompt_excludes_capture_labels_and_document_payload(self) -> None:
        observation, relation = observations(), relations()
        observation.update(view="SECRET_VIEW", expected_text="SECRET_ANSWER", scene_id="SECRET_SCENE",
                           camera_pose="SECRET_POSE", phase="SECRET_PHASE", image_ref="SECRET_FILENAME")
        relation["relations"][0]["document_refs"] = ["SECRET_DOC_REFERENCE"]
        relation["document_evidence"] = ["SECRET_DOCUMENT"]
        prompt = capture_assessment_prompt(observation, relation)
        self.assertNotIn("SECRET_", prompt)
        self.assertTrue(prompt.startswith(CAPTURE_ASSESSMENT_PROMPT))
        self.assertIn("M-17", prompt)
        self.assertIn("plate joint", prompt)


class PipelineObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        document = self.root / "reference.md"
        document.write_text("# Symbols\n\nThe arrow identifies a joint.\n", encoding="utf-8")
        sources = self.root / "sources.json"
        sources.write_text(json.dumps({"sources": [
            {"id": "reference", "group": "documents", "relative_path": "reference.md",
             "sha256": sha256(document), "url": "https://example.com/reference", "media_type": "text/plain"}]}))
        self.index = build_index(self.root, sources)
        self.bundle = Bundle(self.root / "runs", "observer-test", {"test_fixture": True})
        self.frame = {"frame_id": "frame-001", "image_ref": "frames/frame-001.png", "width": 100, "height": 60,
                      "source_id": "SECRET_SOURCE", "view": "SECRET_VIEW", "expected_text": "SECRET_ANSWER",
                      "scene_id": "SECRET_SCENE", "camera_pose": "SECRET_POSE", "phase": "SECRET_PHASE"}
        # Engines are fakes; source pixel loading belongs to the real engines.
        (self.bundle.root / self.frame["image_ref"]).write_bytes(b"fixture for fake engines")
        self.calls, self.prompts = [], []
        self.visual_response = {"scene_summary": "marked plate", "quality_issues": [], "visual_objects": [
            {"observation_id": "joint", "kind": "joint", "bbox_1000": [400, 100, 500, 800],
             "description": "plate joint", "visible_text": None}]}
        self.responses = [self.visual_response, relations(), assessment()]

    def observer(self, bad_ocr: bool = False) -> PipelineObserver:
        test = self

        class OCR:
            def predict(self, image: Path) -> dict:
                test.calls.append("ocr")
                return {"rec_texts": ["M-17"], "rec_scores": [0.4],
                        "rec_polys": [] if bad_ocr else [[[10, 10], [30, 10], [30, 20], [10, 20]]]}

            def close(self) -> None:
                test.calls.append("ocr_closed")

        class VLM:
            def __init__(self) -> None:
                test.calls.append("vlm_loaded")
                self.ordinal = 0

            def generate(self, image: Path, prompt: str) -> str:
                test.calls.append("vlm")
                test.prompts.append(prompt)
                response = test.responses[self.ordinal]
                self.ordinal += 1
                self.last_generation = {"output_tokens": 123, "hit_token_limit": False}
                return json.dumps(response)

            def close(self) -> None:
                test.calls.append("vlm_closed")

        return PipelineObserver(OCR, VLM, self.index, self.root, ["reference"], "arrow joint")

    def test_real_pipeline_contract_and_engine_lifecycle_with_fake_engines(self) -> None:
        observation, relation, result = self.observer().observe(self.bundle, self.frame)
        self.assertEqual(self.calls, ["ocr", "ocr_closed", "vlm_loaded", "vlm", "vlm", "vlm", "vlm_closed"])
        self.assertEqual(self.prompts[0], OBSERVATION_PROMPT)
        self.assertNotIn("The arrow identifies a joint.", self.prompts[0])
        self.assertIn("The arrow identifies a joint.", self.prompts[1])
        self.assertNotIn("The arrow identifies a joint.", self.prompts[2])
        self.assertTrue(all("SECRET_" not in prompt for prompt in self.prompts))
        self.assertEqual(result["stage"], "capture_assessment")
        self.assertFalse(result["causal_glare_verified"])
        self.assertEqual(result["image_size"], {"width": 100, "height": 60})
        self.assertEqual(result["input_result_ids"], [observation["result_id"], relation["result_id"]])
        self.assertFalse((self.bundle.root / "results/frame-001-work_spec_candidate.json").exists())
        evidence = json.loads((self.bundle.root / "evidence/frame-001-retrieval.json").read_text())
        self.assertEqual(evidence["returned_evidence_ids"], evidence["used_evidence_ids"])
        self.assertEqual(evidence["cited_evidence_ids"], [])
        generation = json.loads((self.bundle.root / "results/frame-001-capture-assessment.generation.json").read_text())
        self.assertEqual(generation["output_tokens"], 123)
        self.assertTrue((self.bundle.root / result["raw_output_ref"]).is_file())

    def test_same_assessment_policy_is_used_for_each_frame(self) -> None:
        observer = self.observer()
        observer.observe(self.bundle, self.frame)
        other = {**self.frame, "frame_id": "frame-002", "view": "ANOTHER_SECRET_VIEW"}
        self.responses = [self.visual_response, {"relations": [], "unresolved": []}, unresolved_assessment()]
        observer.observe(self.bundle, other)
        self.assertEqual(self.prompts[0], self.prompts[3])
        self.assertTrue(self.prompts[2].startswith(CAPTURE_ASSESSMENT_PROMPT))
        self.assertTrue(self.prompts[5].startswith(CAPTURE_ASSESSMENT_PROMPT))
        self.assertTrue(all("SECRET_" not in prompt for prompt in self.prompts))

    def test_bad_assessment_keeps_raw_prompt_generation_and_closes_engine(self) -> None:
        self.responses[-1] = unresolved_assessment()
        self.responses[-1]["quality_evidence"][0]["code"] = "unknown"
        with self.assertRaises(ValueError):
            self.observer().observe(self.bundle, self.frame)
        self.assertEqual(self.calls[-1], "vlm_closed")
        self.assertTrue((self.bundle.root / "results/frame-001-relation.json").is_file())
        self.assertFalse((self.bundle.root / "results/frame-001-capture_assessment.json").exists())
        raw = json.loads((self.bundle.root / "results/frame-001-capture-assessment.raw.txt").read_text())
        self.assertEqual(raw["quality_evidence"][0]["code"], "unknown")
        for suffix in ("prompt.txt", "parsed.json", "generation.json"):
            self.assertTrue((self.bundle.root / f"results/frame-001-capture-assessment.{suffix}").is_file())
        self.assertEqual(self.calls.count("vlm"), 3)

    def test_bad_ocr_keeps_raw_and_releases_engine_before_any_vlm(self) -> None:
        with self.assertRaises(ValueError):
            self.observer(bad_ocr=True).observe(self.bundle, self.frame)
        self.assertEqual(self.calls, ["ocr", "ocr_closed"])
        self.assertTrue((self.bundle.root / "results/frame-001-ocr.raw.json").is_file())

    def test_bad_relation_keeps_provided_document_context_and_raw(self) -> None:
        self.responses[1] = deepcopy(relations())
        self.responses[1]["relations"][0]["document_refs"] = ["unknown-document"]
        with self.assertRaises(ValueError):
            self.observer().observe(self.bundle, self.frame)
        self.assertEqual(self.calls[-1], "vlm_closed")
        self.assertTrue((self.bundle.root / "results/frame-001-relation.raw.txt").is_file())
        retrieval = json.loads((self.bundle.root / "evidence/frame-001-retrieval.json").read_text())
        self.assertEqual(retrieval["returned_evidence_ids"], retrieval["used_evidence_ids"])
        self.assertNotIn("cited_evidence_ids", retrieval)
        self.assertFalse((self.bundle.root / "results/frame-001-relation.json").exists())


if __name__ == "__main__":
    unittest.main()
