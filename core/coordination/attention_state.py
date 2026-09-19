"""Canonical Attention-State contract (Mission 1 Round 2, USS-TJR-MSN-1).

Round 2's runtime investigation found something narrower than Round 1
assumed: there is already exactly ONE live, authoritative call path for
mission/coordination data — core/coordination/number_one.py's NumberOne
engine, reached exclusively through context_service.py's
_http_number_one_brief() (GET /brief/number-one), which web
(lcars-portal/src/app/api/number-one-brief/route.ts), the alert-routing
watchdog (core/coordination/command_bus.py), and XO's Telegram /brief
command all already call identically. execution_engine.py's
NumberOneExecutionEngine and Command Centre's coordination.js are not
competing sources of truth — they're unreachable/orphaned (see
docs/architecture/attention-state-round2.md's retirement register).

The real gap this module closes: Captain's Chair / LifeOS Hub's "Needs You"
list (lcars-portal/src/lib/commandState.ts's buildNeedsYouItems()) has NO
field for anything Number One derives — missions, escalations, follow-ups
never reach it. This module is the smallest safe reconciliation: a pure,
lossless NORMALIZER from NumberOne's existing CoordinationBrief into a
small, presentation-agnostic AttentionItem shape, added to
_http_number_one_brief()'s response as an additive `attention_items` field
(no new endpoint, no new persistence, no second computation — every field
here is derived directly from data NumberOne already computed).

Any future consuming surface (Chair, Hub, a Telegram digest, an eventual
iPad surface) reads `attention_items` and gets the same underlying set in
the same category buckets — only how each surface *presents* it may differ,
per mission §3's Domain State / Attention State / Reasoning / Presentation
split. This module is the Attention State layer; NumberOne itself remains
the Reasoning layer (it still explains *why*, via `reason`/`recommendation`
text); Chair/Hub/Telegram/iPad are Presentation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from number_one import CoordinationBrief, EscalationLevel, Priority


class AttentionCategory(str, Enum):
    """Mission §3's attention-state vocabulary. Deliberately small and
    domain-agnostic — a future non-mission source (a decision, a stalled
    personal task) maps into the same categories rather than growing new
    ones per source."""
    NEEDS_NOW = "needs_now"
    IMPORTANT_NOT_IMMEDIATE = "important_not_immediate"
    CAN_WAIT = "can_wait"
    BLOCKED = "blocked"
    DECISION_REQUIRED = "decision_required"


# Lower number = more urgent. Deliberately matches lcars-portal's
# captainsChairSynthesis.ts KIND_PRIORITY table's EXISTING, already-tested
# ranking (safety=0, time_critical=1, blocker=2, ...) rather than inventing
# a new precedence here — NEEDS_NOW maps to 'time_critical' and
# DECISION_REQUIRED maps to 'blocker' in commandState.ts's merge (Mission 1
# Round 2), so this ranking must agree with that pre-existing order or the
# two languages would silently disagree on which of the two comes first.
_CATEGORY_PRIORITY: dict[AttentionCategory, int] = {
    AttentionCategory.NEEDS_NOW: 0,
    AttentionCategory.DECISION_REQUIRED: 1,
    AttentionCategory.BLOCKED: 2,
    AttentionCategory.IMPORTANT_NOT_IMMEDIATE: 3,
    AttentionCategory.CAN_WAIT: 4,
}

_ESCALATION_TO_CATEGORY = {
    EscalationLevel.CRITICAL: AttentionCategory.DECISION_REQUIRED,
    EscalationLevel.HIGH: AttentionCategory.DECISION_REQUIRED,
    EscalationLevel.MEDIUM: AttentionCategory.IMPORTANT_NOT_IMMEDIATE,
}

_PRIORITY_TO_CATEGORY = {
    Priority.P0: AttentionCategory.NEEDS_NOW,
    Priority.P1: AttentionCategory.IMPORTANT_NOT_IMMEDIATE,
    Priority.P2: AttentionCategory.CAN_WAIT,
    Priority.P3: AttentionCategory.CAN_WAIT,
}

_FOLLOW_UP_TYPE_TO_CATEGORY = {
    "LONG_BLOCKED": AttentionCategory.BLOCKED,
    "STALE_MISSION": AttentionCategory.IMPORTANT_NOT_IMMEDIATE,
}


@dataclass
class AttentionItem:
    """One item in the canonical attention set. `source`/`ref` let a
    presentation surface build its own href without this module knowing
    anything about routes; `reason` is NumberOne's own explanation text,
    never re-derived."""
    id: str
    category: AttentionCategory
    priority: int
    title: str
    reason: str
    source: str  # "number_one" today; a future decision/follow-through
    # source would use its own domain tag, not a new category.
    ref: str | None  # mission_id or equivalent, for the presentation layer's href
    generated_at: str  # ISO timestamp, from the brief this was derived from —
    # never re-stamped "now" here, so staleness is traceable to its origin.
    # Mission 2 (USS-TJR-MSN-2): set only when capacity_status actually
    # produced a note for this item (mirrors NumberOne.get_health_adjusted_
    # queue()'s existing capacity_note text verbatim -- not a new rule).
    # None means capacity either wasn't supplied or didn't affect this item
    # (Green/Unknown/no-checkin all leave every item's note empty, same as
    # that function's own per-item behaviour).
    capacity_adjusted_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


# Mission 2 (USS-TJR-MSN-2): mirrors NumberOne.get_health_adjusted_queue()'s
# existing per-item capacity_note rules verbatim (core/coordination/
# number_one.py) so this module doesn't invent a second capacity policy.
# That function only overlays get_work_queue()'s output (WorkQueueItem,
# which carries a real mission `priority`) -- it never touches escalations
# or follow_ups, so neither does this: those sections have no mission-
# priority field to gate on, and capacity is deliberately NOT applied to
# them here, matching the one place this behaviour already exists in
# production.
def _capacity_note_and_category(
    category: AttentionCategory, is_critical: bool, is_high_priority: bool, capacity_status: str | None,
) -> tuple[AttentionCategory, str | None]:
    """Mission 3: generalised so this one canonical policy function can be
    reused by any source with its own notion of priority tiers (Number
    One's Priority enum, or a personal task's urgency/importance), not
    just Number One's. `is_critical` was `mission_priority == Priority.P0`
    and `is_high_priority` was `mission_priority in (Priority.P0,
    Priority.P1)` before this mission — kept as two separate booleans
    (not one) because Red and Amber gate on two DIFFERENT tiers (Red:
    P0-only; Amber: P0-or-P1), so collapsing them into a single boolean
    would silently narrow Amber's existing bypass to P0-only. Behaviour
    for existing Number One callers is unchanged — they now pass both
    booleans explicitly instead of the enum comparisons happening inside
    this function."""
    if capacity_status == "Red":
        if is_critical:
            return category, "CRITICAL — proceed regardless of capacity"
        # Blocked items stay BLOCKED (already off the Needs You path) --
        # only non-blocked items get demoted, matching get_health_adjusted_
        # queue()'s uniform "P0 only today" note without inventing a
        # steeper reclassification it doesn't itself apply.
        demoted = AttentionCategory.CAN_WAIT if category != AttentionCategory.BLOCKED else category
        return demoted, "DEFERRED — Red capacity: P0 only today"
    if capacity_status == "Amber":
        if is_high_priority:
            return category, "Proceed — priority justifies reduced capacity"
        return category, "Advisory: consider deferring on reduced capacity days"
    # Green, "Unknown", or None (no check-in / not supplied): no per-item
    # adjustment -- exactly get_health_adjusted_queue()'s own behaviour,
    # where only the *advisory* wording differs between Green and Unknown,
    # never the per-item capacity_note. Absence must not imply Green; it
    # simply means nothing here is capacity-adjusted.
    return category, None


def attention_items_from_brief(
    brief: CoordinationBrief, capacity_status: str | None = None,
) -> list[AttentionItem]:
    """Pure, lossless transform of an already-computed CoordinationBrief —
    no new data access, no new derivation logic. Every item traces back to
    something NumberOne already put in the brief; this only reclassifies
    it into the shared category vocabulary and orders it.

    `capacity_status` (Mission 2, USS-TJR-MSN-2): optional, defaults to
    None for full backward compatibility with existing callers (e.g.
    context_service.py's _http_number_one_brief(), which doesn't pass it).
    When supplied ("Green"/"Amber"/"Red"/"Unknown"), applies
    NumberOne.get_health_adjusted_queue()'s existing per-item capacity
    rules to `top_priorities`/`blocked_missions` items only -- see
    _capacity_note_and_category()'s docstring for why escalations/
    follow_ups are deliberately untouched.

    "Lossless" means nothing is dropped, not deduplicated: a mission can
    legitimately appear more than once across sections (e.g. once via
    brief.blocked_missions and again via a LONG_BLOCKED follow-up for the
    same mission_id) since NumberOne's own sections aren't mutually
    exclusive. Today's only consumer (commandState.ts) filters to
    NEEDS_NOW/DECISION_REQUIRED and hasn't hit this in practice; a future
    consumer reading the full category range should dedupe by `ref` first."""
    generated_at = brief.timestamp.isoformat()
    items: list[AttentionItem] = []

    for esc in brief.escalations:
        category = _ESCALATION_TO_CATEGORY.get(esc.level, AttentionCategory.IMPORTANT_NOT_IMMEDIATE)
        items.append(AttentionItem(
            id=f"number_one:escalation:{esc.mission_id}:{esc.escalation_type}",
            category=category,
            priority=_CATEGORY_PRIORITY[category],
            title=f"{esc.escalation_type}: {esc.mission_id}",
            reason=esc.reason,
            source="number_one",
            ref=esc.mission_id,
            generated_at=generated_at,
        ))

    for item in brief.blocked_missions:
        category, capacity_reason = _capacity_note_and_category(
            AttentionCategory.BLOCKED,
            item.priority == Priority.P0,
            item.priority in (Priority.P0, Priority.P1),
            capacity_status,
        )
        items.append(AttentionItem(
            id=f"number_one:blocked:{item.mission_id}",
            category=category,
            priority=_CATEGORY_PRIORITY[category],
            title=item.title,
            reason=item.rationale or (item.blockers[0] if item.blockers else "Blocked"),
            source="number_one",
            ref=item.mission_id,
            generated_at=generated_at,
            capacity_adjusted_reason=capacity_reason,
        ))

    for item in brief.top_priorities:
        base_category = _PRIORITY_TO_CATEGORY.get(item.priority, AttentionCategory.CAN_WAIT)
        category, capacity_reason = _capacity_note_and_category(
            base_category,
            item.priority == Priority.P0,
            item.priority in (Priority.P0, Priority.P1),
            capacity_status,
        )
        items.append(AttentionItem(
            id=f"number_one:priority:{item.mission_id}",
            category=category,
            priority=_CATEGORY_PRIORITY[category],
            title=item.title,
            reason=item.rationale or item.next_action or f"{item.priority.value} priority",
            source="number_one",
            ref=item.mission_id,
            generated_at=generated_at,
            capacity_adjusted_reason=capacity_reason,
        ))

    for fu in brief.follow_ups:
        category = _FOLLOW_UP_TYPE_TO_CATEGORY.get(fu.get("type"), AttentionCategory.CAN_WAIT)
        items.append(AttentionItem(
            id=f"number_one:followup:{fu.get('mission_id')}:{fu.get('type')}",
            category=category,
            priority=_CATEGORY_PRIORITY[category],
            title=fu.get("recommendation") or fu.get("reason") or "Follow-up needed",
            reason=fu.get("reason") or "",
            source="number_one",
            ref=fu.get("mission_id"),
            generated_at=generated_at,
        ))

    items.sort(key=lambda i: i.priority)
    return items


__all__ = ["AttentionCategory", "AttentionItem", "attention_items_from_brief"]
