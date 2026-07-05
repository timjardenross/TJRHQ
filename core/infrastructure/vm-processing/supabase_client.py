"""Supabase REST client for the VM Knowledge Processing Engine
(USS-TJR-MSN-0205C).

Stdlib-only urllib client, matching the convention used throughout the repo
(e.g. core/capture/enrichment_worker.py) rather than the supabase-py SDK.
Worker code depends on this only via duck-typed methods (get, insert,
patch) so tests can substitute a fake with no network access.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class SupabaseError(RuntimeError):
    pass


def _strip_null_bytes(value):
    """Postgres text/jsonb columns reject \\u0000 (error 22P05) — some source
    PDFs contain embedded null bytes in their text streams, which otherwise
    surfaces as a write-time crash on an already-successful extraction.
    Recurses through dicts/lists so it covers nested fields like metadata
    and processing_log, not just top-level string values."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _strip_null_bytes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_null_bytes(v) for v in value]
    return value


class SupabaseClient:
    def __init__(self, url: str, service_role_key: str, timeout: int = 15):
        self.url = url.rstrip("/")
        self.key = service_role_key
        self.timeout = timeout

    def _headers(self, prefer: str = "") -> dict:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _require_config(self):
        if not self.url or not self.key:
            raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")

    def get(self, path: str) -> list:
        """path is a PostgREST path+query, e.g. 'processing_documents?status=eq.received&limit=20'."""
        self._require_config()
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"GET {path} failed: {exc.code} {exc.read().decode(errors='replace')}") from exc

    def get_one(self, path: str):
        rows = self.get(path)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> dict:
        self._require_config()
        payload = json.dumps(_strip_null_bytes(row)).encode()
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{table}",
            data=payload, method="POST",
            headers={**self._headers(prefer="return=representation"),
                     "Content-Length": str(len(payload))},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read())
                return result[0] if isinstance(result, list) else result
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"INSERT {table} failed: {exc.code} {exc.read().decode(errors='replace')}") from exc

    def patch(self, table: str, match: dict, update: dict) -> None:
        self._require_config()
        qs = "&".join(f"{k}=eq.{urllib.parse.quote(str(v))}" for k, v in match.items())
        payload = json.dumps(_strip_null_bytes(update)).encode()
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{qs}",
            data=payload, method="PATCH",
            headers={**self._headers(), "Content-Length": str(len(payload))},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"PATCH {table} failed: {exc.code} {exc.read().decode(errors='replace')}") from exc

    def delete(self, table: str, match: dict) -> None:
        """USS-TJR-MSN-0206J-4: used to clear stale processing_chunks rows
        from a previous partial embed before a retry re-runs _do_embed —
        otherwise the (document_id, chunk_index) unique constraint would
        collide on re-insert."""
        self._require_config()
        qs = "&".join(f"{k}=eq.{urllib.parse.quote(str(v))}" for k, v in match.items())
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{qs}",
            method="DELETE",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"DELETE {table} failed: {exc.code} {exc.read().decode(errors='replace')}") from exc
