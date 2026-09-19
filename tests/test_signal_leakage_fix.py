"""Briefs/Captain's Brief consolidation — signal-leakage regression tests.

Locks in the fix for the exact leak the consolidation mission called out:
a raw signal (a scraped headline, a source-health error message, a bare
systemd state transition) must never be written to `core_events.
recommended_action` — that field is reserved for a genuine reasoned action
proposal (core/platform/captain_brief_contract.py's own contract). Raw,
readable content belongs in `core_events.description` (migration 0218)
instead, and downstream consumers (Captain Brief items, the interrupt
dispatcher) must fall back to `description`, never fabricate a
`Recommendation` out of it, and never fall back to the Attention Engine's
bare scoring-formula `reason` while real content exists.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import evaluate_batch
from core.platform.captain_brief_contract import (
    assemble_captain_brief,
    recommendations_from_events,
)
from core.platform.interrupt_dispatcher import dispatch_interrupt_now
from core.platform.notification_service import NotificationResult, Transport


def _fake_notify_ok(*args, **kwargs) -> NotificationResult:
    return NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1)


# ─── Emitters: verify raw signal text lands in `description`, never `recommended_action` ───


def test_source_health_failure_uses_description_not_recommended_action(monkeypatch):
    import intelligence.persistence.intelligence_store as store
    from intelligence.models import SourceHealth

    monkeypatch.setattr(store, "_post", lambda *a, **k: {})
    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    health = SourceHealth(
        source_id="src-1",
        source_name="Example Source",
        checked_at=datetime.now(timezone.utc),
        status="failed",
        error_message="HTTP 401: authentication failed",
    )
    store.save_source_health(health)

    assert len(calls) == 1
    assert calls[0].get("description") == "HTTP 401: authentication failed"
    assert calls[0].get("recommended_action") is None


def test_service_state_transition_uses_description_not_recommended_action(monkeypatch):
    import core.coordination.command_bus as command_bus

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    command_bus._emit_service_state_event("platform.service_down", "nginx", "failed", "high")

    assert len(calls) == 1
    assert calls[0].get("description") == "nginx: failed"
    assert calls[0].get("recommended_action") is None


# ─── Pipeline: a description-only event never becomes a fabricated Recommendation ───


def _observation_event(**overrides) -> dict:
    event = {
        "event_id": "evt-obs-1",
        "event_type": "intelligence.source.failed",
        "domain": "operational-resilience-intelligence",
        "source": "intelligence_store",
        "importance": 90,
        "confidence": 85,
        "relevance": 80,
        "description": "HTTP 401: authentication failed",
        "status": "new",
    }
    event.update(overrides)
    return event


def test_description_only_event_produces_no_recommendation():
    event = _observation_event()
    decisions = evaluate_batch([event])
    recs = recommendations_from_events([event])
    brief = assemble_captain_brief(decisions, recommendations=recs)

    assert len(brief.interrupt_now) == 1
    item = brief.interrupt_now[0]
    # The raw signal must still be visible (it's a real attention item) —
    # but never repackaged as a Recommendation the Captain didn't get.
    assert item.recommendation is None
    assert item.description == "HTTP 401: authentication failed"


def test_dispatcher_falls_back_to_description_not_scoring_formula(monkeypatch):
    event = _observation_event()
    decisions = evaluate_batch([event])
    recs = recommendations_from_events([event])
    brief = assemble_captain_brief(decisions, recommendations=recs)

    calls = []

    def fake_notify(body, **kwargs):
        calls.append(body)
        return _fake_notify_ok()

    dispatch_interrupt_now([event], brief.interrupt_now, notify_fn=fake_notify)

    assert len(calls) == 1
    # Readable description, not the bare "importance=X >= Y AND confidence=..." trace.
    assert calls[0].startswith("HTTP 401: authentication failed")
    assert "importance=" not in calls[0]


def test_dispatcher_uses_scoring_formula_only_when_no_description_or_recommendation(monkeypatch):
    event = _observation_event(description=None)
    decisions = evaluate_batch([event])
    brief = assemble_captain_brief(decisions, recommendations={})

    calls = []
    dispatch_interrupt_now(
        [event], brief.interrupt_now,
        notify_fn=lambda body, **kwargs: calls.append(body) or _fake_notify_ok(),
    )

    assert len(calls) == 1
    assert "importance=" in calls[0]
