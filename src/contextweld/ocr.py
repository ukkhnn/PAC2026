"""교체 가능한 로컬 OCR 어댑터. 실패 시 모의 후보로 대체하지 않는다."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


class OCRUnavailable(RuntimeError):
    pass


def recognize(image: Path, root: Path) -> dict[str, Any]:
    if platform.system() != "Darwin" or shutil.which("swiftc") is None:
        raise OCRUnavailable("실제 사진 OCR에는 macOS와 Swift 개발 도구가 필요합니다. 예제 시연은 계속 사용할 수 있습니다.")
    source = root / "scripts/vision_ocr.swift"
    binary = root / ".local/bin/vision-ocr"
    with _LOCK:
        if not binary.exists() or source.stat().st_mtime > binary.stat().st_mtime:
            binary.parent.mkdir(parents=True, exist_ok=True)
            cache = root / ".local/swift-module-cache"
            cache.mkdir(parents=True, exist_ok=True)
            try:
                result = subprocess.run(["swiftc", "-module-cache-path", str(cache), str(source), "-o", str(binary)],
                                        capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise OCRUnavailable("로컬 OCR 도구를 준비하지 못했습니다.") from error
            if result.returncode:
                raise OCRUnavailable("로컬 OCR 도구 컴파일에 실패했습니다. Swift 개발 도구를 확인해주세요.")
    try:
        result = subprocess.run([str(binary), str(image)], capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OCRUnavailable("이미지 OCR을 완료하지 못했습니다.") from error
    if result.returncode:
        raise OCRUnavailable("이미지 OCR에 실패했습니다. PNG 또는 JPEG 이미지로 다시 시도해주세요.")
    return json.loads(result.stdout)
