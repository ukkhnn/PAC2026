"""작은 합성 PNG로 입력 보존·출처 검증 실패 경로를 확인한다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from contextweld.recapture_inputs import prepare_inputs, verify_inputs


class RecaptureInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp" if Path("/private/tmp").is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = self.root / "scene"
        (self.scene / "frames").mkdir(parents=True)
        self.destination = self.root / "packaged"
        self.write_json(self.scene / "manifest.json", {
            "scenario_id": "synthetic-test-fixture", "marking": {"answer": "NEVER_MODEL_INPUT"},
        })
        for index, view in enumerate(("A", "B")):
            capture = {
                "view": view, "scenario_id": "synthetic-test-fixture", "capture_mode": "pre_captured",
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
                capture[f"{kind}_image_sha256"] = self.digest(path)
            self.write_json(self.scene / f"frames/{view}-capture.json", capture)

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def change_capture(self, view: str, **changes: object) -> None:
        path = self.scene / f"frames/{view}-capture.json"
        value = json.loads(path.read_text())
        value.update(changes)
        self.write_json(path, value)

    def refresh_checksums(self) -> None:
        self.write_json(self.destination / "checksums.json", {
            path.relative_to(self.destination).as_posix(): self.digest(path)
            for path in self.destination.rglob("*") if path.is_file() and path.name != "checksums.json"
        })

    def test_roundtrip_preserves_bytes_and_excludes_scene_answers(self) -> None:
        originals = {p.relative_to(self.scene): p.read_bytes() for p in self.scene.rglob("*") if p.is_file()}
        result = prepare_inputs(self.scene, self.destination)
        self.assertEqual(result, self.destination / "inputs.json")
        inputs = verify_inputs(self.destination)
        self.assertEqual(inputs["inference_status"], "not_run")
        self.assertEqual(inputs["source_manifest_sha256"], self.digest(self.scene / "manifest.json"))
        self.assertEqual([f["view"] for f in inputs["frames"]], ["A", "B"])
        self.assertEqual(inputs["frames"][0]["width"], 8)
        self.assertEqual(inputs["frames"][1]["overview_height"], 8)
        self.assertNotIn("NEVER_MODEL_INPUT", result.read_text())
        for relative, data in originals.items():
            self.assertEqual((self.scene / relative).read_bytes(), data)
            if relative.name.endswith("capture.json"):
                self.assertEqual((self.destination / "provenance" / relative.name).read_bytes(), data)
            elif relative.suffix == ".png":
                self.assertEqual((self.destination / relative).read_bytes(), data)
        self.assertFalse(self.destination.with_name("packaged.incomplete").exists())

    def test_stream_is_never_read(self) -> None:
        (self.scene / "stream").symlink_to(self.root / "absent-stream", target_is_directory=True)
        prepare_inputs(self.scene, self.destination)
        verify_inputs(self.destination)

    def test_refuses_existing_destination_or_incomplete_output(self) -> None:
        self.destination.mkdir()
        (self.destination / "keep").write_text("preserve")
        with self.assertRaises(FileExistsError):
            prepare_inputs(self.scene, self.destination)
        self.assertEqual((self.destination / "keep").read_text(), "preserve")
        other = self.root / "other"
        other.with_name("other.incomplete").mkdir()
        with self.assertRaises(FileExistsError):
            prepare_inputs(self.scene, other)

    def test_refuses_source_output_nesting(self) -> None:
        for target in (self.scene / "new", self.scene, self.root):
            with self.subTest(target=target), self.assertRaises(ValueError):
                prepare_inputs(self.scene, target)

    def test_rejects_noncanonical_reference_and_source_image_mutation(self) -> None:
        for bad in ("stream/wrist.png", "../outside.png", "/absolute.png", "frames/../A.png"):
            self.change_capture("A", wrist_saved_image=bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                prepare_inputs(self.scene, self.destination)
        self.change_capture("A", wrist_saved_image="frames/A-wrist.png")
        with (self.scene / "frames/A-wrist.png").open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            prepare_inputs(self.scene, self.destination)

    def test_rejects_source_and_destination_symlinks(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.scene, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare_inputs(alias, self.destination)
        with self.assertRaises(ValueError):
            prepare_inputs(self.scene, alias / "nested")
        image_path = self.scene / "frames/A-wrist.png"
        real_image = self.root / "image.png"
        image_path.rename(real_image)
        image_path.symlink_to(real_image)
        with self.assertRaises(ValueError):
            prepare_inputs(self.scene, self.destination)

    def test_rejects_missing_metadata_and_invalid_timestamps(self) -> None:
        capture_path = self.scene / "frames/A-capture.json"
        original = capture_path.read_bytes()
        for changes in ({"captured_at_utc": "2026-10-10T00:00:00"},
                        {"captured_at_utc": "2026-10-10T00:00:00+09:00"},
                        {"camera_world_position": [1, 2]}, {"camera_prim_path": None},
                        {"camera_world_quaternion_wxyz": [0, 0, 0, 0]}):
            capture_path.write_bytes(original)
            self.change_capture("A", **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_inputs(self.scene, self.destination)

    def test_rejects_identical_images_even_with_matching_hashes(self) -> None:
        (self.scene / "frames/B-wrist.png").write_bytes((self.scene / "frames/A-wrist.png").read_bytes())
        self.change_capture("B", wrist_image_sha256=self.digest(self.scene / "frames/B-wrist.png"))
        with self.assertRaisesRegex(ValueError, "must differ"):
            prepare_inputs(self.scene, self.destination)

    def test_verify_rejects_tampering_missing_extra_and_symlink_files(self) -> None:
        prepare_inputs(self.scene, self.destination)
        image = self.destination / "frames/A-wrist.png"
        original = image.read_bytes()
        image.write_bytes(b"broken")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            verify_inputs(self.destination)
        image.write_bytes(original)
        image.unlink()
        with self.assertRaisesRegex(ValueError, "list mismatch"):
            verify_inputs(self.destination)
        image.write_bytes(original)
        extra = self.destination / "extra.txt"
        extra.write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "list mismatch"):
            verify_inputs(self.destination)
        extra.unlink()
        image.unlink()
        image.symlink_to(self.scene / "frames/A-wrist.png")
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_inputs(self.destination)

    def test_verify_checks_metadata_against_raw_provenance(self) -> None:
        prepare_inputs(self.scene, self.destination)
        path = self.destination / "inputs.json"
        inputs = json.loads(path.read_text())
        inputs["frames"][0]["width"] = 999
        self.write_json(path, inputs)
        self.refresh_checksums()
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            verify_inputs(self.destination)

    def test_failed_copy_keeps_incomplete_and_never_publishes_destination(self) -> None:
        with patch("contextweld.recapture_inputs.verify_inputs", side_effect=ValueError("fixture failure")):
            with self.assertRaisesRegex(ValueError, "fixture failure"):
                prepare_inputs(self.scene, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.destination.with_name("packaged.incomplete").is_dir())
        with self.assertRaises(FileExistsError):
            prepare_inputs(self.scene, self.destination)


if __name__ == "__main__":
    unittest.main()
