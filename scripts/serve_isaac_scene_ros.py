#!/usr/bin/env python3
"""Isaac가 저장한 실제 RGB와 장면 상태를 기존 ROS/Foxglove 연결에 발행한다.

생산자는 PNG/JPEG 두 파일을 먼저 교체하고 stream/current.json을 마지막에
atomic replace한다. JSON의 이미지 경로는 --output-root 기준 상대경로다.
ROS가 없는 환경에서도 --check-input으로 원본·시각·경로 계약을 검사할 수 있다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 32 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def finite_vector(value: Any, size: int) -> bool:
    return (isinstance(value, list) and len(value) == size
            and all(type(item) in (int, float) and math.isfinite(item) for item in value))


def confined_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or Path(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("장면 파일에는 출력 루트 안의 상대경로가 필요합니다.")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("장면 파일 경로가 출력 루트를 벗어납니다.")
    return path


def capture_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("captured_at_utc 문자열이 필요합니다.")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("captured_at_utc에는 시간대가 필요합니다.")
    stamp = stamp.astimezone(timezone.utc)
    if stamp.timestamp() < 0 or stamp.timestamp() >= 2 ** 31:
        raise ValueError("촬영 시각이 ROS Time의 지원 범위 밖입니다.")
    return stamp


def encoded_image(path: Path) -> dict[str, Any]:
    """재인코딩 없이 실제 파일을 읽는다. PNG의 색 형식은 IHDR에서 확인한다."""
    before = path.stat()
    if not path.is_file() or not 0 < before.st_size <= MAX_IMAGE_BYTES:
        raise ValueError("영상 파일 크기가 없거나 허용 범위를 넘습니다.")
    data = path.read_bytes()
    after = path.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
        raise ValueError("영상 파일이 읽는 도중 교체됐습니다. 다음 갱신에서 재시도합니다.")
    width, height = None, None
    if data.startswith(PNG_SIGNATURE) and len(data) >= 33 and data[12:16] == b"IHDR":
        if not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
            raise ValueError("PNG 파일이 완전하게 저장되지 않았습니다.")
        width, height, depth, color = struct.unpack(">IIBB", data[16:26])
        encodings = {(8, 0): "mono8", (16, 0): "mono16", (8, 2): "rgb8", (16, 2): "rgb16"}
        encoding = encodings.get((depth, color))
        if encoding is None:
            raise ValueError("PNG는 RGB 또는 grayscale 8/16bit로 저장해야 합니다. 팔레트/alpha는 지원하지 않습니다.")
        image_format = f"{encoding}; png compressed" + (f" {encoding}" if color == 2 else "")
        codec = "png"
        if not width or not height or width * height > 64 * 1024 * 1024:
            raise ValueError("PNG 크기가 유효하지 않습니다.")
    elif data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        # JPEG의 원본 픽셀 배열은 제공받지 않았으므로 인코딩을 추정하지 않는다.
        image_format, codec = "jpeg", "jpeg"
    else:
        raise ValueError("PNG 또는 완전한 JPEG 영상 파일이 필요합니다.")
    return {"data": data, "format": image_format, "codec": codec, "width": width,
            "height": height, "sha256": hashlib.sha256(data).hexdigest(), "mtime_ns": after.st_mtime_ns}


def read_snapshot(output_root: Path, relative: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    current = confined_path(output_root, relative)
    before = current.stat()
    if before.st_size > 1024 * 1024:
        raise ValueError("current.json이 허용 크기를 넘습니다.")
    raw = current.read_bytes()
    payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(payload, dict):
        raise ValueError("current.json은 객체여야 합니다.")
    if type(payload.get("sequence")) is not int or payload["sequence"] < 0:
        raise ValueError("sequence는 0 이상의 정수여야 합니다.")
    if not isinstance(payload.get("view"), str) or not payload["view"].strip():
        raise ValueError("현재 장면의 view 문자열이 필요합니다.")
    capture_time(payload.get("captured_at_utc"))
    for key, length in (("camera_world_position", 3), ("camera_world_quaternion_wxyz", 4)):
        if payload.get(key) is not None and not finite_vector(payload[key], length):
            raise ValueError(f"{key}가 유한한 {length}개 수치가 아닙니다.")
    if payload.get("camera_world_quaternion_wxyz") is not None:
        norm = sum(x * x for x in payload["camera_world_quaternion_wxyz"])
        if not 0.99 <= norm <= 1.01:
            raise ValueError("카메라 quaternion이 단위 quaternion이 아닙니다.")
    links = payload.get("robot_link_positions", {})
    if not isinstance(links, dict) or any(not isinstance(name, str) or not finite_vector(point, 3)
                                          for name, point in links.items()):
        raise ValueError("robot_link_positions는 이름→world xyz 객체여야 합니다.")
    joints = payload.get("joint_positions", [])
    if not isinstance(joints, list) or not all(type(x) in (int, float) and math.isfinite(x) for x in joints):
        raise ValueError("joint_positions는 유한한 각도 배열이어야 합니다.")
    images = {}
    for name in ("wrist", "overview"):
        images[name] = encoded_image(confined_path(output_root, payload[f"{name}_image"]))
        expected_hash = payload.get(f"{name}_image_sha256")
        if expected_hash is not None and expected_hash != images[name]["sha256"]:
            raise ValueError(f"{name} 영상과 current.json의 해시가 다릅니다.")
        if images[name]["mtime_ns"] > before.st_mtime_ns:
            raise ValueError("영상 교체 후 current.json 갱신을 기다리는 중입니다.")
    after = current.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size) or current.read_bytes() != raw:
        raise ValueError("장면 메타데이터가 읽는 도중 변경됐습니다.")
    return payload, images


def snapshot_summary(payload: dict[str, Any], images: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"sequence": payload["sequence"], "view": payload["view"],
            "captured_at_utc": payload["captured_at_utc"],
            "images": {name: {key: image[key] for key in ("format", "width", "height", "sha256")}
                       for name, image in images.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--current", default="stream/current.json")
    parser.add_argument("--poll-hz", type=float, default=5.0)
    parser.add_argument("--repeat-interval", type=float, default=0,
                        help="같은 촬영의 재송출 간격(초), 0이면 새 sequence만 영상 송출")
    parser.add_argument("--stale-after", type=float, default=5.0)
    parser.add_argument("--wrist-topic", default="/contextweld/wrist/image")
    parser.add_argument("--overview-topic", default="/contextweld/overview/image")
    parser.add_argument("--status-topic", default="/contextweld/status")
    parser.add_argument("--camera-alias", help="손목 영상의 추가 topic, 예: /camera")
    parser.add_argument("--world-frame", default="world")
    parser.add_argument("--wrist-frame", default="contextweld_wrist_optical")
    parser.add_argument("--overview-frame", default="contextweld_overview_optical")
    parser.add_argument("--publish-map-tf", action="store_true", help="map→world 항등 TF 발행")
    parser.add_argument("--publish-link-markers", action="store_true", help="실제 world link 좌표를 점으로 표시")
    parser.add_argument("--check-input", action="store_true", help="ROS 없이 한 스냅샷을 검증하고 종료")
    args = parser.parse_args(argv)
    if (not math.isfinite(args.poll_hz) or not 0 < args.poll_hz <= 60
            or not math.isfinite(args.repeat_interval) or args.repeat_interval < 0
            or not math.isfinite(args.stale_after) or args.stale_after <= 0):
        parser.error("폴링/재송출/오래된 프레임 판정 간격이 유효하지 않습니다.")
    if args.publish_map_tf and args.world_frame == "map":
        parser.error("map→map 정적 TF는 발행할 수 없습니다.")
    if args.check_input:
        try:
            payload, images = read_snapshot(args.output_root, args.current)
            print(json.dumps(snapshot_summary(payload, images), ensure_ascii=False, indent=2))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"장면 스냅샷 검사 실패: {exc}", file=sys.stderr)
            return 1
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from sensor_msgs.msg import CompressedImage
        from std_msgs.msg import String
        from geometry_msgs.msg import TransformStamped, Point
        from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster
        from visualization_msgs.msg import Marker, MarkerArray
    except ImportError as exc:
        print(f"ROS Jazzy 환경을 source한 Python으로 실행해야 합니다: {exc}", file=sys.stderr)
        return 2

    class ScenePublisher(Node):
        def __init__(self) -> None:
            super().__init__("contextweld_isaac_scene")
            qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.image_publishers = {"wrist": self.create_publisher(CompressedImage, args.wrist_topic, qos),
                                     "overview": self.create_publisher(CompressedImage, args.overview_topic, qos)}
            self.alias = self.create_publisher(CompressedImage, args.camera_alias, qos) if args.camera_alias else None
            self.status = self.create_publisher(String, args.status_topic, qos)
            self.tf = TransformBroadcaster(self)
            self.static_tf = StaticTransformBroadcaster(self)
            self.markers = self.create_publisher(MarkerArray, "/contextweld/robot_link_samples", qos) if args.publish_link_markers else None
            self.last_key: tuple[Any, ...] | None = None
            self.last_publish = 0.0
            self.last_status = 0.0
            self.last_error: str | None = None
            if args.publish_map_tf:
                transform = TransformStamped()
                transform.header.stamp = self.get_clock().now().to_msg()
                transform.header.frame_id, transform.child_frame_id = "map", args.world_frame
                transform.transform.rotation.w = 1.0
                self.static_tf.sendTransform(transform)
            self.create_timer(1 / args.poll_hz, self.poll)
            self.get_logger().info("Isaac 저장 RGB 발행 시작; 기존 bridge와 ROS domain 설정을 그대로 사용합니다.")

        def stamp(self, value: str) -> Any:
            instant = capture_time(value)
            stamp = self.get_clock().now().to_msg()
            stamp.sec = int(instant.timestamp())
            stamp.nanosec = instant.microsecond * 1000
            return stamp

        def poll(self) -> None:
            try:
                payload, images = read_snapshot(args.output_root, args.current)
                captured = capture_time(payload["captured_at_utc"])
                key = (payload.get("run_id"), payload["sequence"], payload["captured_at_utc"])
                new_capture = key != self.last_key
                now = time.monotonic()
                repeated = not new_capture and args.repeat_interval > 0 and now - self.last_publish >= args.repeat_interval
                if new_capture or repeated:
                    stamp = self.stamp(payload["captured_at_utc"])
                    for name, publisher in self.image_publishers.items():
                        message = CompressedImage()
                        message.header.stamp = stamp
                        message.header.frame_id = args.wrist_frame if name == "wrist" else args.overview_frame
                        message.format, message.data = images[name]["format"], images[name]["data"]
                        publisher.publish(message)
                        if name == "wrist" and self.alias is not None:
                            self.alias.publish(message)
                    if (payload.get("camera_pose_convention") == "ros_optical"
                            and payload.get("camera_world_position") is not None
                            and payload.get("camera_world_quaternion_wxyz") is not None):
                        transform = TransformStamped()
                        transform.header.stamp = stamp
                        transform.header.frame_id, transform.child_frame_id = args.world_frame, args.wrist_frame
                        xyz, quat = payload["camera_world_position"], payload["camera_world_quaternion_wxyz"]
                        transform.transform.translation.x = float(xyz[0])
                        transform.transform.translation.y = float(xyz[1])
                        transform.transform.translation.z = float(xyz[2])
                        transform.transform.rotation.w = float(quat[0])
                        transform.transform.rotation.x = float(quat[1])
                        transform.transform.rotation.y = float(quat[2])
                        transform.transform.rotation.z = float(quat[3])
                        self.tf.sendTransform(transform)
                    if self.markers is not None:
                        marker = Marker()
                        marker.header.stamp, marker.header.frame_id = stamp, args.world_frame
                        marker.ns, marker.id, marker.type, marker.action = "actual_link_positions", 0, Marker.SPHERE_LIST, Marker.ADD
                        marker.pose.orientation.w = 1.0
                        marker.scale.x = marker.scale.y = marker.scale.z = 0.035
                        marker.color.r, marker.color.g, marker.color.b, marker.color.a = 0.15, 0.7, 1.0, 1.0
                        marker.points = [Point(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]))
                                         for xyz in payload.get("robot_link_positions", {}).values()]
                        self.markers.publish(MarkerArray(markers=[marker]))
                    self.last_key, self.last_publish = key, now
                if new_capture or repeated or now - self.last_status >= 1:
                    age = max(0.0, (datetime.now(timezone.utc) - captured).total_seconds())
                    status = {"schema_version": "isaac-scene-status.v1", **snapshot_summary(payload, images),
                              "published_at_utc": utc_now(), "capture_age_seconds": round(age, 3),
                              "source_state": "stale" if age > args.stale_after else "recent_capture",
                              "image_published": new_capture or repeated,
                              "publication_kind": "new_capture" if new_capture else "held_capture_republish" if repeated else "held_capture_status",
                              "capture_mode": payload.get("capture_mode", "pre_captured"),
                              "header_stamp_source": "captured_at_utc", "execution_authorized": False,
                              "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"), "scene": payload}
                    message = String()
                    message.data = json.dumps(status, ensure_ascii=False, allow_nan=False)
                    self.status.publish(message)
                    self.last_status = now
                self.last_error = None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                detail = f"{type(exc).__name__}: {exc}"
                now = time.monotonic()
                if detail != self.last_error:
                    self.get_logger().warning("장면 스냅샷 대기: " + detail)
                    self.last_error = detail
                if now - self.last_status >= 1:
                    message = String()
                    message.data = json.dumps({"schema_version": "isaac-scene-status.v1", "source_state": "waiting_for_valid_snapshot",
                                               "published_at_utc": utc_now(), "error": detail, "image_published": False,
                                               "execution_authorized": False}, ensure_ascii=False)
                    self.status.publish(message)
                    self.last_status = now

    rclpy.init(args=[])
    node = None
    try:
        node = ScenePublisher()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
