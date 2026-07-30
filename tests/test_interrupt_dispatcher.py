"""USS-TJR-MSN-0339 WP2: Interrupt-Now Dispatcher tests.

Proves `dispatch_interrupt_now()` — the code that turns a computed
INTERRUPT_NOW classification into a real `notify()` call — actually calls
notify() exactly once per not-yet-acknowledged interrupt, skips anything
already acknowledged (the no-duplicate-notification guardrail WP3's own
gate later requires), and never touches non-interrupt categories.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import evaluate_batch
from core.platform.captain_brief_contract import assemble_captain_brief, recommendations_from_events
from core.platform.interrupt_dispatcher import dispatch_interrupt_now
from core.platform.notification_service import NotificationResult, Transport
from tests.fixtures.synthetic_core_events import (
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
    CAN_BE_DELAYED_MIDRANGE_EVENT,
)


def _fake_notify_ok(*args, **kwargs) -> NotificationResult:
    return NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1)


def _brief_items(events):
    decisions = evaluate_batch(events)
    recs = recommendations_from_events(events)
    brief = assemble_captain_brief(decisions, recommendations=recs)
    return brief.interrupt_now


def test_dispatches_new_interrupt_now_event():
    events = [INTERRUPT_NOW_EVENT]
    items = _brief_items(events)
    assert len(items) == 1

    calls = []

    def fake_notify(body, **kwargs):
        calls.append((body, kwargs))
        return _fake_notify_ok()

    results = dispatch_interrupt_now(events, items, notify_fn=fake_notify)

    assert len(results) == 1
    assert results[0].ok
    assert len(calls) == 1
    body, kwargs = calls[0]
    # Body must be the real recommended_action text, not the scoring formula.
    assert body == INTERRUPT_NOW_EVENT["recommended_action"]
    assert kwargs["title"] == f"{INTERRUPT_NOW_EVENT['domain']} · {INTERRUPT_NOW_EVENT['event_type']}"


def test_skips_already_acknowledged_event():
    ev = dict(INTERRUPT_NOW_EVENT, status="acknowledged")
    events = [ev]
    items = _brief_items(events)

    calls = []
    results = dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: calls.append(1) or _fake_notify_ok())

    assert results == []
    assert calls == []


def test_ignores_non_interrupt_categories():
    events = [NEVER_INTERRUPT_EVENT, CAN_BE_DELAYED_MIDRANGE_EVENT]
    decisions = evaluate_batch(events)
    recs = recommendations_from_events(events)
    brief = assemble_captain_brief(decisions, recommendations=recs)
    # Sanity: fixture choice actually produced no interrupt_now items.
    assert brief.interrupt_now == []

    calls = []
    results = dispatch_interrupt_now(
        events, brief.can_be_delayed + brief.interrupt_now,
        notify_fn=lambda *a, **k: calls.append(1) or _fake_notify_ok(),
    )
    assert results == []
    assert calls == []


def test_marks_event_acknowledged_after_successful_dispatch(monkeypatch):
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    marked = []
    import core.platform.interrupt_dispatcher as mod
    monkeypatch.setattr(mod, "mark_event_status", lambda event_id, status: marked.append((event_id, status)))

    dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: _fake_notify_ok())

    assert marked == [(INTERRUPT_NOW_EVENT["event_id"], "acknowledged")]


def test_does_not_mark_acknowledged_on_failed_dispatch(monkeypatch):
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    marked = []
    import core.platform.interrupt_dispatcher as mod
    monkeypatch.setattr(mod, "mark_event_status", lambda event_id, status: marked.append((event_id, status)))

    def fake_fail(*a, **k):
        return NotificationResult(ok=False, transport=Transport.TELEGRAM, attempts=1, error="boom")

    dispatch_interrupt_now(events, items, notify_fn=fake_fail)

    assert marked == []
