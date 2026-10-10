#!/usr/bin/env python3
"""오프라인 관리자 대시보드 패키지 검사 (표준 라이브러리만 사용, Python 3.9+).

사용: python3 tools/verify_package.py [패키지 폴더] [--json]

확인 항목
1. MANIFEST.json에 적힌 모든 파일이 있고 크기·SHA-256이 같다.
2. MANIFEST 밖 파일이 없다(내보내기 정보 등 기록된 가변 파일 제외).
3. symlink가 없다.
4. bundles/<key>/checksums.json이 있는 실행 묶음은 원본 생산자가 남긴 해시 목록과 사본 파일이 모두 일치한다.
5. 화면 데이터(data/)와 앱 파일에 서버 절대경로(/workspace/)가 없다.

이 도구는 파일을 읽기만 한다. 네트워크·하위 프로세스를 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

PACKAGE_SCHEMA = "contextweld-admin-dashboard.package.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def confined(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if not relative or "\\" in relative or relative.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError("경로 형식 오류: " + relative)
    target = (root / relative).resolve()
    base = root.resolve()
    if target != base and base not in target.parents:
        raise ValueError("패키지 밖 경로: " + relative)
    return target


PATH_KEYS = ("path", "data_file", "bundle_dir", "viewer_html", "thumb_path")
PACKAGE_ROOTED = ("bundles/", "data/", "viewer/", "assets/")


def load_data_js(path: Path):
    """data/*.js 의 'window.PAC_DASHBOARD_DATA.<대상> = <JSON>;' 줄에서 JSON만 꺼낸다."""
    lines = path.read_text("utf-8").split("\n")
    body = lines[1] if len(lines) > 1 else ""
    marker = " = "
    if not body.startswith("window.PAC_DASHBOARD_DATA.") or marker not in body or not body.endswith(";"):
        raise ValueError("예상한 데이터 파일 형식이 아닙니다.")
    return json.loads(body[body.index(marker) + len(marker):-1])


def structural_paths(node, where=""):
    """화면이 파일 위치로 쓰는 필드(path·data_file·bundle_dir·viewer_html·roots)를 모은다. 저장 값(v)은 제외."""
    if isinstance(node, dict):
        if set(node) >= {"v", "src"} and set(node) <= {"v", "src", "o", "n", "absent"}:
            return
        for key, value in node.items():
            if key == "roots" and isinstance(value, dict):
                for root_key, root_path in value.items():
                    yield where + "/roots/" + root_key, root_path
            elif key in PATH_KEYS and isinstance(value, str):
                yield where + "/" + key, value
            else:
                yield from structural_paths(value, where + "/" + key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from structural_paths(value, where + "/" + str(index))


def package_relative(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value or "://" in value or value.startswith("~"):
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def verify(package: Path) -> dict:
    problems = []
    notes = []
    manifest_path = package / "MANIFEST.json"
    if not manifest_path.is_file():
        return {"ok": False, "problems": ["MANIFEST.json이 없습니다."], "notes": [], "checked_files": 0,
                "bundle_checks": []}
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA:
        problems.append("지원하지 않는 패키지 스키마: " + str(manifest.get("schema")))
    listed = {}
    for entry in manifest.get("files", []):
        relative = entry["path"]
        try:
            target = confined(package, relative)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        listed[relative] = entry
        if not target.is_file() or os.path.islink(package / relative):
            problems.append("누락 파일: " + relative)
            continue
        if target.stat().st_size != entry["size"] or sha256(target) != entry["sha256"]:
            problems.append("해시 불일치: " + relative)
    allowed = set(manifest.get("volatile_files", [])) | {"MANIFEST.json"}
    symlinks = []
    for directory, dirnames, filenames in os.walk(package, followlinks=False):
        for name in dirnames + filenames:
            path = Path(directory) / name
            relative = path.relative_to(package).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            elif path.is_file() and relative not in listed and relative not in allowed:
                problems.append("목록 밖 파일: " + relative)
    problems.extend("symlink 금지: " + item for item in symlinks)
    bundle_checks = []
    for root in manifest.get("roots", []):
        base = package / root["package_dir"]
        checksums = base / "checksums.json"
        if not checksums.is_file():
            bundle_checks.append({"key": root["key"], "state": "no_checksums",
                                  "detail": "원본 묶음에 checksums.json 없음(장면·참조 자료 또는 불완전 묶음)"})
            continue
        try:
            recorded = json.loads(checksums.read_text("utf-8"))
        except ValueError as exc:
            bundle_checks.append({"key": root["key"], "state": "fail", "detail": "checksums.json 읽기 실패: " + str(exc)})
            problems.append(root["key"] + ": checksums.json 읽기 실패")
            continue
        bad = []
        for relative, expected in sorted(recorded.items()):
            try:
                target = confined(base, relative)
            except ValueError as exc:
                bad.append(str(exc))
                continue
            if not target.is_file() or sha256(target) != expected:
                bad.append(relative)
        state = "pass" if not bad else "fail"
        bundle_checks.append({"key": root["key"], "state": state, "entries": len(recorded), "mismatched": bad[:20]})
        if bad:
            problems.append(root["key"] + ": 원본 해시 목록과 다른 파일 " + str(len(bad)) + "개")
    bad_refs = []
    for entry in sorted(listed):
        if entry in ("index.html", "assets/app.js", "assets/app.css"):
            if b"/workspace/" in (package / entry).read_bytes():
                bad_refs.append(entry + ": 앱 파일에 서버 경로")
        if entry == "data/index.js" or entry.startswith("data/runs/"):
            try:
                document = load_data_js(package / entry)
            except ValueError as exc:
                problems.append("화면 데이터 형식 오류: " + entry + " (" + str(exc) + ")")
                continue
            for where, value in structural_paths(document):
                if not package_relative(value):
                    bad_refs.append(entry + where + " = " + str(value)[:80])
                elif value.startswith(PACKAGE_ROOTED) and not (package / value).exists():
                    # bundles/·data/·viewer/로 시작하면 패키지 루트 기준 경로이므로 실제로 있어야 한다.
                    # 그 밖의 path는 root 필드와 함께 쓰는 묶음 안 상대경로다.
                    bad_refs.append(entry + where + " = " + value + " (패키지 안에 없음)")
    if bad_refs:
        problems.append("패키지 밖이나 절대경로를 가리키는 화면 데이터 경로: " + "; ".join(bad_refs[:10]))
    stored_mentions = sum(1 for entry in listed if entry.startswith("data/raw/")
                          and b"/workspace/" in (package / entry).read_bytes())
    if stored_mentions:
        notes.append("원본 기록 텍스트 안의 서버 경로 문자열 " + str(stored_mentions)
                     + "개 파일: 저장된 원문 그대로이며 화면 데이터 위치로 쓰지 않습니다.")
    notes.append("이 검사는 파일 동일성만 확인합니다. 스키마별 의미 검증은 저장소의 verify_*.py 검증기로 확인합니다.")
    return {"ok": not problems, "problems": problems, "notes": notes, "checked_files": len(listed),
            "bundle_checks": bundle_checks}


def main(argv: list) -> int:
    args = [arg for arg in argv if arg != "--json"]
    package = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    result = verify(package)
    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("패키지:", package)
        print("확인한 파일:", result["checked_files"])
        for check in result["bundle_checks"]:
            print(" -", check["key"], check["state"], check.get("detail", ""))
        if result["ok"]:
            print("결과: 통과 — 모든 파일이 MANIFEST와 원본 묶음 해시 목록과 일치합니다.")
        else:
            print("결과: 실패")
            for problem in result["problems"]:
                print("   *", problem)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
