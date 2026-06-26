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
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import id_registry

_PORT = int(os.environ.get("MINT_PORT", 5052))


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
            self._send_json(200, {
                "status": "ok",
                "counter_file": str(id_registry._COUNTER_FILE),
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mint":
            self._send_json(404, {"error": "not found"})
            return

        body: dict = {}
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON"})
                return

        prefix = str(body.get("type", "MSN")).upper()
        try:
            mission_id = id_registry.next_id(prefix)
            self._send_json(200, {
                "mission_id": mission_id,
                "type": prefix,
                "status": "allocated",
            })
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})


def main() -> None:
    server = HTTPServer(("0.0.0.0", _PORT), MintHandler)
    print(f"[mint-server] Listening on :{_PORT}  (POST /mint, GET /health)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mint-server] Stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
