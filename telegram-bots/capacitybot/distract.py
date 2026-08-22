"""Capacity Bot — /distract + rescue protocols (V02 WP09).

Distraction mode (spec §17): capacity-tiered bounded activity suggestions.
Deliberately NOT routed through intervention_engine — these are idle-time
filler activities, not capacity-management interventions with a
before/after outcome worth tracking (spec frames this as its own light
catalogue, distinct from §4's "one engine" statement, which is scoped to
CHECK/HELP/GUIDE specifically). No DB writes; "make the catalogue
user-editable later" is explicitly future work (spec §17), not V02.

Rescue protocols (spec §18): read-only display of the 3 default named
protocols seeded into capacity_rescue_protocols/capacity_protocol_steps by
migration 0151 — reusable step-by-step guidance for OFFICE OVERLOAD,
FLAT + CAN'T START, and RACING BRAIN. "V02 may ship with defaults, but
design for future custom protocols" — the DB shape already supports that;
this module is just the read path.
"""

from __future__ import annotations

import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bots.capacitybot.capacity_today import render_question

log = logging.getLogger(__name__)

# ── Distraction mode ──────────────────────────────────────────────────────────

DISTRACT_CAPACITY_OPTIONS = [("r", "🔴 Almost none"), ("o", "🟠 A little"), ("g", "🟢 Reasonable")]
DISTRACT_CAPACITY_SHORT = {"r": "Almost none", "o": "A little", "g": "Reasonable"}

_LOW = [
    "Familiar TV or content", "Music", "A simple game", "Quiet time with a pet",
    "A shower", "Sensory comfort", "Sit outside",
]
_MEDIUM = [
    "A short walk", "A small puzzle", "Music + movement",
    "One small organising activity", "A 10-minute interesting activity",
]
_HIGH = [
    "A creative activity", "Structured exercise", "A bounded personal project",
    "Learn something for 20 minutes", "Brief connection with someone",
]
_TIER_ACTIVITIES = {"r": _LOW, "o": _MEDIUM, "g": _HIGH}
_TIER_LABEL = {"r": "low-capacity", "o": "medium-capacity", "g": "higher-capacity"}


def q_distract_capacity() -> str:
    return render_question("How much capacity do you have?",
                            [label for _, label in DISTRACT_CAPACITY_OPTIONS])


def kb_distract_capacity() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(DISTRACT_CAPACITY_SHORT[code], callback_data=f"cd|cap={code}")
               for code, _label in DISTRACT_CAPACITY_OPTIONS]
    return InlineKeyboardMarkup([buttons])


def pick_activity(tier: str, exclude: list[str] | None = None) -> str | None:
    """Spec §17: offer ONE bounded activity, not a list. Picks randomly
    within the tier so repeat /distract calls don't always suggest the
    same first item; `exclude` supports the 'something else' re-roll."""
    pool = [a for a in _TIER_ACTIVITIES.get(tier, []) if a not in (exclude or [])]
    if not pool:
        pool = _TIER_ACTIVITIES.get(tier, [])
    return random.choice(pool) if pool else None


def render_activity(tier: str, activity: str) -> str:
    return f"{activity}.\n\n({_TIER_LABEL.get(tier, '')} suggestion — pick one, keep it bounded.)"


def kb_activity(tier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sounds good", callback_data=f"cdi|cap={tier}|act=done")],
        [InlineKeyboardButton("🔄 Something else", callback_data=f"cdi|cap={tier}|act=another")],
    ])


def render_done() -> str:
    return "Enjoy — no need to report back on this one."


# ── Rescue protocols — reads only ────────────────────────────────────────────

async def fetch_protocols(db) -> list[dict]:
    if not db:
        return []
    try:
        res = db.table("capacity_rescue_protocols").select("*").eq("enabled", True).execute()
        return res.data or []
    except Exception as exc:
        log.error("capacity_rescue_protocols fetch failed: %s", exc)
        return []


async def fetch_protocol(db, protocol_id) -> dict | None:
    if not db:
        return None
    try:
        res = db.table("capacity_rescue_protocols").select("*").eq("id", protocol_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.error("capacity_rescue_protocols fetch by id failed: %s", exc)
        return None


async def fetch_protocol_steps(db, protocol_id) -> list[dict]:
    if not db:
        return []
    try:
        res = db.table("capacity_protocol_steps").select("*").eq("protocol_id", protocol_id).execute()
        return res.data or []
    except Exception as exc:
        log.error("capacity_protocol_steps fetch failed: %s", exc)
        return []


def q_protocol_list() -> str:
    return "Which situation matches what's happening?"


def kb_protocol_list(protocols: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(p["title"], callback_data=f"cp|id={p['id']}")] for p in protocols]
    return InlineKeyboardMarkup(rows)


def render_protocol(protocol: dict, steps: list[dict]) -> str:
    lines = [protocol["title"]]
    if protocol.get("description"):
        lines.append(protocol["description"])
    lines.append("")
    for s in sorted(steps, key=lambda s: s["step_order"]):
        lines.append(f"{s['step_order']}. {s['instruction']}")
    return "\n".join(lines)


def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result
