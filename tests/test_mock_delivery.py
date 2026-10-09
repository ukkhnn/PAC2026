"""모의 수신의 형식 거부·실제 HTTP 전달·중복·기록 보존을 검사한다."""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from contextweld.mock_delivery import MAX_BODY_BYTES, MockReceiver, send_command, validate_command


def profile() -> dict:
    return {"schema_version": "demo-target-profile.v1", "profile_id": "document-range-review.v1",
            "contract_version": "1", "purpose": "demo_mock", "evaluation_scope": "document_review",
            "parameters": {"process": {"kind": "enum", "unit": None, "allowed_values": ["FCAW"]},
                           "current": {"kind": "range", "unit": "A"},
                           "voltage": {"kind": "range", "unit": "V"},
                           "travel_speed": {"kind": "range", "unit": "in/min"}}}


def command() -> dict:
    reference = {"document_id": "fixture-wps", "revision": "1", "source_hash": "a" * 64,
                 "locator": {"page": 2, "bbox": [10, 20, 100, 40], "table": "pass_conditions", "row": 1}}
    fields = {}
    for name, lower, upper, unit in (("current", 130, 250, "A"), ("voltage", 25, 28, "V"),
                                    ("travel_speed", 3, 12, "in/min")):
        fields[name] = {"min": lower, "max": upper, "unit": unit, "source_kind": "document",
                        "evidence": {**deepcopy(reference), "locator": {**reference["locator"], "column": name}}}
    fields["process"] = {"value": "FCAW", "unit": None, "source_kind": "document", "evidence": deepcopy(reference)}
    return {"schema_version": "demo-command.v1", "contract_version": "1", "command_id": "command-1",
            "run_id": "run-fixture", "spec_id": "spec-1", "target_profile": "document-range-review.v1",
            "purpose": "demo_mock", "evaluation_scope": "document_review", "execution_authorized": False,
            "application_authorized": False, "target": {"project_id": "fixture-project", "block_id": "fixture-block",
                "work_order_id": "fixture-order", "part_id": "fixture-part", "joint_id": "fixture-joint"},
            "documents": [reference], "parameters": fields}


class MockDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_valid_ranges_preserved_without_setpoint_or_authorization(self) -> None:
        payload = command()
        original = deepcopy(payload)
        self.assertEqual(validate_command(payload, profile()), [])
        self.assertEqual(payload, original)
        self.assertNotIn("value", payload["parameters"]["current"])

    def test_missing_conflicting_and_nonfinite_parameters_rejected(self) -> None:
        changes = [
            lambda value: value["parameters"].pop("voltage"),
            lambda value: value["parameters"].update(robot_command={"value": "RUN"}),
            lambda value: value["parameters"]["current"].update(min=True),
            lambda value: value["parameters"]["current"].update(min=float("nan")),
            lambda value: value["parameters"]["current"].update(max=float("inf")),
            lambda value: value["parameters"]["current"].update(min=300, max=200),
            lambda value: value["parameters"]["current"].update(value=190),
            lambda value: value["parameters"]["voltage"].update(unit="A"),
            lambda value: value["parameters"]["process"].update(value="GMAW"),
            lambda value: value["parameters"]["current"]["evidence"].update(source_hash="b" * 64),
            lambda value: value["parameters"]["current"]["evidence"].update(revision="2"),
            lambda value: value["parameters"]["current"]["evidence"].update(locator={}),
            lambda value: value["target"].update(joint_id=None),
            lambda value: value.update(execution_authorized=True),
            lambda value: value.update(application_authorized=True),
            lambda value: value.update(execution_authorized=0),
            lambda value: value.update(purpose="robot_execution"),
            lambda value: value.update(target_profile="manufacturer-real"),
            lambda value: value["documents"].append({**value["documents"][0], "source_hash": "b" * 64}),
        ]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                payload = command()
                change(payload)
                self.assertTrue(validate_command(payload, profile()))

    def test_actual_loopback_http_ack_duplicate_conflict_and_append_log(self) -> None:
        log = self.root / "receiver.jsonl"
        payload = command()
        with MockReceiver(profile(), log) as receiver:
            self.assertTrue(receiver.url.startswith("http://127.0.0.1:"))
            received = send_command(receiver.url, payload)
            duplicate = send_command(receiver.url, deepcopy(payload))
            changed = deepcopy(payload)
            changed["parameters"]["current"]["max"] = 249
            conflict = send_command(receiver.url, changed)
            invalid = command()
            invalid["command_id"] = "command-invalid"
            invalid["parameters"].pop("voltage")
            rejected = send_command(receiver.url, invalid)
        self.assertEqual(received["http_status"], 200)
        self.assertEqual(received["ack"]["status"], "received")
        self.assertFalse(received["ack"]["duplicate"])
        self.assertTrue(duplicate["ack"]["duplicate"])
        self.assertEqual(conflict["http_status"], 409)
        self.assertEqual(conflict["ack"]["status"], "rejected")
        self.assertEqual(rejected["http_status"], 422)
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([row["seq"] for row in rows], [1, 2, 3, 4])
        self.assertEqual(rows[0]["command"], payload)
        self.assertEqual(rows[0]["ack"], received["ack"])
        self.assertTrue(all(row["ack"]["execution_authorized"] is False for row in rows))
        self.assertTrue(all(row["ack"]["application_authorized"] is False for row in rows))
        previous = log.read_bytes()
        with self.assertRaises(FileExistsError):
            with MockReceiver(profile(), log):
                pass
        self.assertEqual(previous, log.read_bytes())

    def test_external_urls_and_unsafe_timeouts_fail_before_network(self) -> None:
        for url in ("https://127.0.0.1:1234/commands", "http://example.com/commands", "http://localhost:1234/commands",
                    "http://127.0.0.1:1234/commands?forward=elsewhere", "http://user@127.0.0.1:1234/commands",
                    "http://127.0.0.1:1234/other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                send_command(url, command())
        for timeout in (0, -1, True, float("inf"), 100):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                send_command("http://127.0.0.1:1/commands", command(), timeout=timeout)

    def test_invalid_json_is_rejected_and_raw_body_saved(self) -> None:
        log = self.root / "receiver.jsonl"
        with MockReceiver(profile(), log) as receiver:
            port = urlsplit(receiver.url).port
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", "/commands", body=b'{"not": json}', headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            ack = json.loads(response.read())
            self.assertEqual(response.status, 422)
            self.assertEqual(ack["status"], "rejected")
            connection.close()
        row = json.loads(log.read_text())
        self.assertEqual(row["raw_request"], '{"not": json}')
        self.assertIsNone(row["command"])

    def test_concurrent_duplicate_requests_have_one_initial_receipt(self) -> None:
        log = self.root / "receiver.jsonl"
        with MockReceiver(profile(), log) as receiver:
            with ThreadPoolExecutor(max_workers=4) as pool:
                deliveries = list(pool.map(lambda unused: send_command(receiver.url, command()), range(4)))
        self.assertEqual(sum(not result["ack"]["duplicate"] for result in deliveries), 1)
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([row["seq"] for row in rows], [1, 2, 3, 4])
        self.assertTrue(all(row["ack"]["status"] == "received" for row in rows))

    def test_wire_nonfinite_values_and_oversize_are_rejected_and_recorded(self) -> None:
        log = self.root / "receiver.jsonl"
        with MockReceiver(profile(), log) as receiver:
            for body in (b'{"value": NaN}', b'{"value": 1e999}'):
                connection = HTTPConnection("127.0.0.1", urlsplit(receiver.url).port, timeout=5)
                connection.request("POST", "/commands", body=body, headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                ack = json.loads(response.read())
                self.assertEqual(response.status, 422)
                self.assertEqual(ack["validation_errors"][-1]["code"], "invalid_json")
                connection.close()
            connection = HTTPConnection("127.0.0.1", urlsplit(receiver.url).port, timeout=5)
            connection.request("POST", "/commands", body=b"", headers={"Content-Type": "application/json",
                                                                         "Content-Length": str(MAX_BODY_BYTES + 1)})
            response = connection.getresponse()
            ack = json.loads(response.read())
            self.assertEqual(response.status, 413)
            self.assertEqual(ack["status"], "rejected")
            connection.close()
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertFalse(rows[-1]["body_read"])
        self.assertEqual(rows[-1]["ack"]["validation_errors"][0]["code"], "body_too_large")


if __name__ == "__main__":
    unittest.main()
