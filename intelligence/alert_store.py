"""Durable AlertStore for ``intelligence.alert_dispatcher`` backed by Supabase PostgREST (service role).

Tables: ``public.incident_alert_state`` and ``public.incident_alert_sends`` (``docs/migration-drafts/DRAFT-incident-alert-state.sql``
plus ``DRAFT-incident-alert-claims.sql`` for the claim columns and the ``test`` mode). Nothing here runs unless the caller builds a store;
``intelligence.alert_runner`` only does so with INCIDENT_ALERTS_V1 on.

Guarantees
  * CLAIM BEFORE SEND. A real send first wins an atomic compare-and-set: ``PATCH incident_alert_state ?incident_key=eq.K & <sent> is null &
    <claim> is null`` setting a random claim token. PostgREST turns that into ONE ``UPDATE ... WHERE`` statement; Postgres re-checks the
    predicate under the row lock, so of N concurrent callers exactly one gets a row back. Everyone else gets nothing and does not send.
  * SENT only after a successful send: ``complete`` stamps ``alerted_at`` / ``restoration_sent_at`` (token-guarded). A failed send calls
    ``release`` (token-guarded) which clears the claim, so the next pass retries.
  * AT MOST ONCE over liveness: a claim has NO expiry for real alerts. If a process dies between claiming and releasing/completing, that
    alert stays claimed (logged as refused on later passes) rather than risking a duplicate; clear it by hand with a service-role UPDATE.
  * ``put`` never writes the real-send columns (only headline, event_ids and the dry-run columns), so a stale cache can never un-send or
    re-arm an alert. Dry-run columns are separate and never consume the real "once".
  * Fail closed: any read failure raises ``StoreUnavailable``; the dispatcher then sends nothing.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from intelligence.alert_dispatcher import AlertState

log = logging.getLogger(__name__)

STATE = "incident_alert_state"
SENDS = "incident_alert_sends"
CACHE_DAYS = 30
TEST_LEASE = timedelta(minutes=10)

# kind -> (sent column, claim time column, claim token column)
COLUMNS = {
    "alert": ("alerted_at", "alert_claimed_at", "alert_claim_token"),
    "restoration": ("restoration_sent_at", "restoration_claimed_at", "restoration_claim_token"),
    "test": ("test_sent_at", "test_claimed_at", "test_claim_token"),
}

Transport = Callable[..., list]   # (method, table, params: list[tuple[str, str]], body=None, prefer=None) -> list[dict]


class StoreUnavailable(RuntimeError):
    """The durable store could not be read or written; the caller must not send."""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(v) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)


def http_transport(url: str | None = None, key: str | None = None, timeout: int = 8) -> Transport:
    """Service-role PostgREST transport, same env vars and header pattern as intelligence/captains_brief.py (``_sb_request``)."""
    url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
    key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise StoreUnavailable("Supabase not configured (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY unset)")

    def call(method, table, params, body=None, prefer=None):
        q = urllib.parse.urlencode(params, safe="(),.:*")
        headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{url}/rest/v1/{table}{'?' + q if q else ''}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url from SUPABASE_URL env, https
                raw = resp.read()
        except Exception as exc:
            raise StoreUnavailable(f"{method} {table}: {type(exc).__name__}") from exc
        return json.loads(raw) if raw else []
    return call


class PostgrestAlertStore:
    def __init__(self, transport: Transport | None = None, *, now: Callable[[], datetime] | None = None):
        self._t = transport or http_transport()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cache: dict[str, AlertState] | None = None
        self._persisted: dict[str, tuple] = {}

    # -- helpers -----------------------------------------------------------------------------------------------------------------
    def _call(self, *a, **k) -> list:
        try:
            return self._t(*a, **k) or []
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise StoreUnavailable(f"{type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _state(row: dict) -> AlertState:
        return AlertState(incident_key=row["incident_key"], event_ids={str(i) for i in row.get("event_ids") or []}, headline=row.get("headline") or "",
                          alerted_at=_parse(row.get("alerted_at")), restoration_sent_at=_parse(row.get("restoration_sent_at")),
                          dry_alerted_at=_parse(row.get("dry_alerted_at")), dry_restoration_at=_parse(row.get("dry_restoration_at")))

    @staticmethod
    def _sig(st: AlertState) -> tuple:
        return (frozenset(st.event_ids), st.headline, st.dry_alerted_at, st.dry_restoration_at)

    def load(self) -> dict[str, AlertState]:
        since = _iso(self._now() - timedelta(days=CACHE_DAYS))
        rows = self._call("GET", STATE, [("select", "*"), ("updated_at", f"gte.{since}"), ("limit", "2000")])
        self._cache = {r["incident_key"]: self._state(r) for r in rows if not str(r["incident_key"]).startswith("test-")}
        self._persisted = {k: self._sig(v) for k, v in self._cache.items()}
        return self._cache

    # -- AlertStore protocol -----------------------------------------------------------------------------------------------------
    def find(self, event_ids: set) -> AlertState | None:
        if self._cache is None:
            self.load()
        ids = {str(i) for i in event_ids}
        for st in self._cache.values():
            if st.event_ids & ids:
                return st
        return None

    def put(self, state: AlertState) -> None:
        if self._cache is None:
            self.load()
        self._cache[state.incident_key] = state
        sig = self._sig(state)
        if self._persisted.get(state.incident_key) == sig:
            return
        body = {"incident_key": state.incident_key, "headline": state.headline, "event_ids": sorted(state.event_ids), "updated_at": _iso(self._now())}
        if state.dry_alerted_at:
            body["dry_alerted_at"] = _iso(state.dry_alerted_at)
        if state.dry_restoration_at:
            body["dry_restoration_at"] = _iso(state.dry_restoration_at)
        self._call("POST", STATE, [("on_conflict", "incident_key")], body, "resolution=merge-duplicates,return=minimal")
        self._persisted[state.incident_key] = sig

    def log_send(self, at: datetime, mode: str, incident_key: str = "", kind: str = "alert") -> None:
        if not incident_key:
            return
        self._call("POST", SENDS, [], {"incident_key": incident_key, "kind": "alert" if kind == "test" else kind, "mode": mode, "sent_at": _iso(at)}, "return=minimal")

    def sends_since(self, since: datetime, mode: str) -> int:
        rows = self._call("GET", SENDS, [("select", "id"), ("mode", f"eq.{mode}"), ("sent_at", f"gt.{_iso(since)}"), ("limit", "1000")])
        return len(rows)

    # -- claim / complete / release ----------------------------------------------------------------------------------------------
    def claim(self, kind: str, incident_key: str, *, now: datetime | None = None, resend_after: timedelta | None = None) -> str | None:
        """Atomically claim the right to send ``kind`` for ``incident_key``; returns the claim token, or None if someone else holds it or it
        was already sent. ``resend_after`` (test alerts only) lets a sent row be claimed again once its sent time is older than that."""
        sent, claimed, tok = COLUMNS[kind]
        now = now or self._now()
        token = uuid.uuid4().hex
        if kind == "test":
            params = [("incident_key", f"eq.{incident_key}"),
                      ("and", f"(or({sent}.is.null,{sent}.lt.{_iso(now - (resend_after or timedelta(hours=6)))}),or({claimed}.is.null,{claimed}.lt.{_iso(now - TEST_LEASE)}))")]
        else:
            params = [("incident_key", f"eq.{incident_key}"), (sent, "is.null"), (claimed, "is.null")]
        rows = self._call("PATCH", STATE, params, {claimed: _iso(now), tok: token}, "return=representation")
        return token if rows else None

    def complete(self, kind: str, incident_key: str, token: str, now: datetime) -> bool:
        sent, claimed, tok = COLUMNS[kind]
        rows = self._call("PATCH", STATE, [("incident_key", f"eq.{incident_key}"), (tok, f"eq.{token}")],
                          {sent: _iso(now), claimed: None, tok: None, "updated_at": _iso(now)}, "return=representation")
        if rows and self._cache is not None and incident_key in self._cache and kind != "test":
            setattr(self._cache[incident_key], "alerted_at" if kind == "alert" else "restoration_sent_at", now)
        return bool(rows)

    def release(self, kind: str, incident_key: str, token: str) -> bool:
        _sent, claimed, tok = COLUMNS[kind]
        rows = self._call("PATCH", STATE, [("incident_key", f"eq.{incident_key}"), (tok, f"eq.{token}")], {claimed: None, tok: None}, "return=representation")
        return bool(rows)

    def ensure_row(self, incident_key: str, headline: str) -> None:
        """Create the state row if missing without touching an existing one (used by the controlled test's fixed, non-incident key)."""
        self._call("POST", STATE, [("on_conflict", "incident_key")], {"incident_key": incident_key, "headline": headline}, "resolution=ignore-duplicates,return=minimal")
