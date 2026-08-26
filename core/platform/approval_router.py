"""Approval Router — mission.status_changed tiered-approval PoC (MSN-0347).

Routes a single event type (mission.status_changed) through the Attention
Engine's severity tiers to a Telegram inline keyboard, closing the loop that
MSN-0306 designed but never wired: evaluate_event() output now drives an
actual push to the Captain.

PoC scope: one event type only. Do not generalise to other event types here
until the end-to-end loop is validated in production (governed by the Captain
Intelligence Platform Wave boundary: MSN-0304 §14).

Loop summary:
    mission.status_changed → evaluate_event() → route_for_approval()
        → send_approval_notification() → XO bot callback → mark_event_status()

The XO bot callback handler (telegram-bots/xo/app.py::handle_mission_approval_callback)
is the other half of this loop; it processes the ms|ack|{mission_id} and
ms|dismiss|{mission_id} button presses.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.platform.attention_engine import (
    AttentionCategory,
    AttentionDecision,
    evaluate_event,
)
from core.platform.notification_service import (
    Severity,
    Transport,
    notify,
)

log = logging.getLogger(__name__)

# The two AttentionCategories that warrant a Captain push for mission events.
# INTERRUPT_NOW: high-importance, high-confidence — push immediately.
# CAN_BE_DELAYED: high-importance but lower-confidence — still notify, but
# the label conveys "review when ready" rather than "act now".
_NOTIFY_CATEGORIES = frozenset({
    AttentionCategory.INTERRUPT_NOW,
    AttentionCategory.CAN_BE_DELAYED,
})


def route_for_approval(decision: AttentionDecision) -> str:
    """Map an AttentionDecision to an approval routing verb.

    Returns:
        'notify'  — send the inline-keyboard approval push to the Captain.
        'skip'    — NEVER_INTERRUPT: silently discard, no push sent.
        'auto'    — low-salience categories (summarised/aggregated/remembered):
                    no immediate push; leave for the next Captain Brief cycle.
    """
    if decision.category in _NOTIFY_CATEGORIES:
        return "notify"
    if decision.category == AttentionCategory.NEVER_INTERRUPT:
        return "skip"
    return "auto"


def send_approval_notification(
    decision: AttentionDecision,
    mission_id: str,
    mission_name: str,
    old_status: str,
    new_status: str,
    event_id: Optional[str] = None,
) -> bool:
    """Send a Telegram message with Acknowledge/Dismiss inline buttons for a
    mission status change.

    The body is rendered via the 'alert' template (HTML mode, severity ALERT
    for INTERRUPT_NOW, WARNING for CAN_BE_DELAYED) so urgency tier is visible
    in the push without extra prose.

    Callback data format: ``ms|{action}|{mission_id}|{event_id}``
    where action is 'ack' or 'dismiss'. event_id is omitted if None.
    The XO bot's handle_mission_approval_callback processes these.

    Args:
        decision:     The AttentionDecision from evaluate_event().
        mission_id:   The mission's ID string (e.g. 'USS-TJR-0347').
        mission_name: Human-readable name, shown in the notification body.
        old_status:   Status before the change.
        new_status:   Status after the change.
        event_id:     core_events row id — embedded in callback_data so the
                      XO bot can call mark_event_status() without bot_data.

    Returns:
        True if the notification was delivered, False otherwise (non-blocking
        — callers must not propagate failures into the mission lifecycle).
    """
    urgency_label = "INTERRUPT" if decision.category == AttentionCategory.INTERRUPT_NOW else "REVIEW"
    title = f"Mission Status Changed [{urgency_label}]"
    body = (
        f"{mission_name} ({mission_id})\n"
        f"{old_status} → {new_status}\n"
        f"Attention: {decision.reason}"
    )
    severity = (
        Severity.ALERT if decision.category == AttentionCategory.INTERRUPT_NOW
        else Severity.WARNING
    )
    # Embed event_id in callback_data so XO bot can call mark_event_status()
    # without relying on cross-process bot_data. Max 64 bytes per Telegram limit;
    # longest case "ms|dismiss|USS-TJR-XXXX|<uuid36>" = ~57 bytes.
    _eid_suffix = f"|{event_id}" if event_id else ""
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Acknowledge", "callback_data": f"ms|ack|{mission_id}{_eid_suffix}"},
            {"text": "🔕 Dismiss",    "callback_data": f"ms|dismiss|{mission_id}{_eid_suffix}"},
        ]]
    }

    result = notify(
        body,
        title=title,
        severity=severity,
        template="alert",
        transport=Transport.TELEGRAM,
        reply_markup=reply_markup,
    )
    if not result.ok:
        log.warning(
            "[approval-router] notification failed for mission %s: %s",
            mission_id, result.error,
        )
    return result.ok


def evaluate_and_route_mission_status_change(
    mission_id: str,
    mission_name: str,
    old_status: str,
    new_status: str,
    event_id: Optional[str] = None,
    importance: Optional[int] = None,
    confidence: Optional[int] = None,
) -> str:
    """Convenience entry point called from mission_lifecycle.py after a
    mission.status_changed event is emitted.

    Builds a minimal core_events-shaped dict from the available mission
    fields, calls evaluate_event(), routes via route_for_approval(), and
    sends the notification when warranted.

    Missing scores (importance/confidence) are passed as None — evaluate_event()
    treats absent scores conservatively (SHOULD_SIMPLY_BE_REMEMBERED), which
    is the correct default for mission events that the emitter did not score.

    Args:
        mission_id:   The mission's ID (e.g. 'USS-TJR-0347').
        mission_name: Human-readable name for the notification body.
        old_status:   Status before the transition.
        new_status:   Status after the transition.
        event_id:     The core_events row ID returned by publish_event(),
                      or None if the publish failed/Supabase is disabled.
        importance:   0-100 importance score, or None if unscored.
        confidence:   0-100 confidence score, or None if unscored.

    Returns:
        The routing verb: 'notify', 'skip', or 'auto'.
    """
    event_dict = {
        "event_type": "mission.status_changed",
        "domain": "mission-lifecycle",
        "event_id": event_id,
        "importance": importance,
        "confidence": confidence,
    }
    decision = evaluate_event(event_dict)
    verb = route_for_approval(decision)

    log.debug(
        "[approval-router] mission=%s %s→%s category=%s verb=%s",
        mission_id, old_status, new_status, decision.category.value, verb,
    )

    if verb == "notify":
        send_approval_notification(decision, mission_id, mission_name, old_status, new_status, event_id=event_id)

    return verb


__all__ = [
    "route_for_approval",
    "send_approval_notification",
    "evaluate_and_route_mission_status_change",
]
