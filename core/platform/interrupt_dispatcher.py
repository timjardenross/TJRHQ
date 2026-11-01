"""Interrupt-Now Dispatcher (USS-TJR-MSN-0339 WP2).

Bridges Attention Engine INTERRUPT_NOW decisions to a real, observable
push — the missing piece MSN-0338 Gap #3 found (`notification_service.notify()`
had zero callers anywhere in the repository). Pure glue: takes
already-computed `CaptainBriefItem`s (from
`captain_brief_orchestrator.assemble_captain_brief_document()`) plus the
raw polled `core_events` rows they were derived from, and for every item
whose backing row is still `status == "new"`, sends one push via
`notification_service.notify()` and advances that row's status to
"acknowledged" (the existing Event Bus status vocabulary —
`event_bus.py::_VALID_STATUSES`) so a repeat `/brief` run — or WP3's future
continuous evaluation — does not re-notify the same event. This satisfies
WP3's own duplicate-notification guardrail one WP early rather than
deferring it.

Manual-trigger only at this stage (called from `commands/brief.py::build_brief()`)
— autonomous/continuous triggering is WP3's explicit scope, not this
module's (USS-TJR-MSN-0339 governing rule 4: this WP restores plumbing,
it doesn't decide when evaluation runs).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from core.notifications.resend_email import send_email
from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem
from core.platform.event_bus import mark_event_status, record_dispatch_message_id
from core.platform.notification_service import (
    NotificationResult,
    Severity,
    Transport,
    notify,
)

log = logging.getLogger(__name__)

# Dual-send target (2026-09-26): the real escalation ladder (a genuine
# "Telegram failed/unacked -> escalate to email" path) doesn't exist yet, so
# this is an unconditional second channel fired alongside Telegram on every
# INTERRUPT_NOW item, not gated on Telegram's own result — same
# env-var-with-real-default recipient convention as
# intelligence/emergency_alerts.py's EMERGENCY_ALERT_EMAIL_TO /
# intelligence/emergency_alert_summary.py's EMERGENCY_ALERT_EMAIL_TO
# (same default address both of those use).
_INTERRUPT_NOW_EMAIL_TO = os.environ.get("INTERRUPT_NOW_EMAIL_TO", "timjardenross1986@gmail.com")


def _email_interrupt_now(title: str, body: str) -> None:
    """Best-effort email copy of the INTERRUPT_NOW push. Never raises and
    never affects dispatch_interrupt_now()'s return value, the Telegram
    result, or the event's ack/dispatch bookkeeping — same fail-open,
    non-blocking contract as captains_brief.py's _email_morning_brief() /
    resend_email.send_email's own never-raise contract."""
    html = body.replace("\n", "<br>\n")
    ok = send_email(_INTERRUPT_NOW_EMAIL_TO, f"INTERRUPT NOW — {title}", html)
    if not ok:
        log.warning(
            "[interrupt-dispatcher] email to %s failed for %s (non-blocking, Telegram unaffected)",
            _INTERRUPT_NOW_EMAIL_TO, title,
        )


def _deep_link(event_id: str) -> str | None:
    """Briefs deep-link for a dispatched event, appended to the Telegram
    push so a bare "importance=X >= Y" scoring trace is never the only
    thing the Captain has to act on — same LCARS_PORTAL_URL pattern as
    intelligence/workflow/service.py::_deep_link. None (omitted, not a
    broken link) when LCARS_PORTAL_URL isn't configured.

    Phase 5 (Captain's Brief retirement): /captains-brief-workbench no
    longer exists as a standalone page (redirects to /briefs), so this no
    longer anchors to a specific #brief-item-{event_id} row — /briefs has
    no equivalent per-event anchor yet. Losing that precision is a known,
    accepted simplification of this retirement, not an oversight; `event_id`
    stays a parameter so that anchor can come back if Briefs ever gains one.
    """
    base = (os.environ.get("LCARS_PORTAL_URL", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/briefs"


def dispatch_interrupt_now(
    events: list[dict[str, Any]],
    items: list[CaptainBriefItem],
    *,
    notify_fn: Callable[..., NotificationResult] = notify,
) -> list[NotificationResult]:
    """Send one push per not-yet-acknowledged INTERRUPT_NOW item.

    `events` is the raw `core_events`-shaped rows `items` were derived
    from (needed for their `status` column — `CaptainBriefItem` itself
    doesn't carry it). An item whose event_id isn't found in `events`, or
    whose row has no `status`, is treated as `status="new"` (never
    dispatched) — matching `core_events.status`'s own DB default, so a
    synthetic/test event with no explicit status still dispatches.
    """
    events_by_id = {e.get("event_id"): e for e in events if e.get("event_id")}
    results: list[NotificationResult] = []

    for item in items:
        if item.category != AttentionCategory.INTERRUPT_NOW:
            continue
        row: dict[str, Any] | None = events_by_id.get(item.event_id or "")
        status = (row or {}).get("status") or "new"
        if status != "new":
            continue

        # Briefs/Captain's Brief consolidation signal-leakage fix: prefer a
        # genuine recommendation, then the event's own readable description
        # (a headline, a state transition) — `item._routing_reason` (a bare
        # scoring formula, "importance=X >= Y AND confidence=Z >= W") is the
        # last resort, not the first fallback, so a push body is never just
        # an unreadable threshold trace when real content exists.
        body = (
            item.recommendation.description
            if item.recommendation
            else (item.description or item._routing_reason)
        )
        link = _deep_link(item.event_id) if item.event_id else None
        if link:
            body = f"{body}\n\n{link}"
        title = f"{item.domain} · {item.event_type}"
        # Dual-send, not escalation-gated: email fires unconditionally
        # alongside Telegram for every INTERRUPT_NOW item below, independent
        # of notify_fn's own outcome (see _email_interrupt_now docstring).
        _email_interrupt_now(title, body)
        result = notify_fn(
            body,
            title=title,
            severity=Severity.ALERT,
            template="alert",
            transport=Transport.TELEGRAM,
        )
        results.append(result)
        if result.ok and item.event_id:
            mark_event_status(item.event_id, "acknowledged")
            if result.message_id is not None:
                record_dispatch_message_id(item.event_id, result.message_id)
        elif not result.ok:
            log.warning(
                "[interrupt-dispatcher] notify failed for event %s: %s",
                item.event_id, result.error,
            )

    return results


__all__ = ["dispatch_interrupt_now"]
