#!/usr/bin/env python3
"""Receive the Isaac scene stream through the Foxglove WebSocket bridge and verify it end to end.

Connects to the existing foxglove_bridge (default ``ws://127.0.0.1:8765``) exactly like a Foxglove
client, subscribes to the scene topics, decodes the CDR payloads itself and reports what actually
arrived: PNG images that decode at the expected size, status JSON whose ``sequence`` and
``captured_at_utc`` advance, image/status SHA-256 agreement, the ``/camera`` alias, and TF frames.
Bridge advertisement alone is never counted as reception.

Run with a Python that has ``websockets`` and ``Pillow`` (the Isaac Sim 6.1 venv does):

    /workspace/venvs/isaacsim-6.1/bin/python scripts/isaac/check_isaac_scene_stream.py \
        --seconds 40 --expect-scenario shipyard-handwriting-glare-01 \
        --report output/isaac-shipyard-20261010/<run>/reception-01.json

The exit status is 0 only when every check passed. The report is a plain JSON file.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json
import struct
import sys
import time
from typing import Any

IMAGE_TOPICS = ("/contextweld/wrist/image", "/contextweld/overview/image", "/camera")
STATUS_TOPIC = "/contextweld/status"
TF_TOPICS = ("/tf", "/tf_static")


class Cdr:
    """Minimal XCDR1 reader for the ROS 2 message layouts used by the scene stream."""

    def __init__(self, payload: bytes) -> None:
        if len(payload) < 4:
            raise ValueError("CDR payload shorter than the encapsulation header")
        self.buf = payload
        self.pos = 4
        self.prefix = "<" if payload[1] == 1 else ">"

    def _align(self, size: int) -> None:
        offset = (self.pos - 4) % size
        if offset:
            self.pos += size - offset

    def _unpack(self, fmt: str, size: int):
        self._align(size)
        value = struct.unpack_from(self.prefix + fmt, self.buf, self.pos)[0]
        self.pos += size
        return value

    def u32(self) -> int:
        return self._unpack("I", 4)

    def i32(self) -> int:
        return self._unpack("i", 4)

    def f64(self) -> float:
        return self._unpack("d", 8)

    def string(self) -> str:
        length = self.u32()
        raw = self.buf[self.pos:self.pos + length]
        self.pos += length
        return raw.rstrip(b"\x00").decode("utf-8", errors="replace")

    def byte_sequence(self) -> bytes:
        length = self.u32()
        raw = self.buf[self.pos:self.pos + length]
        self.pos += length
        return bytes(raw)

    def header(self) -> dict[str, Any]:
        sec, nanosec = self.i32(), self.u32()
        return {"stamp_sec": sec, "stamp_nanosec": nanosec, "frame_id": self.string()}


def decode_compressed_image(payload: bytes) -> dict[str, Any]:
    reader = Cdr(payload)
    header = reader.header()
    fmt = reader.string()
    data = reader.byte_sequence()
    return {"header": header, "format": fmt, "data": data}


def decode_string(payload: bytes) -> str:
    return Cdr(payload).string()


def decode_tf_message(payload: bytes) -> list[dict[str, Any]]:
    reader = Cdr(payload)
    count = reader.u32()
    transforms = []
    for _ in range(count):
        header = reader.header()
        child = reader.string()
        translation = [reader.f64() for _ in range(3)]
        rotation = [reader.f64() for _ in range(4)]
        transforms.append({"header": header, "child_frame_id": child, "translation": translation, "rotation": rotation})
    return transforms


def stamp_to_iso(sec: int, nanosec: int) -> str:
    return datetime.fromtimestamp(sec + nanosec / 1e9, tz=timezone.utc).isoformat()


async def receive(url: str, seconds: float, topics: list[str]) -> dict[str, Any]:
    import websockets

    channels: dict[int, dict[str, Any]] = {}
    subscriptions: dict[int, str] = {}
    subscribed_channel_ids: set[int] = set()
    messages: list[dict[str, Any]] = []
    server_info: dict[str, Any] | None = None
    deadline = time.monotonic() + seconds
    # foxglove_bridge 3.x (Foxglove SDK) negotiates "foxglove.sdk.v1"; older bridges used "foxglove.websocket.v1".
    async with websockets.connect(url, subprotocols=["foxglove.sdk.v1", "foxglove.websocket.v1"], max_size=64 * 1024 * 1024) as ws:
        negotiated = ws.subprotocol
        next_sub_id = 1
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=max(0.05, min(1.0, remaining)))
            except asyncio.TimeoutError:
                continue
            received_at = time.time()
            if isinstance(message, (bytes, bytearray)):
                data = bytes(message)
                if not data or data[0] != 0x01:
                    continue
                sub_id = struct.unpack_from("<I", data, 1)[0]
                log_ns = struct.unpack_from("<Q", data, 5)[0]
                topic = subscriptions.get(sub_id)
                if topic is None:
                    continue
                messages.append({"topic": topic, "received_at_unix": received_at, "bridge_log_time_ns": log_ns, "payload": data[13:]})
                continue
            event = json.loads(message)
            op = event.get("op")
            if op == "serverInfo":
                server_info = {k: event.get(k) for k in ("name", "capabilities", "supportedEncodings", "metadata")}
            elif op == "advertise":
                wanted = []
                for channel in event.get("channels", []):
                    channels[channel["id"]] = channel
                    if channel.get("topic") in topics and channel["id"] not in subscribed_channel_ids:
                        wanted.append(channel)
                        subscribed_channel_ids.add(channel["id"])
                if wanted:
                    payload = {"op": "subscribe", "subscriptions": []}
                    for channel in wanted:
                        subscriptions[next_sub_id] = channel["topic"]
                        payload["subscriptions"].append({"id": next_sub_id, "channelId": channel["id"]})
                        next_sub_id += 1
                    await ws.send(json.dumps(payload))
            elif op == "unadvertise":
                for channel_id in event.get("channelIds", []):
                    channels.pop(channel_id, None)
                    subscribed_channel_ids.discard(channel_id)
    return {"server_info": server_info, "negotiated_subprotocol": negotiated, "channels": {c["topic"]: {"id": c["id"], "encoding": c.get("encoding"), "schemaName": c.get("schemaName")}
                                                   for c in channels.values()}, "subscribed_topics": sorted(set(subscriptions.values())), "messages": messages}


def analyse(raw: dict[str, Any], expect_scenario: str | None, expected_size: tuple[int, int],
            window_start: datetime | None = None) -> dict[str, Any]:
    from PIL import Image

    images: dict[str, list[dict[str, Any]]] = {topic: [] for topic in IMAGE_TOPICS}
    statuses: list[dict[str, Any]] = []
    tf_dynamic: list[dict[str, Any]] = []
    tf_static: list[dict[str, Any]] = []
    decode_errors: list[str] = []
    for item in raw["messages"]:
        topic, payload = item["topic"], item["payload"]
        try:
            if topic in IMAGE_TOPICS:
                decoded = decode_compressed_image(payload)
                data = decoded["data"]
                size, mode = None, None
                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                    with Image.open(io.BytesIO(data)) as im:
                        im.load()
                        size, mode = im.size, im.mode
                images[topic].append({"stamp": stamp_to_iso(decoded["header"]["stamp_sec"], decoded["header"]["stamp_nanosec"]),
                                      "frame_id": decoded["header"]["frame_id"], "format": decoded["format"], "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest(), "size": size, "mode": mode,
                                      "received_at_unix": item["received_at_unix"]})
            elif topic == STATUS_TOPIC:
                status = json.loads(decode_string(payload))
                status["_received_at_unix"] = item["received_at_unix"]
                statuses.append(status)
            elif topic == "/tf":
                tf_dynamic.extend(decode_tf_message(payload))
            elif topic == "/tf_static":
                tf_static.extend(decode_tf_message(payload))
        except Exception as exc:  # noqa: BLE001 - report every decode failure, do not hide it
            decode_errors.append(f"{topic}: {type(exc).__name__}: {exc}")

    # TRANSIENT_LOCAL topics deliver the last pre-window sample at subscription time; count it separately.
    all_images = {topic: list(items) for topic, items in images.items()}
    all_statuses = list(statuses)
    pre_window: dict[str, int] = {}
    waiting_statuses = 0
    if window_start is not None:
        start_unix = window_start.timestamp()
        for topic in IMAGE_TOPICS:
            kept = []
            for m in images[topic]:
                m["captured_before_window"] = datetime.fromisoformat(m["stamp"]) < window_start
                m["received_after_window_start_s"] = round(m["received_at_unix"] - start_unix, 3)
                if m["captured_before_window"]:
                    pre_window[topic] = pre_window.get(topic, 0) + 1
                else:
                    kept.append(m)
            images[topic] = kept
        kept_statuses = []
        for s in statuses:
            captured = s.get("captured_at_utc")
            if isinstance(captured, str):
                if datetime.fromisoformat(captured.replace("Z", "+00:00")) >= window_start:
                    kept_statuses.append(s)
            elif s.get("_received_at_unix", 0) >= start_unix:
                waiting_statuses += 1  # publisher status without a capture (e.g. waiting_for_valid_snapshot)
                kept_statuses.append(s)
        statuses = kept_statuses
    checks: dict[str, Any] = {}
    checks["captured_before_window_samples"] = {"images": pre_window,
                                                "note": "header stamp precedes the receive window: latched at subscription (TRANSIENT_LOCAL) or in flight; kept in details, excluded from the checks below",
                                                "pass": True}
    for topic in IMAGE_TOPICS:
        decoded_ok = [m for m in images[topic] if m["size"] == expected_size and m["mode"] == "RGB"]
        checks[f"images_decoded:{topic}"] = {"received": len(images[topic]), "decoded_rgb_expected_size": len(decoded_ok),
                                              "pass": len(images[topic]) > 0 and len(decoded_ok) == len(images[topic])}
    sequences = [s["sequence"] for s in statuses if isinstance(s.get("sequence"), int)]
    captured = [s["captured_at_utc"] for s in statuses if isinstance(s.get("captured_at_utc"), str)]
    distinct_sequences = sorted(set(sequences))
    captured_times = sorted({datetime.fromisoformat(c.replace("Z", "+00:00")) for c in captured})
    checks["status_sequence_advances"] = {"status_messages": len(statuses), "distinct_sequences": len(distinct_sequences),
                                           "first_sequence": distinct_sequences[0] if distinct_sequences else None,
                                           "last_sequence": distinct_sequences[-1] if distinct_sequences else None,
                                           "non_decreasing_in_arrival_order": all(a <= b for a, b in zip(sequences, sequences[1:])),
                                           "pass": len(distinct_sequences) >= 2 and all(a <= b for a, b in zip(sequences, sequences[1:]))}
    checks["capture_time_advances"] = {"distinct_capture_times": len(captured_times),
                                        "first": captured_times[0].isoformat() if captured_times else None,
                                        "last": captured_times[-1].isoformat() if captured_times else None,
                                        "pass": len(captured_times) >= 2}
    views = sorted({str(s.get("view")) for s in statuses})
    checks["views_seen"] = {"views": views, "pass": "A" in views and "B" in views}
    kinds = {}
    for s in statuses:
        kinds[str(s.get("publication_kind"))] = kinds.get(str(s.get("publication_kind")), 0) + 1
    ages = [s.get("capture_age_seconds") for s in statuses if isinstance(s.get("capture_age_seconds"), (int, float))]
    checks["status_fields"] = {"publication_kinds": kinds, "source_states": sorted({str(s.get("source_state")) for s in statuses}),
                               "statuses_without_capture": waiting_statuses,
                               "capture_age_seconds_min": min(ages) if ages else None, "capture_age_seconds_max": max(ages) if ages else None,
                               "capture_mode": sorted({str(s.get("capture_mode")) for s in statuses}),
                               "execution_authorized": sorted({str(s.get("execution_authorized")) for s in statuses}),
                               "pass": bool(statuses) and all(s.get("execution_authorized") is False for s in statuses)
                               and all(s.get("capture_mode") == "pre_captured" for s in statuses if s.get("source_state") != "waiting_for_valid_snapshot")}
    scenario_ids = sorted({str((s.get("scene") or {}).get("scenario_id")) for s in statuses if s.get("scene")})
    checks["scenario_id"] = {"seen": scenario_ids, "expected": expect_scenario,
                             "pass": expect_scenario is None or scenario_ids == [expect_scenario]}
    # Cross-check: every published image hash should appear in some status message's images table.
    status_hashes = {}
    for s in statuses:
        for name, info in (s.get("images") or {}).items():
            if isinstance(info, dict) and info.get("sha256"):
                status_hashes.setdefault(info["sha256"], set()).add(name)
    cross = {}
    for topic, key in (("/contextweld/wrist/image", "wrist"), ("/contextweld/overview/image", "overview"), ("/camera", "wrist")):
        matched = sum(1 for m in images[topic] if key in status_hashes.get(m["sha256"], set()))
        cross[topic] = {"images": len(images[topic]), "matched_status_hash": matched}
    checks["image_status_hash_crosscheck"] = {**cross, "pass": all(v["images"] > 0 and v["matched_status_hash"] == v["images"] for v in cross.values())}
    wrist_hashes = [m["sha256"] for m in images["/contextweld/wrist/image"]]
    alias_hashes = [m["sha256"] for m in images["/camera"]]
    # The alias is published from the same bytes as the wrist image; with depth-1 QoS a single wrist sample
    # can be dropped in transit, so accept an alias hash if it matches the received wrist set or the
    # publisher's own status table for the wrist image.
    status_wrist = {h for h, names in status_hashes.items() if "wrist" in names}
    unmatched_alias = [h for h in alias_hashes if h not in set(wrist_hashes) and h not in status_wrist]
    checks["camera_alias_matches_wrist"] = {"wrist": len(wrist_hashes), "alias": len(alias_hashes),
                                             "alias_without_received_wrist_twin": sum(1 for h in alias_hashes if h not in set(wrist_hashes)),
                                             "alias_unmatched_anywhere": len(unmatched_alias),
                                             "pass": bool(alias_hashes) and not unmatched_alias}
    dyn_pairs = sorted({(t["header"]["frame_id"], t["child_frame_id"]) for t in tf_dynamic})
    static_pairs = sorted({(t["header"]["frame_id"], t["child_frame_id"]) for t in tf_static})
    checks["tf"] = {"dynamic_transforms": len(tf_dynamic), "dynamic_pairs": [list(p) for p in dyn_pairs],
                    "static_transforms": len(tf_static), "static_pairs": [list(p) for p in static_pairs],
                    "pass": ("world", "contextweld_wrist_optical") in dyn_pairs}
    checks["decode_errors"] = {"count": len(decode_errors), "examples": decode_errors[:5], "pass": not decode_errors}
    stamps = {topic: sorted({m["stamp"] for m in images[topic]}) for topic in IMAGE_TOPICS}
    summary = {
        "bridge_server_info": raw["server_info"],
        "negotiated_subprotocol": raw.get("negotiated_subprotocol"),
        "advertised_channels_for_topics": raw["channels"],
        "subscribed_topics": raw["subscribed_topics"],
        "message_counts": {topic: len(images[topic]) for topic in IMAGE_TOPICS} | {STATUS_TOPIC: len(statuses), "/tf": len(tf_dynamic), "/tf_static": len(tf_static)},
        "image_header_stamps": {topic: {"distinct": len(v), "first": v[0] if v else None, "last": v[-1] if v else None} for topic, v in stamps.items()},
        "checks": checks,
        "all_pass": all(c.get("pass") for c in checks.values()),
        "note": "reception through the Foxglove WebSocket protocol as a client; this verifies delivery on the server side of the tunnel, not a human looking at a Foxglove panel",
    }
    details = {"statuses": [{k: v for k, v in s.items() if k != "scene"} for s in all_statuses],
               "images": {topic: [{k: v for k, v in m.items()} for m in all_images[topic]] for topic in IMAGE_TOPICS},
               "tf_dynamic_sample": tf_dynamic[:3], "tf_static": tf_static[:5]}
    return {"summary": summary, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="ws://127.0.0.1:8765")
    parser.add_argument("--seconds", type=float, default=40.0)
    parser.add_argument("--expect-scenario", help="scenario_id every status.scene must carry")
    parser.add_argument("--expect-size", default="1280x720", help="expected decoded image size WxH")
    parser.add_argument("--report", help="write the JSON report here (summary + details)")
    args = parser.parse_args()
    width, height = (int(v) for v in args.expect_size.lower().split("x"))
    started = datetime.now(timezone.utc).isoformat()
    raw = asyncio.run(receive(args.url, args.seconds, list(IMAGE_TOPICS) + [STATUS_TOPIC, *TF_TOPICS]))
    result = analyse(raw, args.expect_scenario, (width, height), window_start=datetime.fromisoformat(started))
    result["summary"]["receive_window"] = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "seconds": args.seconds, "url": args.url}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
