"""재촬영 루프를 용접 파이프라인의 기록 단계로 연결한다 (의사결정 비변경).

2026-10-16 진단·처방 후속 연결(Option 1). `capture_binding`의
`requires_recapture` 예외(2026-10-15 확정 결정)를 유지한 채, 예외가 났을 때
재촬영 루프를 실행하고 완료 번들을 weld 묶음 안에 보존한다. 루프의 판정
(continue 포함)은 weld 판독 결정을 대체하지 않으므로 파이프라인은 그대로
needs_review/blocked로 끝난다. 데이터 모델(marking-capture.v1 ↔
capture_assessment)이 달라 변환도 하지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from contextweld.recapture_inputs import verify_inputs
from contextweld.recapture_loop import run_recapture_loop, verify_recapture_bundle


def run_recapture_step(*, capture: dict, inputs_root: Path, output_root: Path,
                       run_id: str, observer: Any, config: dict | None = None) -> dict:
    """requires_recapture 판독에 대해 재촬영 루프를 실행·검증하고 결과를 돌려준다.

    `weld_pipeline.run_pipeline`이 capture_binding의 "재관측 뒤에도 판독
    미확정" 예외를 받았을 때만 호출한다. 반환값의 `bundle_path`를 호출자가
    weld 묶음 안에 보존하고 manifest에 참조를 기록한다.

    촬영 프레임과 재촬영 입력의 일치를 먼저 확인한다: capture의 모든
    프레임 image_sha256이 recapture 입력 프레임 sha256에 있어야 한다
    (같은 저장 A/B가 아니면 루프를 실행할 근거가 없다).
    """
    if capture.get("source_kind") != "model" or not capture.get("frames"):
        raise ValueError("재촬영 단계는 실제 인식 기록에만 사용한다")
    read = capture["frames"][-1].get("readout") or {}
    if not (read.get("quality") or {}).get("requires_recapture"):
        raise ValueError("재촬영 단계는 requires_recapture 판독에만 사용한다")
    inputs = verify_inputs(inputs_root)
    input_hashes = {frame["sha256"] for frame in inputs["frames"]}
    for frame in capture["frames"]:
        if frame.get("image_sha256") not in input_hashes:
            raise ValueError("재촬영 입력이 촬영 프레임과 일치하지 않음")
    bundle_path = run_recapture_loop(inputs_root=inputs_root, output_root=output_root,
                                     run_id=run_id, observer=observer, config=config or {})
    manifest = verify_recapture_bundle(bundle_path)
    return {"bundle_path": bundle_path, "recapture_run_id": manifest["run_id"],
            "recapture_outcome": manifest["recapture_outcome"],
            "recapture_visual_outcome": manifest["visual_outcome"]}
