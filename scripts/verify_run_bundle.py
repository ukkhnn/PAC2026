#!/usr/bin/env python3
"""모델을 로드하지 않고 저장 묶음의 해시와 단계 참조를 검증한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contextweld.recognition import safe_path, sha256, verify_bundle


def inspect_bundle(root: Path) -> dict[str, Any]:
    verify_bundle(root)
    read = lambda ref: json.loads(safe_path(root, ref).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    run_id = manifest["run_id"]
    if manifest.get("run_kind") != "bootstrap" or manifest.get("capture_mode") != "public_dataset":
        raise ValueError("이 검사기는 공개 자료 bootstrap 묶음만 지원합니다.")
    if manifest.get("delivery_requested") is not False or manifest.get("execution_authorized") is not False:
        raise ValueError("bootstrap은 전달/실행을 승인할 수 없습니다.")
    frames = {frame["frame_id"]: frame for frame in manifest["frames"]}
    if not frames or len(frames) != len(manifest["frames"]):
        raise ValueError("프레임 ID가 없거나 중복됩니다.")
    for frame in frames.values():
        if sha256(safe_path(root, frame["image_ref"])) != frame["sha256"]:
            raise ValueError("프레임 원본 해시 불일치")
    results: dict[str, dict] = {}
    for ref in manifest["result_refs"]:
        row = read(ref)
        if row.get("schema_version") != "recognition.v1" or row.get("run_id") != run_id:
            raise ValueError("결과 스키마/실행 ID 불일치")
        if row["result_id"] in results:
            raise ValueError("결과 ID 중복")
        if not set(row["input_frame_ids"]) <= frames.keys():
            raise ValueError("알 수 없는 입력 프레임")
        for field in ("raw_output_ref", "config_ref", "evidence_ref"):
            if row.get(field) and not safe_path(root, row[field]).is_file():
                raise ValueError(f"결과 파일 참조 없음: {field}")
        results[row["result_id"]] = row
    expected_stages = {"ocr", "observation", "relation", "work_spec_candidate", "recognition_decision"}
    for frame_id in frames:
        rows = [row for row in results.values() if row["input_frame_ids"] == [frame_id]]
        if len(rows) != len(expected_stages) or {row["stage"] for row in rows} != expected_stages:
            raise ValueError("프레임별 필수 5단계 결과가 없거나 중복됩니다.")
    for row in results.values():
        if row["stage"] in {"ocr", "observation", "relation"} and not row.get("raw_output_ref"):
            raise ValueError("모델 원문 출력 참조가 없습니다.")
        if not row.get("config_ref"):
            raise ValueError("실행 설정 참조가 없습니다.")
        if not set(row["input_result_ids"]) <= results.keys():
            raise ValueError("알 수 없는 입력 결과")
        if row["stage"] == "relation":
            observation_ids: set[str] = set()
            for parent in row["input_result_ids"]:
                source = results[parent]
                if source["input_frame_ids"] != row["input_frame_ids"] or source["stage"] != "observation":
                    raise ValueError("관계가 다른 프레임/단계의 관측을 참조합니다.")
                observation_ids.update(item["observation_id"] for item in source.get("text_observations", []) + source.get("visual_objects", []))
            retrieval = read(row["evidence_ref"])
            hits = {hit["chunk_id"]: hit for hit in retrieval["hits"]}
            for hit in hits.values():
                if not hit.get("locator") or not hit.get("source_hash"):
                    raise ValueError("검색 근거의 위치 또는 원문 해시 없음")
            cited = set()
            for relation in row["relations"]:
                cited.update(relation["document_refs"])
                references = set(relation["source_observation_ids"] + relation["target_observation_candidates"])
                if relation.get("selected_target_observation_id"):
                    references.add(relation["selected_target_observation_id"])
                if not references <= observation_ids:
                    raise ValueError("관계가 현재 프레임 밖의 관측을 참조합니다.")
            if not cited <= hits.keys() or cited != set(retrieval["cited_evidence_ids"]):
                raise ValueError("관계의 실제 사용 근거 불일치")
        if row["stage"] == "work_spec_candidate" and row.get("execution_authorized") is not False:
            raise ValueError("작업 후보는 실행을 승인할 수 없습니다.")
    seen: set[str] = set()
    events = [json.loads(line) for line in safe_path(root, "events.jsonl").read_text().splitlines() if line]
    for seq, event in enumerate(events, 1):
        if event["run_id"] != run_id or event["seq"] != seq or event["event_id"] in seen:
            raise ValueError("사건 순서/ID 불일치")
        if not set(event["parent_event_ids"]) <= seen:
            raise ValueError("사건의 원인이 앞선 사건에 없습니다.")
        if not set(event["input_frame_ids"]) <= frames.keys() or not set(event["input_result_ids"]) <= results.keys():
            raise ValueError("사건 입력 참조 없음")
        if not safe_path(root, event["payload_ref"]).is_file():
            raise ValueError("사건의 payload 파일 없음")
        seen.add(event["event_id"])
    return {"verified": True, "run_id": run_id, "frames": len(frames), "results": len(results),
            "events": len(events), "files": len(manifest["files"]), "inference_status": manifest.get("inference_status"),
            "run_outcome": manifest.get("run_outcome", manifest.get("status")), "demo_complete": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_bundle(args.bundle), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"묶음 검증 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
