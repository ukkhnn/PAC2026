"""가짜 관측으로 제어 흐름·불변 기록만 검증하며 모델 성능을 평가하지 않는다."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from contextweld.recapture_inputs import prepare_inputs
from contextweld.recapture_loop import decide_recapture, run_recapture_loop, verify_recapture_bundle
from contextweld.recognition import sha256, write_json


class FixtureObserver:
    """실제 모델을 호출하지 않는 분기·기록용 fixture."""

    def __init__(self, states: list[str], *, fail: bool = False) -> None:
        self.states, self.fail, self.seen = states, fail, []

    def observe(self, bundle, frame: dict) -> tuple[dict, dict, dict]:
        fid = frame["frame_id"]
        self.seen.append(fid)
        raw = f"results/{fid}-fixture.raw.json"
        write_json(bundle.root / raw, {"evidence_kind": "test_fixture", "frame": fid})
        if self.fail:
            raise TimeoutError("fixture inference timeout")
        state = self.states[len(self.seen) - 1]
        text_id, target_id, relation_id = f"{fid}-text", f"{fid}-plate", f"{fid}-relation-1"
        observation = bundle.result("observation", fid, {
            "text_observations": [{"observation_id": text_id, "raw_text": "fixture marking"}],
            "visual_objects": [{"observation_id": target_id, "kind": "member", "visible_text": None}],
            "scene_summary": "test fixture only", "quality_issues": []}, raw_ref=raw)
        relation = bundle.result("relation", fid, {"relations": [{
            "relation_id": relation_id, "source_observation_ids": [text_id],
            "target_observation_candidates": [target_id], "selected_target_observation_id": target_id,
            "document_refs": [], "interpretation": "fixture", "reason_codes": []}], "unresolved": []},
            input_ids=[observation["result_id"]], raw_ref=raw)
        observed = state in {"observed", "missing_work_order"}
        quality = [{"code": "unreadable", "affected_fields": ["marking_text"],
                    "observation_ids": [text_id], "explanation": "fixture visible obstruction",
                    "viewpoint_change_may_help": True}] if state in {"retry", "observed"} else []
        assessment = bundle.result("capture_assessment", fid, {
            "field_checks": [
                {"field": "marking_text", "status": "observed" if observed else "unresolved",
                 "observation_ids": [text_id], "relation_ids": [], "explanation": f"fixture {state}"},
                {"field": "marking_target", "status": "observed", "observation_ids": [target_id],
                 "relation_ids": [relation_id], "explanation": "fixture target recorded"}],
            "quality_evidence": quality},
            input_ids=[observation["result_id"], relation["result_id"]], raw_ref=raw)
        return observation, relation, assessment


class RecaptureLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        scene = self.root / "scene"
        (scene / "frames").mkdir(parents=True)
        write_json(scene / "manifest.json", {"scenario_id": "fixture-scene"})
        for index, view in enumerate(("A", "B")):
            capture = {"view": view, "scenario_id": "fixture-scene", "capture_mode": "pre_captured",
                       "recognition_feedback_enabled": False, "captured_at_utc": f"2026-10-10T00:00:0{index}Z",
                       "capture_time_semantics": "fixture_sensor_time", "camera_prim_path": "/World/camera",
                       "camera_world_position": [index, 0, 1], "camera_world_quaternion_wxyz": [1, 0, 0, 0],
                       "camera_pose_convention": "wxyz", "world_frame_convention": "right-handed metres",
                       "camera_pose_source": "test_fixture"}
            for kind in ("wrist", "overview"):
                ref = f"frames/{view}-{kind}.png"
                Image.new("RGB", (8, 6), color=(index * 150, 40, 80)).save(scene / ref)
                capture[f"{kind}_saved_image"] = ref
                capture[f"{kind}_image_sha256"] = sha256(scene / ref)
            write_json(scene / f"frames/{view}-capture.json", capture)
        self.inputs = prepare_inputs(scene, self.root / "inputs").parent
        self.outputs = self.root / "runs"
        self.original_hashes = self.hashes(self.inputs)

    @staticmethod
    def hashes(root: Path) -> dict[str, str]:
        return {str(path.relative_to(root)): sha256(path) for path in root.rglob("*") if path.is_file()}

    @staticmethod
    def read(root: Path, ref: str = "manifest.json"):
        return json.loads((root / ref).read_text())

    @staticmethod
    def rehash(root: Path) -> None:
        manifest = RecaptureLoopTests.read(root)
        write_json(root / "checksums.json", {ref: sha256(root / ref) for ref in manifest["files"]})

    @staticmethod
    def events(root: Path) -> list[dict]:
        return [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]

    @staticmethod
    def write_events(root: Path, events: list[dict]) -> None:
        (root / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))

    def run_fixture(self, states: list[str], *, run_id: str = "fixture", fail: bool = False):
        observer = FixtureObserver(states, fail=fail)
        bundle = run_recapture_loop(inputs_root=self.inputs, output_root=self.outputs, run_id=run_id,
                                    observer=observer, config={"evidence_kind": "test_fixture"})
        return bundle, observer

    def test_observed_a_does_not_infer_b_despite_quality_issue(self) -> None:
        bundle, observer = self.run_fixture(["observed"])
        manifest = verify_recapture_bundle(bundle)
        self.assertEqual(observer.seen, ["frame-A"])
        self.assertEqual(manifest["visual_outcome"], "ready_for_document_review")
        self.assertEqual(manifest["recapture_outcome"], "not_requested")
        self.assertEqual(manifest["run_outcome"], "needs_review")
        self.assertEqual(manifest["request_refs"], [])
        self.assertFalse(any("movement" in event["type"] for event in self.events(bundle)))

    def test_observation_problem_requests_once_and_rechecks_b(self) -> None:
        bundle, observer = self.run_fixture(["retry", "observed"])
        manifest = verify_recapture_bundle(bundle)
        self.assertEqual(observer.seen, ["frame-A", "frame-B"])
        self.assertEqual(manifest["recapture_outcome"], "resolved")
        self.assertEqual(len(manifest["request_refs"]), 1)
        request = self.read(bundle, manifest["request_refs"][0])
        self.assertEqual(request["affected_fields"], ["marking_text"])
        self.assertFalse(request["physical_movement_triggered"])
        events = self.events(bundle)
        requested = next(event for event in events if event["type"] == "recapture_requested")
        ingested = next(event for event in events if event["stage"] == "frame_ingest"
                        and event["input_frame_ids"] == ["frame-B"])
        self.assertIn(requested["event_id"], ingested["parent_event_ids"])
        self.assertEqual(ingested["request_id"], request["request_id"])
        frame_b = manifest["frames"][1]
        self.assertEqual(frame_b["captured_at_utc"], "2026-10-10T00:00:01Z")
        self.assertNotEqual(frame_b["captured_at_utc"], frame_b["ingested_at_utc"])
        self.assertEqual(frame_b["request_link_semantics"], "saved_frame_selection")

    def test_b_still_unresolved_stops_without_second_request(self) -> None:
        bundle, observer = self.run_fixture(["retry", "retry"])
        manifest = verify_recapture_bundle(bundle)
        self.assertEqual(observer.seen, ["frame-A", "frame-B"])
        self.assertEqual(manifest["visual_outcome"], "needs_review")
        self.assertEqual(manifest["recapture_outcome"], "unresolved")
        self.assertEqual(len(manifest["request_refs"]), 1)
        decision = self.read(bundle, "results/frame-B-recognition_decision.json")
        self.assertEqual(decision["reason_codes"], ["recapture_limit_reached"])
        self.assertEqual(manifest["delivery_status"], "not_requested")

    def test_semantic_or_document_uncertainty_without_visual_remedy_stays_review(self) -> None:
        for state in ("semantic_uncertainty", "missing_work_order"):
            with self.subTest(state=state):
                bundle, observer = self.run_fixture([state], run_id=state)
                manifest = verify_recapture_bundle(bundle)
                self.assertEqual(observer.seen, ["frame-A"])
                self.assertEqual(manifest["request_refs"], [])
                expected = "ready_for_document_review" if state == "missing_work_order" else "needs_review"
                self.assertEqual(manifest["visual_outcome"], expected)
                self.assertEqual(manifest["run_outcome"], "needs_review")

    def test_technical_failure_exports_error_and_preserves_raw_output(self) -> None:
        bundle, observer = self.run_fixture([], fail=True)
        manifest = verify_recapture_bundle(bundle)
        self.assertEqual(observer.seen, ["frame-A"])
        self.assertEqual(manifest["run_outcome"], "failed")
        self.assertEqual(manifest["export_status"], "complete")
        self.assertEqual(self.read(bundle, "results/error.json")["error_type"], "TimeoutError")
        self.assertEqual(self.read(bundle, "results/frame-A-fixture.raw.json")["evidence_kind"], "test_fixture")
        self.assertEqual(self.hashes(self.inputs), self.original_hashes)

    def test_inputs_and_completed_bundle_are_immutable_and_run_id_cannot_repeat(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        original = self.hashes(bundle)
        first_events = self.events(bundle)
        for _ in range(2):
            verify_recapture_bundle(bundle)
            self.assertEqual(self.events(bundle), first_events)
        with self.assertRaises(FileExistsError):
            self.run_fixture(["observed"])
        self.assertEqual(self.hashes(self.inputs), self.original_hashes)
        self.assertEqual(self.hashes(bundle), original)
        self.assertFalse(bundle.with_name(bundle.name + ".incomplete").exists())

    def test_changed_bytes_fail_hash_verification(self) -> None:
        bundle, _ = self.run_fixture(["observed"])
        (bundle / "results/frame-A-fixture.raw.json").write_text("tampered")
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_path_escape_is_rejected_even_after_rehash(self) -> None:
        bundle, _ = self.run_fixture(["observed"])
        result_ref = "results/frame-A-observation.json"
        result = self.read(bundle, result_ref)
        result["raw_output_ref"] = "../outside.json"
        write_json(bundle / result_ref, result)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_future_b_reference_is_rejected_even_after_rehash(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        events = self.events(bundle)
        events[1]["input_frame_ids"].append("frame-B")
        self.write_events(bundle, events)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_missing_request_parent_is_rejected_even_after_rehash(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        events = self.events(bundle)
        event = next(event for event in events if event["stage"] == "frame_ingest"
                     and event["input_frame_ids"] == ["frame-B"])
        event["parent_event_ids"] = []
        self.write_events(bundle, events)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_forged_decision_is_rejected_even_after_rehash(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        ref = "results/frame-A-recognition_decision.json"
        result = self.read(bundle, ref)
        result["affected_fields"] = ["marking_target"]
        write_json(bundle / ref, result)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_forged_request_source_or_scope_is_rejected_even_after_rehash(self) -> None:
        mutations = {"run_id": "another-run", "source_frame_ids": ["frame-B"],
                     "source_result_ids": ["unknown-result"], "reason_codes": ["invented-reason"],
                     "affected_fields": ["marking_target"], "capture_mode": "live_closed_loop"}
        for index, (key, value) in enumerate(mutations.items()):
            with self.subTest(key=key):
                bundle, _ = self.run_fixture(["retry", "observed"], run_id=f"request-{index}")
                ref = "requests/recapture-01.json"
                request = self.read(bundle, ref)
                request[key] = value
                write_json(bundle / ref, request)
                self.rehash(bundle)
                with self.assertRaises(ValueError):
                    verify_recapture_bundle(bundle)

    def test_request_inventory_must_reference_recorded_request(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        manifest = self.read(bundle)
        manifest["request_refs"] = ["results/inference-config.json"]
        write_json(bundle / "manifest.json", manifest)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_result_id_and_event_identity_tampering_is_rejected(self) -> None:
        for index, mutation in enumerate(({"result_id": "invented"}, {"run_id": "invented"},
                                          {"stage": "invented"}, {"producer": "user"},
                                          {"schema_version": "invented.v9"})):
            with self.subTest(mutation=mutation):
                bundle, _ = self.run_fixture(["observed"], run_id=f"identity-{index}")
                ref = "results/frame-A-observation.json"
                result = self.read(bundle, ref)
                result.update(mutation)
                write_json(bundle / ref, result)
                self.rehash(bundle)
                with self.assertRaises(ValueError):
                    verify_recapture_bundle(bundle)

    def test_capture_metadata_cannot_disagree_with_immutable_inputs(self) -> None:
        for index, mutation in enumerate(({"captured_at_utc": "2099-01-01T00:00:00Z"},
                                          {"camera_pose": {"position": [9, 9, 9]}})):
            with self.subTest(mutation=mutation):
                bundle, _ = self.run_fixture(["observed"], run_id=f"capture-{index}")
                manifest = self.read(bundle)
                manifest["frames"][0].update(mutation)
                write_json(bundle / "manifest.json", manifest)
                write_json(bundle / "frames/frame-A.json", manifest["frames"][0])
                self.rehash(bundle)
                with self.assertRaises(ValueError):
                    verify_recapture_bundle(bundle)

    def test_duplicate_manifest_frame_is_rejected(self) -> None:
        bundle, _ = self.run_fixture(["observed"])
        manifest = self.read(bundle)
        manifest["frames"].append(deepcopy(manifest["frames"][0]))
        write_json(bundle / "manifest.json", manifest)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_b_assessment_cannot_reuse_a_observations_as_b_evidence(self) -> None:
        bundle, _ = self.run_fixture(["retry", "observed"])
        ref = "results/frame-B-capture_assessment.json"
        result = self.read(bundle, ref)
        result["input_result_ids"] = ["frame-A-observation", "frame-A-relation"]
        for check in result["field_checks"]:
            check["observation_ids"] = [identifier.replace("frame-B", "frame-A")
                                        for identifier in check["observation_ids"]]
            check["relation_ids"] = [identifier.replace("frame-B", "frame-A")
                                     for identifier in check["relation_ids"]]
        for quality in result["quality_evidence"]:
            quality["observation_ids"] = [identifier.replace("frame-B", "frame-A")
                                          for identifier in quality["observation_ids"]]
        write_json(bundle / ref, result)
        events = self.events(bundle)
        event = next(event for event in events if event["payload_ref"] == ref)
        event["input_result_ids"] = result["input_result_ids"]
        event["parent_event_ids"] = [item["event_id"] for item in events
                                     if item["payload_ref"] in {
                                         "results/frame-A-observation.json", "results/frame-A-relation.json",
                                         "frames/frame-B.json"}]
        self.write_events(bundle, events)
        self.rehash(bundle)
        with self.assertRaises(ValueError):
            verify_recapture_bundle(bundle)

    def test_manifest_cannot_claim_delivery_authority_or_live_recognition(self) -> None:
        mutations = {"application_authorized": True, "delivery_requested": True,
                     "recognition_feedback_enabled": True, "saved_frame_selection_enabled": False,
                     "run_kind": "scenario"}
        for index, (key, value) in enumerate(mutations.items()):
            with self.subTest(key=key):
                bundle, _ = self.run_fixture(["observed"], run_id=f"scope-{index}")
                manifest = self.read(bundle)
                manifest[key] = value
                write_json(bundle / "manifest.json", manifest)
                self.rehash(bundle)
                with self.assertRaises(ValueError):
                    verify_recapture_bundle(bundle)

    def test_decision_rejects_unsupported_quality_codes_and_retry_limit(self) -> None:
        assessment = {"field_checks": [{"field": field, "status": "unresolved"}
                                      for field in ("marking_text", "marking_target")],
                      "quality_evidence": [{"code": "missing_wps", "affected_fields": ["marking_text"],
                                            "viewpoint_change_may_help": True}]}
        with self.assertRaises(ValueError):
            decide_recapture(assessment, 0)
        assessment["quality_evidence"] = []
        with self.assertRaises(ValueError):
            decide_recapture(assessment, 2)


if __name__ == "__main__":
    unittest.main()
