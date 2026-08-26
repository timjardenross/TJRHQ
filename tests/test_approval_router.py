"""MSN-0347 PoC: Approval Router tests.

Proves the full routing table for `core/platform/approval_router.py`:
- route_for_approval() maps AttentionDecision categories to the correct verbs
- send_approval_notification() calls notify() with the expected Telegram
  inline keyboard markup
- evaluate_and_route_mission_status_change() integrates evaluate_event()
  with routing and only calls notify() when the verb is 'notify'

Pure unit tests — no Supabase, no network, no live system dependency.
All notify() calls are replaced with a fake that records arguments.
"""

import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import AttentionCategory, AttentionDecision
from core.platform.approval_router import (
    evaluate_and_route_mission_status_change,
    route_for_approval,
    send_approval_notification,
)
from core.platform.notification_service import NotificationResult, Transport


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _decision(category: AttentionCategory) -> AttentionDecision:
    return AttentionDecision(
        event_id="evt-001",
        category=category,
        reason=f"test: {category.value}",
        importance=80 if category == AttentionCategory.INTERRUPT_NOW else 50,
        confidence=80 if category == AttentionCategory.INTERRUPT_NOW else 40,
        relevance=None,
        domain="mission-lifecycle",
        event_type="mission.status_changed",
    )


def _fake_notify_ok(*args, **kwargs) -> NotificationResult:
    return NotificationResult(ok=True, transport=Transport.TELEGRAM, attempts=1)


def _fake_notify_fail(*args, **kwargs) -> NotificationResult:
    return NotificationResult(ok=False, transport=Transport.TELEGRAM, attempts=1, error="mock-fail")


# ── route_for_approval ────────────────────────────────────────────────────────


def test_interrupt_now_routes_to_notify():
    decision = _decision(AttentionCategory.INTERRUPT_NOW)
    assert route_for_approval(decision) == "notify"


def test_can_be_delayed_routes_to_notify():
    decision = _decision(AttentionCategory.CAN_BE_DELAYED)
    assert route_for_approval(decision) == "notify"


def test_never_interrupt_routes_to_skip():
    decision = _decision(AttentionCategory.NEVER_INTERRUPT)
    assert route_for_approval(decision) == "skip"


def test_should_be_summarised_routes_to_auto():
    decision = _decision(AttentionCategory.SHOULD_BE_SUMMARISED)
    assert route_for_approval(decision) == "auto"


def test_should_be_aggregated_routes_to_auto():
    decision = _decision(AttentionCategory.SHOULD_BE_AGGREGATED)
    assert route_for_approval(decision) == "auto"


def test_should_simply_be_remembered_routes_to_auto():
    decision = _decision(AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED)
    assert route_for_approval(decision) == "auto"


# ── send_approval_notification ────────────────────────────────────────────────


def test_send_approval_notification_passes_inline_keyboard(monkeypatch):
    """notify() must receive reply_markup with the two ms| callback buttons."""
    captured: list[dict[str, Any]] = []

    def fake_notify(body, **kwargs):
        captured.append({"body": body, **kwargs})
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    decision = _decision(AttentionCategory.INTERRUPT_NOW)
    result = send_approval_notification(
        decision,
        mission_id="USS-TJR-0347",
        mission_name="EOS Blueprint",
        old_status="Designed",
        new_status="Approved",
    )

    assert result is True
    assert len(captured) == 1
    call = captured[0]

    # reply_markup must contain the two ms| buttons
    markup = call.get("reply_markup", {})
    keyboard = markup.get("inline_keyboard", [])
    assert keyboard, "inline_keyboard must be non-empty"
    row = keyboard[0]
    callback_datas = [btn["callback_data"] for btn in row]
    assert "ms|ack|USS-TJR-0347" in callback_datas
    assert "ms|dismiss|USS-TJR-0347" in callback_datas


def test_send_approval_notification_uses_alert_template_for_interrupt_now(monkeypatch):
    """INTERRUPT_NOW dispatches as ALERT severity."""
    from core.platform.notification_service import Severity
    captured: list[dict] = []

    def fake_notify(body, **kwargs):
        captured.append(kwargs)
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    decision = _decision(AttentionCategory.INTERRUPT_NOW)
    send_approval_notification(decision, "USS-TJR-0001", "Test Mission", "Idea", "Active")

    assert captured[0]["severity"] == Severity.ALERT
    assert captured[0]["template"] == "alert"


def test_send_approval_notification_uses_warning_severity_for_can_be_delayed(monkeypatch):
    from core.platform.notification_service import Severity
    captured: list[dict] = []

    def fake_notify(body, **kwargs):
        captured.append(kwargs)
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    decision = _decision(AttentionCategory.CAN_BE_DELAYED)
    send_approval_notification(decision, "USS-TJR-0002", "Delayed Mission", "Idea", "Planned")

    assert captured[0]["severity"] == Severity.WARNING


def test_send_approval_notification_returns_false_on_notify_failure(monkeypatch):
    monkeypatch.setattr("core.platform.approval_router.notify", _fake_notify_fail)
    decision = _decision(AttentionCategory.INTERRUPT_NOW)
    result = send_approval_notification(decision, "USS-TJR-X", "Fail Test", "Idea", "Active")
    assert result is False


# ── evaluate_and_route_mission_status_change ──────────────────────────────────


def test_high_importance_and_confidence_triggers_notify(monkeypatch):
    """importance=80, confidence=80 → INTERRUPT_NOW → 'notify' → notify() called."""
    notify_calls: list[dict] = []

    def fake_notify(body, **kwargs):
        notify_calls.append({"body": body, **kwargs})
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    verb = evaluate_and_route_mission_status_change(
        mission_id="USS-TJR-0347",
        mission_name="EOS Blueprint",
        old_status="Designed",
        new_status="Approved",
        importance=80,
        confidence=80,
    )

    assert verb == "notify"
    assert len(notify_calls) == 1, "notify() must be called exactly once"


def test_low_importance_skips_notification(monkeypatch):
    """importance=10 → NEVER_INTERRUPT → 'skip' → notify() not called."""
    notify_calls: list[dict] = []

    def fake_notify(body, **kwargs):
        notify_calls.append(kwargs)
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    verb = evaluate_and_route_mission_status_change(
        mission_id="USS-TJR-0001",
        mission_name="Trivial Mission",
        old_status="Idea",
        new_status="Closed",
        importance=10,
        confidence=90,
    )

    assert verb == "skip"
    assert len(notify_calls) == 0, "notify() must not be called for NEVER_INTERRUPT"


def test_absent_scores_route_to_auto_without_notification(monkeypatch):
    """No importance/confidence → SHOULD_SIMPLY_BE_REMEMBERED → 'auto' → no notify()."""
    notify_calls: list[dict] = []

    def fake_notify(body, **kwargs):
        notify_calls.append(kwargs)
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    verb = evaluate_and_route_mission_status_change(
        mission_id="USS-TJR-9999",
        mission_name="Unscored Mission",
        old_status="Idea",
        new_status="Planned",
        # importance and confidence intentionally absent
    )

    assert verb == "auto"
    assert len(notify_calls) == 0


def test_high_importance_low_confidence_routes_to_notify(monkeypatch):
    """importance=80, confidence=50 → CAN_BE_DELAYED → 'notify'."""
    notify_calls: list[dict] = []

    def fake_notify(body, **kwargs):
        notify_calls.append(kwargs)
        return _fake_notify_ok()

    monkeypatch.setattr("core.platform.approval_router.notify", fake_notify)

    verb = evaluate_and_route_mission_status_change(
        mission_id="USS-TJR-0010",
        mission_name="Uncertain Mission",
        old_status="Designed",
        new_status="Implemented",
        importance=80,
        confidence=50,
    )

    assert verb == "notify"
    assert len(notify_calls) == 1


def test_evaluate_and_route_is_non_blocking_on_notify_failure(monkeypatch):
    """A notify() failure must not raise — evaluate_and_route still returns the verb."""
    monkeypatch.setattr("core.platform.approval_router.notify", _fake_notify_fail)

    # Must not raise
    verb = evaluate_and_route_mission_status_change(
        mission_id="USS-TJR-FAIL",
        mission_name="Notify Failure Test",
        old_status="Idea",
        new_status="Active",
        importance=80,
        confidence=80,
    )
    assert verb == "notify"  # routing decision is still correct despite send failure
