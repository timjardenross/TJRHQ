"""
Workflow repository — the data-access seam for the Phase A governance workflow.

The governance service, watchlist tracker, and Telstra PoC all talk to a
WorkflowRepository rather than to Supabase directly, so the orchestration logic
is:
  * testable in-memory (InMemoryRepository) — no network, deterministic, and the
    basis for the offline Telstra PoC (the GO/NO-GO gate), and
  * runnable in production (SupabaseRepository) — a thin adapter over the existing
    PostgREST helpers in intelligence.persistence.intelligence_store.

Rows are plain dicts keyed by their table's PK: intelligence_events(event_id),
intelligence_briefs(brief_id), watchlist_items(id), watchlist_tracking(id),
brief_lessons_learned(id).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class WorkflowRepository(Protocol):
    # events
    def get_event(self, event_id: str) -> Optional[dict]: ...
    def update_event(self, event_id: str, fields: dict) -> dict: ...
    def list_events(self, signal_status: Optional[str] = None) -> list[dict]: ...
    def insert_event(self, row: dict) -> dict: ...
    # briefs
    def get_brief(self, brief_id: str) -> Optional[dict]: ...
    def update_brief(self, brief_id: str, fields: dict) -> dict: ...
    def insert_brief(self, row: dict) -> dict: ...
    # watchlist + lessons
    def insert_watchlist_item(self, row: dict) -> dict: ...
    def list_watchlist_items(self, brief_id: str) -> list[dict]: ...
    def insert_watchlist_tracking(self, row: dict) -> dict: ...
    def list_watchlist_tracking(self, watchlist_item_id: str) -> list[dict]: ...
    def insert_lesson(self, row: dict) -> dict: ...


class RepositoryError(Exception):
    """Raised when a repository operation targets a missing record."""


# ─── In-memory (tests + offline PoC) ─────────────────────────────────────────
class InMemoryRepository:
    """Deterministic in-memory WorkflowRepository. IDs are caller-supplied or
    generated as 'evt-N'/'brf-N'/'wli-N'/... in insertion order (no randomness,
    so the PoC is fully reproducible)."""

    def __init__(self) -> None:
        self.events: dict[str, dict] = {}
        self.briefs: dict[str, dict] = {}
        self.watchlist_items: dict[str, dict] = {}
        self.watchlist_tracking: dict[str, dict] = {}
        self.lessons: dict[str, dict] = {}
        self._counters: dict[str, int] = {}

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]}"

    # events
    def insert_event(self, row: dict) -> dict:
        row = dict(row)
        eid = row.get("event_id") or self._next_id("evt")
        row["event_id"] = eid
        row.setdefault("signal_status", "TO_COLLECT")
        self.events[eid] = row
        return row

    def get_event(self, event_id: str) -> Optional[dict]:
        row = self.events.get(event_id)
        return dict(row) if row else None

    def update_event(self, event_id: str, fields: dict) -> dict:
        if event_id not in self.events:
            raise RepositoryError(f"no event {event_id}")
        self.events[event_id].update(fields)
        return dict(self.events[event_id])

    def list_events(self, signal_status: Optional[str] = None) -> list[dict]:
        rows = list(self.events.values())
        if signal_status is not None:
            rows = [r for r in rows if r.get("signal_status") == signal_status]
        return [dict(r) for r in rows]

    # briefs
    def insert_brief(self, row: dict) -> dict:
        row = dict(row)
        bid = row.get("brief_id") or self._next_id("brf")
        row["brief_id"] = bid
        row.setdefault("approval_status", "IN_REVIEW")
        row.setdefault("approval_audit", {})
        self.briefs[bid] = row
        return row

    def get_brief(self, brief_id: str) -> Optional[dict]:
        row = self.briefs.get(brief_id)
        return dict(row) if row else None

    def update_brief(self, brief_id: str, fields: dict) -> dict:
        if brief_id not in self.briefs:
            raise RepositoryError(f"no brief {brief_id}")
        self.briefs[brief_id].update(fields)
        return dict(self.briefs[brief_id])

    # watchlist + lessons
    def insert_watchlist_item(self, row: dict) -> dict:
        row = dict(row)
        wid = row.get("id") or self._next_id("wli")
        row["id"] = wid
        self.watchlist_items[wid] = row
        return row

    def list_watchlist_items(self, brief_id: str) -> list[dict]:
        return [dict(r) for r in self.watchlist_items.values() if r.get("brief_id") == brief_id]

    def insert_watchlist_tracking(self, row: dict) -> dict:
        row = dict(row)
        tid = row.get("id") or self._next_id("wlt")
        row["id"] = tid
        self.watchlist_tracking[tid] = row
        return row

    def list_watchlist_tracking(self, watchlist_item_id: str) -> list[dict]:
        return [dict(r) for r in self.watchlist_tracking.values()
                if r.get("watchlist_item_id") == watchlist_item_id]

    def insert_lesson(self, row: dict) -> dict:
        row = dict(row)
        lid = row.get("id") or self._next_id("les")
        row["id"] = lid
        self.lessons[lid] = row
        return row


# ─── Supabase adapter (production) ───────────────────────────────────────────
class SupabaseRepository:
    """Thin adapter delegating to intelligence.persistence.intelligence_store
    PostgREST helpers. Import is lazy so tests/PoC never require Supabase config."""

    def __init__(self) -> None:
        from intelligence.persistence import intelligence_store as store
        self._s = store

    def get_event(self, event_id: str) -> Optional[dict]:
        rows = self._s._get(f"intelligence_events?event_id=eq.{event_id}&limit=1")
        return rows[0] if rows else None

    def update_event(self, event_id: str, fields: dict) -> dict:
        return self._s.patch_row("intelligence_events", f"event_id=eq.{event_id}", fields)

    def list_events(self, signal_status: Optional[str] = None) -> list[dict]:
        q = "intelligence_events?order=collected_at.desc&limit=500"
        if signal_status is not None:
            q = f"intelligence_events?signal_status=eq.{signal_status}&limit=500"
        return self._s._get(q)

    def insert_event(self, row: dict) -> dict:
        return self._s._post("intelligence_events", row) or row

    def get_brief(self, brief_id: str) -> Optional[dict]:
        rows = self._s._get(f"intelligence_briefs?brief_id=eq.{brief_id}&limit=1")
        return rows[0] if rows else None

    def update_brief(self, brief_id: str, fields: dict) -> dict:
        return self._s.patch_row("intelligence_briefs", f"brief_id=eq.{brief_id}", fields)

    def insert_brief(self, row: dict) -> dict:
        return self._s._post("intelligence_briefs", row) or row

    def insert_watchlist_item(self, row: dict) -> dict:
        return self._s._post("watchlist_items", row) or row

    def list_watchlist_items(self, brief_id: str) -> list[dict]:
        return self._s._get(f"watchlist_items?brief_id=eq.{brief_id}")

    def insert_watchlist_tracking(self, row: dict) -> dict:
        return self._s._post("watchlist_tracking", row) or row

    def list_watchlist_tracking(self, watchlist_item_id: str) -> list[dict]:
        return self._s._get(f"watchlist_tracking?watchlist_item_id=eq.{watchlist_item_id}")

    def insert_lesson(self, row: dict) -> dict:
        return self._s._post("brief_lessons_learned", row) or row
