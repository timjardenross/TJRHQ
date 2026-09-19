"""Personal Task Attention Adapter (Mission 3, Capture/Remember/Follow-Through).

Mission 2 explicitly deferred this: "Mission 3 owns it." Discovery
confirmed the gap was real — no code path anywhere turned a personal_tasks
row into anything Attention State, Number One, Captain's Chair, or LifeOS
Hub could see (core/coordination/test_attention_state.py:43's own comment
named personal_tasks as a future source; attention_items_from_brief()
hard-codes source="number_one" on every item it emits).

This module is the smallest safe reconciliation, mirroring attention_state.
py's own pattern exactly: a pure, deterministic NORMALIZER from a list of
personal_tasks rows (already fetched by the caller — this module does no
Supabase I/O itself, same separation attention_state.py keeps from
number_one.py) into the same AttentionItem shape, using the same
AttentionCategory vocabulary and the same canonical capacity policy
(_capacity_note_and_category, reused verbatim — see Mission 3's
generalisation of that function, not a second capacity implementation).

Deliberately deterministic, not scored (mission §14: "avoid opaque
scoring where deterministic rules are sufficient"):
  - completed / abandoned tasks -> never emitted (nothing to attend to)
  - follow_through_paused=True  -> never emitted (Captain's own override
    always wins — mission §23)
  - work_state == 'blocked'     -> BLOCKED
  - overdue (due_date < today) or (urgency=5 and importance>=4)
                                -> NEEDS_NOW
  - due today/tomorrow, or importance>=4, or 3+ consecutive deferrals
    (Follow-Through's own stalled-item signal, migration 0165's
    deferral_count — mission §10's "Follow-Through detecting stalled
    action" resurfacing trigger)
                                -> IMPORTANT_NOT_IMMEDIATE
  - everything else             -> CAN_WAIT

This module does NOT decide when/whether to send a Telegram nudge — that
remains intelligence/adhd/follow_through_engine.py's job (lifecycle/nudge-
specific behaviour, mission's explicit "Follow-Through may continue to own
lifecycle/nudge-specific behaviour"). This module only decides whether a
task is currently attention-worthy for passive display in Chair/Hub/
Number One's attention_items — a separate, smaller question with a
separate, smaller (and much cheaper — no Telegram send, no daily cap) set
of rules. The two are expected to overlap on genuinely urgent items
without being the same code path, exactly as Follow-Through keeps its own
mode-based nudge scheduling untouched by this mission.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import (
    _CATEGORY_PRIORITY,
    AttentionCategory,
    AttentionItem,
    _capacity_note_and_category,
)

_TERMINAL_WORK_STATES = {"completed", "abandoned"}
_STALLED_DEFERRAL_COUNT = 3


def _parse_due_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None


def _base_category(task: dict, today: date) -> AttentionCategory:
    if task.get("work_state") == "blocked":
        return AttentionCategory.BLOCKED

    urgency = task.get("urgency") or 1
    importance = task.get("importance") or 1
    due = _parse_due_date(task.get("due_date"))
    overdue = due is not None and due < today
    due_soon = due is not None and (due - today).days <= 1
    stalled = (task.get("deferral_count") or 0) >= _STALLED_DEFERRAL_COUNT

    if overdue or (urgency >= 5 and importance >= 4):
        return AttentionCategory.NEEDS_NOW
    if due_soon or importance >= 4 or stalled:
        return AttentionCategory.IMPORTANT_NOT_IMMEDIATE
    return AttentionCategory.CAN_WAIT


def attention_items_from_personal_tasks(
    tasks: list[dict], capacity_status: str | None = None, generated_at: str | None = None,
) -> list[AttentionItem]:
    """Pure transform — `tasks` is whatever the caller already fetched
    (no fixed shape requirement beyond the fields this function reads:
    id, title, work_state, urgency, importance, due_date, deferral_count,
    follow_through_paused). Unknown/missing fields default to their least
    urgent interpretation (urgency/importance default 1, no due_date),
    matching this codebase's existing "absence is not urgency" posture.

    `generated_at` defaults to now (unlike attention_state.attention_
    items_from_brief, which stamps every item with the brief's own
    timestamp) because there is no equivalent "already-computed brief"
    timestamp here — the caller fetched these rows itself, right now.
    """
    today = datetime.now(timezone.utc).date()
    stamp = generated_at or datetime.now(timezone.utc).isoformat()
    items: list[AttentionItem] = []

    for task in tasks:
        if task.get("work_state") in _TERMINAL_WORK_STATES:
            continue
        if task.get("follow_through_paused"):
            continue

        base_category = _base_category(task, today)
        category, capacity_reason = _capacity_note_and_category(
            base_category,
            base_category == AttentionCategory.NEEDS_NOW,
            base_category in (AttentionCategory.NEEDS_NOW, AttentionCategory.IMPORTANT_NOT_IMMEDIATE),
            capacity_status,
        )

        due = _parse_due_date(task.get("due_date"))
        if task.get("work_state") == "blocked":
            reason = f"Blocked: {task.get('blocker_category') or 'reason not recorded'}"
        elif due is not None and due < today:
            reason = f"Overdue since {due.isoformat()}"
        elif due is not None:
            reason = f"Due {due.isoformat()}"
        elif (task.get("deferral_count") or 0) >= _STALLED_DEFERRAL_COUNT:
            reason = f"Deferred {task['deferral_count']} times — stalled"
        else:
            reason = "Open personal task"

        items.append(AttentionItem(
            id=f"personal_task:{task['id']}",
            category=category,
            priority=_CATEGORY_PRIORITY[category],
            title=task.get("title") or "Untitled task",
            reason=reason,
            source="personal_task",
            ref=str(task["id"]),
            generated_at=stamp,
            capacity_adjusted_reason=capacity_reason,
        ))

    items.sort(key=lambda i: i.priority)
    return items


__all__ = ["attention_items_from_personal_tasks"]
