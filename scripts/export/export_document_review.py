#!/usr/bin/env python3
"""검증한 문서 실행·명시적 재검토 묶음을 원본 변경 없이 단일 오프라인 HTML로 내보낸다."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[2]
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


HEAD = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
"""
STYLE = """:root{color-scheme:light;--ink:#172b38;--muted:#506471;--line:#d8e3e6;--accent:#075e59}
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
.tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;margin:0 6px 4px 0}.t-model{background:#e3ecf7;color:#183f6b}.t-user{background:#fde7ef;color:#7a1640}.t-fixture{background:#efe6fb;color:#4b2380}.t-rule{background:#e2f2ea;color:#155238}.t-doc{background:#f3ead8;color:#5c3d07}.fail{background:#fde2e1;color:#7d1b16}
"""


def page_head(title: str) -> str:
    """CSP로 외부 연결·스크립트를 막는 공통 머리말. 제목도 이스케이프한다."""
    return HEAD + "<title>" + text(title) + "</title><style>\n" + STYLE + "</style></head>"


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


def frame_outputs(source: Path, frame_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    """원래 인식 묶음에서 선택 프레임의 원본 이미지와 모델 원문·구조화 결과를 읽는다."""
    source_manifest = read_json(source, "manifest.json")
    frame = next((item for item in source_manifest["frames"] if item["frame_id"] == frame_id), None)
    outputs = []
    for ref in source_manifest.get("result_refs", []):
        result = read_json(source, ref)
        if frame_id in result.get("input_frame_ids", []):
            raw_ref = result.get("raw_output_ref")
            outputs.append({"ref": ref, "result": result, "raw_ref": raw_ref,
                            "raw": safe_path(source, raw_ref).read_text(encoding="utf-8") if raw_ref else None})
    uri = image_uri(safe_path(source, frame["image_ref"]).read_bytes()) if frame else None
    return frame, outputs, uri


def collect_review(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(root, "manifest.json")
    frame, outputs, uri = frame_outputs(safe_path(root, manifest["input_bundle_ref"]), manifest["frame_id"])
    delivery = read_json(root, "results/delivery.json")
    transport = read_json(root, "commands/transport.json") if delivery.get("sent") else None
    receipts_path = root / "commands/receiver.jsonl"
    return {
        "manifest": manifest, "verification": report,
        "checksums_sha256": hashlib.sha256((root / "checksums.json").read_bytes()).hexdigest(),
        "frame": frame,
        "image_uri": uri,
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
    parts = [page_head("ContextWeld · 문서 검토 기록") + """<body><header><div class="eyebrow">CONTEXTWELD / OFFLINE REVIEW</div><h1>관측에서 문서 조건까지</h1>
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


KIND_TAGS = {"model": ("원본 · model", "t-model"), "user": ("수정 · user", "t-user"),
             "demo_fixture": ("수정 · demo_fixture (사람 검수 아님)", "t-fixture"), "fixture": ("시연 fixture", "t-fixture"),
             "rule": ("재판단 · rule", "t-rule"), "document": ("문서 · document", "t-doc"), "system": ("system", "t-rule")}


def tag(kind: Any) -> str:
    label, css = KIND_TAGS.get(kind, (str(kind), "t-rule"))
    return '<span class="tag ' + css + '">' + text(label) + "</span>"


def collect_review_run(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    """검증한 review-bundle.v1의 원관측·수정·요청·재판단·전달 기록을 읽기만 한다."""
    manifest = read_json(root, "manifest.json")
    lineage = read_json(root, "results/lineage.json")
    origin = safe_path(root, lineage["ancestors"][0]["bundle_ref"])
    origin_manifest = read_json(origin, "manifest.json")
    frame, outputs, uri = frame_outputs(safe_path(origin, origin_manifest["input_bundle_ref"]), manifest["frame_id"])
    delivery = read_json(root, "results/delivery.json")
    commands = root / "commands"
    receipts_path = commands / "receiver.jsonl"
    return {
        "manifest": manifest, "verification": report, "lineage": lineage,
        "checksums_sha256": hashlib.sha256((root / "checksums.json").read_bytes()).hexdigest(),
        "frame": frame, "image_uri": uri, "outputs": outputs,
        "original_selection": read_json(origin, "results/observation-selection.json"),
        "origin_spec": read_json(origin, "results/work-spec.json"),
        "parent_spec": read_json(root, manifest["parent_bundle_ref"] + "/results/work-spec.json"),
        "request": read_json(root, "inputs/review-request.json"),
        "corrections": [read_json(root, f"inputs/corrections/{item}.json") for item in manifest["correction_ids"]],
        "application": read_json(root, "results/correction-application.json"),
        "interpretation": read_json(root, "results/effective-interpretation.json"),
        "matching": read_json(root, "results/matching.json"),
        "spec": read_json(root, "results/work-spec.json"),
        "resolution": read_json(root, "results/issue-resolution.json"),
        "delivery": delivery,
        "transport": read_json(root, "commands/transport.json") if (commands / "transport.json").is_file() else None,
        "transport_error": read_json(root, "commands/transport-error.json") if (commands / "transport-error.json").is_file() else None,
        "receipts": [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines()] if receipts_path.is_file() else [],
        "events": [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()],
    }


def render_review_run(data: dict[str, Any]) -> str:
    """원본(model)·수정(user/demo_fixture)·재판단(rule)을 구분해 표시한다. 실행·저장·전송 기능은 없다."""
    manifest, spec, request = data["manifest"], data["spec"], data["request"]
    issues = spec.get("validation", {}).get("issues", [])
    delivery = data["delivery"]
    outcome = manifest.get("run_outcome")
    badge = {"succeeded": ("재검토 통과", ""), "needs_review": ("검토 보류", " hold"), "failed": ("기술 실패", " fail")}.get(outcome, (str(outcome), " hold"))
    against_parent = data["resolution"].get("against_parent", {})
    kinds = manifest.get("correction_source_kinds") or []
    who = {("user",): "사용자 수정", ("demo_fixture",): "시연 fixture 수정 (사람 검수 아님)"}.get(tuple(kinds), "선택 수정 (" + ", ".join(map(str, kinds)) + ")")
    fault = manifest.get("delivery_fault_injection")
    sources = {item.get("correction_id"): item.get("source_kind") for item in data["corrections"]}
    parts = [page_head("ContextWeld · 명시적 재검토 기록") + '<body><header><div class="eyebrow">CONTEXTWELD / OFFLINE EXPLICIT REVIEW</div><h1>' + text("원래 관측 · " + who + " · 새 규칙 검토") + """</h1>
<p class="subtle">저장된 재검토 실행을 읽는 화면 · 이 HTML은 추론, 수정 저장, 재검토, 전송을 실행하지 않습니다</p>""",
             '<span class="badge' + badge[1] + '">' + text(badge[0]) + "</span>",
             ('<span class="badge fail">' + text("시연용 결함 주입: " + str(fault)) + "</span>") if fault else "",
             "<p>재검토 실행 " + text(manifest.get("run_id")) + " · 요청 " + text(manifest.get("review_request_id")) + "</p>",
             '<nav><a href="#overview">결과</a><a href="#observation">원래 관측</a><a href="#corrections">수정 기록</a><a href="#request">재검토 요청</a><a href="#rejudge">새 판단</a><a href="#issues">해결·보류</a><a href="#events">시간순 기록</a><a href="#delivery">모의 전달</a></nav></header><main>',
             '<section id="overview"><h2>재검토 결과</h2><p class="notice">문서 범위 규칙 재검토입니다. 선택한 수정만 적용했고 새 모델 호출은 없습니다. 이미지 의미·시각 관계의 재해석, 실제 설비 실행과 현장 적용 승인은 포함하지 않으며 전체 데모 완료를 뜻하지 않습니다.</p><div class="grid">']
    for label, value in [("run_outcome", outcome), ("모의 전달", delivery.get("status")), ("남은 검증 이슈", len(issues)),
                         ("부모 대비 해결", against_parent.get("summary", {}).get("resolved")), ("새 모델 호출", manifest.get("new_model_calls")),
                         ("delivery_requested", manifest.get("delivery_requested")), ("전달 결함 주입", fault or "없음"),
                         ("수정 작성 주체", kinds), ("execution_authorized", manifest.get("execution_authorized")),
                         ("application_authorized", manifest.get("application_authorized")), ("demo_complete", manifest.get("demo_complete"))]:
        parts.append('<div class="card"><small>' + text(label) + "</small><strong>" + text(value) + "</strong></div>")
    parts += ["</div>", table(["기록", "값"], [["시작 (UTC)", manifest.get("started_at_utc")], ["종료 (UTC)", manifest.get("finished_at_utc")],
                  ["즉시 부모 실행", manifest.get("parent_run_id")], ["원래 문서 실행", manifest.get("origin_run_id")],
                  ["원래 인식 실행", manifest.get("recognition_run_id")], ["프레임", manifest.get("frame_id")],
                  ["재검토 범위", manifest.get("review_scope")], ["관계 재해석", manifest.get("relation_reinterpretation")],
                  ["checksums.json SHA-256", data["checksums_sha256"]]]),
              "<h3>실행 계보</h3>", table(["순서", "실행", "스키마", "종류", "manifest SHA-256", "묶음 내 위치"],
                  [[index, item.get("run_id"), item.get("bundle_schema"), item.get("run_kind"), item.get("manifest_sha256"), item.get("bundle_ref")]
                   for index, item in enumerate(data["lineage"].get("ancestors", []), 1)] + [["새 실행", manifest.get("run_id"), manifest.get("schema_version"), "review", "이 묶음", "."]]),
              detail("묶음 검증 결과", data["verification"]), detail("기록된 한계", manifest.get("limitations")), "</section>"]
    frame = data.get("frame") or {}
    parts += ['<section id="observation"><h2>' + tag("model") + "원래 관측 · 보존된 모델 출력</h2><p>" + text(manifest.get("frame_id")) + " · " + text(frame.get("capture_mode")) + " · 원래 인식 실행 " + text(manifest.get("recognition_run_id")) + "</p>"]
    uri = data.get("image_uri")
    if uri and (uri.startswith("data:image/png;base64,") or uri.startswith("data:image/jpeg;base64,")):
        parts.append('<img class="frame" alt="원래 인식 실행의 원본 프레임" src="' + text(uri) + '">')
    else:
        parts.append('<p class="notice">원본 프레임 미기록 또는 미지원 형식입니다. 이미지를 재생성하지 않았습니다.</p>')
    selection = data["original_selection"]
    parts.append(table(["관측 ID", "OCR 원문", "OCR 정규화", "겹치는 VLM 원문", "원래 이슈"],
                       [[row["ocr"].get("observation_id"), row["ocr"].get("raw_text"), row.get("normalized_identifier"),
                         [item.get("raw_text") for item in row.get("vlm", [])],
                         [item.get("code") for item in selection.get("issues", []) if item.get("field") == row["ocr"].get("observation_id")]]
                        for row in selection.get("observations", [])]))
    parts += ['<p class="subtle">새 사진·새 OCR이 없으며 위 원문은 원래 실행의 기록 그대로입니다.</p>', detail("원래 관측 선택 전체", selection)]
    for output in data["outputs"]:
        parts.append(detail(str(output["result"].get("stage", UNKNOWN)) + " 원문 · " + str(output.get("raw_ref") or UNKNOWN), output.get("raw"), raw=True))
    kinds = sorted({item.get("source_kind") for item in data["corrections"]}, key=str)
    parts += ["</section>", '<section id="corrections"><h2>' + "".join(tag(kind) for kind in kinds) + "수정 기록 · 원본과 분리 저장</h2>",
              "<p>수정은 원래 묶음 밖 저장소에 별도 파일로 기록된 뒤 이 재검토 요청에서 명시적으로 선택된 것만 복사되었습니다. 저장만으로 재검토·전송·학습을 시작하지 않습니다.</p>"]
    if any(item.get("source_kind") == "demo_fixture" for item in data["corrections"]):
        parts.append('<p class="notice">demo_fixture 수정은 자동 시연을 위해 만든 예시이며 실제 사용자가 원본을 검수한 기록이 아닙니다.</p>')
    parts.append(table(["수정 ID", "작성 주체", "동작", "대상 실행 / 결과 / 필드", "수정 전", "수정 후", "사유", "기록 (UTC)"],
                       [[item.get("correction_id"), {"source_kind": item.get("source_kind"), "author": item.get("author")}, item.get("action"),
                         {k: item.get("target", {}).get(k) for k in ("run_id", "result_ref", "result_sha256", "field", "observation_id")},
                         item.get("before"), item.get("after"), item.get("reason"), item.get("recorded_at_utc")] for item in data["corrections"]]))
    parts += [detail("수정 기록 원문", data["corrections"]), "</section>",
              '<section id="request"><h2>명시적 재검토 요청</h2>',
              table(["요청 항목", "값"], [[key, request.get(key) if request.get(key) is not None or key != "delivery_fault_injection" else "없음 (결함 주입 안 함)"]
                    for key in ("review_request_id", "requested_by", "reason", "correction_ids",
                    "delivery_requested", "delivery_fault_injection", "parent_run_id", "parent_manifest_sha256", "requested_at_utc", "request_sha256", "interface")]),
              "<p>수정 저장, 재검토 실행, 모의 전달 요청은 각각 별도 명령입니다. 전달 요청은 <code>delivery_requested</code>로 기록되며 이 화면에서는 보낼 수 없습니다.</p></section>"]
    interpretation = data["interpretation"]
    parts += ['<section id="rejudge"><h2>' + tag("rule") + "새 판단 · 규칙 재검토</h2>",
              "<h3>관측 후보와 적용 식별자</h3>",
              table(["관측 ID", "OCR (model)", "VLM (model)", "적용 식별자", "적용 주체 / 수정 ID"],
                    [[row["ocr"].get("observation_id"), row.get("normalized_identifier"), [item.get("raw_text") for item in row.get("vlm", [])],
                      (row.get("effective_identifier") or {}).get("value") or "선택 없음 · 모델 후보 유지",
                      {k: (row.get("effective_identifier") or {}).get(k) for k in ("source_kind", "correction_id")}]
                     for row in interpretation.get("observations", [])]),
              "<p>원래 후보 " + text(interpretation.get("original_candidates")) + " → 재검토 후보 " + text(interpretation.get("candidates")) + "</p>",
              "<h3>수정 적용 순서</h3>",
              table(["순서", "단계", "수정 ID", "주체", "대상 관계", "적용 시점 값 일치", "상태", "미적용 사유", "수정 사유", "효과"],
                    [[item.get("order"), item.get("stage"), item.get("correction_id"), item.get("source_kind"),
                      item.get("target", {}).get("relation_to_review"), item.get("state_at_application") == item.get("before"),
                      item.get("status"), item.get("status_reason") or "없음", item.get("correction_reason"), item.get("effect")]
                     for item in data["application"].get("entries", [])]),
              "<h3>작업지시 연결</h3>", "<p>matching: " + text(data["matching"].get("status")) + " / " + text(data["matching"].get("reason")) + "</p>",
              detail("선택 대상", spec.get("target")), detail("대상 필드별 근거", spec.get("target_evidence")), detail("작업지시 matching 원문", data["matching"]),
              table(["문서", "개정", "출처 종류", "위치", "원문 SHA-256"], [[d.get("document_id"), d.get("revision"),
                    {"source_kind": d.get("source_kind"), "document_origin": d.get("document_origin")}, d.get("locator"), d.get("source_hash")] for d in spec.get("documents", [])]),
              "<h3>" + tag("document") + "명세 필드 · 단위 · 근거</h3>"]
    rows = []
    for name, value in spec.get("parameters", {}).items():
        evidence = value.get("evidence", {})
        locator = evidence.get("locator", {})
        displayed = value.get("value") if "value" in value else {"min": value.get("min"), "max": value.get("max")}
        rows.append([name, displayed, value.get("unit"), value.get("raw_value"), evidence.get("document_id"), locator.get("page"),
                     locator.get("bbox"), value.get("restored_by_correction_id") or "원래 문서 조회"])
    parts += [table(["필드", "값 / 범위", "단위", "원문 값", "문서", "페이지", "bbox", "복구 수정"], rows) if rows else "<p>명세 필드 없음 · 누락으로 보류</p>",
              detail("문서 근거 복구 기록", spec.get("parameter_restorations")), detail("시험용 결함 주입 (원래 사례)", spec.get("fault_injections")),
              detail("새 명세 전체", spec), "</section>",
              '<section id="issues"><h2>해결된 문제와 남은 보류</h2><p>이전 이슈를 지우지 않고 새 검사 결과와 대조했습니다. 사용자가 확인했다는 이유로 성공으로 바꾸지 않습니다.</p>',
              "<p>현재 검증 상태: " + text(spec.get("validation", {}).get("status")) + "</p>",
              table(["이전 이슈", "필드", "상태", "해결 방식", "연결 수정 ID", "연결 수정 주체"],
                    [[item["issue"].get("code"), item["issue"].get("field"), item.get("status"),
                      item.get("resolution") or ("미해결 · 보류 유지" if item.get("status") == "open" else None), item.get("correction_ids") or "없음",
                      [sources.get(cid) for cid in item.get("correction_ids", [])] or "없음"]
                     for item in against_parent.get("entries", [])]) if against_parent.get("entries") else "<p>즉시 부모 실행에 검증 이슈가 없었습니다.</p>",
              "<h3>새로 생긴 이슈</h3>", pretty(against_parent.get("new_issues")) if against_parent.get("new_issues") else "<p>없음</p>",
              "<h3>남은 검증 이슈</h3>", pretty(issues) if issues else "<p>남은 문서 검토 이슈 없음. 실제 용접 적용 적합성은 별도 미확인입니다.</p>",
              detail("원래 문서 실행 대비 대조", data["resolution"].get("against_origin")), detail("현장 적용에 남은 정보", spec.get("application_missing")),
              table(["적용 상태", "기록값"], [[key, spec.get(key)] for key in ("physical_applicability", "range_combination_validated", "execution_authorized", "application_authorized")]),
              "</section>",
              '<section id="events"><h2>시간순 사건 기록</h2><p class="subtle">producer로 사람(user)·시연 fixture·규칙(rule)·system을 구분합니다.</p>',
              table(["UTC", "seq", "종류", "단계", "생성 주체", "요청 / 명령", "저장된 결과"],
                    [[event.get("recorded_at_utc"), event.get("seq"), event.get("type"), event.get("stage"), event.get("producer"),
                      [event.get("request_id"), event.get("command_id")], event.get("payload_ref")]
                     for event in sorted(data["events"], key=lambda event: (event.get("recorded_at_utc") or "", event.get("seq", 0)))]),
              detail("사건 원문 전체", data["events"]), "</section>",
              '<section id="delivery"><h2>모의 전달 요청 · 수신 ACK</h2><p>실행 당시의 로컬 loopback 기록입니다. 이 HTML을 열거나 펼쳐도 요청은 발생하지 않습니다.</p>',
              detail("전달 상태", delivery)]
    transport, error = data.get("transport"), data.get("transport_error")
    if transport:
        parts += [table(["전달 기록", "값"], [[key, transport.get(key)] for key in ("transport", "endpoint", "sent_at_utc", "http_status", "request_sha256")]),
                  detail("실제 전송 request", transport.get("request")), detail("실제 수신 ACK", transport.get("ack")), detail("수신기 원본 기록", data.get("receipts"))]
    elif error:
        cause = ("시연용 결함 주입(" + str(fault) + ")으로 일부러 만든 실패입니다." if fault else "실제 기술 실패입니다.")
        parts += ['<p class="notice">' + text("전달 시도가 실패했습니다. " + cause + " 성공 ACK를 만들지 않았으며 run_outcome은 failed입니다.") + "</p>",
                  table(["실패 기록", "값"], [[key, error.get(key)] for key in ("error_type", "error", "endpoint", "fault_injection", "http_status",
                        "receiver_side", "client_ack_confirmed", "note", "request_sha256", "recorded_at_utc")]),
                  detail("실제 받은 응답 본문 (있을 때)", error.get("raw_response"), raw=True),
                  detail("보내려던 request", error.get("request")), detail("수신기 원본 기록", data.get("receipts"))]
    else:
        parts.append('<p class="notice">전송 기록 없음 · 요청과 ACK를 만들지 않았습니다. 전달 미요청이거나 검증 보류입니다.</p>')
    parts += ['</section></main><footer class="subtle">ContextWeld · review-bundle.v1 오프라인 조회. 추론·수정 저장·재검토·재전송 기능이 없으며 전체 관리자 화면(P3), A/B 재촬영 재생, 운영 서비스 완료 범위가 아닙니다.</footer></body></html>']
    return "".join(parts)


def verify_bundle_any(root: Path) -> tuple[str, dict[str, Any]]:
    """스키마에 맞는 기존 검증기를 사용한다. 지원하지 않는 묶음은 내보내지 않는다."""
    from contextweld.review import inspect_review_bundle
    schema = read_json(root, "manifest.json").get("schema_version")
    if schema == "document-demo-bundle.v1":
        return schema, inspect_document_bundle(root)
    if schema == "review-bundle.v1":
        return schema, inspect_review_bundle(root)
    raise ValueError("지원하지 않는 묶음 스키마: " + str(schema))


def export_review(bundle: Path, output: Path) -> dict[str, Any]:
    root, destination = bundle.resolve(), output.resolve()
    if destination.is_relative_to(root):
        raise ValueError("원본 묶음 안에는 HTML을 저장할 수 없습니다.")
    if output.exists() or output.is_symlink():
        raise FileExistsError("기존 출력은 덮어쓰지 않습니다: " + str(output))
    schema, report = verify_bundle_any(root)
    before = (root / "checksums.json").read_bytes()
    if schema == "review-bundle.v1":
        content = render_review_run(collect_review_run(root, report))
    else:
        content = render_review(collect_review(root, report))
    # 읽는 동안 입력이 바뀌었으면 결과를 저장하지 않는다.
    if verify_bundle_any(root) != (schema, report) or (root / "checksums.json").read_bytes() != before:
        raise ValueError("내보내기 도중 원본 묶음이 변경되었습니다.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(content)
    return {"output": str(destination), "bytes": destination.stat().st_size, "schema": schema, "verification": report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="document-demo-bundle.v1 또는 review-bundle.v1 디렉토리")
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
