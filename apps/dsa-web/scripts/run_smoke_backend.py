from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _has_uvicorn() -> bool:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        return False
    return True


class _StubHandler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/v1/auth/status":
            self._write_json(
                200,
                {
                    "authEnabled": False,
                    "loggedIn": False,
                    "passwordSet": False,
                    "passwordChangeable": False,
                    "setupState": "no_password",
                },
            )
            return

        if self.path == "/api/health":
            self._write_json(200, {"status": "ok", "stub": True})
            return

        self._write_json(404, {"error": "not_found", "message": self.path})

    def do_POST(self) -> None:  # noqa: N802
        self._write_json(
            503,
            {
                "error": "stub_backend_only",
                "message": "Smoke backend stub is active because uvicorn is unavailable.",
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _run_stub_server(host: str, port: int) -> None:
    class _ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with _ReusableTCPServer((host, port), _StubHandler) as httpd:
        print(f"[smoke-backend] using stub backend on http://{host}:{port}", flush=True)
        httpd.serve_forever()


def _run_real_backend(host: str, port: int) -> int:
    repo_root = _repo_root()
    cmd = [sys.executable, "main.py", "--webui-only", "--host", host, "--port", str(port)]
    proc = subprocess.run(cmd, cwd=repo_root)
    return proc.returncode


def main() -> int:
    host = os.getenv("DSA_WEB_SMOKE_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("DSA_WEB_SMOKE_BACKEND_PORT", "8000"))

    if _has_uvicorn():
        return _run_real_backend(host, port)

    _run_stub_server(host, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
