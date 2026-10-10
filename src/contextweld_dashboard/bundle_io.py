"""묶음 읽기 전용 접근. 모든 경로는 기존 ``contextweld.recognition.safe_path``로 묶음 안에 가둔다.

이 모듈은 파일을 쓰지 않는다. 화면 모델의 출처 표기(``src``)를 만드는 도우미도 함께 둔다.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

from contextweld.recognition import safe_path

from .model import ABSENT, V, ref, resolve_pointer, pointer

TEXT_SUFFIXES = {".json", ".jsonl", ".txt", ".md", ".csv", ".log", ".py", ".usda", ".html", ".htm", ".svg", ".xml"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_size(data: bytes) -> tuple[int, int] | None:
    """PNG/JPEG 헤더에서 원본 픽셀 크기를 읽는다(재인코딩 없음). 다른 형식은 ``None``."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data[:3] == b"\xff\xd8\xff":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = struct.unpack(">H", data[index + 2:index + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return int(width), int(height)
            index += 2 + length
    return None


def media_type(path: str) -> str:
    suffix = os.path.splitext(path)[1].lower()
    return {
        ".json": "application/json", ".jsonl": "application/x-ndjson", ".txt": "text/plain", ".md": "text/markdown",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".html": "text/html", ".htm": "text/html",
        ".csv": "text/csv", ".py": "text/x-python", ".usda": "text/plain", ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


class BundleReader:
    """원본 또는 패키지 사본 묶음을 읽는다. ``key``는 화면 모델 출처 표기의 루트 이름이다."""

    def __init__(self, root: Path, key: str):
        self.root = Path(root)
        self.key = key
        self._json: dict[str, Any] = {}

    # --- 경로 -------------------------------------------------------------------------------------
    def path(self, relative: str) -> Path:
        return safe_path(self.root, relative)

    def exists(self, relative: str) -> bool:
        try:
            target = self.path(relative)
        except ValueError:
            return False
        return target.is_file() and not target.is_symlink()

    def is_dir(self, relative: str) -> bool:
        try:
            target = self.path(relative)
        except ValueError:
            return False
        return target.is_dir() and not target.is_symlink()

    def listdir(self, relative: str) -> list[str]:
        """묶음 안 디렉터리의 파일 이름 목록(정렬). symlink는 제외한다."""
        if not self.is_dir(relative):
            return []
        base = self.path(relative)
        return sorted(item.name for item in base.iterdir() if item.is_file() and not item.is_symlink())

    # --- 읽기 -------------------------------------------------------------------------------------
    def bytes(self, relative: str) -> bytes:
        target = self.path(relative)
        if target.is_symlink():
            raise ValueError(f"symlink는 읽지 않습니다: {relative}")
        return target.read_bytes()

    def text(self, relative: str) -> str:
        return self.bytes(relative).decode("utf-8")

    def json(self, relative: str) -> Any:
        if relative not in self._json:
            self._json[relative] = json.loads(self.text(relative), parse_constant=_reject_constant)
        return self._json[relative]

    def jsonl(self, relative: str) -> list[Any]:
        """JSON Lines. 빈 줄은 건너뛰며, 출처 pointer의 첫 토큰은 빈 줄을 제외한 줄 번호(0부터)다."""
        key = relative + "\x00jsonl"
        if key not in self._json:
            lines = [line for line in self.text(relative).splitlines() if line.strip()]
            self._json[key] = [json.loads(line, parse_constant=_reject_constant) for line in lines]
        return self._json[key]

    def get(self, relative: str, *tokens: Any) -> Any:
        """JSON(또는 .jsonl) 안의 값. 키가 없으면 ``ABSENT``."""
        document = self.jsonl(relative) if relative.endswith(".jsonl") else self.json(relative)
        return resolve_pointer(document, pointer(*tokens))

    # --- 출처 표기 -----------------------------------------------------------------------------------
    def src(self, relative: str, *tokens: Any) -> str:
        return ref(self.key, relative, pointer(*tokens))

    def value(self, relative: str, *tokens: Any, origin: str | None = None, note: str | None = None) -> dict[str, Any]:
        """저장 값을 출처와 함께 감싼다. 키가 없으면 ``absent`` 표시가 붙는다."""
        return V(self.get(relative, *tokens), self.src(relative, *tokens), origin=origin, note=note)

    def wrap(self, value: Any, relative: str, *tokens: Any, origin: str | None = None) -> dict[str, Any]:
        """이미 읽은 값을 출처와 함께 감싼다. 테스트가 ``src``를 다시 읽어 같은지 대조한다."""
        return V(value, self.src(relative, *tokens), origin=origin)

    # --- 목록·해시 ----------------------------------------------------------------------------------
    def inventory(self) -> list[dict[str, Any]]:
        """묶음 안 모든 항목(상대경로·크기·SHA-256·symlink 여부). symlink는 따라가지 않는다."""
        entries: list[dict[str, Any]] = []
        for directory, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames.sort()
            base = Path(directory)
            for name in sorted(dirnames):
                candidate = base / name
                if candidate.is_symlink():
                    entries.append({"path": candidate.relative_to(self.root).as_posix(), "symlink": True,
                                    "target": os.readlink(candidate)})
            for name in sorted(filenames):
                candidate = base / name
                relative = candidate.relative_to(self.root).as_posix()
                if candidate.is_symlink():
                    entries.append({"path": relative, "symlink": True, "target": os.readlink(candidate)})
                    continue
                entries.append({"path": relative, "size": candidate.stat().st_size, "sha256": sha256_file(candidate),
                                "media_type": media_type(relative)})
        return sorted(entries, key=lambda item: item["path"])

    def image_meta(self, relative: str) -> dict[str, Any] | None:
        if not self.exists(relative):
            return None
        data = self.bytes(relative)
        size = image_size(data)
        return {"path": relative, "width": size[0] if size else None, "height": size[1] if size else None,
                "sha256": hashlib.sha256(data).hexdigest(), "supported": size is not None}


def _reject_constant(value: str) -> Any:
    raise ValueError(f"JSON에 허용하지 않는 값: {value}")


__all__ = ["BundleReader", "sha256_file", "image_size", "media_type", "TEXT_SUFFIXES", "IMAGE_SUFFIXES", "ABSENT"]
