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

import intelligence.scheduler as scheduler  # noqa: E402
import core.platform.event_bus as event_bus  # noqa: E402
import core.platform.interrupt_dispatcher as interrupt_dispatcher  # noqa: E402
from core.platform.notification_service import NotificationResult, Transport  # noqa: E402
from tests.fixtures.synthetic_core_events import INTERRUPT_NOW_EVENT, NEVER_INTERRUPT_EVENT  # noqa: E402


def test_evaluates_and_dispatches_real_interrupt_now_event(monkeypatch):
    monkeypatch.setattr(event_bus, "poll_events", lambda limit=200: [dict(INTERRUPT_NOW_EVENT)])

    dispatched = []

    def fake_dispatch(events, items, **kwargs):
        dispatched.extend(items)
        return [NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1)]

    monkeypatch.setattr(interrupt_dispatcher, "dispatch_interrupt_now", fake_dispatch)

    scheduler._attention_evaluation_job()

    assert len(dispatched) == 1
    assert dispatched[0].event_id == INTERRUPT_NOW_EVENT["event_id"]


def test_no_dispatch_call_when_nothing_qualifies(monkeypatch):
    monkeypatch.setattr(event_bus, "poll_events", lambda limit=200: [dict(NEVER_INTERRUPT_EVENT)])

    calls = []
    monkeypatch.setattr(
        interrupt_dispatcher, "dispatch_interrupt_now",
        lambda *a, **k: calls.append(1) or [],
    )

    scheduler._attention_evaluation_job()

    assert calls == []


def test_job_never_raises_on_poll_failure(monkeypatch):
    def boom(limit=200):
        raise RuntimeError("Supabase unavailable")

    monkeypatch.setattr(event_bus, "poll_events", boom)
    scheduler._attention_evaluation_job()  # must not raise — same non-blocking contract as every other job in this file
