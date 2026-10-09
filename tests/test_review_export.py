"""재검토 묶음의 읽기 전용 HTML: 이동한 묶음 조회, 출처 구분, 실행 기능·외부 자원 없음, 이스케이프를 확인한다."""
from __future__ import annotations

from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from test_explicit_review import ReviewFixture, inventory

from contextweld.review import inspect_review_bundle

ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location("review_export", ROOT / "scripts/export_document_review.py")
assert MODULE_SPEC and MODULE_SPEC.loader
viewer = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(viewer)


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


class ReviewExportTests(ReviewFixture):
    def test_moved_bundle_verifies_and_exports_static_html_without_original_paths(self) -> None:
        self.voltage(kind="demo_fixture")
        first = Path(self.review(self.bundle("missing"), ["corr-voltage"], "review-move-a", kind="demo_fixture")["bundle"])
        later = Path(self.review(first, ["corr-voltage"], "review-move-b", deliver=True, kind="demo_fixture")["bundle"])
        moved = self.root / "elsewhere" / "copied-bundle"
        shutil.copytree(later, moved)
        shutil.rmtree(self.out)
        shutil.rmtree(self.fixture.output)
        for path in moved.rglob("*"):
            if path.is_file():
                self.assertNotIn(str(self.root).encode(), path.read_bytes(), str(path))
        report = inspect_review_bundle(moved)
        self.assertEqual((report["run_outcome"], report["delivery_status"]), ("succeeded", "received"))
        output = self.root / "moved.html"
        before = inventory(moved)
        with patch("contextweld.mock_delivery.MockReceiver") as receiver, patch("contextweld.mock_delivery.send_command") as send:
            result = viewer.export_review(moved, output)
            receiver.assert_not_called()
            send.assert_not_called()
        self.assertEqual(before, inventory(moved))
        self.assertEqual(result["schema"], "review-bundle.v1")
        content = output.read_text()
        self.assertNotIn("사람의 수정", content)
        for expected in ("원본 · model", "수정 · demo_fixture", "재판단 · rule", "사람의 검수가 아니다", "review-move-b", "시연 fixture 수정 (사람 검수 아님)",
                         "rr-review-move-b", "corr-voltage", "실제 수신 ACK", "수신기 원본 기록", "demo_complete",
                         "Content-Security-Policy", "restored_by_correction_id", "delivery_requested"):
            self.assertIn(expected, content)
        parser = Elements()
        parser.feed(content)
        self.assertFalse(any(tag in {"script", "iframe", "object", "embed", "form", "link", "input", "button"} for tag, _ in parser.elements))
        for _, attrs in parser.elements:
            self.assertFalse(any(key.startswith("on") for key in attrs))
            if attrs.get("href"):
                self.assertTrue(attrs["href"].startswith("#"))


    def test_review_viewer_escapes_untrusted_correction_text(self) -> None:
        bundle = self.bundle("observation-conflict")
        payload = '</pre><script>alert("x")</script><img src="https://bad.invalid/x" onerror="bad()">'
        request = self.request(bundle, "select_observed_candidate", "corr-payload", after={"part_id": "BISB30N-29"})
        request["reason"] = payload
        self.record(bundle, request)
        review = Path(self.review(bundle, ["corr-payload"], "review-payload", reason=payload)["bundle"])
        content = viewer.render_review_run(viewer.collect_review_run(review, inspect_review_bundle(review)))
        self.assertIn("&lt;script&gt;", content)
        parser = Elements()
        parser.feed(content)
        self.assertFalse(any(tag in {"script", "iframe", "form", "link"} for tag, _ in parser.elements))
        for _, attrs in parser.elements:
            self.assertFalse(any(key.startswith("on") for key in attrs))
            if attrs.get("src"):
                self.assertTrue(attrs["src"].startswith("data:image/"))


    def test_exported_review_stays_unchanged_when_delivery_is_requested_later(self) -> None:
        self.voltage()
        first = Path(self.review(self.bundle("missing"), ["corr-voltage"], "review-exported")["bundle"])
        viewer.export_review(first, self.root / "exported.html")
        before = inventory(first)
        self.assertIn("전송 기록 없음", (self.root / "exported.html").read_text())
        later = self.review(first, ["corr-voltage"], "review-exported-deliver", deliver=True)
        self.assertEqual(later["delivery_status"], "received")
        self.assertEqual(before, inventory(first))
        self.assertEqual(inspect_review_bundle(first)["delivery_status"], "not_requested")


if __name__ == "__main__":
    unittest.main()
