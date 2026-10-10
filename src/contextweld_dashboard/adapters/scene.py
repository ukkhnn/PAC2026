"""Isaac 장면 자료(isaac-*-capture.v1) 읽기 어댑터. 실행 묶음이 아니므로 재생·결과 상태를 만들지 않는다."""
from __future__ import annotations

from typing import Any

from ..model import block, notice, row, tab
from .common import absent, base_summary

UNLINKED = ("이 장면 자료는 공개 사진 인식·문서 검토·재검토 실행과 연결된 기록이 없습니다. 장면의 J01과 문서의 "
            "JOINT-DEMO-01은 미연결입니다.")
SCHEDULED = ("예약 A/B 자세 이동(capture_mode=pre_captured, recognition_feedback_enabled=false) — 인식이 요청한 팔 "
             "이동이 아닙니다.")


def build(source, reader, integrity, ctx) -> dict[str, Any]:
    m = reader.json("manifest.json")
    name = source.display_path.rsplit("/", 1)[-1]
    summary = base_summary(source, reader, kind_label="Isaac 장면 자료 (예약 A/B 촬영)", title=f"{name} · {m.get('scenario_id')}",
                           final_seq=None)
    summary["replay"] = {"enabled": False, "reason": "장면 자료에는 사건 기록(events.jsonl)이 없어 단계 재생 대상이 아닙니다."}
    summary["flags"] = [row("execution_authorized", reader.value("manifest.json", "execution_authorized")),
                        row("recognition_feedback_enabled", reader.value("manifest.json", "recognition_feedback_enabled")),
                        row("presentation", reader.value("manifest.json", "presentation"))]
    summary["links"] = [{"relation": "unlinked", "label": "인식·문서 실행", "run_id": reader.value("manifest.json", "run_id"),
                         "run_key": None, "note": UNLINKED}]
    pairs = []
    for camera, label in (("wrist", "손목 카메라"), ("overview", "전체 장면")):
        items = []
        for view in ("A", "B"):
            rec = (m.get("frames") or {}).get(view) or {}
            path = rec.get(f"{camera}_saved_image")
            image = ctx.image(reader, path, label=f"{view} · {label}") if isinstance(path, str) else None
            if image is None:
                continue
            f = lambda *k: reader.value("manifest.json", "frames", view, *k, origin="simulator")  # noqa: E731
            items.append({"label": f"{view} · {label}", "image": image, "rows": [
                row("captured_at_utc", f("captured_at_utc")), row("simulation_time (초)", f("simulation_time")),
                row("sequence (스트림 카운터, 사건 seq 아님)", f("sequence")),
                row("기록 SHA-256", f(f"{camera}_image_sha256")),
                row("camera_world_position (m)", f("camera_world_position")),
                row("camera_position_error_m", f("camera_position_error_m")),
                row("joint_positions (rad)", f("joint_positions")), row("ik_converged", f("ik_converged")),
                row("capture_mode", f("capture_mode")), row("presentation_mode", f("presentation_mode"))]})
        if items:
            pairs.append(block("image_pair", f"pair-{camera}", f"A/B 원본 비교 · {label} (시점이 다른 두 저장 이미지)", items=items))
    initial = [ctx.image(reader, f"frames/initial-{c}.png", label=f"초기 · {c}") for c in ("wrist", "overview")]
    initial = [i for i in initial if i]
    capture_blocks = [notice("unlinked", "warning", "인식 결과 미연결 — 이 장면 프레임에 대한 OCR/VLM 실행 기록이 없습니다."),
                      notice("video", "info", "저장된 팔 이동 영상 없음(미기록). 정지 이미지(초기·A·B)만 있습니다.")] + pairs
    if initial:
        capture_blocks.append(block("image_pair", "initial", "초기 자세 (manifest에 해시 미기록)",
                                    items=[{"label": i["label"], "image": i, "rows": []} for i in initial]))
    recap = [notice("sched", "warning", SCHEDULED),
             notice("glare", "info", "장면 설정의 반사(glare) 의도는 시뮬레이터 설계 정보입니다. 모델의 판독·원인 진단 기록은 없습니다."),
             block("json", "moves", "로봇 이동 기록 (요청 vs 실제, simulator)", value=reader.value("manifest.json", "robot"),
                   collapsed=True),
             block("json", "views", "장면 설계 의도 views (config.json, simulator)", value=reader.value("config.json", "views")
                   if reader.exists("config.json") else reader.value("manifest.json", "views"), collapsed=True)]
    if reader.exists("prediction.json"):
        recap.append(block("json", "prediction", "렌더 전 반사 기하 추정 (prediction.json, simulator — 모델 예측 아님)",
                           value=reader.value("prediction.json"), collapsed=True))
    tabs = {
        "summary": tab("available", [notice("scene", "info", "Isaac 장면 자료는 실행 묶음이 아닙니다(run_id·run_outcome·export_status·사건 없음)."),
                                     notice("unlinked", "warning", UNLINKED),
                                     block("fields", "id", "장면 식별", rows=[
                                         row("schema_version", reader.value("manifest.json", "schema_version")),
                                         row("scenario_id", reader.value("manifest.json", "scenario_id")),
                                         row("capture_mode", reader.value("manifest.json", "capture_mode")),
                                         row("run_outcome", reader.value("manifest.json", "run_outcome")),
                                         row("export_status", reader.value("manifest.json", "export_status")),
                                         row("completed_at_utc", reader.value("manifest.json", "completed_at_utc"))]),
                                     block("raw_files", "raws", "원문 파일", files=[{"root": reader.key, "path": p} for p in
                                           ("manifest.json", "config.json", "prediction.json") if reader.exists(p)])]),
        "capture": tab("partial", capture_blocks, "인식 결과가 연결되지 않은 장면 원본만 있음"),
        "timeline": absent("사건 기록(events.jsonl)이 없습니다. A/B 촬영 순서는 촬영 전후 비교의 촬영 UTC·시뮬레이션 시각으로 확인합니다."),
        "recapture": tab("partial", recap, "예약 A/B 자세만 있음(인식 요청 기반 재촬영 아님)"),
        "evidence": absent("이 장면 자료에는 인식·해석·문서 근거 기록이 없습니다."),
        "delivery": absent("이 장면 자료에는 전달 기록이 없습니다."),
        "corrections": absent("이 장면 자료에는 수정·재검토 기록이 없습니다."),
    }
    return {"summary": summary, "steps": [], "tabs": tabs}
