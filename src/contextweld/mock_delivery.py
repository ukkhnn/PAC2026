"""문서 검토용 범위값을 로컬 HTTP 수신기에서 검사하고 수신 기록을 남긴다."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
from threading import Lock, Thread
import time
from typing import Any
from urllib.parse import urlsplit
import uuid

MAX_BODY_BYTES = 64 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _parse_json(raw: bytes) -> Any:
    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("유한하지 않은 JSON 수치입니다.")
        return parsed

    return json.loads(raw.decode("utf-8"), parse_float=finite_float,
                      parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))


def _locator(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    if "page" in value and (type(value["page"]) is not int or value["page"] < 1):
        return False
    if "bbox" in value:
        box = value["bbox"]
        if (not isinstance(box, list) or len(box) != 4 or not all(_number(item) for item in box)
                or not (0 <= box[0] < box[2] and 0 <= box[1] < box[3])):
            return False
    return True


def _reference(value: Any) -> bool:
    return (isinstance(value, dict) and _text(value.get("document_id")) and _text(value.get("revision"))
            and isinstance(value.get("source_hash"), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", value["source_hash"])) and _locator(value.get("locator")))


def _identity(reference: dict) -> tuple[str, str, str]:
    return reference["document_id"], reference["revision"], reference["source_hash"]


def _check_profile(profile: dict) -> None:
    if (not isinstance(profile, dict) or profile.get("schema_version") != "demo-target-profile.v1"
            or not _text(profile.get("profile_id")) or not _text(profile.get("contract_version"))
            or profile.get("purpose") != "demo_mock" or profile.get("evaluation_scope") != "document_review"
            or not isinstance(profile.get("parameters"), dict) or not profile["parameters"]):
        raise ValueError("문서 검토용 모의 프로파일이 필요합니다.")
    for name, spec in profile["parameters"].items():
        if not _text(name) or not isinstance(spec, dict) or spec.get("kind") not in {"range", "enum"}:
            raise ValueError("지원하지 않는 모의 파라미터 정의입니다.")
        if spec["kind"] == "range" and not _text(spec.get("unit")):
            raise ValueError("범위 파라미터에 단위가 필요합니다.")
        if spec["kind"] == "enum" and (not isinstance(spec.get("allowed_values"), list)
                                        or not spec["allowed_values"]
                                        or not all(_text(item) for item in spec["allowed_values"])):
            raise ValueError("열거 파라미터에 허용 문자열 목록이 필요합니다.")


def validate_command(command: Any, profile: dict) -> list[dict[str, str]]:
    """형식·범위·근거 참조만 검사한다. 물리적 적용성과 실행을 승인하지 않는다."""
    _check_profile(profile)
    errors: list[dict[str, str]] = []

    def error(path: str, code: str) -> None:
        errors.append({"path": path, "code": code})

    if not isinstance(command, dict):
        return [{"path": "$", "code": "object_required"}]
    expected = {"schema_version": "demo-command.v1", "contract_version": profile["contract_version"],
                "target_profile": profile["profile_id"], "purpose": "demo_mock", "evaluation_scope": "document_review"}
    for key, value in expected.items():
        if command.get(key) != value:
            error(key, "unsupported_contract_value")
    for key in ("execution_authorized", "application_authorized"):
        if command.get(key) is not False:
            error(key, "must_be_false")
    for key in ("command_id", "run_id", "spec_id"):
        if not _text(command.get(key)):
            error(key, "nonempty_string_required")
    target = command.get("target")
    if not isinstance(target, dict):
        error("target", "object_required")
    else:
        for key in ("project_id", "block_id", "work_order_id", "part_id", "joint_id"):
            if not _text(target.get(key)):
                error(f"target.{key}", "nonempty_string_required")
    documents = command.get("documents")
    identities = set()
    document_hashes: dict[tuple[str, str], str] = {}
    if not isinstance(documents, list) or not documents:
        error("documents", "nonempty_reference_array_required")
    else:
        for index, document in enumerate(documents):
            if not _reference(document):
                error(f"documents[{index}]", "invalid_document_reference")
                continue
            identity = _identity(document)
            if identity[:2] in document_hashes and document_hashes[identity[:2]] != identity[2]:
                error(f"documents[{index}]", "conflicting_document_hash")
            document_hashes[identity[:2]] = identity[2]
            identities.add(identity)
    parameters = command.get("parameters")
    if not isinstance(parameters, dict):
        error("parameters", "object_required")
        return errors
    for name in parameters.keys() - profile["parameters"].keys():
        error(f"parameters.{name}", "unexpected_parameter")
    for name, definition in profile["parameters"].items():
        field = parameters.get(name)
        path = f"parameters.{name}"
        if not isinstance(field, dict):
            error(path, "required_parameter_missing")
            continue
        if "unit" not in field or field["unit"] != definition.get("unit"):
            error(f"{path}.unit", "unit_mismatch")
        if field.get("source_kind") != "document":
            error(f"{path}.source_kind", "document_source_required")
        reference = field.get("evidence")
        if not _reference(reference):
            error(f"{path}.evidence", "invalid_document_reference")
        elif _identity(reference) not in identities:
            error(f"{path}.evidence", "unregistered_document_reference")
        if definition["kind"] == "range":
            if "value" in field:
                error(path, "range_required_no_scalar")
            if not _number(field.get("min")) or not _number(field.get("max")):
                error(path, "finite_numeric_range_required")
            elif field["min"] > field["max"]:
                error(path, "reversed_range")
        else:
            if "min" in field or "max" in field or field.get("value") not in definition["allowed_values"]:
                error(path, "unsupported_enum_value")
    return errors


class MockReceiver:
    """127.0.0.1 임의 포트에서만 동작하는 수신·검사·중복 기록 서버."""

    def __init__(self, profile: dict, log_path: Path) -> None:
        _check_profile(profile)
        self.profile = deepcopy(profile)
        self.log_path = Path(log_path)
        self.url: str | None = None
        self._lock = Lock()
        self._commands: dict[str, str] = {}
        self._seq = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self._log = None

    def _receive(self, raw: bytes, transport_errors: list[dict[str, str]], *,
                 status_override: int | None = None, body_read: bool = True) -> tuple[int, dict]:
        try:
            command = _parse_json(raw)
            errors = transport_errors + validate_command(command, self.profile)
        except (ValueError, UnicodeDecodeError):
            command = None
            errors = transport_errors + [{"path": "$", "code": "invalid_json"}]
        digest = hashlib.sha256(_canonical(command) if command is not None else raw).hexdigest()
        command_id = command.get("command_id") if isinstance(command, dict) and _text(command.get("command_id")) else None
        with self._lock:
            duplicate = False
            status_code = status_override or (422 if errors else 200)
            if command_id in self._commands:
                if self._commands[command_id] == digest:
                    duplicate = True
                else:
                    errors.append({"path": "command_id", "code": "command_id_payload_conflict"})
                    status_code = 409
            self._seq += 1
            ack = {"schema_version": "demo-ack.v1", "ack_id": str(uuid.uuid4()), "command_id": command_id,
                   "status": "rejected" if errors else "received", "received_at_utc": _now(),
                   "validation_errors": errors, "duplicate": duplicate, "command_sha256": digest,
                   "purpose": "demo_mock", "evaluation_scope": "document_review",
                   "application_authorized": False, "execution_authorized": False}
            record = {"seq": self._seq, "request_sha256": hashlib.sha256(raw).hexdigest(),
                      "raw_request": raw.decode("utf-8", errors="replace"), "command": command,
                      "body_read": body_read, "http_status": status_code, "ack": ack}
            # ACK 전에 기록을 확정하여 기록에 없는 정상 수신 응답을 보내지 않는다.
            self._log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            self._log.flush()
            os.fsync(self._log.fileno())
            if command_id is not None and command_id not in self._commands:
                self._commands[command_id] = digest
            return status_code, ack

    def __enter__(self) -> MockReceiver:
        if self._server is not None:
            raise RuntimeError("이미 시작한 수신기입니다.")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # 기존 실행의 로그와 중복 판정 상태를 새 실행에서 덮어쓰지 않는다.
        self._log = self.log_path.open("x", encoding="utf-8")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def reply(self, status_code: int, ack: dict) -> None:
                body = _canonical(ack)
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                if self.path != "/commands":
                    self.send_error(404)
                    return
                self.connection.settimeout(5)
                errors = []
                raw_length = self.headers.get("Content-Length")
                try:
                    length = int(raw_length) if raw_length is not None else -1
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY_BYTES:
                    errors = [{"path": "$", "code": "body_too_large" if length > MAX_BODY_BYTES else "content_length_required"}]
                    status_code, ack = owner._receive(b"", errors, status_override=413 if length > MAX_BODY_BYTES else 411,
                                                      body_read=False)
                    self.reply(status_code, ack)
                    return
                if self.headers.get_content_type() != "application/json":
                    errors.append({"path": "$", "code": "json_content_type_required"})
                if self.headers.get("Transfer-Encoding"):
                    errors.append({"path": "$", "code": "transfer_encoding_unsupported"})
                try:
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        errors.append({"path": "$", "code": "incomplete_request_body"})
                    status_code, ack = owner._receive(raw, errors)
                except (TimeoutError, OSError):
                    self.send_error(500)
                    return
                self.reply(status_code, ack)

        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self._server.daemon_threads = False
            port = self._server.server_address[1]
            self.url = f"http://127.0.0.1:{port}/commands"
            self._thread = Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            self._thread.start()
        except BaseException:
            self._log.close()
            if self._server is not None:
                self._server.server_close()
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=6)
        if self._log is not None:
            self._log.close()


def send_command(url: str, command: dict, timeout: float = 5) -> dict:
    """로컬 수신기에 한 번 전달한다. 타임아웃·연결 실패는 호출자에게 예외로 반환한다."""
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.path != "/commands" or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("127.0.0.1의 /commands 모의 수신기만 허용합니다.")
    if not _number(timeout) or not 0 < timeout <= 60:
        raise ValueError("타임아웃은 0 초과 60초 이하이어야 합니다.")
    body = _canonical(command)
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("모의 명령이 최대 크기를 넘습니다.")
    connection = HTTPConnection("127.0.0.1", parsed.port, timeout=timeout)
    sent_at = _now()
    started = time.monotonic()
    try:
        connection.request("POST", "/commands", body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES or response.status not in {200, 409, 422}:
            raise ValueError(f"예상하지 않은 모의 수신 응답: HTTP {response.status}")
        ack = _parse_json(raw)
        if (not isinstance(ack, dict) or ack.get("schema_version") != "demo-ack.v1"
                or ack.get("command_id") != command.get("command_id")
                or ack.get("status") != ("received" if response.status == 200 else "rejected")
                or ack.get("execution_authorized") is not False or ack.get("application_authorized") is not False
                or ack.get("purpose") != "demo_mock" or ack.get("evaluation_scope") != "document_review"
                or ack.get("command_sha256") != hashlib.sha256(body).hexdigest()):
            raise ValueError("모의 ACK 계약 또는 명령 연결이 일치하지 않습니다.")
        return {"schema_version": "demo-delivery.v1", "transport": "http_loopback", "endpoint": url,
                "sent_at_utc": sent_at, "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "http_status": response.status, "request_sha256": hashlib.sha256(body).hexdigest(),
                "request": deepcopy(command), "ack": ack}
    finally:
        connection.close()
