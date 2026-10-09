#!/usr/bin/env python3
"""공개 데모 자료를 검증해 내려받거나 기존 실험 원본에서 복사한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO = Path(__file__).resolve().parents[1]
SUCCESS = {"downloaded", "copied", "verified"}
MEDIA = {"image/jpeg", "image/png", "application/pdf", "text/html", "text/plain"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def https_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS 공개 URL만 허용")


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def no_symlink(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("symlink 경로는 허용하지 않음")


def under(root: Path, relative: str) -> Path:
    if not relative or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("유효한 상대경로가 필요함")
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("상대경로 탈출 또는 빈 구성요소")
    result = root / relative
    no_symlink(result)
    return result


def inspect_file(path: Path, media_type: str) -> tuple[str, int]:
    no_symlink(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("비어 있거나 일반 파일이 아님")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        head = handle.read(1024)
        handle.seek(0)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    valid = {
        "image/jpeg": head.startswith(b"\xff\xd8\xff"),
        "image/png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "application/pdf": head.startswith(b"%PDF-"),
        "text/html": bool(re.search(br"<(?:!doctype\s+html|html(?:\s|>))", head.lower())),
        "text/plain": True,
    }[media_type]
    if not valid:
        raise ValueError("예상한 미디어 서명이 아님")
    if media_type == "text/plain":
        path.read_text(encoding="utf-8")
    return digest.hexdigest(), path.stat().st_size


def expected_hash(source: dict, previous: dict | None) -> str | None:
    if source.get("sha256") is not None:
        return source["sha256"]
    if previous and all(previous.get(key) == source[key] for key in ("id", "relative_path", "url")):
        return previous.get("sha256") if previous.get("status") in SUCCESS else previous.get("expected_sha256")
    return None


def prepare(source: dict, destination: Path, previous: dict | None,
            local_root: Path | None, verify_only: bool) -> dict:
    target = under(destination, source["relative_path"])
    expected = expected_hash(source, previous)
    if target.exists():
        if not expected:
            raise ValueError("기존 파일의 신뢰할 SHA-256 없음; 덮어쓰지 않음")
        actual, size = inspect_file(target, source["media_type"])
        if actual != expected:
            raise ValueError("기존 파일 SHA-256 불일치; 덮어쓰지 않음")
        status = "verified"
    else:
        if verify_only:
            raise ValueError("검증할 파일 없음")
        target.parent.mkdir(parents=True, exist_ok=True)
        no_symlink(target.parent)
        descriptor, temporary = tempfile.mkstemp(prefix=".asset-", suffix=".part", dir=target.parent)
        os.close(descriptor)
        part = Path(temporary)
        try:
            local = under(local_root, source["source_path"]) if local_root and source.get("source_path") else None
            if local and local.exists():
                if not local.is_file():
                    raise ValueError("로컬 원본이 일반 파일이 아님")
                shutil.copyfile(local, part)
                status = "copied"
            else:
                opener = build_opener(HTTPSRedirect())
                for attempt in range(3):  # 최초 시도와 최대 두 번의 재시도
                    try:
                        request = Request(source["url"], headers={"User-Agent": "ContextWeld-demo-data/1.0"})
                        with opener.open(request, timeout=30) as response, part.open("wb") as handle:
                            https_url(response.geturl())
                            shutil.copyfileobj(response, handle)
                        break
                    except (OSError, ValueError):
                        if attempt == 2:
                            raise
                status = "downloaded"
            actual, size = inspect_file(part, source["media_type"])
            if expected and actual != expected:
                raise ValueError("받은 파일 SHA-256 불일치")
            no_symlink(target)
            if target.exists():
                raise ValueError("대상 파일이 새로 생김; 덮어쓰지 않음")
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)
    return {**source, "declared_sha256": source.get("sha256"), "sha256": actual,
            "size_bytes": size, "status": status, "checked_at_utc": utc_now()}


def save_manifest(path: Path, assets: dict[str, dict]) -> None:
    no_symlink(path)
    descriptor, name = tempfile.mkstemp(prefix=".manifest-", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": "demo-assets.v1", "generated_at_utc": utc_now(),
                       "assets": list(assets.values())}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO / "configs/demo_data_sources.json")
    parser.add_argument("--destination", type=Path, default=REPO / "data/raw/demo-bootstrap-v1")
    parser.add_argument("--verify-only", action="store_true", help="네트워크·파일 쓰기 없이 검증")
    parser.add_argument("--group", action="append", help="선택 그룹; 여러 번 지정 가능")
    parser.add_argument("--local-steel-root", type=Path, help="source_path의 기준 디렉토리")
    args = parser.parse_args(argv)
    try:
        destination = args.destination.expanduser().absolute()
        local_root = args.local_steel_root.expanduser().absolute() if args.local_steel_root else None
        no_symlink(destination)
        destination = destination.resolve()
        if local_root:
            no_symlink(local_root)
            local_root = local_root.resolve()
        for protected in (REPO / "experiments/e1_ocr/inputs", local_root):
            if protected and destination.is_relative_to(protected.resolve()):
                raise ValueError("기존 실험 원본 안에는 저장할 수 없음")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if config.get("schema_version") != "demo-data-sources.v1" or not isinstance(config.get("sources"), list):
            raise ValueError("지원하지 않는 자료 설정")
        selected, ids, paths = [], set(), set()
        for source in config["sources"]:
            if not isinstance(source, dict):
                raise ValueError("자료 항목은 객체여야 함")
            for key in ("id", "group", "url", "relative_path", "media_type", "source_kind"):
                if not isinstance(source.get(key), str) or not source[key]:
                    raise ValueError(f"잘못된 필수 필드: {key}")
            if not isinstance(source.get("required"), bool) or source["media_type"] not in MEDIA:
                raise ValueError("잘못된 required 또는 media_type")
            if source["source_kind"] not in {"public_dataset", "public_document"}:
                raise ValueError("지원하지 않는 source_kind")
            if source.get("sha256") is not None:
                if not isinstance(source["sha256"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source["sha256"]):
                    raise ValueError("잘못된 SHA-256")
                source["sha256"] = source["sha256"].lower()
            https_url(source["url"])
            under(destination, source["relative_path"])
            if source["id"] in ids or source["relative_path"] in paths or source["relative_path"].split("/")[0] == "asset-manifest.json":
                raise ValueError("중복 ID·경로 또는 예약된 manifest 경로")
            ids.add(source["id"])
            paths.add(source["relative_path"])
            if not args.group or source["group"] in args.group:
                selected.append(source)
        if not selected or args.group and set(args.group) - {item["group"] for item in selected}:
            raise ValueError("선택 그룹에 자료가 없음")
        manifest_path = under(destination, "asset-manifest.json")
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        if previous and previous.get("schema_version") != "demo-assets.v1":
            raise ValueError("지원하지 않는 기존 manifest")
        assets = {item["id"]: item for item in previous.get("assets", [])}
        if not args.verify_only:
            destination.mkdir(parents=True, exist_ok=True)
        failed = interrupted = False
        for source in selected:
            try:
                row = prepare(source, destination, assets.get(source["id"]), local_root, args.verify_only)
            except (OSError, ValueError, KeyboardInterrupt) as error:
                interrupted = isinstance(error, KeyboardInterrupt)
                row = {**source, "status": "failed", "sha256": None, "size_bytes": None,
                       "expected_sha256": expected_hash(source, assets.get(source["id"])),
                       "checked_at_utc": utc_now(), "error": "interrupted" if interrupted else str(error)}
                failed = failed or source["required"]
            assets[source["id"]] = row
            print(f"{source['id']} {row['status']} {source['relative_path']}", flush=True)
            if row["status"] == "failed":
                print(f"  {'required' if source['required'] else 'optional'}: {row['error']}", file=sys.stderr)
            if not args.verify_only:
                save_manifest(manifest_path, assets)
            if interrupted:
                return 130
        return 1 if failed else 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"자료 준비 실패: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
