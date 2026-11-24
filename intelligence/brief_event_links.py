"""Opt-in recording of which events a Captain's brief contained (default OFF), so surfacing can be measured by id, not text match.

Why not ``intelligence_store.link_events_to_brief``: that function PATCHes ``intelligence_events.brief_id``, which is a foreign key to
``intelligence_briefs`` (the canonical resilience brief). Captain's briefs live in ``captains_daily_briefs`` (a different id space), so
passing its id would violate the key (the PATCH fails) and, were it ever to succeed, would overwrite a legitimate canonical-brief link.
The legacy path is therefore untouched. This module records the links in a SEPARATE table, ``captains_brief_events``, drafted (NOT applied)
in ``docs/migration-drafts/DRAFT-captains-brief-events.sql``.

Flag: ``CAPTAINS_BRIEF_RECORD_EVENTS`` (read at call time, default OFF). While off, ``note`` and ``flush`` do nothing at all.
Flow: the evidence block calls ``note(kind, ids)`` while rendering; ``send_brief`` calls ``flush(brief_type)`` after the brief is persisted.
Best-effort: a failure is logged and never raised, the brief is never blocked.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from typing import Protocol

log = logging.getLogger(__name__)

FLAG = "CAPTAINS_BRIEF_RECORD_EVENTS"
TABLE = "captains_brief_events"
_TRUE = ("1", "true", "yes", "on")
_local = threading.local()


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


class LinkStore(Protocol):
    def record(self, brief_ref: str | None, brief_type: str, event_ids: list[str]) -> None: ...


class InMemoryLinkStore:
    def __init__(self):
        self.rows: list[dict] = []

    def record(self, brief_ref, brief_type, event_ids):
        self.rows += [{"brief_id": brief_ref, "brief_type": brief_type, "event_id": e} for e in event_ids]


class PostgrestLinkStore:
    """Writes to ``captains_brief_events`` via PostgREST (``on_conflict`` ignore). Only constructed when the flag is on; the table must
    first exist (draft migration, not applied here), otherwise the POST fails and is logged."""

    def __init__(self, url: str, key: str):
        self.url, self.key = url, key

    def record(self, brief_ref, brief_type, event_ids):
        if not event_ids:
            return
        body = json.dumps([{"brief_id": brief_ref, "brief_type": brief_type, "event_id": e} for e in event_ids]).encode()
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                   "Prefer": "return=minimal,resolution=ignore-duplicates"}
        req = urllib.request.Request(f"{self.url}/rest/v1/{TABLE}?on_conflict=brief_id,event_id", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10):  # nosec B310 - SUPABASE_URL env, https
            pass


def begin() -> None:
    _local.ids = {}


def note(kind: str, event_ids: list[str]) -> None:
    """Remember event ids shown in the brief being rendered. No-op unless the flag is on."""
    if not enabled():
        return
    store = getattr(_local, "ids", None)
    if store is None:
        store = _local.ids = {}
    store.setdefault(kind, set()).update(str(e) for e in event_ids)


def drain(kind: str) -> list[str]:
    store = getattr(_local, "ids", None) or {}
    return sorted(store.pop(kind, set()))


def flush(brief_type: str, *, brief_ref: str | None = None, store: LinkStore | None = None, kind: str | None = None) -> int:
    """Write the noted ids for ``brief_type`` (evidence kind defaults to the same name). Returns how many were recorded; 0 when off."""
    if not enabled():
        return 0
    ids = drain(kind or brief_type)
    if not ids:
        return 0
    try:
        if store is None:
            url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            if not url or not key:
                return 0
            store = PostgrestLinkStore(url, key)
        store.record(brief_ref, brief_type, ids)
        return len(ids)
    except Exception as exc:  # noqa: BLE001 - best-effort audit trail; the brief is already generated and sent
        log.warning("Could not record brief event links (%s): %s", brief_type, exc)
        return 0
