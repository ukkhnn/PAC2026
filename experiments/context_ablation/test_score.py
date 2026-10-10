"""채점 분모·보류·문맥 오판·기록 무결성의 회귀 검증."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from experiments.context_ablation.score import NORMAL_CONDITIONS, main, normalize, score_run


class ScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "records").mkdir()
        self.inputs = {"samples": [{"sample_id": "S01-R00", "image_id": "S01"},
                                    {"sample_id": "S02-R00", "image_id": "S02"}]}
        self.truth = {"targets": {"S01-R00": {"text": "B1Sb30N-15"},
                                   "S02-R00": {"text": "B1Sb30N-29"}},
                      "excluded": [{"sample_id": "S10-R00", "reason": "difficult"}]}
        self.fixtures = {"fixtures": {}}
        self.jobs = []
        for sample in self.inputs["samples"]:
            sample_id = sample["sample_id"]
            truth = self.truth["targets"][sample_id]["text"]
            self.fixtures["fixtures"][sample_id] = {"variants": {
                "normal": {"candidate_ids": [truth, "BISb30N-15"]},
                "absent": {"candidate_ids": ["BISb30N-15"]},
                "wrong_context": {"candidate_ids": [truth, "BISb30N-15"]},
            }}
            for condition in NORMAL_CONDITIONS:
                self.jobs.append({"sample_id": sample_id, "condition": condition, "variant": "normal"})
                self.write_record(sample_id, condition, truth)
        self.write_plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, **extra: object) -> None:
        (self.root / "plan.json").write_text(json.dumps({"jobs": self.jobs, **extra}))

    def write_record(self, sample_id: str, condition: str, text: str | None, *,
                     status: str = "resolved", selected: str | None = None,
                     variant: str = "normal", error: str | None = None) -> dict:
        candidate = condition not in {"A_ocr", "B_crop", "C_scene"}
        record = {"sample_id": sample_id, "condition": condition, "variant": variant,
                  "input_image_refs": [] if condition == "F_context_only" else ["crop.png"],
                  "ocr_reading": text, "elapsed_seconds": 1.0, "error": error,
                  "parsed": {"visible_text": text,
                             "selected_candidate_id": (text if selected is None and status == "resolved" else selected) if candidate else None,
                             "status": status, "reason": "test", "evidence": []}}
        (self.root / "records" / f"{sample_id}--{condition}.json").write_text(json.dumps(record))
        return record

    def score(self) -> dict:
        return score_run(self.root, self.truth, self.inputs, self.fixtures)

    def test_normalization_never_repairs_ambiguous_characters(self) -> None:
        self.assertEqual(normalize(" b1Sb30N-15 "), "B1SB30N-15")
        self.assertNotEqual(normalize("B1Sb30N-15"), normalize("BISb3ON-15"))
        self.assertNotEqual(normalize("B1 Sb30N-15"), normalize("B1Sb30N-15"))
        self.write_record("S01-R00", "A_ocr", "BISb30N-15")
        result = self.score()["per_condition"]["A_ocr"]
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["character_errors"], 1)

    def test_abstention_is_not_correct_even_when_literal_is_correct(self) -> None:
        self.write_record("S01-R00", "E_context", "B1Sb30N-15", status="ambiguous")
        result = self.score()["per_condition"]["E_context"]
        self.assertEqual(result["text_exact"], 2)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["abstentions"], 1)
        self.assertEqual(result["accuracy_accepted"], 1.0)
        self.assertEqual(result["coverage"], 0.5)
        self.assertEqual(result["accuracy_all"], 0.5)

    def test_missing_record_stays_in_denominator_and_is_invalid(self) -> None:
        (self.root / "records" / "S01-R00--B_crop.json").unlink()
        result = self.score()
        self.assertFalse(result["validation"]["valid"])
        metric = result["per_condition"]["B_crop"]
        self.assertEqual(metric["n"], 2)
        self.assertEqual(metric["missing_records"], 1)
        self.assertEqual(metric["accuracy_all"], 0.5)

    def test_duplicate_case_invalidates_run(self) -> None:
        original = self.root / "records" / "S01-R00--A_ocr.json"
        (self.root / "records" / "duplicate.json").write_bytes(original.read_bytes())
        result = self.score()
        self.assertFalse(result["validation"]["valid"])
        self.assertTrue(any("duplicate record" in error for error in result["validation"]["errors"]))

    def test_plan_cannot_silently_remove_failed_case(self) -> None:
        self.jobs = [job for job in self.jobs if not (job["sample_id"] == "S01-R00" and job["condition"] == "B_crop")]
        self.write_plan()
        result = self.score()
        self.assertFalse(result["validation"]["valid"])
        self.assertTrue(any("missing from plan" in error for error in result["validation"]["errors"]))

    def test_negative_context_cannot_accept_invented_candidate(self) -> None:
        self.jobs.append({"sample_id": "S01-R00", "condition": "E_absent", "variant": "absent"})
        self.jobs.append({"sample_id": "S01-R00", "condition": "E_wrong", "variant": "wrong_context"})
        self.write_plan()
        self.write_record("S01-R00", "E_absent", "B1Sb30N-15", variant="absent")
        self.write_record("S01-R00", "E_wrong", "B1Sb30N-15", selected="BISb30N-15", variant="wrong_context")
        result = self.score()
        absent = result["negative_context"]["E_absent"]
        wrong = result["negative_context"]["E_wrong"]
        self.assertEqual(absent["selected_outside_candidates"], 1)
        self.assertEqual(absent["correct_literal_maintained"], 1)
        self.assertEqual(absent["correct"], 0)
        self.assertEqual(absent["accepted"], 0)
        self.assertEqual(wrong["wrong_accepted"], 1)
        self.assertEqual(result["per_condition"]["E_context"]["n"], 2)

    def test_recovery_and_harm_are_paired_with_same_sample(self) -> None:
        self.write_record("S01-R00", "B_crop", "BISb30N-15")
        self.write_record("S02-R00", "C_scene", "BISb30N-29")
        result = self.score()["transitions"]["B_crop->C_scene"]
        self.assertEqual(result["wrong_to_correct"], 1)
        self.assertEqual(result["correct_to_wrong"], 1)
        self.assertEqual(result["net_correct_change"], 0)

    def test_model_failure_not_abstention(self) -> None:
        self.write_record("S01-R00", "B_crop", None, status="unreadable", error="generation failed")
        result = self.score()["per_condition"]["B_crop"]
        self.assertEqual(result["model_errors"], 1)
        self.assertEqual(result["abstentions"], 0)
        self.assertEqual(result["correct"], 1)

    def test_image_macro_does_not_weight_multi_region_photo_more(self) -> None:
        sample = {"sample_id": "S01-R01", "image_id": "S01"}
        self.inputs["samples"].append(sample)
        self.truth["targets"]["S01-R01"] = {"text": "B1Sb30N-15"}
        self.fixtures["fixtures"]["S01-R01"] = deepcopy(self.fixtures["fixtures"]["S01-R00"])
        for condition in NORMAL_CONDITIONS:
            self.jobs.append({"sample_id": "S01-R01", "condition": condition, "variant": "normal"})
            self.write_record("S01-R01", condition, "B1Sb30N-15")
        self.write_record("S02-R00", "A_ocr", "bad")
        self.write_plan()
        result = self.score()["per_condition"]["A_ocr"]
        self.assertAlmostEqual(result["accuracy_all"], 2 / 3)
        self.assertEqual(result["image_macro_accuracy_all"], 0.5)

    def test_declared_input_hashes_are_checked(self) -> None:
        path = self.root / "truth.json"
        path.write_text(json.dumps(self.truth))
        self.write_plan(input_hashes={"truth": hashlib.sha256(path.read_bytes()).hexdigest()})
        result = score_run(self.root, self.truth, self.inputs, self.fixtures, asset_paths={"truth": path})
        self.assertTrue(result["validation"]["valid"])
        path.write_text("changed")
        result = score_run(self.root, self.truth, self.inputs, self.fixtures, asset_paths={"truth": path})
        self.assertFalse(result["validation"]["valid"])

    def test_no_image_control_rejects_accidental_image(self) -> None:
        path = self.root / "records" / "S01-R00--F_context_only.json"
        record = json.loads(path.read_text())
        record["input_image_refs"] = ["crop.png"]
        path.write_text(json.dumps(record))
        result = self.score()
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(result["per_condition"]["F_context_only"]["schema_errors"], 1)

    def test_record_error_overrides_successful_parsed_answer(self) -> None:
        self.write_record("S01-R00", "E_context", "B1Sb30N-15", error="answer failed validation")
        result = self.score()["per_condition"]["E_context"]
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["text_exact"], 1)
        self.assertEqual(result["model_errors"], 1)

    def test_reported_model_schema_failure_keeps_experiment_integrity(self) -> None:
        self.write_record("S01-R00", "E_context", "B1Sb30N-15", selected="INVENTED",
                          error="selected candidate outside supplied roster")
        report = self.score()
        result = report["per_condition"]["E_context"]
        self.assertTrue(report["validation"]["valid"])
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["schema_errors"], 1)
        self.assertEqual(result["model_errors"], 1)

    def test_invalid_status_is_reported_without_crashing(self) -> None:
        path = self.root / "records" / "S01-R00--B_crop.json"
        record = json.loads(path.read_text())
        record["parsed"]["status"] = ["resolved"]
        path.write_text(json.dumps(record))
        result = self.score()
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(result["per_condition"]["B_crop"]["schema_errors"], 1)

    def test_artifact_tampering_is_detected(self) -> None:
        path = self.root / "records" / "S01-R00--A_ocr.json"
        (self.root / "checksums.json").write_text(json.dumps({str(path.relative_to(self.root)):
            hashlib.sha256(path.read_bytes()).hexdigest()}))
        self.assertTrue(self.score()["validation"]["valid"])
        self.write_record("S01-R00", "A_ocr", "BISb30N-15")
        self.assertFalse(self.score()["validation"]["valid"])

    def test_cli_never_overwrites_an_existing_score(self) -> None:
        arguments = ["--run", str(self.root)]
        for key, payload in (("truth", self.truth), ("inputs", self.inputs), ("fixtures", self.fixtures)):
            path = self.root / f"{key}.json"
            path.write_text(json.dumps(payload))
            arguments += [f"--{key}", str(path)]
        output = self.root / "score.json"
        arguments += ["--output", str(output)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(arguments), 0)
            original = output.read_bytes()
            self.assertEqual(main(arguments), 2)
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
