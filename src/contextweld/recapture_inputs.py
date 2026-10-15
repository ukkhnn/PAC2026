"""저장된 Isaac A/B 원본을 추론과 분리된 불변 입력 묶음으로 준비한다."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "recapture-inputs.v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid SHA256")
    return value


def _absolute(path: Path) -> Path:
    # resolve() 전에 검사해야 중간 심볼릭 링크를 놓치지 않는다.
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal is not allowed")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink is not allowed: {current}")
    return path


def _relative(root: Path, name: Any) -> Path:
    if (not isinstance(name, str) or not name or "\\" in name
            or PurePosixPath(name).is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError("invalid relative input path")
    path = _absolute(root / name)
    if not path.is_relative_to(root):
        raise ValueError("input path escapes root")
    return path


def _read(root: Path, name: str) -> bytes:
    path = _relative(root, name)
    if not path.is_file():
        raise ValueError(f"missing regular file: {name}")
    return path.read_bytes()


def _json(data: bytes) -> dict:
    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {field}")
    return value


def _utc(value: Any) -> datetime:
    value = _text(value, "captured_at_utc")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid captured_at_utc") from error
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("captured_at_utc must include the UTC timezone")
    return parsed


def _vector(value: Any, length: int, field: str) -> list:
    if (not isinstance(value, list) or len(value) != length
            or any(type(item) not in {int, float} or not math.isfinite(item) for item in value)):
        raise ValueError(f"invalid {field}")
    return value


def _dimensions(data: bytes) -> tuple[int, int]:
    from PIL import Image
    with Image.open(BytesIO(data)) as image:
        if image.format != "PNG":
            raise ValueError("saved capture must be PNG")
        image.verify()
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.size


def _frame(capture: dict, view: str, scenario: str, raw: bytes,
           wrist: bytes, overview: bytes) -> dict:
    if (capture.get("view") != view or capture.get("scenario_id") != scenario
            or capture.get("capture_mode") != "pre_captured"
            or capture.get("recognition_feedback_enabled") is not False):
        raise ValueError("capture identity or pre_captured provenance mismatch")
    for kind, data in (("wrist", wrist), ("overview", overview)):
        if capture.get(f"{kind}_saved_image") != f"frames/{view}-{kind}.png":
            raise ValueError("only canonical saved frames are allowed")
        if _sha(capture.get(f"{kind}_image_sha256")) != _digest(data):
            raise ValueError(f"saved {view}/{kind} image SHA256 mismatch")
    _utc(capture.get("captured_at_utc"))
    position = _vector(capture.get("camera_world_position"), 3, "camera position")
    quaternion = _vector(capture.get("camera_world_quaternion_wxyz"), 4, "camera quaternion")
    if abs(sum(item * item for item in quaternion) - 1.0) > 0.01:
        raise ValueError("camera quaternion is not normalized")
    width, height = _dimensions(wrist)
    overview_width, overview_height = _dimensions(overview)
    return {
        "frame_id": f"frame-{view}", "view": view,
        "image_ref": f"frames/{view}-wrist.png",
        "overview_ref": f"frames/{view}-overview.png",
        "width": width, "height": height,
        "overview_width": overview_width, "overview_height": overview_height,
        "sha256": _digest(wrist), "overview_sha256": _digest(overview),
        "captured_at_utc": capture["captured_at_utc"],
        "capture_time_semantics": _text(capture.get("capture_time_semantics"), "capture_time_semantics"),
        "camera_id": _text(capture.get("camera_prim_path"), "camera_prim_path"),
        "camera_pose": {
            "position": position, "quaternion_wxyz": quaternion,
            "camera_convention": _text(capture.get("camera_pose_convention"), "camera_pose_convention"),
            "world_convention": _text(capture.get("world_frame_convention"), "world_frame_convention"),
            "source": _text(capture.get("camera_pose_source"), "camera_pose_source"),
        },
        "source_capture_ref": f"provenance/{view}-capture.json",
        "source_capture_sha256": _digest(raw),
    }


def _distinct(frames: list[dict]) -> None:
    if frames[0]["sha256"] == frames[1]["sha256"]:
        raise ValueError("A and B wrist images must differ")
    if frames[0]["camera_id"] != frames[1]["camera_id"]:
        raise ValueError("A and B must use the same wrist camera")
    if frames[0]["camera_pose"] == frames[1]["camera_pose"]:
        raise ValueError("A and B camera poses must differ")
    if _utc(frames[1]["captured_at_utc"]) <= _utc(frames[0]["captured_at_utc"]):
        raise ValueError("B capture must follow A capture")


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def prepare_inputs(scene_root: Path, destination: Path) -> Path:
    """원본을 검증·복사해 inputs.json 경로를 반환한다. 실패한 staging은 보존한다."""
    scene_root, destination = _absolute(scene_root), _absolute(destination)
    if destination.is_relative_to(scene_root) or scene_root.is_relative_to(destination):
        raise ValueError("source and destination must not contain one another")
    staging = destination.with_name(destination.name + ".incomplete")
    _absolute(staging)
    if destination.exists() or staging.exists():
        raise FileExistsError("destination or its incomplete directory already exists")
    source_data = {"manifest.json": _read(scene_root, "manifest.json")}
    manifest = _json(source_data["manifest.json"])
    scenario = _text(manifest.get("scenario_id"), "scenario_id")
    files: dict[str, bytes] = {}
    frames = []
    for view in ("A", "B"):
        capture_name = f"frames/{view}-capture.json"
        raw = source_data[capture_name] = _read(scene_root, capture_name)
        capture = _json(raw)
        # stream/가 존재해도 열지 않는다. 고정 경로와 JSON의 saved 참조가 모두 맞아야 한다.
        for kind in ("wrist", "overview"):
            name = f"frames/{view}-{kind}.png"
            if capture.get(f"{kind}_saved_image") != name:
                raise ValueError("only canonical saved frames are allowed")
            files[name] = source_data[name] = _read(scene_root, name)
        files[f"provenance/{view}-capture.json"] = raw
        frames.append(_frame(capture, view, scenario, raw,
                             files[f"frames/{view}-wrist.png"], files[f"frames/{view}-overview.png"]))
    _distinct(frames)
    inputs = {
        "schema_version": SCHEMA, "capture_mode": "pre_captured",
        "inference_status": "not_run", "source_kind": "simulator",
        "scenario_id": scenario, "source_manifest_sha256": _digest(source_data["manifest.json"]),
        "frames": frames,
    }
    files["inputs.json"] = _encoded(inputs)
    files["checksums.json"] = _encoded({name: _digest(data) for name, data in sorted(files.items())})
    destination.parent.mkdir(parents=True, exist_ok=True)
    _absolute(destination.parent)
    staging.mkdir()
    for name, data in files.items():
        path = _relative(staging, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
    # 복사 중 변경된 원본은 새 묶음의 출처로 확정하지 않는다.
    for name, data in source_data.items():
        if _read(scene_root, name) != data:
            raise ValueError(f"source changed during preparation: {name}")
    verify_inputs(staging)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("destination appeared during preparation")
    os.rename(staging, destination)
    return destination / "inputs.json"


def verify_inputs(root: Path) -> dict:
    """전체 파일 목록·SHA·픽셀 크기·촬영 계보를 검증하고 입력 객체를 반환한다."""
    root = _absolute(root)
    if not root.is_dir():
        raise ValueError("input root must be a directory")
    actual = set()
    for directory, subdirs, names in os.walk(root, followlinks=False):
        for name in subdirs + names:
            path = _absolute(Path(directory) / name)
            if name in names:
                if not path.is_file():
                    raise ValueError("input package contains a non-regular file")
                actual.add(path.relative_to(root).as_posix())
    checksums = _json(_read(root, "checksums.json"))
    if set(checksums) != actual - {"checksums.json"}:
        raise ValueError("checksum file list mismatch")
    for name, expected in checksums.items():
        if _digest(_read(root, name)) != _sha(expected):
            raise ValueError(f"input SHA256 mismatch: {name}")
    inputs = _json(_read(root, "inputs.json"))
    if (inputs.get("schema_version") != SCHEMA or inputs.get("capture_mode") != "pre_captured"
            or inputs.get("inference_status") != "not_run" or inputs.get("source_kind") != "simulator"):
        raise ValueError("invalid recapture input schema or provenance")
    if set(inputs) != {"schema_version", "capture_mode", "inference_status", "source_kind",
                       "scenario_id", "source_manifest_sha256", "frames"}:
        raise ValueError("unexpected input fields")
    _sha(inputs.get("source_manifest_sha256"))
    scenario = _text(inputs.get("scenario_id"), "scenario_id")
    frames = inputs.get("frames")
    if not isinstance(frames, list) or len(frames) != 2:
        raise ValueError("exactly A and B frames are required")
    expected_files = {"inputs.json", "checksums.json"}
    for view, frame in zip(("A", "B"), frames):
        capture_name = f"provenance/{view}-capture.json"
        wrist_name, overview_name = f"frames/{view}-wrist.png", f"frames/{view}-overview.png"
        raw, wrist, overview = (_read(root, name) for name in (capture_name, wrist_name, overview_name))
        expected = _frame(_json(raw), view, scenario, raw, wrist, overview)
        if frame != expected:
            raise ValueError(f"derived metadata differs from capture provenance: {view}")
        expected_files.update((capture_name, wrist_name, overview_name))
    if actual != expected_files:
        raise ValueError("unexpected files in input package")
    _distinct(frames)
    return inputs
