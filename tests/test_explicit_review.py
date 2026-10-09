"""수정 저장 → 명시적 재검토 → 선택적 모의 전달의 분리·원본 불변·계보·변조 거절을 검사한다."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import test_workflow as workflow_fixtures

from contextweld import mock_delivery
from contextweld.corrections import (CorrectionConflict, CorrectionRejected, describe_targets, read_json,
                                     record_correction)
from contextweld.recognition import sha256, write_json
from contextweld.review import ReviewConflict, ReviewRejected, inspect_review_bundle, run_review
from contextweld.workflow import inspect_document_bundle, run_document_demo

ROOT = Path(__file__).resolve().parents[1]
def inventory(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def rehash(bundle: Path) -> None:
    manifest = read_json(bundle / "manifest.json")
    write_json(bundle / "checksums.json", {ref: sha256(bundle / ref) for ref in manifest["files"]})


class ReviewFixture(unittest.TestCase):
    """합성 문서 실행과 수정 저장소를 만드는 공통 준비. 테스트는 하위 클래스에 둔다."""

    def setUp(self) -> None:
        self.fixture = workflow_fixtures.WorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.store, self.out = self.root / "store", self.root / "reviews"
        self.bundles: dict[str, Path] = {}

    def bundle(self, case: str) -> Path:
        if case not in self.bundles:
            self.bundles[case] = self.fixture.run_case(case, deliver=True)
        return self.bundles[case]

    def request(self, bundle: Path, action: str, correction_id: str, *, field: str | None = None,
                after: dict | None = None, kind: str = "user") -> dict:
        templates = [item["request"] for item in describe_targets(bundle)["templates"]
                     if item["request"]["action"] == action and (field is None or item["request"]["target"].get("field") == field)]
        request = deepcopy(templates[0])
        request.update(correction_id=correction_id, reason="unit test reason", author={"kind": kind, "id": "tester-1"})
        if after is not None:
            request["after"] = after
        return request

    def record(self, bundle: Path, request: dict) -> dict:
        return record_correction(bundle, request, self.store)

    def voltage(self, correction_id: str = "corr-voltage", kind: str = "user") -> str:
        bundle = self.bundle("missing")
        self.record(bundle, self.request(bundle, "restore_document_parameter", correction_id, field="parameters.voltage", kind=kind))
        return correction_id

    def select(self, correction_id: str, value: str, bundle: Path | None = None) -> str:
        bundle = bundle or self.bundle("observation-conflict")
        self.record(bundle, self.request(bundle, "select_observed_candidate", correction_id, after={"part_id": value}))
        return correction_id

    def review(self, parent: Path, ids: list[str], run_id: str, *, request_id: str | None = None,
               deliver: bool = False, fault: str | None = None, reason: str = "explicit review", kind: str = "user") -> dict:
        return run_review(repo=ROOT, parent_bundle=parent, store=self.store, correction_ids=ids,
                          review_request_id=request_id or "rr-" + run_id, run_id=run_id, output_root=self.out,
                          requested_by={"kind": kind, "id": "operator-1"}, reason=reason, deliver=deliver,
                          delivery_fault=fault)

    def runs(self) -> list[str]:
        return sorted(path.name for path in self.out.glob("run_*")) if self.out.exists() else []


class ExplicitReviewTests(ReviewFixture):
    def test_record_only_writes_separate_file_without_review_model_or_delivery(self) -> None:
        bundle = self.bundle("missing")
        before = inventory(bundle)
        request = self.request(bundle, "restore_document_parameter", "corr-voltage", field="parameters.voltage")
        with patch("contextweld.mock_delivery.MockReceiver") as receiver, patch("contextweld.mock_delivery.send_command") as send, \
                patch("contextweld.review.compute_review") as review, patch("contextweld.recognition.QwenEngine") as vlm, \
                patch("contextweld.recognition.PaddleEngine") as ocr:
            result = self.record(bundle, request)
            for mock in (receiver, send, review, vlm, ocr):
                mock.assert_not_called()
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(before, inventory(bundle))
        self.assertEqual([path.name for path in self.store.iterdir()], ["corr-voltage.json"])
        self.assertEqual(self.runs(), [])
        record = read_json(self.store / "corr-voltage.json")
        self.assertEqual((record["source_kind"], record["producer"]), ("user", "user"))
        self.assertEqual(record["effects"]["review_started"], False)
        self.assertEqual(record["effects"]["delivery_requested"], False)
        self.assertEqual(record["target"]["run_id"], "unit-missing")
        self.assertEqual(record["target"]["result_sha256"], sha256(bundle / "results/work-spec.json"))
        self.assertEqual(record["before"], {"field": "parameters.voltage", "present": False, "missing": True})
        self.assertEqual(record["after"], {"document_id": "lanl-wps-3501", "revision": "1", "row_id": "layer-1"})

    def test_hold_is_recorded_and_never_starts_review_or_delivery(self) -> None:
        bundle = self.bundle("observation-conflict")
        hold = self.request(bundle, "hold", "corr-hold")
        self.assertEqual(self.record(bundle, hold)["status"], "recorded")
        self.assertEqual(read_json(self.store / "corr-hold.json")["after"], {"decision": "hold"})
        with patch("contextweld.mock_delivery.MockReceiver") as receiver:
            with self.assertRaises(ReviewRejected) as caught:
                self.review(bundle, ["corr-hold"], "after-hold", deliver=True)
            receiver.assert_not_called()
        self.assertEqual(caught.exception.code, "hold_not_applicable")
        self.assertEqual(self.runs(), [])
        self.assertFalse((self.store / "review-requests").exists())

    def test_selected_review_without_delivery_succeeds_without_command_or_ack(self) -> None:
        parent = self.bundle("missing")
        before = inventory(parent)
        self.voltage()
        # 같은 저장소에 있지만 선택하지 않은 기록과 손상 파일은 읽거나 적용하지 않는다.
        self.record(parent, self.request(parent, "hold", "corr-unselected-hold"))
        (self.store / "corr-corrupt.json").write_text("{not json")
        with patch("contextweld.mock_delivery.MockReceiver") as receiver:
            result = self.review(parent, ["corr-voltage"], "review-voltage")
            receiver.assert_not_called()
        self.assertEqual((result["run_outcome"], result["delivery_status"]), ("succeeded", "not_requested"))
        bundle = Path(result["bundle"])
        report = inspect_review_bundle(bundle)
        self.assertEqual(report["issues"], 0)
        manifest = read_json(bundle / "manifest.json")
        self.assertEqual((manifest["run_kind"], manifest["parent_run_id"], manifest["origin_run_id"]),
                         ("review", "unit-missing", "unit-missing"))
        self.assertEqual(manifest["correction_ids"], ["corr-voltage"])
        self.assertFalse(manifest["delivery_requested"])
        self.assertEqual(manifest["review_request_id"], "rr-review-voltage")
        self.assertEqual(sorted(path.name for path in (bundle / "inputs/corrections").iterdir()), ["corr-voltage.json"])
        self.assertEqual(list((bundle / "commands").iterdir()), [])
        spec = read_json(bundle / "results/work-spec.json")
        self.assertEqual(spec["spec_id"], "review-voltage-spec-001")
        self.assertEqual(spec["parameters"]["voltage"]["source_kind"], "document")
        self.assertEqual((spec["parameters"]["voltage"]["min"], spec["parameters"]["voltage"]["max"]), (24, 28))
        self.assertEqual(spec["parameters"]["voltage"]["restored_by_correction_id"], "corr-voltage")
        self.assertEqual(spec["fault_injections"], [{"op": "omit_parameter", "field": "voltage"}])
        self.assertFalse(spec["application_authorized"])
        entry = read_json(bundle / "results/correction-application.json")["entries"][0]
        self.assertEqual((entry["correction_reason"], entry["status"], entry["status_reason"]), ("unit test reason", "applied", None))
        resolution = read_json(bundle / "results/issue-resolution.json")["against_parent"]
        self.assertEqual(resolution["entries"][0]["status"], "resolved")
        self.assertEqual(resolution["entries"][0]["correction_ids"], ["corr-voltage"])
        self.assertEqual(before, inventory(parent))

    def test_residual_issue_keeps_needs_review_and_blocks_requested_delivery(self) -> None:
        parent = self.bundle("observation-conflict")
        self.select("corr-pick-vlm", "B1SB3ON-29")
        with patch("contextweld.mock_delivery.MockReceiver") as receiver:
            result = self.review(parent, ["corr-pick-vlm"], "review-pick", deliver=True)
            receiver.assert_not_called()
        self.assertEqual((result["run_outcome"], result["delivery_status"]), ("needs_review", "blocked"))
        bundle = Path(result["bundle"])
        interpretation = read_json(bundle / "results/effective-interpretation.json")
        row = interpretation["observations"][0]
        self.assertEqual(row["ocr"]["raw_text"], "BISb30N-29")
        self.assertEqual(row["normalized_identifier"], "BISB30N-29")
        self.assertEqual(row["effective_identifier"]["value"], "B1SB3ON-29")
        self.assertEqual(row["effective_identifier"]["source_kind"], "user")
        self.assertEqual(row["effective_identifier"]["chosen_from"][0]["engine"], "vlm")
        self.assertEqual(interpretation["original_candidates"], ["BISB30N-29", "B1SB3ON-29"])
        self.assertEqual(interpretation["candidates"], ["B1SB3ON-29"])
        entries = {item["issue"]["code"]: item for item in read_json(bundle / "results/issue-resolution.json")["against_parent"]["entries"]}
        self.assertEqual(entries["ocr_vlm_disagreement"]["status"], "resolved")
        self.assertEqual(entries["ocr_vlm_disagreement"]["correction_ids"], ["corr-pick-vlm"])
        self.assertEqual(entries["work_order_no_valid_order"]["status"], "open")
        self.assertEqual(list((bundle / "commands").iterdir()), [])
        self.assertEqual(inspect_review_bundle(bundle)["run_outcome"], "needs_review")

    def test_explicit_delivery_records_actual_loopback_request_ack_and_receipt(self) -> None:
        self.voltage()
        result = self.review(self.bundle("missing"), ["corr-voltage"], "review-deliver", deliver=True)
        self.assertEqual((result["run_outcome"], result["delivery_status"]), ("succeeded", "received"))
        bundle = Path(result["bundle"])
        command = read_json(bundle / "commands/command.json")
        transport = read_json(bundle / "commands/transport.json")
        receipts = [json.loads(line) for line in (bundle / "commands/receiver.jsonl").read_text().splitlines()]
        self.assertEqual(command["command_id"], "review-deliver-command-001")
        self.assertEqual(command["spec_id"], "review-deliver-spec-001")
        self.assertEqual(transport["request"], command)
        self.assertEqual(transport["ack"]["status"], "received")
        self.assertTrue(transport["endpoint"].startswith("http://127.0.0.1:"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0]["raw_request"]), command)
        self.assertEqual(receipts[0]["ack"], transport["ack"])
        self.assertFalse(transport["ack"]["execution_authorized"])
        self.assertEqual(inspect_review_bundle(bundle)["delivery_status"], "received")

    def test_delivery_after_export_is_new_run_and_previous_bundle_is_unchanged(self) -> None:
        self.voltage()
        first = Path(self.review(self.bundle("missing"), ["corr-voltage"], "review-first")["bundle"])
        before = inventory(first)
        result = self.review(first, ["corr-voltage"], "review-later", deliver=True)
        self.assertEqual((result["run_outcome"], result["delivery_status"]), ("succeeded", "received"))
        self.assertEqual(before, inventory(first))
        self.assertEqual(list((first / "commands").iterdir()), [])
        later = Path(result["bundle"])
        lineage = read_json(later / "results/lineage.json")
        self.assertEqual([item["run_id"] for item in lineage["ancestors"]], ["unit-missing", "review-first"])
        self.assertEqual(lineage["ancestors"][0]["bundle_ref"], "inputs/parent/inputs/parent")
        entry = read_json(later / "results/correction-application.json")["entries"][0]
        self.assertEqual((entry["target"]["run_id"], entry["target"]["relation_to_review"]), ("unit-missing", "ancestor"))
        manifest = read_json(later / "manifest.json")
        self.assertEqual((manifest["parent_run_id"], manifest["origin_run_id"]), ("review-first", "unit-missing"))
        self.assertEqual(inspect_review_bundle(later)["lineage_depth"], 2)

    def test_stale_wrong_target_and_unsupported_fields_are_rejected_at_record(self) -> None:
        missing, conflict, normal = self.bundle("missing"), self.bundle("observation-conflict"), self.bundle("normal")
        before = {name: inventory(path) for name, path in self.bundles.items()}
        base = self.request(missing, "restore_document_parameter", "corr-x", field="parameters.voltage")
        pick = self.request(conflict, "select_observed_candidate", "corr-y", after={"part_id": "BISB30N-29"})
        cases = [
            ("stale_before_value", missing, lambda r: r["before"].update(present=True)),
            ("stale_result", missing, lambda r: r["target"].update(result_sha256="0" * 64)),
            ("target_run_mismatch", conflict, lambda r: None),
            ("unsupported_field", missing, lambda r: r["after"].update(min=1, max=999)),
            ("unsupported_field", missing, lambda r: r["target"].update(field="application_authorized")),
            ("unsupported_field", missing, lambda r: r.update(execution_authorized=True)),
            ("unsupported_field", missing, lambda r: r["target"].update(field="parameters.validation") or r["before"].update(field="parameters.validation")),
            ("unsupported_action", missing, lambda r: r.update(action="json_patch")),
            ("document_reference_mismatch", missing, lambda r: r["after"].update(row_id="layer-2")),
            ("invalid_request", missing, lambda r: r.update(author={"kind": "model", "id": "x"})),
        ]
        for code, target, change in cases:
            with self.subTest(code=code):
                request = deepcopy(base)
                change(request)
                with self.assertRaises(CorrectionRejected) as caught:
                    record_correction(target, request, self.store)
                self.assertEqual(caught.exception.code, code)
        for code, change in [("candidate_not_observed", lambda r: r["after"].update(part_id="BISB30N-15")),
                             ("observation_not_found", lambda r: r["target"].update(observation_id="frame-999-ocr-1")),
                             ("unsupported_field", lambda r: r["target"].update(field="confidence"))]:
            with self.subTest(code=code):
                request = deepcopy(pick)
                change(request)
                with self.assertRaises(CorrectionRejected) as caught:
                    record_correction(conflict, request, self.store)
                self.assertEqual(caught.exception.code, code)
        present = deepcopy(base)
        present["target"].update(run_id="unit-normal", result_sha256=sha256(normal / "results/work-spec.json"))
        present["before"].update(present=True, missing=False)
        with self.assertRaises(CorrectionRejected) as caught:
            record_correction(normal, present, self.store)
        self.assertEqual(caught.exception.code, "parameter_not_missing")
        with self.assertRaises(CorrectionRejected) as caught:
            record_correction(missing, base, missing / "corrections")
        self.assertEqual(caught.exception.code, "store_inside_bundle")
        with self.assertRaises(CorrectionRejected) as caught:
            record_correction(conflict, self.request(conflict, "restore_document_parameter", "corr-w", field="parameters.voltage")
                              | {"after": {"document_id": "lanl-wps-3501", "revision": "1", "row_id": "layer-1"}}, self.store)
        self.assertEqual(caught.exception.code, "no_document_reference")
        self.assertFalse(self.store.exists())
        self.assertEqual(before, {name: inventory(path) for name, path in self.bundles.items()})

    def test_unrelated_stale_duplicate_and_conflicting_selections_are_rejected_at_review(self) -> None:
        self.voltage()
        self.select("corr-ocr", "BISB30N-29")
        self.select("corr-vlm", "B1SB3ON-29")
        cases = [("unrelated_run", self.bundle("normal"), ["corr-voltage"]),
                 ("correction_not_found", self.bundle("missing"), ["corr-missing-id"]),
                 ("duplicate_selection", self.bundle("missing"), ["corr-voltage", "corr-voltage"]),
                 ("conflicting_or_stale_basis", self.bundle("observation-conflict"), ["corr-ocr", "corr-vlm"])]
        for code, parent, ids in cases:
            with self.subTest(code=code), patch("contextweld.mock_delivery.MockReceiver") as receiver:
                with self.assertRaises(CorrectionRejected) as caught:
                    self.review(parent, ids, "rejected-" + code.replace("_", "-"), deliver=True)
                self.assertEqual(caught.exception.code, code)
                receiver.assert_not_called()
        # 같은 run_id라도 수정 당시와 다른 묶음이면 오래된 수정으로 거절한다.
        other = run_document_demo(**{**self.fixture.kwargs, "output_root": self.root / "other"}, run_id="unit-missing",
                                  case="missing", deliver=False)
        with self.assertRaises(ReviewRejected) as caught:
            self.review(other, ["corr-voltage"], "rejected-stale-bundle")
        self.assertEqual(caught.exception.code, "stale_target_bundle")
        # 저장소 파일을 바꾸면 내장 요청 해시와 맞지 않아 적용하지 않는다.
        path = self.store / "corr-voltage.json"
        record = read_json(path)
        record["after"]["row_id"] = "layer-9"
        path.write_text(json.dumps(record))
        with self.assertRaises(CorrectionRejected) as caught:
            self.review(self.bundle("missing"), ["corr-voltage"], "rejected-tampered-store")
        self.assertEqual(caught.exception.code, "invalid_correction_record")
        self.assertEqual(self.runs(), [])

    def test_sequential_correction_basis_across_review_lineage(self) -> None:
        self.select("corr-ocr", "BISB30N-29")
        first = Path(self.review(self.bundle("observation-conflict"), ["corr-ocr"], "review-ocr")["bundle"])
        # 첫 재검토의 해석(사용자 선택 반영)을 대상으로 다른 후보를 다시 고른다.
        self.select("corr-vlm-after-ocr", "B1SB3ON-29", bundle=first)
        record = read_json(self.store / "corr-vlm-after-ocr.json")
        self.assertEqual(record["before"]["effective_identifier"], {"value": "BISB30N-29", "correction_id": "corr-ocr"})
        second = Path(self.review(first, ["corr-ocr", "corr-vlm-after-ocr"], "review-both")["bundle"])
        row = read_json(second / "results/effective-interpretation.json")["observations"][0]
        self.assertEqual(row["effective_identifier"]["correction_id"], "corr-vlm-after-ocr")
        self.assertEqual(inspect_review_bundle(second)["run_outcome"], "needs_review")
        with self.assertRaises(ReviewRejected) as caught:
            self.review(first, ["corr-vlm-after-ocr"], "review-without-basis")
        self.assertEqual(caught.exception.code, "conflicting_or_stale_basis")

    def test_correction_retry_is_idempotent_and_different_content_conflicts(self) -> None:
        bundle = self.bundle("missing")
        request = self.request(bundle, "restore_document_parameter", "corr-retry", field="parameters.voltage")
        self.assertEqual(self.record(bundle, request)["status"], "recorded")
        stored = (self.store / "corr-retry.json").read_bytes()
        self.assertEqual(self.record(bundle, deepcopy(request))["status"], "duplicate_retry")
        with self.assertRaises(CorrectionConflict):
            self.record(bundle, {**request, "reason": "different reason"})
        self.assertEqual(stored, (self.store / "corr-retry.json").read_bytes())
        variants = [{**request, "correction_id": "corr-race", "reason": f"writer {index % 2}"} for index in range(8)]

        def attempt(item: dict) -> str:
            try:
                return record_correction(bundle, item, self.store)["status"]
            except CorrectionConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, variants))
        self.assertEqual(outcomes.count("recorded"), 1)
        self.assertEqual(outcomes.count("recorded") + outcomes.count("duplicate_retry") + outcomes.count("conflict"), 8)
        self.assertEqual(sorted(path.name for path in self.store.iterdir()), ["corr-race.json", "corr-retry.json"])

    def test_review_request_retry_does_not_resend_and_changed_request_conflicts(self) -> None:
        self.voltage()
        real = mock_delivery.send_command
        with patch("contextweld.mock_delivery.send_command", side_effect=real) as send:
            first = self.review(self.bundle("missing"), ["corr-voltage"], "review-once", request_id="rr-same", deliver=True)
            retry = self.review(self.bundle("missing"), ["corr-voltage"], "review-twice", request_id="rr-same", deliver=True)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(first["delivery_status"], "received")
        self.assertEqual((retry["status"], retry["run_id"], retry["new_run_created"]), ("duplicate_request", "review-once", False))
        self.assertEqual(self.runs(), ["run_review-once"])
        with self.assertRaises(ReviewConflict):
            self.review(self.bundle("missing"), ["corr-voltage"], "review-thrice", request_id="rr-same", deliver=False)
        self.assertEqual(self.runs(), ["run_review-once"])
        # 출력 위치를 바꿔 재시도해도 요청 ID 등록은 수정 저장소에 하나이므로 다시 실행·전송하지 않는다.
        self.out = self.root / "reviews-other-day"
        with patch("contextweld.mock_delivery.send_command", side_effect=real) as send:
            moved = self.review(self.bundle("missing"), ["corr-voltage"], "review-other-day", request_id="rr-same", deliver=True)
        send.assert_not_called()
        self.assertEqual((moved["status"], moved["run_id"]), ("duplicate_request", "review-once"))
        self.assertEqual(self.runs(), [])

    def test_new_ids_and_output_outside_every_bundle_are_required(self) -> None:
        self.voltage()
        first = Path(self.review(self.bundle("missing"), ["corr-voltage"], "review-ids")["bundle"])
        # 요청 ID 등록부가 없는 별도 저장소에서도 계보의 ID 재사용을 거절한다.
        other_store = self.root / "store-b"
        other_store.mkdir()
        shutil.copyfile(self.store / "corr-voltage.json", other_store / "corr-voltage.json")
        for run_id, request_id, code in [("unit-missing", "rr-new-1", "run_id_reused"), ("review-ids", "rr-new-2", "run_id_reused"),
                                         ("steel-batch-20261010-02", "rr-new-3", "run_id_reused"),
                                         ("review-ids-2", "rr-review-ids", "review_request_id_reused")]:
            with self.subTest(code=code, run_id=run_id):
                with self.assertRaises(ReviewRejected) as caught:
                    run_review(repo=ROOT, parent_bundle=first, store=other_store, correction_ids=["corr-voltage"],
                               review_request_id=request_id, run_id=run_id, output_root=self.root / "fresh-out",
                               requested_by={"kind": "user", "id": "operator-1"}, reason="x", deliver=True)
                self.assertEqual(caught.exception.code, code)
        before = inventory(first)
        for output in (first / "commands", self.bundle("missing") / "nested", self.bundle("normal") / "results"):
            with self.subTest(output=str(output)):
                with self.assertRaises(ReviewRejected) as caught:
                    run_review(repo=ROOT, parent_bundle=first, store=self.store, correction_ids=["corr-voltage"],
                               review_request_id="rr-inside", run_id="review-inside", output_root=output,
                               requested_by={"kind": "user", "id": "operator-1"}, reason="x", deliver=True)
                self.assertEqual(caught.exception.code, "output_inside_bundle")
        with self.assertRaises(CorrectionRejected) as caught:
            record_correction(first, self.request(first, "hold", "corr-hold-inside"), self.bundle("normal") / "store")
        self.assertEqual(caught.exception.code, "store_inside_bundle")
        self.assertEqual(before, inventory(first))
        self.assertFalse((self.bundle("missing") / "nested").exists())

    def test_semantic_tampering_missing_files_and_path_escape_fail_even_with_rehash(self) -> None:
        self.voltage()
        source = Path(self.review(self.bundle("missing"), ["corr-voltage"], "review-tamper", deliver=True)["bundle"])

        def spec_value(bundle: Path) -> None:
            path = bundle / "results/work-spec.json"
            value = read_json(path)
            value["parameters"]["voltage"]["max"] = 999
            write_json(path, value)

        def correction_after(bundle: Path) -> None:
            path = bundle / "inputs/corrections/corr-voltage.json"
            record = read_json(path)
            record["reason"] = record["request"]["reason"] = "forged reason"
            path.write_text(json.dumps(record))
            (bundle / "corrections.jsonl").write_text(json.dumps(record, sort_keys=True) + "\n")

        def interpretation(bundle: Path) -> None:
            path = bundle / "results/effective-interpretation.json"
            value = read_json(path)
            value["candidates"] = ["FORGED-1"]
            write_json(path, value)

        def receipt(bundle: Path) -> None:
            path = bundle / "commands/receiver.jsonl"
            row = json.loads(path.read_text())
            row["command"]["parameters"]["current"]["max"] = 999
            path.write_text(json.dumps(row) + "\n")

        def parent_spec(bundle: Path) -> None:
            path = bundle / "inputs/parent/results/work-spec.json"
            value = read_json(path)
            value["validation"]["issues"] = []
            write_json(path, value)
            rehash(bundle / "inputs/parent")

        def request(bundle: Path) -> None:
            path = bundle / "inputs/review-request.json"
            value = read_json(path)
            value["delivery_requested"] = False
            write_json(path, value)

        def manifest_scope(bundle: Path) -> None:
            path = bundle / "manifest.json"
            value = read_json(path)
            value.update(relation_reinterpretation="performed_by_model", review_scope="full_visual_relation_reinterpretation",
                         limitations=["field approved"])
            write_json(path, value)

        def endpoint(bundle: Path) -> None:
            path = bundle / "commands/transport.json"
            value = read_json(path)
            value["endpoint"] = "http://192.168.10.20:502/weld-controller/execute"
            write_json(path, value)

        def fault_label(bundle: Path) -> None:
            for name in ("manifest.json", "results/delivery.json"):
                value = read_json(bundle / name)
                value["delivery_fault_injection" if name == "manifest.json" else "fault_injection"] = "receiver_unavailable"
                write_json(bundle / name, value)

        def fake_event(bundle: Path) -> None:
            path = bundle / "events.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[4]["producer"] = "user"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))

        def extra_file(bundle: Path) -> None:
            (bundle / "ACK-received.json").write_text("{}")
            value = read_json(bundle / "manifest.json")
            value["files"] = sorted(value["files"] + ["ACK-received.json"])
            write_json(bundle / "manifest.json", value)

        def bool_type(bundle: Path) -> None:
            for name, key in (("manifest.json", "delivery_requested"), ("results/delivery.json", "requested")):
                value = read_json(bundle / name)
                value[key] = "true"
                write_json(bundle / name, value)

        def event_escape(bundle: Path) -> None:
            path = bundle / "events.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[2]["payload_ref"] = "../../../etc/passwd"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))

        for name, change in [("spec", spec_value), ("correction", correction_after), ("interpretation", interpretation),
                             ("receipt", receipt), ("parent", parent_spec), ("request", request), ("escape", event_escape),
                             ("manifest-scope", manifest_scope), ("endpoint", endpoint), ("fault-label", fault_label),
                             ("fake-event", fake_event), ("extra-file", extra_file), ("bool-type", bool_type)]:
            with self.subTest(name=name):
                bundle = self.root / ("tampered-" + name)
                shutil.copytree(source, bundle)
                change(bundle)
                rehash(bundle)
                with self.assertRaises((ValueError, KeyError)):
                    inspect_review_bundle(bundle)
        missing = self.root / "tampered-missing"
        shutil.copytree(source, missing)
        (missing / "results/issue-resolution.json").unlink()
        with self.assertRaisesRegex(ValueError, "파일 목록"):
            inspect_review_bundle(missing)
        linked = self.root / "tampered-symlink"
        shutil.copytree(source, linked)
        (linked / "results/work-spec.json").unlink()
        os.symlink(source / "results/work-spec.json", linked / "results/work-spec.json")
        with self.assertRaises(ValueError):
            inspect_review_bundle(linked)
        self.assertTrue(inspect_review_bundle(source)["verified"])

    def test_delivery_failures_are_failed_with_records_and_no_fabricated_ack(self) -> None:
        self.voltage()
        parent = self.bundle("missing")
        with patch("contextweld.mock_delivery.send_command", side_effect=TimeoutError("test timeout")):
            timeout = self.review(parent, ["corr-voltage"], "review-timeout", deliver=True)
        refused = self.review(parent, ["corr-voltage"], "review-refused", deliver=True, fault="receiver_unavailable")
        with patch("contextweld.mock_delivery.send_command", side_effect=ValueError("ACK mismatch")):
            mismatch = self.review(parent, ["corr-voltage"], "review-mismatch", deliver=True)
        for result, error_type in [(timeout, "TimeoutError"), (refused, "ConnectionRefusedError"), (mismatch, "ValueError")]:
            with self.subTest(error=error_type):
                bundle = Path(result["bundle"])
                self.assertEqual((result["run_outcome"], result["delivery_status"]), ("failed", "failed"))
                error = read_json(bundle / "commands/transport-error.json")
                self.assertEqual(error["error_type"], error_type)
                self.assertIsNone(error["ack"])
                self.assertFalse((bundle / "commands/transport.json").exists())
                self.assertEqual(read_json(bundle / "manifest.json")["export_status"], "complete")
                self.assertEqual(inspect_review_bundle(bundle)["run_outcome"], "failed")
        self.assertEqual((Path(refused["bundle"]) / "commands/receiver.jsonl").read_text(), "")
        self.assertEqual(refused["delivery_fault_injection"], "receiver_unavailable")
        # 수신기는 받았지만 클라이언트가 응답을 확인하지 못한 경우: 실패로 두되 수신기 측 수신을 표시한다.
        real_receive = mock_delivery.MockReceiver._receive

        def slow_receive(receiver, *args, **kwargs):
            result = real_receive(receiver, *args, **kwargs)
            import time
            time.sleep(0.6)
            return result
        with patch.object(mock_delivery.MockReceiver, "_receive", slow_receive):
            late = run_review(repo=ROOT, parent_bundle=parent, store=self.store, correction_ids=["corr-voltage"],
                              review_request_id="rr-late", run_id="review-late-ack", output_root=self.out,
                              requested_by={"kind": "user", "id": "operator-1"}, reason="late", deliver=True, timeout=0.2)
        delivery = read_json(Path(late["bundle"]) / "results/delivery.json")
        self.assertEqual((late["run_outcome"], delivery["status"], delivery["receiver_side"], delivery["client_ack_confirmed"]),
                         ("failed", "failed", "received", False))
        self.assertEqual(inspect_review_bundle(Path(late["bundle"]))["receiver_side"], "received")
        with patch("contextweld.review._deliver", side_effect=RuntimeError("unexpected crash")):
            with self.assertRaises(RuntimeError):
                self.review(parent, ["corr-voltage"], "review-crash", request_id="rr-crash", deliver=True)
        incomplete = self.out / "run_review-crash.incomplete"
        manifest = read_json(incomplete / "manifest.json")
        self.assertEqual((manifest["export_status"], manifest["run_outcome"]), ("incomplete", "failed"))
        retry = self.review(parent, ["corr-voltage"], "review-crash-2", request_id="rr-crash", deliver=True)
        self.assertEqual((retry["status"], retry["export_status"]), ("duplicate_request", "incomplete"))
        self.assertFalse((self.out / "run_review-crash-2").exists())

    def test_missing_empty_commands_directory_is_same_as_empty(self) -> None:
        bundle = self.bundle("missing")
        (bundle / "commands").rmdir()
        self.assertEqual(inspect_document_bundle(bundle)["run_outcome"], "needs_review")
        self.voltage()
        review = Path(self.review(bundle, ["corr-voltage"], "review-no-commands-dir")["bundle"])
        (review / "commands").rmdir()
        self.assertEqual(inspect_review_bundle(review)["run_outcome"], "succeeded")
        # 빈 디렉토리 대신 파일이 있으면 받아들이지 않는다.
        (bundle / "commands").write_text('{"ack": {"status": "received"}}')
        manifest = read_json(bundle / "manifest.json")
        manifest["files"] = sorted(manifest["files"] + ["commands"])
        write_json(bundle / "manifest.json", manifest)
        rehash(bundle)
        with self.assertRaises(ValueError):
            inspect_document_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
