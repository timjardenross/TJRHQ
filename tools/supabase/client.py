#!/usr/bin/env python3
"""Supabase persistence wrapper for Commander runtime events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


COMMANDER_EVENT_TABLE = "commander_events"
COMMANDER_DECISION_TABLE = "commander_decisions"
COMMANDER_MISSION_TABLE = "commander_mission_candidates"
COMMANDER_MEMORY_TABLE = "commander_memory_events"


@dataclass
class SupabaseWriteResult:
    ok: bool
    enabled: bool
    table: str
    error: str | None = None


class CommanderSupabaseClient:
    """Supabase client with insert, select, patch, and delete support.

    Uses supabase-py when installed. Falls back to PostgREST over urllib so the
    Slack bot can run without adding a dependency during this MVP.
    """

    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.key_source = "service_role" if self.key else "missing"
        self._supabase = None
        if self.is_enabled():
            try:
                from supabase import create_client  # type: ignore

                self._supabase = create_client(self.url, self.key)
            except Exception:
                self._supabase = None

    @property
    def raw_client(self):
        """Return the underlying supabase-py client when available."""
        return self._supabase

    def is_enabled(self) -> bool:
        return bool(self.url and self.key)

    def insert(self, table: str, payload: dict[str, Any]) -> SupabaseWriteResult:
        if not self.is_enabled():
            return SupabaseWriteResult(ok=False, enabled=False, table=table, error="supabase_disabled")
        try:
            if self._supabase is not None:
                self._supabase.table(table).insert(payload).execute()
            else:
                self._rest_insert(table, payload)
            return SupabaseWriteResult(ok=True, enabled=True, table=table)
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8")[:200]
            except Exception:
                detail = ""
            error_name = f"HTTPError({error.code})"
            if error.code == 401:
                error_name = f"{error_name}:unauthorized:{self.key_source}"
            return SupabaseWriteResult(ok=False, enabled=True, table=table, error=error_name + (f":{detail}" if detail else ""))
        except Exception as error:
            return SupabaseWriteResult(ok=False, enabled=True, table=table, error=type(error).__name__)

    def _rest_insert(self, table: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}",
            data=body,
            method="POST",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        with urllib.request.urlopen(request, timeout=20):
            return

    def select_recent(self, table: str, limit: int) -> list[dict[str, Any]]:
        if not self.is_enabled():
            return []
        try:
            if self._supabase is not None:
                result = (
                    self._supabase.table(table)
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return list(result.data or [])
            return self._rest_select_recent(table, limit)
        except Exception:
            return []

    def _rest_select_recent(self, table: str, limit: int) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
        })
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{params}",
            method="GET",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def get(self, query: str, timeout: int = 10) -> list[dict[str, Any]]:
        """GET /rest/v1/{query} — query is the full path including filters.

        Example: client.get("missions?id=eq.USS-TJR-MSN-0001&select=id,status")
        Returns a list of row dicts, or [] on error / disabled.
        """
        if not self.is_enabled():
            return []
        try:
            if self._supabase is not None:
                # supabase-py path: parse table + params from query string
                table, _, params_str = query.partition("?")
                builder = self._supabase.table(table).select("*")
                # Pass raw params via rpc-style for complex filters; fall back to REST
                result = self._rest_get(query, timeout)
                return result
            return self._rest_get(query, timeout)
        except Exception:
            return []

    def _rest_get(self, query: str, timeout: int = 10) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{query}",
            method="GET",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result if isinstance(result, list) else [result]

    def _patch(self, query: str, payload: dict[str, Any], timeout: int = 10) -> bool:
        """PATCH /rest/v1/{query} with payload. Returns True on success.

        Example: client._patch("missions?mission_id=eq.USS-TJR-MSN-0001", {"status": "Active"})
        """
        if not self.is_enabled():
            return False
        try:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.url}/rest/v1/{query}",
                data=body,
                method="PATCH",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout):
                return True
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).debug("[supabase] _patch failed (%s): %s", query, exc)
            return False

    def delete(self, query: str, timeout: int = 10) -> bool:
        """DELETE /rest/v1/{query}. Returns True on success.

        Example: client.delete("escalation_history?id=eq.some-key")
        """
        if not self.is_enabled():
            return False
        try:
            request = urllib.request.Request(
                f"{self.url}/rest/v1/{query}",
                method="DELETE",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Prefer": "return=minimal",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout):
                return True
        except Exception:
            return False


def is_supabase_enabled() -> bool:
    return CommanderSupabaseClient().is_enabled()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_commander_event(payload: dict[str, Any]) -> SupabaseWriteResult:
    return CommanderSupabaseClient().insert(COMMANDER_EVENT_TABLE, payload)


def log_decision(payload: dict[str, Any]) -> SupabaseWriteResult:
    return CommanderSupabaseClient().insert(COMMANDER_DECISION_TABLE, payload)


def log_mission_candidate(payload: dict[str, Any]) -> SupabaseWriteResult:
    return CommanderSupabaseClient().insert(COMMANDER_MISSION_TABLE, payload)


def log_memory_event(payload: dict[str, Any]) -> SupabaseWriteResult:
    return CommanderSupabaseClient().insert(COMMANDER_MEMORY_TABLE, payload)


def fetch_recent_context(limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    client = CommanderSupabaseClient()
    return {
        "events": client.select_recent(COMMANDER_EVENT_TABLE, limit),
        "decisions": client.select_recent(COMMANDER_DECISION_TABLE, limit),
        "missions": client.select_recent(COMMANDER_MISSION_TABLE, limit),
        "memory": client.select_recent(COMMANDER_MEMORY_TABLE, limit),
    }
