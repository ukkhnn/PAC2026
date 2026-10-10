#!/usr/bin/env python3
"""선택 사항: 패키지를 이 컴퓨터 안(127.0.0.1)에서만 정적 파일로 제공한다 (Python 3.9+ 표준 라이브러리).

index.html은 파일을 더블클릭해도 열린다. 브라우저 정책 때문에 file:// 열기가 막힌 경우에만 사용한다.
이 서버는 GET/HEAD만 허용하고 다른 요청은 거부한다. 추론·전송·저장 기능이 없다.

사용: python3 tools/serve_package.py [--port 8765]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
from pathlib import Path

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; "
       "font-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")


class ReadOnlyHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def list_directory(self, path):  # noqa: D401 - 디렉터리 목록은 제공하지 않는다
        self.send_error(404, "디렉터리 목록은 제공하지 않습니다.")
        return None

    def _reject(self) -> None:
        self.send_error(405, "읽기 전용 패키지입니다 (GET/HEAD만 허용).")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _reject  # type: ignore[assignment]


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="관리자 대시보드 패키지 로컬 정적 제공 (127.0.0.1 전용)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(ReadOnlyHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"http://127.0.0.1:{server.server_address[1]}/index.html  (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
