"""재촬영 브릿지: requires_recapture 예외가 루프를 기록 단계로 연결하되 판독 결정을 대체하지 않는지 검사한다."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image

from contextweld.recognition import sha256
from contextweld.recapture_inputs import prepare_inputs
from contextweld.recapture_loop import verify_recapture_bundle
from contextweld.weld_pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


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


def observed_assessment() -> dict:
    return {"field_checks": [
        {"field": "marking_text", "status": "observed", "observation_ids": ["frame-001-ocr-001"],
         "relation_ids": [], "explanation": "The OCR records the marking."},
        {"field": "marking_target", "status": "observed", "observation_ids": ["frame-001-vlm-joint"],
         "relation_ids": ["r1"], "explanation": "The relation selects the visible joint."}],
        "quality_evidence": []}


def unresolved_assessment(viewpoint_change_may_help: bool) -> dict:
    return {"field_checks": [
        {"field": field, "status": "unresolved", "observation_ids": [], "relation_ids": [],
         "explanation": "The required information is not visible."}
        for field in ("marking_text", "marking_target")],
        "quality_evidence": [{"code": "unreadable", "affected_fields": ["marking_text"],
                              "observation_ids": [], "explanation": "Bright region has no legible text.",
                              "viewpoint_change_may_help": viewpoint_change_may_help}]}


class FakeObserver:
    """실제 엔진 대신 result 기록과 일관된 (관측, 관계, 판단)을 프레임 순서대로 되돌린다."""

    def __init__(self, assessments: list) -> None:
        self.assessments = assessments
        self.calls: list[str] = []

    def observe(self, bundle, frame) -> tuple[dict, dict, dict]:
        self.calls.append(frame["frame_id"])
        assessment = self.assessments[min(len(self.calls) - 1, len(self.assessments) - 1)]()
        observation = bundle.result("observation", frame["frame_id"], deepcopy(observations()), producer="model")
        relation = bundle.result("relation", frame["frame_id"], deepcopy(relations()), producer="model",
                                 input_ids=[observation["result_id"]])
        assessed = bundle.result("capture_assessment", frame["frame_id"], assessment, producer="model",
                                 input_ids=[observation["result_id"], relation["result_id"]])
        return observation, relation, assessed


class BrokenObserver:
    def observe(self, bundle, frame) -> tuple[dict, dict, dict]:
        raise ValueError("fixture engine failure")


class RecaptureBridgeTests(unittest.TestCase):
    """합성 A/B 입력으로 브릿지 연결·보존·회귀 경로를 확인한다."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="recapture-bridge-test-", dir="/private/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.scene = self.tmp / "scene"
        (self.scene / "frames").mkdir(parents=True)
        (self.scene / "manifest.json").write_text(json.dumps(
            {"scenario_id": "synthetic-bridge-fixture", "marking": {"answer": "NEVER_MODEL_INPUT"}}))
        for index, view in enumerate(("A", "B")):
            capture = {
                "view": view, "scenario_id": "synthetic-bridge-fixture", "capture_mode": "pre_captured",
                "recognition_feedback_enabled": False,
                "captured_at_utc": f"2026-10-10T00:00:0{index}Z",
                "capture_time_semantics": "synthetic test fixture timestamp; not a model result",
                "camera_prim_path": "/Fixture/Camera",
                "camera_world_position": [index, 0, 1],
                "camera_world_quaternion_wxyz": [1, 0, 0, 0],
                "camera_pose_convention": "ros_optical", "world_frame_convention": "usd_z_up",
                "camera_pose_source": "synthetic test fixture",
            }
            for kind, size in (("wrist", (8, 6)), ("overview", (12, 8))):
                relative = f"frames/{view}-{kind}.png"
                path = self.scene / relative
                Image.new("RGB", size, (70 + index * 80, 10, 20)).save(path)
                capture[f"{kind}_saved_image"] = relative
                capture[f"{kind}_image"] = f"stream/{kind}.png"
                capture[f"{kind}_image_sha256"] = sha256(path)
            (self.scene / f"frames/{view}-capture.json").write_text(json.dumps(capture))
        self.inputs = self.tmp / "recapture-inputs"
        prepare_inputs(self.scene, self.inputs)
        self.wrist_a_sha256 = sha256(self.scene / "frames/A-wrist.png")
        self.data_root = ROOT / "data/raw/demo-bootstrap-v1"
        self.index = ROOT / "output/document-rag/server-v1/index.json"

    def make_capture_source(self, image_sha256: str) -> Path:
        src = self.tmp / "source"
        src.mkdir()
        capture = {"schema_version": "marking-capture.v1", "run_id": "test-source-01",
                   "started_at_utc": "2026-10-15T00:00:00Z", "source_kind": "model",
                   "capture_mode": "pre_captured", "physical_movement_triggered": False,
                   "frames": [{"frame_id": "frame-B", "image_sha256": image_sha256,
                               "readout": {"markings": [], "relations": [],
                                           "quality": {"requires_recapture": True}}}],
                   "model_calls": 3}
        (src / "capture.json").write_text(json.dumps(capture))
        return src

    def run_with(self, observer, output: str) -> Path:
        return run_pipeline(repo=ROOT, output=self.tmp / output, source=self.make_capture_source(self.wrist_a_sha256),
                            source_kind="capture", data_root=self.data_root, index_path=self.index,
                            recapture={"inputs_root": self.inputs, "output_root": self.tmp / "loop-out",
                                       "run_id": "test-loop-01", "observer": observer, "config": {}})

    def assert_checksums_cover_every_file(self, bundle: Path) -> None:
        sums = json.loads((bundle / "checksums.json").read_text())
        actual = {str(p.relative_to(bundle)) for p in bundle.rglob("*")
                  if p.is_file() and p != bundle / "checksums.json"}
        self.assertEqual(set(sums), actual)
        for name, digest in sums.items():
            self.assertEqual(sha256(bundle / name), digest)

    def test_recapture_loop_runs_and_bundle_is_preserved(self) -> None:
        observer = FakeObserver([lambda: unresolved_assessment(True), observed_assessment])
        bundle = self.run_with(observer, "run_bridge")
        self.assertEqual(observer.calls, ["frame-A", "frame-B"])
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual((manifest["run_outcome"], manifest["delivery_status"]), ("needs_review", "blocked"))
        self.assertEqual(manifest["recapture_bundle_ref"], "inputs/recapture-bundle")
        self.assertEqual(manifest["recapture_run_id"], "test-loop-01")
        self.assertEqual(manifest["recapture_outcome"], "resolved")
        self.assertEqual(manifest["recapture_visual_outcome"], "ready_for_document_review")
        error = json.loads((bundle / "results/error.json").read_text())
        self.assertIn("재관측 뒤에도 판독 미확정", error["message"])
        self.assertIn("재촬영 루프 기록", error["message"])
        self.assertFalse((bundle / "inputs/recapture-bundle/results/error.json").exists())
        # 루프 판정은 판독 결정을 대체하지 않는다: 전달 없이 blocked 유지.
        self.assertEqual(list((bundle / "commands").iterdir()), [])
        self.assert_checksums_cover_every_file(bundle)
        self.assertEqual(verify_recapture_bundle(bundle / "inputs/recapture-bundle")["run_outcome"], "needs_review")

    def test_needs_review_loop_keeps_blocked_and_records_bundle(self) -> None:
        observer = FakeObserver([lambda: unresolved_assessment(False)])
        bundle = self.run_with(observer, "run_needs_review")
        self.assertEqual(observer.calls, ["frame-A"])
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual((manifest["run_outcome"], manifest["delivery_status"]), ("needs_review", "blocked"))
        self.assertEqual(manifest["recapture_outcome"], "not_requested")
        self.assertEqual(manifest["recapture_visual_outcome"], "needs_review")
        self.assertEqual(manifest["recapture_bundle_ref"], "inputs/recapture-bundle")
        self.assertFalse((bundle / "inputs/recapture-bundle/requests/recapture-01.json").exists())

    def test_loop_technical_failure_preserves_both_bundles(self) -> None:
        bundle = self.run_with(BrokenObserver(), "run_loop_failed")
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual(manifest["recapture_outcome"], "failed")
        self.assertEqual(manifest["recapture_visual_outcome"], "failed")
        self.assertIn("재촬영 루프 기록", json.loads((bundle / "results/error.json").read_text())["message"])
        loop_error = json.loads((bundle / "inputs/recapture-bundle/results/error.json").read_text())
        self.assertEqual(loop_error["message"], "fixture engine failure")
        self.assertEqual(verify_recapture_bundle(bundle / "inputs/recapture-bundle")["run_outcome"], "failed")

    def test_without_recapture_inputs_keeps_original_exception(self) -> None:
        bundle = run_pipeline(repo=ROOT, output=self.tmp / "run_no_recapture",
                              source=self.make_capture_source(self.wrist_a_sha256), source_kind="capture",
                              data_root=self.data_root, index_path=self.index)
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertNotIn("recapture_bundle_ref", manifest)
        self.assertFalse((bundle / "inputs/recapture-bundle").exists())
        message = json.loads((bundle / "results/error.json").read_text())["message"]
        self.assertEqual(message, "재관측 뒤에도 판독 미확정")

    def test_frame_hash_mismatch_is_rejected_without_loop(self) -> None:
        bundle = run_pipeline(repo=ROOT, output=self.tmp / "run_mismatch",
                              source=self.make_capture_source("b" * 64), source_kind="capture",
                              data_root=self.data_root, index_path=self.index,
                              recapture={"inputs_root": self.inputs, "output_root": self.tmp / "loop-out",
                                         "run_id": "test-loop-01", "observer": FakeObserver([observed_assessment]),
                                         "config": {}})
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertNotIn("recapture_bundle_ref", manifest)
        self.assertFalse((bundle / "inputs/recapture-bundle").exists())
        self.assertEqual(json.loads((bundle / "results/error.json").read_text())["message"],
                         "재촬영 입력이 촬영 프레임과 일치하지 않음")

    def test_extended_bundle_checksums_cover_recapture_files(self) -> None:
        observer = FakeObserver([lambda: unresolved_assessment(True), observed_assessment])
        bundle = self.run_with(observer, "run_checksums")
        sums = json.loads((bundle / "checksums.json").read_text())
        recapture_refs = [name for name in sums if name.startswith("inputs/recapture-bundle/")]
        self.assertIn("inputs/recapture-bundle/manifest.json", recapture_refs)
        self.assertIn("inputs/recapture-bundle/checksums.json", recapture_refs)
        self.assert_checksums_cover_every_file(bundle)


if __name__ == "__main__":
    unittest.main()
