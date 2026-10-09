"""자료 준비의 무결성·기존 파일 보존·오프라인 확인 계약을 검사한다."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_demo_data.py"
SPEC = importlib.util.spec_from_file_location("prepare_demo_data", SCRIPT)
assert SPEC and SPEC.loader
prepare_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_data)


class PrepareDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.original = self.root / "original"
        self.original.mkdir()
        self.content = b"public document fixture\n"
        (self.original / "source.txt").write_bytes(self.content)
        self.destination = self.root / "prepared"
        self.config = self.root / "sources.json"
        self.source = {
            "id": "sample", "group": "documents", "url": "https://example.org/source.txt",
            "relative_path": "docs/source.txt", "source_path": "source.txt",
            "sha256": hashlib.sha256(self.content).hexdigest(), "media_type": "text/plain",
            "source_kind": "public_document", "required": True,
        }

    def run_cli(self, *extra: str) -> tuple[int, str]:
        self.config.write_text(json.dumps({"schema_version": "demo-data-sources.v1", "sources": [self.source]}))
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(
            prepare_data, "build_opener", side_effect=AssertionError("테스트에서 네트워크 호출 금지")
        ):
            result = prepare_data.main([
                "--config", str(self.config), "--destination", str(self.destination),
                "--local-steel-root", str(self.original), *extra,
            ])
        return result, output.getvalue()

    def test_copy_and_verify_without_writing(self) -> None:
        self.assertEqual(self.run_cli()[0], 0)
        manifest = self.destination / "asset-manifest.json"
        before = manifest.read_bytes()
        result, output = self.run_cli("--verify-only")
        self.assertEqual(result, 0)
        self.assertIn("verified", output)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((self.original / "source.txt").read_bytes(), self.content)

    def test_wrong_hash_does_not_publish_file(self) -> None:
        self.source["sha256"] = "0" * 64
        self.assertEqual(self.run_cli()[0], 1)
        self.assertFalse((self.destination / "docs/source.txt").exists())
        self.assertFalse(list(self.destination.rglob("*.part")))

    def test_changed_existing_file_is_preserved(self) -> None:
        self.assertEqual(self.run_cli()[0], 0)
        target = self.destination / "docs/source.txt"
        target.write_bytes(b"user modification")
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(target.read_bytes(), b"user modification")

    def test_document_hash_survives_failed_check(self) -> None:
        self.source["sha256"] = None
        self.assertEqual(self.run_cli()[0], 0)
        target = self.destination / "docs/source.txt"
        target.write_bytes(b"changed")
        self.assertEqual(self.run_cli()[0], 1)
        target.write_bytes(self.content)
        result, output = self.run_cli("--verify-only")
        self.assertEqual(result, 0, output)
        self.assertIn("verified", output)

    def test_path_escape_is_rejected_before_writing(self) -> None:
        self.source["relative_path"] = "../outside.txt"
        self.assertEqual(self.run_cli()[0], 1)
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertFalse(self.destination.exists())

    def test_missing_verify_does_not_create_directory(self) -> None:
        self.assertEqual(self.run_cli("--verify-only")[0], 1)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
