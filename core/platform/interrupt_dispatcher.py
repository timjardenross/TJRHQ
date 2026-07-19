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
from typing import Any, Callable, Optional

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem
from core.platform.event_bus import mark_event_status
from core.platform.notification_service import (
    NotificationResult,
    Severity,
    Transport,
    notify,
)

log = logging.getLogger(__name__)


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
        row: Optional[dict[str, Any]] = events_by_id.get(item.event_id or "")
        status = (row or {}).get("status") or "new"
        if status != "new":
            continue

        body = item.recommendation.description if item.recommendation else item.reason
        title = f"{item.domain} · {item.event_type}"
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
        elif not result.ok:
            log.warning(
                "[interrupt-dispatcher] notify failed for event %s: %s",
                item.event_id, result.error,
            )

    return results


__all__ = ["dispatch_interrupt_now"]
