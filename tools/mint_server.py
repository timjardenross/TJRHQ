#!/usr/bin/env python3
"""
MSN-0147: Mission ID mint server — shared REST allocator for all clients.

Endpoints:
    POST /mint          Body: {"type": "MSN"} (optional; defaults to MSN)
                        Response: {"mission_id": "USS-TJR-MSN-NNNN", "type": "MSN", "status": "allocated"}
    GET  /health        Response: {"status": "ok", "counter_file": "<path>"}

Port: MINT_PORT env var (default 5052).
No external dependencies — uses Python built-in http.server.

Usage:
    python3 tools/mint_server.py
    MINT_PORT=5053 python3 tools/mint_server.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import id_registry

_PORT = int(os.environ.get("MINT_PORT", 5052))
_HOST = os.environ.get("MINT_HOST", "127.0.0.1")  # localhost-only by default; override for debugging
_VALID_PREFIXES = {"MSN", "BREQ", "DEC"}


class MintHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # suppress access log noise
        print(f"[mint-server] {fmt % args}", file=sys.stderr)

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            # File not yet existing is normal (created on first mint).
            # Degraded only if the file exists but is unreadable/corrupt.
            counter_file = id_registry._COUNTER_FILE
            if counter_file.exists():
                try:
                    import json as _json
                    _json.loads(counter_file.read_text(encoding="utf-8"))
                    counter_ok = True
                except Exception:
                    counter_ok = False
            else:
                counter_ok = True
            self._send_json(200 if counter_ok else 503, {
                "status": "ok" if counter_ok else "degraded",
                "counter_file": str(counter_file),
                "counter_readable": counter_ok,
                "valid_prefixes": sorted(_VALID_PREFIXES),
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mint":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body: dict = {}
        if length:
            if length > 1024:
                self._send_json(400, {"error": "request_too_large", "message": "Body exceeds 1 KB"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid_json", "message": "Request body is not valid JSON"})
                return

        prefix = str(body.get("type", "MSN")).upper()
        if prefix not in _VALID_PREFIXES:
            self._send_json(400, {
                "error": "invalid_prefix",
                "message": f"Unknown prefix. Valid prefixes: {', '.join(sorted(_VALID_PREFIXES))}",
                "valid_prefixes": sorted(_VALID_PREFIXES),
            })
            return

        try:
            mission_id = id_registry.next_id(prefix)
            self._send_json(200, {
                "mission_id": mission_id,
                "type": prefix,
                "status": "allocated",
                "allocated_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            self._send_json(500, {"error": "internal_error", "message": "Failed to allocate ID. Please retry.", "detail": str(exc)})


def main() -> None:
    server = HTTPServer((_HOST, _PORT), MintHandler)
    print(f"[mint-server] Listening on :{_PORT}  (POST /mint, GET /health)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mint-server] Stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
