#!/usr/bin/env python3
"""로컬 보존 사본(타르·zip)의 기록 해시 재대조 도구 (2026-10-16).

P1(server-artifact-recovery)의 로컬 선행 작업. 서버(Runpod) 접근 재개 전에 로컬
보존 사본이 기록된 해시와 여전히 일치하는지 스트리밍으로 재확인한다. 표준
라이브러리만 쓰고 사본을 풀지 않는다(타르·zip 멤버를 1MiB 단위로 읽어 해시).

방식(--... 옵션은 반복 지정 가능, 전체 통과 시 exit 0):
  --tar-json TAR JSON           JSON이 {경로: {"bytes", "sha256"}} 지도일 때
  --tar-working-files TAR JSON  JSON["working_files"] = [{path, sha256, ...}]일 때
  --zip-sha ZIP SHA256          zip 전체 파일의 sha256 대조
  --tar-sha-file TAR FILE       "sha256  경로" 줄 목록과 타르 멤버 대조
  --tar-member-sha TAR MEMBER SHA256   타르 내 멤버 1개의 sha256 대조
  --tar-internal-json TAR MEMBER PREFIX   타르 내부 JSON({경로: sha256})과
                                          PREFIX 하위 멤버 대조
  --tar-vs-dir TAR DIR          타르 멤버 ↔ 추출본 디렉터리 바이트 동일성
  --json-out PATH               리포트 저장 경로(기본: 표준 출력만)

결과는 JSON {"ok": bool, "groups": [...]}로 출력한다. 불일치·누락이 하나라도
있으면 exit 1. 파일 누락·JSON 파싱 오류는 stderr에 남기고 exit 1.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

CHUNK = 1024 * 1024


def _sha256_stream(fobj) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = fobj.read(CHUNK)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return _sha256_stream(handle)


def _tar_index(tar_path: Path) -> dict[str, tarfile.TarInfo]:
    handle = tarfile.open(tar_path, "r:*")
    index = {}
    for member in handle.getmembers():
        if member.isreg():
            index[member.name] = member
    return index


def _tar_member_hash(handle: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    extracted = handle.extractfile(member)
    if extracted is None:
        raise ValueError(f"타르 멤버를 읽을 수 없음: {member.name}")
    return _sha256_stream(extracted)


def _result(mode: str, checked: int, matched: int, missing: list[str], mismatched: list[str]) -> dict:
    return {
        "mode": mode,
        "ok": not missing and not mismatched,
        "checked": checked,
        "matched": matched,
        "missing": missing,
        "mismatched": mismatched,
    }


def _fail(groups: list[dict], message: str) -> tuple[list[dict], bool]:
    return groups + [{"mode": "error", "ok": False, "message": message}], False


def check_tar_against_json(tar_path: Path, json_path: Path) -> dict:
    """JSON 지도 {경로: {"bytes", "sha256"}}의 모든 항목을 타르 멤버와 대조."""
    expected = json.loads(json_path.read_text("utf-8"))
    if not isinstance(expected, dict):
        raise ValueError(f"{json_path} 최상위가 객체(경로 지도)가 아님: {type(expected).__name__}")
    handle = tarfile.open(tar_path, "r:*")
    index = _tar_index(tar_path)
    missing, mismatched = [], []
    for name, info in expected.items():
        member = index.get(name)
        if member is None:
            missing.append(name)
            continue
        if member.size != info.get("bytes"):
            mismatched.append(f"{name} (크기 {member.size} != {info.get('bytes')})")
            continue
        digest = _tar_member_hash(handle, member)
        if digest != info.get("sha256"):
            mismatched.append(name)
    return _result("tar-json", len(expected), len(expected) - len(missing) - len(mismatched),
                   missing, mismatched)


def check_tar_against_working_files(tar_path: Path, json_path: Path) -> dict:
    """inventory.json의 working_files [{path, sha256, ...}]를 타르 멤버와 대조."""
    payload = json.loads(json_path.read_text("utf-8"))
    entries = payload.get("working_files")
    if not isinstance(entries, list):
        raise ValueError(f"{json_path}에 working_files 목록이 없음")
    handle = tarfile.open(tar_path, "r:*")
    index = _tar_index(tar_path)
    missing, mismatched = [], []
    for entry in entries:
        name = entry.get("path")
        member = index.get(name)
        if member is None:
            missing.append(name)
            continue
        digest = _tar_member_hash(handle, member)
        if digest != entry.get("sha256"):
            mismatched.append(name)
    return _result("tar-working-files", len(entries),
                   len(entries) - len(missing) - len(mismatched), missing, mismatched)


def check_zip_sha(zip_path: Path, expected_sha: str) -> dict:
    with zipfile.ZipFile(zip_path, "r") as handle:  # 열기 자체로 손상 여부 확인
        if handle.testzip() is not None:
            raise ValueError(f"{zip_path} zip 내부 손상(CRC 오류) 멤버 존재")
    digest = _sha256_file(zip_path)
    mismatched = [] if digest == expected_sha else [zip_path.name]
    return _result("zip-sha", 1, 1 if digest == expected_sha else 0, [], mismatched)


def check_tar_sha_file(tar_path: Path, sha_file: Path) -> dict:
    """"sha256  경로" 줄 목록(sha256sum 출력 형식)과 타르 멤버 대조."""
    handle = tarfile.open(tar_path, "r:*")
    index = _tar_index(tar_path)
    missing, mismatched = [], []
    entries = 0
    for line in sha_file.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"{sha_file} 줄 형식 오류: {line!r}")
        digest, name = parts[0], parts[-1]
        if name.startswith("*"):
            name = name[1:]
        entries += 1
        member = index.get(name)
        if member is None:
            missing.append(name)
            continue
        if _tar_member_hash(handle, member) != digest:
            mismatched.append(name)
    return _result("tar-sha-file", entries, entries - len(missing) - len(mismatched),
                   missing, mismatched)


def check_tar_member_sha(tar_path: Path, member_name: str, expected_sha: str) -> dict:
    handle = tarfile.open(tar_path, "r:*")
    index = _tar_index(tar_path)
    member = index.get(member_name)
    if member is None:
        return _result("tar-member-sha", 1, 0, [member_name], [])
    digest = _tar_member_hash(handle, member)
    mismatched = [] if digest == expected_sha else [member_name]
    return _result("tar-member-sha", 1, 1 if digest == expected_sha else 0, [], mismatched)


def check_tar_internal_json(tar_path: Path, member_name: str, prefix: str) -> dict:
    """타르 내부 checksums JSON({경로: sha256})과 prefix 하위 멤버 대조."""
    handle = tarfile.open(tar_path, "r:*")
    index = _tar_index(tar_path)
    member = index.get(member_name)
    if member is None:
        return _result("tar-internal-json", 0, 0, [member_name], [])
    payload = json.loads(handle.extractfile(member).read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{member_name} 최상위가 객체가 아님: {type(payload).__name__}")
    base = prefix.rstrip("/")
    missing, mismatched = [], []
    for rel, expected_sha in payload.items():
        name = f"{base}/{rel}"
        target = index.get(name)
        if target is None:
            missing.append(name)
            continue
        if _tar_member_hash(handle, target) != expected_sha:
            mismatched.append(name)
    return _result("tar-internal-json", len(payload),
                   len(payload) - len(missing) - len(mismatched), missing, mismatched)


def check_tar_against_dir(tar_path: Path, dir_path: Path) -> dict:
    """타르 멤버 전부를 추출본 디렉터리(dir/<멤버 경로>)와 바이트 대조."""
    handle = tarfile.open(tar_path, "r:*")
    missing, mismatched = [], []
    checked = 0
    for member in handle.getmembers():
        if not member.isreg():
            continue
        checked += 1
        disk = dir_path / member.name
        if not disk.is_file():
            missing.append(member.name)
            continue
        if disk.stat().st_size != member.size:
            mismatched.append(f"{member.name} (크기 {disk.stat().st_size} != {member.size})")
            continue
        if _sha256_file(disk) != _tar_member_hash(handle, member):
            mismatched.append(member.name)
    return _result("tar-vs-dir", checked, checked - len(missing) - len(mismatched),
                   missing, mismatched)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tar-json", nargs=2, action="append", default=[], metavar=("TAR", "JSON"))
    parser.add_argument("--tar-working-files", nargs=2, action="append", default=[], metavar=("TAR", "JSON"))
    parser.add_argument("--zip-sha", nargs=2, action="append", default=[], metavar=("ZIP", "SHA256"))
    parser.add_argument("--tar-sha-file", nargs=2, action="append", default=[], metavar=("TAR", "FILE"))
    parser.add_argument("--tar-member-sha", nargs=3, action="append", default=[], metavar=("TAR", "MEMBER", "SHA256"))
    parser.add_argument("--tar-internal-json", nargs=3, action="append", default=[], metavar=("TAR", "MEMBER", "PREFIX"))
    parser.add_argument("--tar-vs-dir", nargs=2, action="append", default=[], metavar=("TAR", "DIR"))
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    groups: list[dict] = []
    try:
        for tar, json_path in args.tar_json:
            groups.append(check_tar_against_json(Path(tar), Path(json_path)))
        for tar, json_path in args.tar_working_files:
            groups.append(check_tar_against_working_files(Path(tar), Path(json_path)))
        for zip_path, expected in args.zip_sha:
            groups.append(check_zip_sha(Path(zip_path), expected))
        for tar, sha_file in args.tar_sha_file:
            groups.append(check_tar_sha_file(Path(tar), Path(sha_file)))
        for tar, member, expected in args.tar_member_sha:
            groups.append(check_tar_member_sha(Path(tar), member, expected))
        for tar, member, prefix in args.tar_internal_json:
            groups.append(check_tar_internal_json(Path(tar), member, prefix))
        for tar, dir_path in args.tar_vs_dir:
            groups.append(check_tar_against_dir(Path(tar), Path(dir_path)))
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile) as exc:
        groups, ok = _fail(groups, str(exc))
        report = {"ok": ok, "groups": groups}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.json_out:
            args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
        return 1

    ok = all(group["ok"] for group in groups)
    report = {"ok": ok, "groups": groups}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
