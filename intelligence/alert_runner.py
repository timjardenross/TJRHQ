"""Scheduled caller, controlled delivery test and 7-day replay for ``intelligence.alert_dispatcher``.

``run_after_collection`` is called at the end of each collection batch by the EXISTING ``intelligence.scheduler`` jobs (no second scheduler).
Strictly gated: with INCIDENT_ALERTS_V1 unset it returns immediately, before importing or reading anything. It never raises into the
collection job, never overlaps itself, and stops handling incidents once its time budget (INCIDENT_ALERT_BUDGET_S, default 25 s) is spent.
It is dry-run unless INCIDENT_ALERTS_SEND is truthy AND INCIDENT_ALERT_DESTINATION is set (``xo`` = the XO bot's default chat).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from intelligence import alert_dispatcher as ad

log = logging.getLogger(__name__)

BUDGET_ENV = "INCIDENT_ALERT_BUDGET_S"
LOOKBACK_ENV = "INCIDENT_ALERT_LOOKBACK_HOURS"
DEFAULT_BUDGET_S = 25.0
DEFAULT_LOOKBACK_H = 72
TEST_KEY = "test-alert-path"                   # fixed, never an ``inc-`` incident key
_lock = threading.Lock()


def _num(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return min(hi, max(lo, float(os.getenv(name, "") or default)))
    except ValueError:
        return default


def load_events(hours: int, *, limit: int | None = None) -> list[dict]:
    from intelligence import brief_evidence as be
    from intelligence.captains_brief import _sb_request
    events = be.load_events(_sb_request, hours=hours, **({} if limit is None else {"limit": limit}))
    note = be.retrieval_note(events, hours)
    if note:
        log.warning("[incident-alert] %s", note)
    return events


def run_after_collection(source: str = "", *, store=None, sender: Callable | None = None, events: list[dict] | None = None,
                         now: datetime | None = None) -> dict | None:
    """One alert pass after a collection batch. Returns a small summary (or None when the master flag is off). Never raises."""
    if not ad.enabled():
        return None
    if not _lock.acquire(blocking=False):
        log.info("[incident-alert] pass already running; skipping (%s)", source)
        return {"skipped": "busy"}
    started = time.monotonic()
    try:
        from intelligence import incident_clustering as ic
        budget = _num(BUDGET_ENV, DEFAULT_BUDGET_S, 2, 120)
        deadline = started + budget
        now = now or datetime.now(timezone.utc)
        if events is None:
            events = load_events(int(_num(LOOKBACK_ENV, DEFAULT_LOOKBACK_H, 24, 168)))
        if not events:
            return {"source": source, "events": 0, "handled": 0}
        incidents = ic.cluster_incidents(events, now=now, force=True)
        if time.monotonic() > deadline:
            log.warning("[incident-alert] budget spent clustering; skipping dispatch (%s)", source)
            return {"source": source, "events": len(events), "handled": 0, "budget_exceeded": True}
        if store is None:
            from intelligence.alert_store import PostgrestAlertStore
            store = PostgrestAlertStore()
        if sender is None and ad.real_send_allowed():
            from intelligence import alert_telegram
            sender = alert_telegram.send
        out = ad.process(incidents, now=now, store=store, sender=sender, deadline=deadline)
        summary = {"source": source, "events": len(events), "incidents": len(incidents), "handled": len(out),
                   "sent": sum(1 for p in out if p["sent"]), "dry": sum(1 for p in out if p["dry_run"]),
                   "deferred": sum(1 for p in out if p["deferred"]), "seconds": round(time.monotonic() - started, 2)}
        log.info("[incident-alert] pass complete: %s", summary)
        return summary
    except Exception as exc:  # noqa: BLE001 - alerting must never break or delay the collection job; nothing is sent when the store is unreadable
        log.warning("[incident-alert] pass failed (%s): %s: %s", source, type(exc).__name__, exc)
        return {"source": source, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        _lock.release()


# ── controlled delivery test ─────────────────────────────────────────────────────────────────────────────────────────────────────

def controlled_test(*, yes: bool, destination: str | None = None, store=None, sender: Callable | None = None, now: datetime | None = None,
                    window_hours: float = 6.0, out: Callable[[str], None] = print) -> int:
    """Send exactly ONE clearly-labelled test alert through the real sender and record it (mode='test'); a second call inside the window is
    suppressed from persisted state. Uses the fixed key ``test-alert-path``, never an incident key, never touches incident state.
    Exit codes: 0 sent or suppressed, 1 send/store failure, 2 refused (no --yes / no destination)."""
    from intelligence import alert_telegram
    dest = (destination or os.getenv(ad.DESTINATION_ENV, "")).strip()
    if not yes:
        out("[controlled-test] REFUSED: pass --yes to send one test alert. Nothing was sent.")
        return 2
    if not dest:
        out(f"[controlled-test] REFUSED: no destination. Pass --destination xo (or set {ad.DESTINATION_ENV}). Nothing was sent.")
        return 2
    now = now or datetime.now(timezone.utc)
    window = timedelta(hours=window_hours)
    out(f"[controlled-test] destination={dest} key={TEST_KEY} window={window_hours:g}h")
    try:
        if store is None:
            from intelligence.alert_store import PostgrestAlertStore
            store = PostgrestAlertStore()
        store.ensure_row(TEST_KEY, alert_telegram.TEST_HEADLINE)
        token = store.claim("test", TEST_KEY, now=now, resend_after=window)
    except Exception as exc:  # noqa: BLE001 - fail closed: no durable state, no send
        out(f"[controlled-test] FAILED before sending (store unavailable, nothing sent): {type(exc).__name__}: {exc}")
        return 1
    if token is None:
        out(f"[controlled-test] SUPPRESSED: a test alert was already sent (or is in progress) within the last {window_hours:g}h; nothing sent.")
        return 0
    payload = {"kind": "test", "incident_key": TEST_KEY, "headline": alert_telegram.TEST_HEADLINE, "text": alert_telegram.TEST_HEADLINE}
    ok = False
    try:
        ok = bool((sender or alert_telegram.send)(payload, dest))
    except Exception as exc:  # noqa: BLE001 - reported below
        out(f"[controlled-test] send raised: {type(exc).__name__}: {exc}")
    if not ok:
        try:
            store.release("test", TEST_KEY, token)
        except Exception as exc:  # noqa: BLE001
            out(f"[controlled-test] could not release claim (self-expires in 10 min): {exc}")
        out("[controlled-test] FAILED: the sender did not confirm delivery. State left retryable.")
        return 1
    try:
        store.complete("test", TEST_KEY, token, now)
        store.log_send(now, "test", TEST_KEY, "alert")
    except Exception as exc:  # noqa: BLE001
        out(f"[controlled-test] SENT but recording failed ({type(exc).__name__}: {exc}); a re-run after 10 min would send again.")
        return 1
    out("[controlled-test] SENT one test alert and recorded it in incident_alert_sends (mode=test). Re-run within the window to prove suppression.")
    return 0


# ── 7-day replay (read-only) ─────────────────────────────────────────────────────────────────────────────────────────────────────

def replay(events: list[dict], *, bucket_minutes: int = 30, out: Callable[[str], None] = print) -> list[dict]:
    """What WOULD have alerted over the supplied events, replayed in collection order against a throwaway in-memory store. Reads only; the
    dispatcher is forced into ``dry_only`` so no sender can be invoked and no database write happens."""
    from intelligence import incident_clustering as ic
    from tools.intelligence.alert_replay import _ts
    evs = sorted((e for e in events if e.get("collected_at")), key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    if not evs:
        out("[replay] no events")
        return []
    store = ad.InMemoryAlertStore()
    step = timedelta(minutes=bucket_minutes)
    t, end = _ts(evs[0]["collected_at"]), _ts(evs[-1]["collected_at"])
    alerts: list[dict] = []
    i = 0
    while t <= end + step:
        grew = False
        while i < len(evs) and _ts(evs[i]["collected_at"]) <= t:
            i += 1
            grew = True
        if grew:
            seen = [e for e in evs[:i] if _ts(e["collected_at"]) >= t - timedelta(hours=DEFAULT_LOOKBACK_H)]
            for p in ad.process(ic.cluster_incidents(seen, now=t, force=True), now=t, store=store, dry_only=True, force=True):
                if not p["deferred"]:
                    alerts.append({**p, "at": t.isoformat()})
        t += step
    out(f"[replay] {len(evs)} events, {len(alerts)} would-have-alerted (dry, nothing sent):")
    for p in alerts:
        out(f"  {p['at']}  {p['kind'].upper():11} {p['incident_key']}  {p['headline']}")
    return alerts
