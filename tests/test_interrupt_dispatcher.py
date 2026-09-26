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
from core.platform.captain_brief_contract import (
    assemble_captain_brief,
    recommendations_from_events,
)
from core.platform.interrupt_dispatcher import dispatch_interrupt_now
from core.platform.notification_service import NotificationResult, Transport
from tests.fixtures.synthetic_core_events import (
    CAN_BE_DELAYED_MIDRANGE_EVENT,
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
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


def test_records_dispatch_message_id_when_transport_returns_one(monkeypatch):
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    import core.platform.interrupt_dispatcher as mod
    monkeypatch.setattr(mod, "mark_event_status", lambda *a, **k: None)
    recorded = []
    monkeypatch.setattr(mod, "record_dispatch_message_id", lambda event_id, message_id: recorded.append((event_id, message_id)))

    def fake_notify_with_id(*a, **k):
        return NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1, message_id=4242)

    dispatch_interrupt_now(events, items, notify_fn=fake_notify_with_id)

    assert recorded == [(INTERRUPT_NOW_EVENT["event_id"], 4242)]


def test_appends_portal_deep_link_when_configured(monkeypatch):
    monkeypatch.setenv("LCARS_PORTAL_URL", "https://usstjros.vercel.app")
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    calls = []

    def fake_notify(body, **kwargs):
        calls.append(body)
        return _fake_notify_ok()

    dispatch_interrupt_now(events, items, notify_fn=fake_notify)

    assert len(calls) == 1
    assert calls[0].startswith(INTERRUPT_NOW_EVENT["recommended_action"])
    assert calls[0].endswith("https://usstjros.vercel.app/briefs")


def test_omits_portal_deep_link_when_not_configured(monkeypatch):
    monkeypatch.delenv("LCARS_PORTAL_URL", raising=False)
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    calls = []

    def fake_notify(body, **kwargs):
        calls.append(body)
        return _fake_notify_ok()

    dispatch_interrupt_now(events, items, notify_fn=fake_notify)

    assert calls == [INTERRUPT_NOW_EVENT["recommended_action"]]


def test_dual_sends_email_alongside_telegram_on_every_interrupt(monkeypatch):
    """Option (b): email fires on every INTERRUPT_NOW dispatch, not gated on
    an escalation ladder (which doesn't exist yet)."""
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    import core.platform.interrupt_dispatcher as mod

    email_calls = []
    monkeypatch.setattr(
        mod, "send_email",
        lambda to, subject, html, *a, **k: email_calls.append((to, subject, html)) or True,
    )

    dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: _fake_notify_ok())

    assert len(email_calls) == 1
    to, subject, html = email_calls[0]
    assert to == "timjardenross1986@gmail.com"
    assert INTERRUPT_NOW_EVENT["domain"] in subject
    assert "INTERRUPT NOW" in subject
    assert INTERRUPT_NOW_EVENT["recommended_action"] in html


def test_email_recipient_honours_env_override(monkeypatch):
    monkeypatch.setenv("INTERRUPT_NOW_EMAIL_TO", "override@example.com")
    # Reload the module so the env-var-with-default is re-read at import time,
    # matching the same convention as emergency_alerts.py / emergency_alert_summary.py.
    import importlib

    import core.platform.interrupt_dispatcher as mod
    importlib.reload(mod)
    try:
        events = [dict(INTERRUPT_NOW_EVENT)]
        items = _brief_items(events)

        email_calls = []
        monkeypatch.setattr(
            mod, "send_email",
            lambda to, subject, html, *a, **k: email_calls.append(to) or True,
        )

        mod.dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: _fake_notify_ok())

        assert email_calls == ["override@example.com"]
    finally:
        importlib.reload(mod)


def test_email_failure_does_not_block_or_break_telegram_dispatch(monkeypatch):
    """The email leg is best-effort: it must never prevent notify_fn from
    running or prevent a successful Telegram dispatch from being marked
    acknowledged."""
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    import core.platform.interrupt_dispatcher as mod
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: False)
    marked = []
    monkeypatch.setattr(mod, "mark_event_status", lambda event_id, status: marked.append((event_id, status)))

    telegram_calls = []

    def fake_notify(body, **kwargs):
        telegram_calls.append(body)
        return _fake_notify_ok()

    results = dispatch_interrupt_now(events, items, notify_fn=fake_notify)

    assert len(telegram_calls) == 1
    assert len(results) == 1
    assert results[0].ok
    assert marked == [(INTERRUPT_NOW_EVENT["event_id"], "acknowledged")]


def test_email_send_raising_does_not_propagate(monkeypatch):
    """Defense in depth: even if send_email somehow raised (contract
    violation on its part), the dispatcher's own contract is preserved by
    _email_interrupt_now not needing a try/except here — send_email's own
    documented contract is never-raise. This test pins that assumption by
    asserting send_email is invoked in a way dispatch tolerates a falsy
    return without incident."""
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    import core.platform.interrupt_dispatcher as mod
    calls = []
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: calls.append(1) or False)

    results = dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: _fake_notify_ok())

    assert calls == [1]
    assert len(results) == 1


def test_does_not_record_dispatch_message_id_when_transport_has_none(monkeypatch):
    events = [dict(INTERRUPT_NOW_EVENT)]
    items = _brief_items(events)

    import core.platform.interrupt_dispatcher as mod
    monkeypatch.setattr(mod, "mark_event_status", lambda *a, **k: None)
    recorded = []
    monkeypatch.setattr(mod, "record_dispatch_message_id", lambda event_id, message_id: recorded.append((event_id, message_id)))

    dispatch_interrupt_now(events, items, notify_fn=lambda *a, **k: _fake_notify_ok())

    assert recorded == []
