#!/usr/bin/env python3
"""검증한 문서 실행 묶음을 원본 변경 없이 단일 오프라인 HTML로 내보낸다."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contextweld.recognition import safe_path
from contextweld.workflow import inspect_document_bundle

UNKNOWN = "미기록 / unknown"


def text(value: Any) -> str:
    """원문은 HTML/속성으로 실행하지 않고 항상 텍스트로 표시한다."""
    if value is None:
        value = UNKNOWN
    elif not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(value, quote=True)


def pretty(value: Any) -> str:
    return "<pre>" + text(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre>"


def detail(title: str, value: Any, *, raw: bool = False) -> str:
    body = "<pre>" + text(value) + "</pre>" if raw else pretty(value)
    return "<details><summary>" + text(title) + "</summary>" + body + "</details>"


def table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join("<th>" + text(item) + "</th>" for item in headers)
    body = "".join("<tr>" + "".join("<td>" + text(item) + "</td>" for item in row) + "</tr>" for row in rows)
    return '<div class="scroll"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def read_json(root: Path, ref: str) -> Any:
    return json.loads(safe_path(root, ref).read_text(encoding="utf-8"))


def image_uri(data: bytes) -> str | None:
    # SVG/HTML 등 실행 가능한 문서는 이미지로 삽입하지 않는다.
    media = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None
    return "data:" + media + ";base64," + base64.b64encode(data).decode("ascii") if media else None


def collect_review(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(root, "manifest.json")
    source = safe_path(root, manifest["input_bundle_ref"])
    source_manifest = read_json(source, "manifest.json")
    frame_id = manifest["frame_id"]
    frame = next((item for item in source_manifest["frames"] if item["frame_id"] == frame_id), None)
    outputs = []
    for ref in source_manifest.get("result_refs", []):
        result = read_json(source, ref)
        if frame_id in result.get("input_frame_ids", []):
            raw_ref = result.get("raw_output_ref")
            outputs.append({"ref": ref, "result": result, "raw_ref": raw_ref,
                            "raw": safe_path(source, raw_ref).read_text(encoding="utf-8") if raw_ref else None})
    delivery = read_json(root, "results/delivery.json")
    transport = read_json(root, "commands/transport.json") if delivery.get("sent") else None
    receipts_path = root / "commands/receiver.jsonl"
    return {
        "manifest": manifest, "verification": report,
        "checksums_sha256": hashlib.sha256((root / "checksums.json").read_bytes()).hexdigest(),
        "frame": frame,
        "image_uri": image_uri(safe_path(source, frame["image_ref"]).read_bytes()) if frame else None,
        "outputs": outputs,
        "selection": read_json(root, "results/observation-selection.json"),
        "matching": read_json(root, "results/matching.json"),
        "spec": read_json(root, "results/work-spec.json"),
        "retrieval": read_json(root, "evidence/retrieval.json"),
        "delivery": delivery, "transport": transport,
        "receipts": [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines()] if receipts_path.exists() else [],
        "events": [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()],
    }


def render_review(data: dict[str, Any]) -> str:
    manifest, spec = data["manifest"], data["spec"]
    validation = spec.get("validation", {})
    issues = validation.get("issues", [])
    delivery = data["delivery"]
    status = "검토 보류" if issues else "문서 검토 통과"
    parts = ["""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>ContextWeld · 문서 검토 기록</title><style>
:root{color-scheme:light;--ink:#172b38;--muted:#506471;--line:#d8e3e6;--accent:#075e59}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f2f6f6;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
header,main,footer{max-width:1160px;margin:auto;padding:28px}header{padding-top:40px}h1{font-size:32px;line-height:1.2;margin:12px 0}h2{font-size:23px;margin:0 0 14px}h3{font-size:18px;margin:24px 0 10px}
p{margin:10px 0}.eyebrow{color:var(--accent);font-size:13px;font-weight:750;letter-spacing:.13em}.subtle{color:var(--muted)}
.badge{display:inline-block;padding:5px 12px;border-radius:20px;background:#dceee9;color:#074d45;font-weight:700}.hold{background:#ffedcb;color:#684300}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}nav a{color:var(--accent);background:white;border:1px solid var(--line);border-radius:8px;padding:7px 12px;text-decoration:none}
section{background:white;border:1px solid var(--line);border-radius:14px;margin-bottom:20px;padding:26px;scroll-margin-top:20px}
.notice{border-left:4px solid #d29336;background:#fff6e8;padding:12px 16px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.card{padding:14px;border:1px solid var(--line);border-radius:9px;overflow-wrap:anywhere}.card small{display:block;color:var(--muted)}
.frame{display:block;width:100%;max-height:640px;object-fit:contain;background:#15242c;border-radius:10px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:11px 12px;overflow-wrap:anywhere}th{background:#f1f6f5}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:540px;overflow:auto;background:#f3f6f7;padding:16px;border-radius:8px;font:13px/1.6 ui-monospace,monospace}details{border:1px solid var(--line);border-radius:8px;margin:12px 0;padding:10px 14px}summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}code{overflow-wrap:anywhere}.excerpt{white-space:pre-wrap;max-height:340px;overflow:auto;border-left:3px solid #95b6b0;padding:12px 18px;background:#f7faf9;font-size:14px}
@media(max-width:700px){header,main,footer{padding:18px}h1{font-size:27px}.grid{grid-template-columns:1fr}section{padding:18px}th,td{padding:8px}}@media print{nav{display:none}body{background:white}section{break-inside:avoid}pre,.excerpt{max-height:none}}
</style></head><body><header><div class="eyebrow">CONTEXTWELD / OFFLINE REVIEW</div><h1>관측에서 문서 조건까지</h1>
<p class="subtle">저장된 실행 기록을 읽는 문서 검토 화면 · 추론, 수정, 재전송 기능 없음</p>""",
             '<span class="badge' + (' hold' if issues else '') + '">' + text(status) + "</span>",
             "<p>실행 " + text(manifest.get("run_id")) + " · 사례 " + text(manifest.get("case")) + "</p>",
             '<nav><a href="#overview">결과</a><a href="#observation">원본 관측</a><a href="#matching">문서 연결</a><a href="#wps">WPS 근거</a><a href="#issues">검증·보류</a><a href="#events">시간순 기록</a><a href="#delivery">모의 전달</a></nav></header><main>',
             '<section id="overview"><h2>실행 결과</h2><p class="notice">문서 검토용 부분 실행입니다. 실제 설비 실행과 현장 적용은 승인되지 않았으며 전체 데모 완료를 뜻하지 않습니다.</p><div class="grid">']
    for label, value in [("run_outcome", manifest.get("run_outcome")), ("모의 전달", delivery.get("status")),
                         ("검증 이슈", len(issues)), ("execution_authorized", manifest.get("execution_authorized")),
                         ("application_authorized", manifest.get("application_authorized")), ("demo_complete", manifest.get("demo_complete"))]:
        parts.append('<div class="card"><small>' + text(label) + "</small><strong>" + text(value) + "</strong></div>")
    parts += ["</div>", table(["기록", "값"], [["시작 (UTC)", manifest.get("started_at_utc")], ["종료 (UTC)", manifest.get("finished_at_utc")],
                  ["원래 인식 실행", manifest.get("parent_run_id")], ["새 모델 호출 수", manifest.get("new_model_calls")],
                  ["checksums.json SHA-256", data["checksums_sha256"]]]),
              detail("묶음 검증 결과", data["verification"]), detail("기록된 한계", manifest.get("limitations")), "</section>"]
    frame = data.get("frame") or {}
    parts += ['<section id="observation"><h2>선택 프레임 · 실제 모델 원문</h2><p>' + text(manifest.get("frame_id")) + " · " + text(frame.get("capture_mode")) + "</p>"]
    uri = data.get("image_uri")
    if uri and (uri.startswith("data:image/png;base64,") or uri.startswith("data:image/jpeg;base64,")):
        parts.append('<img class="frame" alt="선택된 원본 프레임" src="' + text(uri) + '">')
    else:
        parts.append('<p class="notice">원본 프레임 미기록 또는 미지원 형식입니다. 이미지를 재생성하지 않았습니다.</p>')
    parts += [detail("프레임 출처·해시·촬영 정보", frame), detail("OCR/VLM 관측 선택과 불일치", data["selection"])]
    for output in data["outputs"]:
        parts.append(detail(str(output["result"].get("stage", UNKNOWN)) + " 원문 · " + str(output.get("raw_ref") or UNKNOWN), output.get("raw"), raw=True))
        parts.append(detail("구조화 결과 · " + output["ref"], output["result"]))
    if not data["outputs"]:
        parts.append("<p>선택 프레임의 모델 출력: " + UNKNOWN + "</p>")
    parts += ['</section><section id="matching"><h2>문서 연결 · 출처 구분</h2>',
              '<p class="notice">작업지시·도면의 fixture / synthetic_demo는 시연 설정입니다. 실제 사진의 재질·두께·용접부 확인으로 해석하지 않습니다.</p>',
              table(["문서", "개정", "출처 종류", "위치", "원문 SHA-256"], [[d.get("document_id"), d.get("revision"),
                    {"source_kind": d.get("source_kind"), "document_origin": d.get("document_origin")}, d.get("locator"), d.get("source_hash")] for d in spec.get("documents", [])]),
              detail("선택 대상", spec.get("target")), detail("대상 필드별 근거", spec.get("target_evidence")),
              detail("작업지시 matching 원문", data["matching"]), '</section><section id="wps"><h2>WPS 값 · 단위 · 원문 위치</h2>',
              '<p class="subtle">범위는 문서 전사값입니다. 특정 운전값이나 유효한 조합을 선택한 결과가 아닙니다.</p>']
    rows = []
    for name, value in spec.get("parameters", {}).items():
        evidence = value.get("evidence", {})
        locator = evidence.get("locator", {})
        displayed = value.get("value") if "value" in value else {"min": value.get("min"), "max": value.get("max")}
        rows.append([name, displayed, value.get("unit"), value.get("raw_value"), evidence.get("document_id"),
                     locator.get("page"), locator.get("bbox"), locator.get("coordinate_system")])
    parts.append(table(["필드", "값 / 범위", "단위", "원문 값", "문서", "페이지", "bbox", "좌표계"], rows))
    parts += [detail("필드 전체 근거 · 헤더·행·열·개정·해시", spec.get("parameters")), detail("조건과 제한", spec.get("constraints")),
              detail("전사 검수 정보 · 현장 적용 승인과 구분", spec.get("source_review")),
              '<h3>검색된 원문 발췌</h3><p>원본 PDF 포함 여부: ' + text(manifest.get("source_document_originals_included")) +
              " · 아래 텍스트와 위치는 실행 묶음에 저장된 검색 결과입니다.</p>"]
    for hit in data["retrieval"].get("hits", []):
        parts += ["<h3>" + text(hit.get("document_id")) + " · " + text(hit.get("chunk_id")) + "</h3>",
                  "<p>위치 " + text(hit.get("locator")) + "</p>", '<div class="excerpt">' + text(hit.get("text")) + "</div>",
                  detail("발췌 출처·검토 상태", {k: hit.get(k) for k in ("document_id", "revision", "source_hash", "locator", "review_status", "content_reviewed", "application_authorized")})]
    if not data["retrieval"].get("hits"):
        parts.append("<p>원문 발췌: " + UNKNOWN + "</p>")
    parts += ['</section><section id="issues"><h2>검증 이슈와 보류</h2>', "<p>" + text(validation.get("status")) + "</p>",
              pretty(issues) if issues else "<p>기록된 문서 검토 이슈 없음. 실제 용접 적용 적합성은 별도 미확인 상태입니다.</p>",
              detail("전체 검증 결과 · 누락 필드", validation), detail("현장 적용에 남은 정보", spec.get("application_missing")),
              detail("시험용 결함 주입", spec.get("fault_injections")),
              table(["적용 상태", "기록값"], [[key, spec.get(key)] for key in ("physical_applicability", "range_combination_validated", "execution_authorized", "application_authorized")]),
              '</section><section id="events"><h2>시간순 사건 기록</h2><p class="subtle">UTC 기록 시간순으로 표시합니다. seq와 부모 사건 ID를 함께 보존합니다.</p>',
              table(["UTC", "seq", "단계", "사건 ID", "부모 사건", "저장된 결과"], [[event.get("recorded_at_utc"), event.get("seq"), event.get("stage"),
                    event.get("event_id"), event.get("parent_event_ids"), event.get("payload_ref")] for event in sorted(data["events"], key=lambda event: (event.get("recorded_at_utc") or "", event.get("seq", 0)))]),
              detail("사건 원문 전체", data["events"]), '</section><section id="delivery"><h2>실제 모의 요청 · 수신 ACK</h2>',
              "<p>실행 당시의 로컬 모의 수신 기록입니다. 이 HTML을 열어도 요청은 발생하지 않습니다.</p>", detail("전달 상태", delivery)]
    transport = data.get("transport")
    if transport:
        parts += [table(["전달 기록", "값"], [[key, transport.get(key)] for key in ("transport", "endpoint", "sent_at_utc", "http_status", "request_sha256")]),
                  detail("실제 전송 request", transport.get("request")), detail("실제 수신 ACK", transport.get("ack")), detail("수신기 원본 기록", data.get("receipts"))]
    else:
        parts.append('<p class="notice">전송 기록 없음 · 요청과 ACK를 만들지 않았습니다. 보류 이유와 전달 상태를 확인하세요.</p>')
    parts += ['</section></main><footer class="subtle">ContextWeld · document-demo-bundle.v1 오프라인 조회. 전체 관리자 화면(P3), A/B 재촬영 재생, 운영 서비스 완료 범위가 아닙니다.</footer></body></html>']
    return "".join(parts)


def export_review(bundle: Path, output: Path) -> dict[str, Any]:
    root, destination = bundle.resolve(), output.resolve()
    if destination.is_relative_to(root):
        raise ValueError("원본 묶음 안에는 HTML을 저장할 수 없습니다.")
    if output.exists() or output.is_symlink():
        raise FileExistsError("기존 출력은 덮어쓰지 않습니다: " + str(output))
    report = inspect_document_bundle(root)
    before = (root / "checksums.json").read_bytes()
    content = render_review(collect_review(root, report))
    # 읽는 동안 입력이 바뀌었으면 결과를 저장하지 않는다.
    if inspect_document_bundle(root) != report or (root / "checksums.json").read_bytes() != before:
        raise ValueError("내보내기 도중 원본 묶음이 변경되었습니다.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(content)
    return {"output": str(destination), "bytes": destination.stat().st_size, "verification": report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="document-demo-bundle.v1 디렉토리")
    parser.add_argument("--output", required=True, type=Path, help="새 단일 HTML 경로 (묶음 밖)")
    args = parser.parse_args()
    try:
        print(json.dumps(export_review(args.bundle, args.output), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("내보내기 실패: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
