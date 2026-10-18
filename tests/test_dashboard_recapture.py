"""재촬영 루프 묶음(recapture-bundle.v1)을 대시보드 화면 모델로 읽는 어댑터·검증 연결 검사.

fixture 묶음은 실제 모델을 호출하지 않고 분기·기록만 만든다(``test_recapture_loop.FixtureObserver``).
화면 모델의 모든 저장 값을 원본 파일에서 다시 읽어 같은지 대조한다(``assert_linkage``).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

import admin_dashboard_support as support
from contextweld.recapture_inputs import prepare_inputs
from contextweld.recapture_loop import run_recapture_loop, verify_recapture_bundle
from contextweld.recognition import sha256, write_json
from contextweld_dashboard import integrity
from contextweld_dashboard.adapters import build_model
from contextweld_dashboard.bundle_io import BundleReader
from contextweld_dashboard.catalog import Source
from contextweld_dashboard.model import SCHEMA_RUN
from test_recapture_loop import FixtureObserver


def _make_bundle(root: Path, states: list[str], run_id: str, *, fail: bool = False) -> Path:
    """A/B 저장 장면을 불변 입력으로 준비하고, fixture 관측으로 재촬영 루프 묶음을 만든다."""
    scene = root / "scene"
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
    inputs_root = prepare_inputs(scene, root / "inputs").parent
    observer = FixtureObserver(states, fail=fail)
    return run_recapture_loop(inputs_root=inputs_root, output_root=root / "runs", run_id=run_id,
                              observer=observer, config={"evidence_kind": "test_fixture"})


class RecaptureDashboardTests(unittest.TestCase):
    def build(self, states: list[str], *, run_id: str = "recapture-fixture", fail: bool = False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        bundle = _make_bundle(root, states, run_id, fail=fail)
        verify_recapture_bundle(bundle)  # fixture가 유효한지 먼저 확인
        source = Source("added-recapture", bundle, str(bundle), "recapture", "recapture")
        check = integrity.inspect(bundle)
        self.assertEqual(check["state"], "verified", check.get("message"))
        ctx = support.context_for([source])
        reader = BundleReader(bundle, source.key)
        model = build_model(source, reader, check, ctx)
        run = {"schema": SCHEMA_RUN, "key": source.key, "summary": model["summary"], "integrity": check,
               "files": [], "steps": model["steps"], "tabs": model["tabs"], "roots": {source.key: str(bundle)}}
        return run, {source.key: bundle}

    def test_observed_a_renders_continue_without_request(self) -> None:
        run, roots = self.build(["observed"])
        support.assert_valid(self, run)
        support.assert_linkage(self, run, roots)
        self.assertEqual(run["summary"]["flags"][0]["value"]["v"], "ready_for_document_review")  # visual_outcome
        self.assertEqual(run["summary"]["flags"][1]["value"]["v"], "not_requested")  # recapture_outcome
        self.assertEqual(run["tabs"]["recapture"]["availability"], "available")
        self.assertEqual(run["tabs"]["delivery"]["availability"], "absent")
        # B는 입력 패키지에 있지만 요청이 없어 미사용: 저장 자료 미리보기로 구분된다.
        text = support.all_text(run)
        self.assertIn("미사용", text)
        self.assertNotIn("recapture-01", text)

    def test_request_then_b_recheck_renders_request_and_difference(self) -> None:
        run, roots = self.build(["retry", "observed"], run_id="recapture-requested")
        support.assert_valid(self, run)
        support.assert_linkage(self, run, roots)
        self.assertEqual(run["summary"]["flags"][1]["value"]["v"], "resolved")  # recapture_outcome
        recapture_blocks = support.blocks_of(run, "recapture")
        self.assertTrue(any(blk.get("id", "").startswith("req-") for blk in recapture_blocks),
                        "재촬영 요청 원문 블록이 있어야 한다")
        wrist = next((blk for blk in support.blocks_of(run, "capture") if blk.get("id") == "pair-wrist"), None)
        self.assertIsNotNone(wrist)
        self.assertEqual([item["label"].split(" · ")[0] for item in wrist["items"]], ["frame-A", "frame-B"])

    def test_failed_run_renders_without_decision(self) -> None:
        run, roots = self.build([], run_id="recapture-failed", fail=True)
        support.assert_valid(self, run)
        support.assert_linkage(self, run, roots)
        self.assertEqual(run["summary"]["flags"][0]["value"]["v"], "failed")  # visual_outcome
        self.assertEqual(run["tabs"]["recapture"]["availability"], "absent")
        self.assertEqual(run["tabs"]["delivery"]["availability"], "absent")


if __name__ == "__main__":
    unittest.main()
