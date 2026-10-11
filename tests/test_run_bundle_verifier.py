"""해시가 재작성된 묶음에서도 단계와 프레임 참조 손상을 찾는다."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from contextweld.recognition import Bundle, sha256, write_json

spec = importlib.util.spec_from_file_location("bundle_verifier", Path(__file__).resolve().parents[1] / "scripts/verify/verify_run_bundle.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BundleVerifierTests(unittest.TestCase):
    def build(self, directory: Path) -> Path:
        bundle = Bundle(directory, "test", {})
        for frame_id in ("frame-001", "frame-002"):
            image_ref = f"frames/{frame_id}.jpg"
            (bundle.root / image_ref).write_bytes(b"test fixture, not a model input")
            bundle.manifest["frames"].append({"frame_id": frame_id, "image_ref": image_ref,
                                               "sha256": sha256(bundle.root / image_ref)})
            raw_ref = f"results/{frame_id}.raw.txt"
            (bundle.root / raw_ref).write_text("fixture model output")
            ocr = bundle.result("ocr", frame_id, {"text_observations": []}, raw_ref=raw_ref)
            obs = bundle.result("observation", frame_id, {"text_observations": [], "visual_objects": []},
                                input_ids=[ocr["result_id"]], raw_ref=raw_ref)
            evidence_ref = f"evidence/{frame_id}.json"
            write_json(bundle.root / evidence_ref, {"hits": [], "used_evidence_ids": [], "cited_evidence_ids": []})
            relation = bundle.result("relation", frame_id, {"relations": [], "evidence_ref": evidence_ref},
                                     input_ids=[obs["result_id"]], raw_ref=raw_ref)
            bundle.result("work_spec_candidate", frame_id, {"execution_authorized": False},
                          input_ids=[relation["result_id"]], producer="rule")
            bundle.result("recognition_decision", frame_id, {"action": "needs_review"},
                          input_ids=[relation["result_id"]], producer="rule")
        return bundle.finish()

    def rehash(self, root: Path) -> None:
        checks = {str(p.relative_to(root)): sha256(p) for p in root.rglob("*")
                  if p.is_file() and p.name != "checksums.json"}
        write_json(root / "checksums.json", checks)

    def test_valid_graph_and_byte_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.build(Path(temp))
            self.assertEqual(module.inspect_bundle(root)["frames"], 2)
            (root / "results/frame-001.raw.txt").write_text("changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                module.inspect_bundle(root)

    def test_missing_required_stage_even_with_fresh_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.build(Path(temp))
            p = root / "manifest.json"
            value = json.loads(p.read_text())
            value["result_refs"] = [ref for ref in value["result_refs"] if "recognition_decision" not in ref]
            write_json(p, value)
            self.rehash(root)
            with self.assertRaisesRegex(ValueError, "5단계"):
                module.inspect_bundle(root)

    def test_cross_frame_relation_even_with_fresh_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.build(Path(temp))
            p = root / "results/frame-001-relation.json"
            value = json.loads(p.read_text())
            value["input_result_ids"] = ["frame-002-observation"]
            write_json(p, value)
            self.rehash(root)
            with self.assertRaisesRegex(ValueError, "다른 프레임"):
                module.inspect_bundle(root)


if __name__ == "__main__":
    unittest.main()
