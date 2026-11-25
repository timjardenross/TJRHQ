"""Shared fakes for the notification-service structured-result tests. Nothing here can reach the network:
``urllib.request.urlopen`` is replaced by a scripted transport, ``time.sleep`` is recorded not slept."""
from __future__ import annotations

import io
import json
import urllib.error


class _Resp:
    def __init__(self, payload: bytes):
        self._p = payload

    def read(self, *a):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ScriptedTelegram:
    """Scripted per-request behaviour. Tokens: ok, timeout, reset, h400, h429, h500, refused, badjson, okNoId."""

    def __init__(self, *script: str):
        self.script = list(script)
        self.wire: list[str] = []          # text of every request actually written (the 'wire')

    def __call__(self, req, timeout=None):
        self.wire.append(json.loads(req.data)["text"])
        tok = self.script.pop(0) if self.script else "ok"
        n = len(self.wire)
        if tok == "ok":
            return _Resp(json.dumps({"ok": True, "result": {"message_id": 1000 + n}}).encode())
        if tok == "okNoId":
            return _Resp(json.dumps({"ok": True, "result": {}}).encode())
        if tok == "badjson":
            return _Resp(b"<html>")
        if tok == "timeout":
            raise TimeoutError("timed out")
        if tok == "reset":
            raise ConnectionResetError("Connection reset by peer")
        if tok == "refused":
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        code = {"h400": 400, "h429": 429, "h500": 500}[tok]
        raise urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps({"description": f"desc {code}"}).encode()))


LONG_PLAIN = ("word " * 2000).strip()          # ~10k chars -> 3 chunks at 4096
LONG_RAW = "<b>" + ("word " * 2000).strip() + "</b>"
