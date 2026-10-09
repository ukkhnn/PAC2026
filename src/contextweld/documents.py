"""원문 위치를 보존하는 작은 문서 색인과 명시적 범위의 BM25 검색."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from typing import Any


INDEX_SCHEMA = "documents.index.v1"
RETRIEVAL_SCHEMA = "documents.retrieval.v1"
RETRIEVER = {"name": "bm25", "version": "1", "k1": 1.5, "b": 0.75,
             "tokenizer": "unicode_words_hangul_bigrams.v1"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_path(root: Path, relative: str) -> Path:
    """색인과 출처 목록의 경로가 원문 루트를 벗어나지 않게 한다."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("유효한 원문 상대경로가 필요합니다.")
    if Path(relative).is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise ValueError("원문 상대경로가 루트를 벗어납니다.")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("원문 symlink가 루트를 벗어납니다.")
    return path


def tokenize(text: str) -> list[str]:
    """영문 대소문자와 한글 조사 차이를 다루는 작은 결정적 토크나이저."""
    tokens = re.findall(r"[^\W_]+(?:[-.][^\W_]+)*", text.casefold(), re.UNICODE)
    for token in list(tokens):
        if re.fullmatch(r"[가-힣]+", token) and len(token) > 2:
            tokens.extend(token[index:index + 2] for index in range(len(token) - 1))
    return tokens


class _HTMLBlocks(HTMLParser):
    """스크립트·메뉴를 제외하고 절과 원문 줄 위치를 보존한다."""

    ignored = {"script", "style", "nav", "header", "footer", "noscript", "svg"}
    blocks = {"p", "li", "pre", "blockquote", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self.skip: list[str] = []
        self.current: str | None = None
        self.parts: list[str] = []
        self.start = 1
        self.section: str | None = None
        self.nesting = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip:
            if tag not in self.void:
                self.skip.append(tag)
            return
        if tag in self.ignored:
            self.skip.append(tag)
            return
        if tag in self.blocks and self.current is None:
            self.current, self.start = tag, self.getpos()[0]
            self.parts, self.nesting = [], 0
        elif self.current is not None and tag == self.current:
            self.nesting += 1
        if self.current is not None and tag in {"br", "tr", "td", "th", "p", "li"}:
            self.parts.append("\n" if tag in {"br", "tr", "p", "li"} else " | ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.void:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            if tag in self.skip:
                while self.skip and self.skip.pop() != tag:
                    pass
            return
        if tag != self.current:
            return
        if self.nesting:
            self.nesting -= 1
            return
        self._flush(self.getpos()[0])

    def handle_data(self, data: str) -> None:
        if not self.skip and self.current is not None:
            self.parts.append(data)

    def _flush(self, end: int) -> None:
        text = "\n".join(re.sub(r"[ \t\r\f\v]+", " ", line).strip()
                         for line in "".join(self.parts).splitlines()).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text:
            if self.current and re.fullmatch(r"h[1-6]", self.current):
                self.section = text
            self.rows.append({"text": text, "locator": {
                "kind": "html_table" if self.current == "table" else "html_block",
                "section": self.section, "block": len(self.rows) + 1,
                "tag": self.current, "line_start": self.start, "line_end": end,
            }})
        self.current, self.parts = None, []


def extract_html(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parser = _HTMLBlocks()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    if parser.current is not None:
        parser._flush(parser.getpos()[0])
    first_heading = next((index for index, row in enumerate(parser.rows) if row["locator"]["tag"] == "h1"), 0)
    return parser.rows[first_heading:], {"name": "stdlib.html.parser", "mode": "semantic_blocks",
                                        "limitations": ["nontext_figures_not_extracted"]}


def extract_markdown(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows: list[dict[str, Any]] = []
    section: str | None = None
    start, pending, fence = 1, [], False

    def flush(end: int) -> None:
        if not pending:
            return
        text = "\n".join(pending)
        kind = "markdown_table" if re.search(r"(?m)^\s*\|.*\|\s*$", text) else "markdown_block"
        if re.search(r"<table(?:\s|>)", text, re.I):
            parser = _HTMLBlocks()
            parser.feed(text)
            parser.close()
            if parser.rows:
                text = "\n".join(row["text"] for row in parser.rows)
                kind = "markdown_html_table"
        rows.append({"text": text, "locator": {
            "kind": kind,
            "section": section, "block": len(rows) + 1,
            "line_start": start, "line_end": end,
        }})
        pending.clear()

    for number, line in enumerate(lines, 1):
        heading = re.match(r"^#{1,6}\s+(.+)", line) if not fence else None
        if heading:
            flush(number - 1)
            section = heading.group(1).strip()
        if not line.strip() and not fence:
            flush(number - 1)
            continue
        if not pending:
            start = number
        pending.append(line)
        if re.fullmatch(r"`{3,}[^`]*|~{3,}[^~]*", line.strip()):
            fence = not fence
    flush(len(lines))
    return rows, {"name": "stdlib", "mode": "markdown_blocks_whole_tables"}


def extract_pdf(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ValueError("PDF 추출에는 격리 실행환경의 pdfplumber가 필요합니다.") from exc
    rows = []
    with pdfplumber.open(path) as document:
        for number, page in enumerate(document.pages, 1):
            text = page.extract_text(layout=False) or ""
            if not text.strip():
                raise ValueError(f"{path.name} {number}쪽에 텍스트가 없습니다. 문서 OCR이 필요합니다.")
            words = [{"text": word["text"], "bbox": [word["x0"], word["top"], word["x1"], word["bottom"]]}
                     for word in page.extract_words()]
            tables = []
            for table_number, table in enumerate(page.find_tables(), 1):
                tables.append({"table": table_number, "bbox": list(table.bbox),
                               "rows": table.extract(),
                               "cells": [list(cell) for cell in table.cells],
                               "review_status": "unreviewed"})
            # 숫자 행만 잘라내지 않고 같은 페이지의 머리글·단위·주석을 함께 반환한다.
            lines = [{"text": line["text"], "bbox": [line["x0"], line["top"], line["x1"], line["bottom"]]}
                     for line in page.extract_text_lines(return_chars=False)]
            warnings = ["unmapped_pdf_glyphs"] if "(cid:" in text else []
            rows.append({"text": text, "locator": {
                "kind": "pdf_page", "page": number, "section": None,
                "bbox": list(page.bbox), "coordinate_system": "pdf_points_top_left",
            }, "words": words, "lines": lines, "tables": tables,
                "warnings": warnings, "review_status": "unreviewed"})
    return rows, {"name": "pdfplumber", "version": pdfplumber.__version__,
                  "mode": "whole_page_with_words_and_tables",
                  "limitations": ["automatic_tables_unreviewed", "unruled_tables_may_not_be_segmented"]}


def build_index(data_root: Path, sources_path: Path) -> dict[str, Any]:
    """등록된 문서만 해시 검증 후 추출한다. 누락·손상은 색인 성공으로 바꾸지 않는다."""
    source_payload = json.loads(sources_path.read_text(encoding="utf-8"))
    if not isinstance(source_payload, dict) or not isinstance(source_payload.get("sources"), list):
        raise ValueError("sources 배열이 있는 출처 목록이 필요합니다.")
    sources = [row for row in source_payload["sources"] if row.get("group") == "documents"]
    if not sources:
        raise ValueError("출처 목록에 문서가 없습니다.")
    documents, chunks, seen = [], [], set()
    for source in sources:
        document_id = source["id"]
        if not isinstance(document_id, str) or not document_id or document_id in seen:
            raise ValueError("문서 ID가 없거나 중복됩니다.")
        seen.add(document_id)
        path = source_path(data_root, source["relative_path"])
        expected = source.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError(f"{document_id}: 신뢰할 원문 SHA-256이 필요합니다.")
        if file_hash(path) != expected:
            raise ValueError(f"{document_id}: 원문 SHA-256 불일치")
        media = source["media_type"]
        if media == "application/pdf":
            rows, extractor = extract_pdf(path)
        elif media == "text/html":
            rows, extractor = extract_html(path)
        elif media == "text/plain":
            rows, extractor = extract_markdown(path)
        else:
            raise ValueError(f"{document_id}: 지원하지 않는 문서 형식 {media}")
        if not rows:
            raise ValueError(f"{document_id}: 추출된 본문이 없습니다.")
        revision = source.get("revision")
        if revision is not None and (not isinstance(revision, str) or not revision.strip()):
            raise ValueError(f"{document_id}: revision은 명시된 문자열 또는 null이어야 합니다.")
        role = source.get("document_role", "blank_template" if document_id == "lanl-wts" else "public_reference")
        document = {
            "document_id": document_id, "title": source.get("title", document_id),
            "revision": revision, "revision_status": "declared" if revision is not None else "unconfirmed",
            "source_hash": expected, "source_url": source["url"],
            "relative_path": source["relative_path"], "media_type": media,
            "document_origin": "public_document", "document_role": role,
            "license_declared": source.get("license_declared"),
            "content_reviewed": False, "application_authorized": False,
            "extraction": extractor, "chunk_count": len(rows),
        }
        documents.append(document)
        for row in rows:
            locator = row["locator"]
            chunk_id = f"{document_id}:{_digest({'source_hash': expected, 'locator': locator, 'text': row['text']})[:16]}"
            chunks.append({**row, "chunk_id": chunk_id, "document_id": document_id,
                           "revision": revision, "source_hash": expected,
                           "document_role": role, "content_reviewed": False,
                           "application_authorized": False})
    index = {"schema_version": INDEX_SCHEMA, "created_at": _now(),
             "source_registry_hash": file_hash(sources_path), "retriever": dict(RETRIEVER),
             "documents": documents, "chunks": chunks, "execution_authorized": False}
    index["index_hash"] = _digest(index)
    return index


def validate_index(index: dict[str, Any], data_root: Path | None = None) -> None:
    if not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA:
        raise ValueError("지원하는 문서 색인 형식이 아닙니다.")
    expected = index.get("index_hash")
    if expected != _digest({key: value for key, value in index.items() if key != "index_hash"}):
        raise ValueError("문서 색인 SHA-256 불일치")
    if data_root is not None:
        for document in index["documents"]:
            path = source_path(data_root, document["relative_path"])
            if file_hash(path) != document["source_hash"]:
                raise ValueError(f"{document['document_id']}: 원문 SHA-256 불일치")


def load_index(path: Path, data_root: Path | None = None) -> dict[str, Any]:
    index = json.loads(path.read_text(encoding="utf-8"))
    validate_index(index, data_root)
    return index


def search_documents(index: dict[str, Any], query: str, *, document_ids: list[str],
                     revision: str | None = None, top_k: int = 5,
                     data_root: Path | None = None) -> dict[str, Any]:
    """명시한 문서 범위 안에서만 검색한다. 없는 개정은 다른 문서로 대체하지 않는다."""
    validate_index(index, data_root)
    if not isinstance(query, str) or not tokenize(query):
        raise ValueError("검색할 질의가 필요합니다.")
    if (not isinstance(document_ids, list) or not document_ids
            or any(not isinstance(item, str) or not item for item in document_ids)):
        raise ValueError("하나 이상의 명시적 document_ids 필터가 필요합니다.")
    if revision is not None and (not isinstance(revision, str) or not revision.strip()):
        raise ValueError("revision 필터는 문자열이어야 합니다.")
    if type(top_k) is not int or not 1 <= top_k <= 50:
        raise ValueError("top_k는 1~50의 정수여야 합니다.")
    selected_ids = list(dict.fromkeys(document_ids))
    eligible_documents = [doc for doc in index["documents"] if doc["document_id"] in selected_ids
                          and (revision is None or doc["revision"] == revision)]
    eligible_ids = {doc["document_id"] for doc in eligible_documents}
    missing_ids = [item for item in selected_ids if item not in eligible_ids]
    # 일부만 찾았을 때도 작업의 명시적 문서 계약을 충족한 것으로 보지 않는다.
    candidates = [] if missing_ids else [chunk for chunk in index["chunks"] if chunk["document_id"] in eligible_ids]
    term_counts = [Counter(tokenize(chunk["text"])) for chunk in candidates]
    lengths = [sum(counts.values()) for counts in term_counts]
    average_length = sum(lengths) / len(lengths) if lengths else 0
    query_terms = set(tokenize(query))
    frequencies = {term: sum(term in counts for counts in term_counts) for term in query_terms}
    hits = []
    for chunk, counts, length in zip(candidates, term_counts, lengths):
        score = 0.0
        for term in sorted(query_terms):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (len(candidates) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            denominator = frequency + RETRIEVER["k1"] * (1 - RETRIEVER["b"] + RETRIEVER["b"] * length / average_length)
            score += idf * frequency * (RETRIEVER["k1"] + 1) / denominator
        if score > 0:
            hits.append({**deepcopy(chunk), "score": score})
    hits.sort(key=lambda hit: (-hit["score"], hit["chunk_id"]))
    hits = hits[:top_k]
    for rank, hit in enumerate(hits, 1):
        hit["rank"] = rank
    reason = "document_filter_no_match" if missing_ids else "matched" if hits else "no_lexical_match"
    return {"schema_version": RETRIEVAL_SCHEMA, "created_at": _now(),
            "index_hash": index["index_hash"], "retriever": dict(RETRIEVER),
            "query": query, "filters": {"document_ids": selected_ids, "revision": revision},
            "top_k": top_k, "status": "retrieved" if hits else "needs_review", "reason": reason,
            "missing_document_ids": missing_ids,
            "raw_sources_verified": data_root is not None,
            "hits": hits, "returned_evidence_ids": [hit["chunk_id"] for hit in hits],
            "used_evidence_ids": [], "execution_authorized": False}


def mark_context_used(retrieval: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    """반환한 근거와 실제 모델 입력으로 선택한 근거를 분리해서 기록한다."""
    if (not isinstance(evidence_ids, list) or len(evidence_ids) != len(set(evidence_ids))
            or any(item not in retrieval["returned_evidence_ids"] for item in evidence_ids)):
        raise ValueError("사용한 근거는 검색 결과의 중복 없는 ID여야 합니다.")
    result = deepcopy(retrieval)
    result["used_evidence_ids"] = list(evidence_ids)
    return result


def write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    """이전 실행 결과를 덮어쓰지 않는다."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
