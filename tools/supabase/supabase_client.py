#!/usr/bin/env python3
"""Small Supabase REST helper for the USS TJR knowledge prototype."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SupabaseError(RuntimeError):
    """Raised when Supabase returns a non-successful response."""


class SupabaseClient:
    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        if not self.url or not self.key:
            raise SupabaseError(
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
                "(or SUPABASE_ANON_KEY for read-only checks)."
            )

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=body,
            method=method,
            headers=self._headers(headers),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8")
            raise SupabaseError(f"{method} {path} failed: {error.code} {detail}") from error

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = {"select": columns}
        if filters:
            params.update(filters)
        if limit is not None:
            params["limit"] = str(limit)
        query = urllib.parse.urlencode(params, safe="*,().")
        return self.request("GET", f"/rest/v1/{table}?{query}") or []

    def upsert(self, table: str, rows: list[dict[str, Any]], conflict: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"on_conflict": conflict})
        return self.request(
            "POST",
            f"/rest/v1/{table}?{query}",
            rows,
            headers={
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        ) or []

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.request(
            "POST",
            f"/rest/v1/{table}",
            rows,
            headers={"Prefer": "return=representation"},
        ) or []

    def update(
        self,
        table: str,
        values: dict[str, Any],
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(filters, safe="*,().")
        return self.request(
            "PATCH",
            f"/rest/v1/{table}?{query}",
            values,
            headers={"Prefer": "return=representation"},
        ) or []

    def delete(self, table: str, filters: dict[str, str]) -> None:
        query = urllib.parse.urlencode(filters, safe="*,().")
        self.request("DELETE", f"/rest/v1/{table}?{query}")

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", f"/rest/v1/rpc/{name}", payload)


# ---------------------------------------------------------------------------
# Module-level convenience shims — used by slack-bot commands that import
# `from supabase_client import supabase_get, is_configured` after sys.path
# manipulation may have resolved to this file instead of core/health/supabase_client.py.
# ---------------------------------------------------------------------------

def _module_client() -> SupabaseClient:
    return SupabaseClient()


def supabase_get(path: str, timeout: int = 10) -> list[dict[str, Any]]:
    import urllib.parse as _up
    client = _module_client()
    full_path = f"/rest/v1/{path}" if not path.startswith("/") else path
    result = client.request("GET", full_path)
    return result if isinstance(result, list) else ([result] if result else [])


def is_configured() -> bool:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    return bool(url and key)
