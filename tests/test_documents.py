"""문서 근거의 위치·범위·손상·별도 실행 보존을 검증한다."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from contextweld.documents import (build_index, extract_html, extract_markdown,
                                   load_index, mark_context_used, search_documents,
                                   write_json_exclusive)


ROOT = Path(__file__).resolve().parents[1]


class DocumentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source_rows = []
        fixtures = [
            ("symbol", "symbol.html", "text/html",
             "<html><form><nav><p>ignore navigation</p></nav>\n"
             "<h1>Welding symbols</h1>\n<h2>Arrow side</h2>\n"
             "<p>The arrow identifies the joint and side.</p>\n"
             "<script>dangerous irrelevant text</script></form></html>", "rev1"),
            ("lanl-wts", "template.md", "text/plain",
             "# Sample blank WTS\n\nReference WPS: ______\nAmps: ______\n", None),
            ("manufacturer", "manual.md", "text/plain",
             "\ufeff# Controller manual\n\n```arccond``` inline command.\n\n"
             "### Parameters\n\n<table>\n<tr><th>항목</th><th>의미</th></tr>\n"
             "<tr><td>전류</td><td>설정에 따라 범위 상이</td></tr>\n</table>\n\n"
             "### Examples\n\n```python\narccond D, cur=170\n```\n", "rev2"),
        ]
        for doc_id, filename, media, text, revision in fixtures:
            path = self.root / filename
            path.write_text(text, encoding="utf-8")
            source_rows.append({"id": doc_id, "group": "documents", "relative_path": filename,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "media_type": media, "url": "https://example.org/" + filename,
                                "revision": revision})
        self.registry = self.root / "sources.json"
        self.registry.write_text(json.dumps({"sources": source_rows}))
        self.index = build_index(self.root, self.registry)

    def search(self, query: str, **kwargs: object) -> dict:
        return search_documents(self.index, query, data_root=self.root, **kwargs)

    def test_html_wrapping_form_and_source_line_survive(self) -> None:
        rows, _ = extract_html(self.root / "symbol.html")
        row = next(row for row in rows if "identifies" in row["text"])
        self.assertEqual(row["locator"]["line_start"], 4)
        self.assertEqual(row["locator"]["section"], "Arrow side")
        self.assertNotIn("navigation", " ".join(row["text"] for row in rows))
        self.assertNotIn("dangerous", " ".join(row["text"] for row in rows))

    def test_markdown_bom_inline_backticks_and_table_preserve_sections(self) -> None:
        rows, _ = extract_markdown(self.root / "manual.md")
        table = next(row for row in rows if row["locator"]["kind"] == "markdown_html_table")
        self.assertEqual(table["locator"]["section"], "Parameters")
        self.assertEqual((table["locator"]["line_start"], table["locator"]["line_end"]), (7, 10))
        self.assertIn("전류", table["text"])
        self.assertIn("설정에 따라 범위 상이", table["text"])
        example = next(row for row in rows if "cur=170" in row["text"])
        self.assertEqual(example["locator"]["section"], "Examples")
        self.assertEqual(rows[0]["locator"]["section"], "Controller manual")

    def test_scope_revision_missing_and_empty_results_do_not_fallback(self) -> None:
        result = self.search("arrow joint", document_ids=["symbol"], revision="rev1")
        self.assertEqual(result["status"], "retrieved")
        self.assertEqual({hit["document_id"] for hit in result["hits"]}, {"symbol"})
        self.assertEqual(result["used_evidence_ids"], [])
        for ids, revision in [(["symbol"], "rev2"), (["absent"], None),
                              (["symbol", "absent"], None), (["lanl-wts"], "rev1")]:
            with self.subTest(ids=ids, revision=revision):
                absent = self.search("arrow", document_ids=ids, revision=revision)
                self.assertEqual(absent["status"], "needs_review")
                self.assertEqual(absent["reason"], "document_filter_no_match")
                self.assertEqual(absent["hits"], [])
        no_match = self.search("unseenword", document_ids=["symbol"])
        self.assertEqual(no_match["reason"], "no_lexical_match")
        with self.assertRaises(ValueError):
            self.search("arrow", document_ids=[])

    def test_blank_template_is_not_instruction_or_approved_parameter(self) -> None:
        result = self.search("Amps", document_ids=["lanl-wts"])
        hit = result["hits"][0]
        self.assertEqual(hit["document_role"], "blank_template")
        self.assertIsNone(hit["revision"])
        self.assertIn("______", hit["text"])
        self.assertFalse(hit["content_reviewed"])
        self.assertFalse(hit["application_authorized"])
        self.assertFalse(result["execution_authorized"])

    def test_original_and_index_tampering_are_rejected(self) -> None:
        (self.root / "symbol.html").write_text("<html>changed</html>")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_index(self.root, self.registry)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.search("arrow", document_ids=["symbol"])
        damaged = deepcopy(self.index)
        damaged["chunks"][0]["text"] = "forged answer"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            search_documents(damaged, "forged", document_ids=["symbol"])

    def test_context_selection_is_separate_and_rejects_invented_evidence(self) -> None:
        result = self.search("arrow", document_ids=["symbol"])
        identifiers = result["returned_evidence_ids"][:1]
        marked = mark_context_used(result, identifiers)
        self.assertEqual(marked["used_evidence_ids"], identifiers)
        self.assertEqual(result["used_evidence_ids"], [])
        with self.assertRaises(ValueError):
            mark_context_used(result, ["invented"])
        with self.assertRaises(ValueError):
            mark_context_used(result, identifiers * 2)

    def test_index_round_trip_and_search_ranking_are_reproducible(self) -> None:
        path = self.root / "index.json"
        write_json_exclusive(path, self.index)
        loaded = load_index(path, self.root)
        first = self.search("joint arrow", document_ids=["symbol"])
        second = search_documents(loaded, "joint arrow", document_ids=["symbol"], data_root=self.root)
        self.assertEqual(first["hits"], second["hits"])
        self.assertEqual(first["index_hash"], second["index_hash"])
        self.assertEqual(first["hits"][0]["locator"]["line_start"], 4)
        self.assertTrue(first["raw_sources_verified"])

    def test_output_reuse_fails_and_cli_saves_empty_search(self) -> None:
        path = self.root / "index.json"
        write_json_exclusive(path, self.index)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_json_exclusive(path, {"replacement": True})
        self.assertEqual(path.read_bytes(), before)
        output = self.root / "search.json"
        command = [sys.executable, str(ROOT / "scripts/run/query_documents.py"), "--index", str(path),
                   "--data-root", str(self.root), "--query", "arrow", "--document-id", "missing",
                   "--output", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(output.read_text())["status"], "needs_review")
        repeated = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2)
        self.assertIn("이미 존재", repeated.stderr)

    def test_source_path_escape_and_duplicate_ids_fail(self) -> None:
        data = json.loads(self.registry.read_text())
        data["sources"][0]["relative_path"] = "../outside.html"
        self.registry.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "루트"):
            build_index(self.root, self.registry)
        data["sources"][0]["relative_path"] = "symbol.html"
        data["sources"].append(data["sources"][0])
        self.registry.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "중복"):
            build_index(self.root, self.registry)


if __name__ == "__main__":
    unittest.main()
