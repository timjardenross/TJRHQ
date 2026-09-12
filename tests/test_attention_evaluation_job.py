"""USS-TJR-MSN-0339 WP3: `intelligence.scheduler._attention_evaluation_job()`
tests — the autonomous trigger MSN-0338 Gap #5 found didn't exist
(Attention Engine evaluation only ever ran from a manual `/brief` click).

Patches at the source modules (`core.platform.event_bus.poll_events`,
`core.platform.interrupt_dispatcher.dispatch_interrupt_now`) rather than on
`intelligence.scheduler`'s own namespace, since the job imports them inside
its own function body on every call (matching this file's existing job
functions' own import style) — a namespace-level patch on the scheduler
module would silently miss the real call site.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform import (
    event_bus,
    interrupt_dispatcher,
)
from core.platform.notification_service import NotificationResult, Transport
from intelligence import scheduler
from tests.fixtures.synthetic_core_events import (
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
)


def test_evaluates_and_dispatches_real_interrupt_now_event(monkeypatch):
    monkeypatch.setattr(event_bus, "poll_events", lambda limit=200, **kwargs: [dict(INTERRUPT_NOW_EVENT)])

    dispatched = []

    def fake_dispatch(events, items, **kwargs):
        dispatched.extend(items)
        return [NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1)]

    monkeypatch.setattr(interrupt_dispatcher, "dispatch_interrupt_now", fake_dispatch)

    scheduler._attention_evaluation_job()

    assert len(dispatched) == 1
    assert dispatched[0].event_id == INTERRUPT_NOW_EVENT["event_id"]


def test_no_dispatch_call_when_nothing_qualifies(monkeypatch):
    monkeypatch.setattr(event_bus, "poll_events", lambda limit=200, **kwargs: [dict(NEVER_INTERRUPT_EVENT)])

    calls = []
    monkeypatch.setattr(
        interrupt_dispatcher, "dispatch_interrupt_now",
        lambda *a, **k: calls.append(1) or [],
    )

    scheduler._attention_evaluation_job()

    assert calls == []


def test_job_never_raises_on_poll_failure(monkeypatch):
    def boom(limit=200, **kwargs):
        raise RuntimeError("Supabase unavailable")

    monkeypatch.setattr(event_bus, "poll_events", boom)
    scheduler._attention_evaluation_job()  # must not raise — same non-blocking contract as every other job in this file


def test_polls_recommended_action_so_dispatched_pushes_have_real_content(monkeypatch):
    """Regression test: this job's explicit `columns` list previously omitted
    `recommended_action`, so captain_brief_contract.recommendation_from_event()
    always saw it as absent and every INTERRUPT_NOW push fell back to
    interrupt_dispatcher's `item.reason` — the Attention Engine's bare
    threshold formula ("importance=90 >= 75 AND confidence=80 >= 70") — with
    no actual signal content, even though intelligence_store.py writes a
    real title into `recommended_action` for exactly this purpose."""
    seen_columns = {}

    def fake_poll(limit=200, columns="*", **kwargs):
        seen_columns["value"] = columns
        return [dict(INTERRUPT_NOW_EVENT)]

    monkeypatch.setattr(event_bus, "poll_events", fake_poll)
    monkeypatch.setattr(interrupt_dispatcher, "dispatch_interrupt_now", lambda *a, **k: [])

    scheduler._attention_evaluation_job()

    assert "recommended_action" in seen_columns["value"].split(",")
