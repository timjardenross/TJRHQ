"""Capacity Bot — /guide (V02 WP08).

"I am not necessarily in distress, but I do not know what would be
sensible to do next." (spec §16)

Reuses a recent /capacity check-in when one exists — never re-asks
capacity/stimulation/pain the user just answered (spec §16, §28). Only
"available time" has no equivalent in capacity_checkins, so that's always
asked. Ranks through intervention_engine.rank_interventions() like
/helpme and /capacity Q9 (spec §4).

Callback prefixes: `cg|` for the recent-check-reuse / fallback questions,
`cgi|` for the offer screen (Accept / Another option / Why this?).
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bots.capacitybot.capacity_today import (
    CAPACITY_CODE_TO_STATE,
    CAPACITY_LABEL,
    CAPACITY_OPTIONS,
    CAPACITY_SHORT,
    PAIN_CODE_TO_STATE,
    PAIN_LABEL,
    PAIN_OPTIONS,
    PAIN_SHORT,
    STIM_CODE_TO_STATE,
    STIMULATION_LABEL,
    STIMULATION_OPTIONS,
    STIMULATION_SHORT,
    render_question,
)

STATE_TO_CAPACITY_CODE = {v: k for k, v in CAPACITY_CODE_TO_STATE.items()}
STATE_TO_STIM_CODE = {v: k for k, v in STIM_CODE_TO_STATE.items()}
STATE_TO_PAIN_CODE = {v: k for k, v in PAIN_CODE_TO_STATE.items()}

# A capacity_checkins row this recent is treated as "the current state" —
# older than this, spec §16's "recent" no longer applies and /guide falls
# back to asking directly.
RECENT_CHECKIN_WINDOW_MINUTES = 120

TIME_OPTIONS = [("s", "⏱ Under 10 min"), ("m", "⏱ 10-30 min"), ("l", "⏱ 30+ min")]
TIME_SHORT = {"s": "Under 10 min", "m": "10-30 min", "l": "30+ min"}
TIME_TO_MAX_MINUTES = {"s": 10, "m": 30, "l": None}

_LEVER_LABEL = {
    "reduce_load": "Reduce demand",
    "regulate": "Regulate",
    "recover": "Recover",
    "redesign": "Rethink the setup",
}


# ── Fallback questions (no recent /capacity check-in to reuse) ──────────────
# Same option tables and wording as /capacity's Q1-Q3, `cg|` callback prefix
# so answers route back into this flow instead of the quick-check-in one.

def kb_guide_capacity() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(CAPACITY_SHORT[code], callback_data=f"cg|cap={code}")
               for code, _label in CAPACITY_OPTIONS]
    return InlineKeyboardMarkup([buttons])


def kb_guide_stimulation(cap: str) -> InlineKeyboardMarkup:
    base = f"cg|cap={cap}"
    buttons = [InlineKeyboardButton(STIMULATION_SHORT[code], callback_data=f"{base}|stim={code}")
               for code, _label in STIMULATION_OPTIONS]
    return InlineKeyboardMarkup([buttons])


def kb_guide_pain(cap: str, stim: str) -> InlineKeyboardMarkup:
    base = f"cg|cap={cap}|stim={stim}"
    buttons = [InlineKeyboardButton(PAIN_SHORT[code], callback_data=f"{base}|pain={code}")
               for code, _label in PAIN_OPTIONS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def q_time_available() -> str:
    return render_question("How much time do you have?", [label for _, label in TIME_OPTIONS])


def kb_time_available(prefix: str) -> InlineKeyboardMarkup:
    """`prefix` is the already-built `cg|...` base (either from a reused
    recent check-in or from the 3-tap fallback) — this is always the last
    question before ranking."""
    buttons = [InlineKeyboardButton(f"{i} · {TIME_SHORT[code]}", callback_data=f"{prefix}|t={code}")
               for i, (code, _label) in enumerate(TIME_OPTIONS, 1)]
    return InlineKeyboardMarkup([buttons])


def render_offer(intervention: dict) -> str:
    """Plain text, no MarkdownV2 — matches this bot's convention throughout
    (capacity_today.py's own docstring: avoids escaping bugs)."""
    lever = _LEVER_LABEL.get(intervention.get("management_lever"), "Try this")
    lines = [lever.upper(), "", intervention.get("full_description") or intervention["title"]]
    minutes = intervention.get("estimated_minutes")
    if minutes:
        lines.append(f"\n(~{minutes} min)")
    return "\n".join(lines)


def render_why(intervention: dict, capacity_state: str | None, stimulation_state: str | None,
               pain_state: str | None) -> str:
    bits = []
    if capacity_state:
        bits.append(f"capacity is {CAPACITY_LABEL.get(capacity_state, capacity_state).split(' ', 1)[-1].lower()}")
    if stimulation_state:
        bits.append(f"stimulation is {STIMULATION_LABEL.get(stimulation_state, stimulation_state).split(' ', 1)[-1].lower()}")
    if pain_state:
        bits.append(f"pain is {PAIN_LABEL.get(pain_state, pain_state).split(' ', 1)[-1].lower()}")
    context = ", ".join(bits) if bits else "what you've told me"
    lever = _LEVER_LABEL.get(intervention.get("management_lever"), "this")
    return (
        f"Because {context}, {intervention['title'].lower()} is a "
        f"low-effort way to {lever.lower()} right now."
    )


def kb_offer(intervention_id: str, showing_why: bool = False) -> InlineKeyboardMarkup:
    base = f"cgi|iid={intervention_id}"
    rows = [[InlineKeyboardButton("✅ I'll do that", callback_data=f"{base}|act=accept")]]
    if not showing_why:
        rows.append([InlineKeyboardButton("❓ Why this?", callback_data=f"{base}|act=why")])
    rows.append([InlineKeyboardButton("🔄 Another option", callback_data=f"{base}|act=another")])
    return InlineKeyboardMarkup(rows)


def render_no_options() -> str:
    return "Nothing fits that time window right now. Try /helpme or /capacity instead."


def render_accepted(intervention: dict, reminder_minutes: int | None) -> str:
    lines = [f"✅ {intervention['title']}"]
    if reminder_minutes:
        lines.append(f"\nI'll check back in {reminder_minutes} minutes.")
    return "\n".join(lines)


def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result
