"""로컬 화면과 분석·확인 API를 제공한다."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import mimetypes
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ocr import OCRUnavailable, recognize
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 12 * 1024 * 1024


def validate_observations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 200:
        raise ValueError("1~200개의 표기 영역이 필요합니다.")
    ids = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in ids:
            raise ValueError("표기 영역의 고유 식별자를 확인해주세요.")
        ids.add(item["id"])
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or any(not isinstance(n, (float, int)) or isinstance(n, bool) or not math.isfinite(n) or not 0 <= n <= 1 for n in bbox):
            raise ValueError("표기 영역은 정규화한 좌표 4개여야 합니다.")
        if bbox[0] + bbox[2] > 1.01 or bbox[1] + bbox[3] > 1.01:
            raise ValueError("표기 영역이 이미지 범위를 벗어났습니다.")
        candidates = item.get("candidates")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 10:
            raise ValueError("영역별 문자 후보가 필요합니다.")
        for candidate in candidates:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("text"), str) or len(candidate["text"]) > 1000:
                raise ValueError("문자 후보의 형식이 올바르지 않습니다.")
            score = candidate.get("score")
            if score is not None and (not isinstance(score, (float, int)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError("OCR 점수는 0~1 범위여야 합니다.")
    return value


def validate_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("작업 맥락은 객체여야 합니다.")
    allowed = {"part_id", "seam_id", "expected_size_mm", "weld_type", "material", "thickness_mm", "position", "plan_revision", "preceding_complete"}
    result = {key: val for key, val in value.items() if key in allowed}
    for key in ("part_id", "seam_id", "weld_type", "material", "position", "plan_revision"):
        val = result.get(key)
        if val is not None and (not isinstance(val, str) or len(val) > 100):
            raise ValueError(f"{key}는 짧은 문자열이어야 합니다.")
    for key in ("thickness_mm", "expected_size_mm"):
        val = result.get(key)
        if val is not None and (not isinstance(val, (float, int)) or isinstance(val, bool) or not math.isfinite(val) or not 0 < val <= 200):
            raise ValueError(f"{key}의 숫자 범위를 확인해주세요.")
    if result.get("preceding_complete") is not None and not isinstance(result["preceding_complete"], bool):
        raise ValueError("선행작업 상태를 확인해주세요.")
    return result


def create_server(port: int = 8765, root: Path = ROOT, database: Path | None = None) -> ThreadingHTTPServer:
    store = Store(database or root / ".local/contextweld.sqlite3")
    knowledge = json.loads((root / "data/knowledge/demo-rules.json").read_text())
    scenarios = json.loads((root / "data/examples/scenarios.json").read_text())
    by_id = {item["id"]: item for item in scenarios}
    web = root / "src/contextweld/web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # 이미지·작업 맥락이나 개인 입력을 로그에 출력하지 않는다.
            pass

        def send_bytes(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, status: int, payload: Any) -> None:
            self.send_bytes(status, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), "application/json; charset=utf-8")

        def valid_host(self) -> bool:
            host = self.headers.get("Host", "").split(":")[0]
            return host in {"127.0.0.1", "localhost"}

        def do_GET(self) -> None:
            if not self.valid_host():
                self.send_json(403, {"error": "로컬 주소에서만 접근할 수 있습니다."})
                return
            path = urlsplit(self.path).path
            if path == "/api/health":
                self.send_json(200, {"ok": True, "rules_version": knowledge["version"]})
            elif path == "/api/scenarios":
                self.send_json(200, scenarios)
            elif path == "/api/history":
                self.send_json(200, store.history())
            elif re.fullmatch(r"/api/runs/[a-f0-9]{32}", path):
                try:
                    self.send_json(200, store.get(path.rsplit("/", 1)[1]))
                except KeyError:
                    self.send_json(404, {"error": "분석 기록이 없습니다."})
            else:
                allowed = {"/": web / "index.html", "/app.js": web / "app.js", "/style.css": web / "style.css"}
                if re.fullmatch(r"/examples/[a-z-]+\.svg", path):
                    allowed[path] = root / "data/examples" / path.rsplit("/", 1)[1]
                if re.fullmatch(r"/uploads/[a-f0-9]{32}\.(png|jpg)", path):
                    allowed[path] = root / ".local/uploads" / path.rsplit("/", 1)[1]
                target = allowed.get(path)
                if target is None or not target.is_file():
                    self.send_json(404, {"error": "파일을 찾을 수 없습니다."})
                else:
                    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                    self.send_bytes(200, target.read_bytes(), mime + ("; charset=utf-8" if mime.startswith("text/") else ""))

        def do_POST(self) -> None:
            try:
                if not self.valid_host():
                    self.send_json(403, {"error": "로컬 주소에서만 접근할 수 있습니다."})
                    return
                origin = self.headers.get("Origin")
                if origin and origin != f"http://{self.headers.get('Host')}":
                    self.send_json(403, {"error": "같은 로컬 화면에서 요청해주세요."})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.send_json(413, {"error": "입력 크기는 12 MB 이하여야 합니다."})
                    return
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("JSON 입력이 필요합니다.")
                payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("유한한 숫자가 필요합니다.")))
                if not isinstance(payload, dict):
                    raise ValueError("입력은 객체여야 합니다.")
                path = urlsplit(self.path).path
                if path == "/api/analyze":
                    started = time.perf_counter()
                    if "scenario_id" in payload:
                        case = by_id.get(payload["scenario_id"])
                        if case is None:
                            raise ValueError("시연 사례를 찾을 수 없습니다.")
                        observations = validate_observations(case["observations"])
                        source = {key: case[key] for key in ("source_kind", "provider", "image_url")}
                        source["scenario_id"] = case["id"]
                        source["image_sha256"] = hashlib.sha256((root / "data/examples" / f"{case['id']}.svg").read_bytes()).hexdigest()
                        context = validate_context(payload.get("context", case["context"]))
                    else:
                        upload_id = payload.get("upload_id", "")
                        if not isinstance(upload_id, str) or not re.fullmatch(r"[a-f0-9]{32}", upload_id):
                            raise ValueError("업로드한 사진을 먼저 선택해주세요.")
                        record_path = root / ".local/uploads" / f"{upload_id}.json"
                        if not record_path.exists():
                            raise ValueError("업로드 기록이 없습니다.")
                        record = json.loads(record_path.read_text())
                        observations = validate_observations(record["observations"])
                        source = record["source"]
                        context = validate_context(payload.get("context", {}))
                    run = store.create(source, observations, context, knowledge)
                    run["response_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
                    self.send_json(200, run)
                elif path == "/api/upload":
                    encoded = payload.get("image_base64")
                    if not isinstance(encoded, str):
                        raise ValueError("이미지 데이터가 필요합니다.")
                    try:
                        image = base64.b64decode(encoded, validate=True)
                    except binascii.Error as error:
                        raise ValueError("이미지 인코딩을 확인해주세요.") from error
                    suffix = "png" if image.startswith(b"\x89PNG\r\n\x1a\n") else "jpg" if image.startswith(b"\xff\xd8\xff") else None
                    if suffix is None:
                        raise ValueError("PNG 또는 JPEG 이미지만 지원합니다.")
                    upload_id = uuid.uuid4().hex
                    directory = root / ".local/uploads"
                    directory.mkdir(parents=True, exist_ok=True)
                    image_path = directory / f"{upload_id}.{suffix}"
                    image_path.write_bytes(image)
                    try:
                        ocr = recognize(image_path, root)
                    except OCRUnavailable:
                        image_path.unlink(missing_ok=True)
                        raise
                    source = {"source_kind": "user_upload", "provider": ocr["provider"],
                              "image_url": f"/uploads/{image_path.name}", "image_sha256": hashlib.sha256(image).hexdigest()}
                    record = {"source": source, "observations": ocr["observations"]}
                    (directory / f"{upload_id}.json").write_text(json.dumps(record, ensure_ascii=False))
                    self.send_json(200, {"upload_id": upload_id, **record})
                elif path == "/api/review":
                    corrections = payload.get("corrections", {})
                    if not isinstance(corrections, dict):
                        raise ValueError("수정 항목은 객체여야 합니다.")
                    if not isinstance(payload.get("note"), str) or len(payload["note"]) > 2000:
                        raise ValueError("확인 이유는 2000자 이내로 입력해주세요.")
                    revision = payload.get("revision")
                    if not isinstance(revision, int) or isinstance(revision, bool):
                        raise ValueError("분석 버전이 필요합니다.")
                    self.send_json(200, store.review(payload.get("run_id", ""), payload.get("action", ""), payload["note"], corrections, revision, knowledge))
                else:
                    self.send_json(404, {"error": "요청 경로가 없습니다."})
            except (ValueError, TypeError, KeyError) as error:
                self.send_json(400, {"error": str(error)})
            except OCRUnavailable as error:
                self.send_json(503, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "처리를 완료하지 못했습니다. 입력과 로컬 실행 환경을 확인해주세요."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="ContextWeld 로컬 spike")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f"ContextWeld: http://127.0.0.1:{server.server_port}", flush=True)
    print("시연 규칙 기반 로컬 프로토타입 · 종료: Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
