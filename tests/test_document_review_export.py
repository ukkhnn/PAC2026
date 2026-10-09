"""오프라인 조회의 입력 검증·불변성·보류 표시·HTML 안전성을 확인한다."""
from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import unittest

import test_workflow as workflow_fixtures

ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location("document_review_export", ROOT / "scripts/export_document_review.py")
assert MODULE_SPEC and MODULE_SPEC.loader
viewer = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(viewer)


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


class DocumentReviewExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = workflow_fixtures.WorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    @staticmethod
    def inventory(bundle: Path) -> dict[str, str]:
        return {str(path.relative_to(bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in bundle.rglob("*") if path.is_file()}

    def test_normal_and_two_held_cases_are_verified_and_input_unchanged(self) -> None:
        for case, outcome, issue in [("normal", "succeeded", None), ("missing", "needs_review", "required_parameter_missing"),
                                     ("observation-conflict", "needs_review", "ocr_vlm_disagreement")]:
            with self.subTest(case=case):
                bundle = self.fixture.run_case(case, deliver=False)
                before = self.inventory(bundle)
                output = self.fixture.root / (case + ".html")
                report = viewer.export_review(bundle, output)
                content = output.read_text()
                self.assertEqual(report["verification"]["run_outcome"], outcome)
                self.assertEqual(before, self.inventory(bundle))
                self.assertIn("execution_authorized", content)
                self.assertIn("demo_complete", content)
                self.assertIn("synthetic_demo", content)
                self.assertIn("pdf_points_top_left", content)
                self.assertIn("전송 기록 없음", content)
                self.assertIn("검토 보류" if issue else "문서 검토 통과", content)
                if issue:
                    self.assertIn(issue, content)

    def test_changed_or_semantically_forged_bundle_rejected_before_export(self) -> None:
        bundle = self.fixture.run_case("normal", deliver=False)
        path = bundle / "results/work-spec.json"
        value = json.loads(path.read_text())
        value["parameters"]["current"]["max"] = 999
        path.write_text(json.dumps(value))
        output = self.fixture.root / "bad.html"
        with self.assertRaises(ValueError):
            viewer.export_review(bundle, output)
        self.fixture.refresh_hashes(bundle)
        with self.assertRaisesRegex(ValueError, "재계산"):
            viewer.export_review(bundle, output)
        self.assertFalse(output.exists())

    def test_existing_output_and_bundle_internal_destination_rejected(self) -> None:
        bundle = self.fixture.run_case("normal", deliver=False)
        output = self.fixture.root / "kept.html"
        output.write_text("original")
        with self.assertRaises(FileExistsError):
            viewer.export_review(bundle, output)
        self.assertEqual(output.read_text(), "original")
        with self.assertRaises(ValueError):
            viewer.export_review(bundle, bundle / "review.html")
        self.assertFalse((bundle / "review.html").exists())

    def test_untrusted_text_cannot_inject_html_or_external_resources(self) -> None:
        bundle = self.fixture.run_case("normal", deliver=False)
        data = viewer.collect_review(bundle, viewer.inspect_document_bundle(bundle))
        payload = '</pre><script>alert("bad")</script><img src="https://bad.invalid/x" onerror="bad()">'
        data["outputs"] = [{"result": {"stage": payload}, "ref": payload, "raw_ref": payload, "raw": payload}]
        data["manifest"]["run_id"] = payload
        data["retrieval"]["hits"][0]["text"] = payload
        content = viewer.render_review(data)
        parser = Elements()
        parser.feed(content)
        self.assertIn("&lt;script&gt;", content)
        self.assertFalse(any(tag in {"script", "iframe", "object", "embed", "form", "link"} for tag, _ in parser.elements))
        for _, attrs in parser.elements:
            self.assertFalse(any(key.startswith("on") for key in attrs))
            if attrs.get("href"):
                self.assertTrue(attrs["href"].startswith("#"))
            if attrs.get("src"):
                self.assertTrue(attrs["src"].startswith("data:image/"))

    def test_png_embedded_as_original_bytes_and_svg_rejected(self) -> None:
        image = b"\x89PNG\r\n\x1a\noriginal-image-bytes"
        uri = viewer.image_uri(image)
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), image)
        self.assertIsNone(viewer.image_uri(b'<svg onload="bad()"></svg>'))
        self.assertIsNone(viewer.image_uri(b"<html>not an image</html>"))

    def test_received_transport_shows_actual_request_ack_and_receipt(self) -> None:
        # 유효한 실제 loopback 전송 기록은 workflow 자체가 만들고 검사한다.
        bundle = self.fixture.run_case("normal", deliver=True)
        output = self.fixture.root / "received.html"
        result = viewer.export_review(bundle, output)
        content = output.read_text()
        self.assertEqual(result["verification"]["delivery_status"], "received")
        for expected in ("실제 전송 request", "실제 수신 ACK", "수신기 원본 기록", "http_status", "command_sha256", "raw_request"):
            self.assertIn(expected, content)
        self.assertNotIn("전송 기록 없음", content)


if __name__ == "__main__":
    unittest.main()
