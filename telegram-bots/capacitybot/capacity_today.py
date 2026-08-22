"""Capacity Bot — MY CAPACITY TODAY (V02 — Regulate, WP01: Telegram rendering fix).

Purpose: "track what my system needs today, not what diagnosis explains
it." Not a diagnostic tool — tracks capacity, stimulation, pain, overload,
masking/compensation, and what actually helps. See
MY_CAPACITY_TODAY_V02_Mission_and_Scope.md for the full product spec.

Convention:
  - Callback data is pipe-delimited key=value pairs, flow tag `ct|`.
  - All state lives in the callback data itself — no ConversationHandler.
  - query.edit_message_text() updates the same message in place.
  - Terminal state is detected by field presence, not a step counter.

V02 WP01 rendering rule (spec §3): every question's full text and every
option's full wording is always shown in the MESSAGE BODY. Inline buttons
never carry the full wording — only a compact "N · short label", numbered
to match the body listing. `stored_value` (the single-letter/word code)
never changes: this is a presentation-layer fix only, no data migration.
Long multi-select lists (>6 options) paginate the BUTTON rows only; the
body always lists every option, unpaginated, with a checkmark per
selection — see PAGE_SIZE / kb_multiselect below.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_TZ = ZoneInfo("Australia/Brisbane")
log = logging.getLogger(__name__)

TABLE = "capacity_checkins"

PAGE_SIZE = 6  # spec §3.3: prefer 4-6 visible multi-select options per page


# ── Option tables (full wording — always shown in the message body) ───────────

CAPACITY_OPTIONS = [
    ("g", "🟢 Sustainable"),
    ("o", "🟠 Stretched"),
    ("r", "🔴 Depleted"),
]
CAPACITY_SHORT = {"g": "Sustainable", "o": "Stretched", "r": "Depleted"}
CAPACITY_LABEL = {"green": "🟢 Sustainable", "orange": "🟠 Stretched", "red": "🔴 Depleted"}
CAPACITY_CODE_TO_STATE = {"g": "green", "o": "orange", "r": "red"}

STIMULATION_OPTIONS = [
    ("l", "⬇️ Not enough"),
    ("b", "⚖️ About right"),
    ("h", "⬆️ Too much"),
]
STIMULATION_SHORT = {"l": "Not enough", "b": "About right", "h": "Too much"}
STIMULATION_LABEL = {"low": "⬇️ Not enough", "balanced": "⚖️ About right", "high": "⬆️ Too much"}
STIM_CODE_TO_STATE = {"l": "low", "b": "balanced", "h": "high"}

PAIN_OPTIONS = [
    ("l", "🟢 Lower than usual"),
    ("b", "🟡 Around usual"),
    ("e", "🟠 Higher than usual"),
    ("h", "🔴 Much higher than usual"),
]
PAIN_SHORT = {"l": "Lower", "b": "Around usual", "e": "Higher", "h": "Much higher"}
PAIN_LABEL = {
    "low": "🟢 Lower than usual", "baseline": "🟡 Around usual",
    "elevated": "🟠 Higher than usual", "high": "🔴 Much higher than usual",
}
PAIN_CODE_TO_STATE = {"l": "low", "b": "baseline", "e": "elevated", "h": "high"}

REGULATION_OPTIONS = [
    ("s", "😌 Settled"),
    ("m", "🙂 Manageable"),
    ("a", "😣 Activated"),
    ("o", "🚨 Overloaded"),
]
REGULATION_SHORT = {"s": "Settled", "m": "Manageable", "a": "Activated", "o": "Overloaded"}
REGULATION_LABEL = {
    "settled": "😌 Settled", "manageable": "🙂 Manageable",
    "activated": "😣 Activated", "overloaded": "🚨 Overloaded",
}
REG_CODE_TO_STATE = {"s": "settled", "m": "manageable", "a": "activated", "o": "overloaded"}

EF_OPTIONS = [
    ("g", "✅ Working well"),
    ("s", "🟡 More effort than usual"),
    ("d", "🟠 Difficult"),
    ("v", "🔴 Very difficult"),
]
EF_SHORT = {"g": "Working well", "s": "More effort", "d": "Difficult", "v": "Very difficult"}
EF_LABEL = {
    "good": "✅ Working well", "strained": "🟡 More effort than usual",
    "difficult": "🟠 Difficult", "very_difficult": "🔴 Very difficult",
}
EF_CODE_TO_STATE = {"g": "good", "s": "strained", "d": "difficult", "v": "very_difficult"}

COMPENSATION_OPTIONS = [
    ("l", "🟢 Very little"),
    ("m", "🟡 Some"),
    ("h", "🟠 A lot"),
    ("e", "🔴 I'm forcing myself through"),
]
COMPENSATION_SHORT = {"l": "Very little", "m": "Some", "h": "A lot", "e": "Forcing through"}
COMPENSATION_LABEL = {
    "low": "🟢 Very little", "moderate": "🟡 Some",
    "high": "🟠 A lot", "extreme": "🔴 I'm forcing myself through",
}
COMP_CODE_TO_STATE = {"l": "low", "m": "moderate", "h": "high", "e": "extreme"}

# V02.1 (2026-08-22) — Sleep, Emotional, Social. Added to close 3 of the 5
# data gaps in the Human Systems Workbench's Capacity & Recovery Conditions
# card; migration 0152_capacity_checkins_sleep_emotional_social.sql. Sleep
# is asked once per day only (cmd_capacity checks for an existing today's
# check-in first); Emotional and Social are asked on every quick check-in
# — Captain's explicit choice over the cheaper active_loads-tag-presence
# proxy that was also on the table.

SLEEP_OPTIONS = [
    ("u5", "Under 5h"), ("56", "5-6h"), ("67", "6-7h"), ("78", "7-8h"), ("8p", "8h+"),
]
SLEEP_SHORT = {"u5": "Under 5h", "56": "5-6h", "67": "6-7h", "78": "7-8h", "8p": "8h+"}
SLEEP_CODE_TO_STATE = {"u5": "under_5", "56": "5_6", "67": "6_7", "78": "7_8", "8p": "8_plus"}
SLEEP_LABEL = {"under_5": "Under 5h", "5_6": "5-6h", "6_7": "6-7h", "7_8": "7-8h", "8_plus": "8h+"}

EMOTIONAL_OPTIONS = [
    ("l", "🟢 Light"), ("m", "🟡 Moderate"), ("h", "🟠 Heavy"), ("o", "🔴 Overwhelming"),
]
EMOTIONAL_SHORT = {"l": "Light", "m": "Moderate", "h": "Heavy", "o": "Overwhelming"}
EMOTIONAL_CODE_TO_STATE = {"l": "light", "m": "moderate", "h": "heavy", "o": "overwhelming"}
EMOTIONAL_LABEL = {
    "light": "🟢 Light", "moderate": "🟡 Moderate", "heavy": "🟠 Heavy", "overwhelming": "🔴 Overwhelming",
}

SOCIAL_OPTIONS = [
    ("g", "🟢 Plenty"), ("m", "🟡 Some"), ("l", "🟠 Limited"), ("n", "🔴 None left"),
]
SOCIAL_SHORT = {"g": "Plenty", "m": "Some", "l": "Limited", "n": "None left"}
SOCIAL_CODE_TO_STATE = {"g": "plenty", "m": "some", "l": "limited", "n": "none"}
SOCIAL_LABEL = {"plenty": "🟢 Plenty", "some": "🟡 Some", "limited": "🟠 Limited", "none": "🔴 None left"}

# index-coded multi-select — position in this list IS the callback digit
ACTIVE_LOADS = [
    "🔊 Noise / sensory input", "👥 People / social interaction", "💼 Work",
    "🧠 Thinking / decisions", "🔄 Change / uncertainty", "🩹 Pain / physical symptoms",
    "😟 Anxiety / emotional load", "😴 Poor sleep / fatigue", "📱 Too much stimulation",
    "🥱 Not enough stimulation", "🏠 Life admin / chores", "❓ Something else",
]
ACTIVE_LOADS_SHORT = [
    "Noise", "People", "Work", "Thinking", "Change", "Pain",
    "Anxiety", "Poor sleep", "Overstim.", "Understim.", "Admin", "Other",
]
ACTIVE_LOADS_OTHER_IDX = 11

IDENTIFIED_NEEDS = [
    "🔇 Less sensory input", "🛑 Reduce demands", "🧘 Quiet / solitude", "🚶 Movement",
    "🎵 Music / stimulation", "🎯 Something interesting to focus on", "🛌 Rest", "💤 Sleep",
    "🩹 Pain management", "📋 Clear plan / structure", "🔄 More predictability",
    "💬 Connection / talk to someone", "🍽️ Food / hydration", "🌿 Outside / change of environment",
    "⏸️ Stop pushing", "❓ Something else",
]
IDENTIFIED_NEEDS_SHORT = [
    "Less input", "Reduce demands", "Solitude", "Movement", "Music",
    "Focus task", "Rest", "Sleep", "Pain mgmt", "Structure",
    "Predictability", "Connection", "Food/water", "Change env.", "Stop pushing", "Other",
]
IDENTIFIED_NEEDS_OTHER_IDX = 15

LOAD_CATEGORY_OPTIONS = [
    ("p", "physical"), ("c", "cognitive"), ("s", "sensory"),
    ("e", "emotional"), ("so", "social"), ("en", "environmental"),
]
DAY_WIN_HELPED_OPTIONS = [
    "Rest", "Movement", "Reduced demands", "Sensory control", "Structure",
    "Connection", "Interesting activity", "Pain management", "Nothing clearly helped",
]
DAY_WIN_HELPED_SHORT = [
    "Rest", "Movement", "Less demand", "Sensory ctrl", "Structure",
    "Connection", "Interesting", "Pain mgmt", "None helped",
]


# ── Action suggestion engine (spec §2 + §10 REVS levers) ──────────────────────
# Small master table of short codes -> action text, so a chosen action can
# live in callback data as a code instead of free text (kept fully in the
# existing "state lives in the callback string" pattern rather than relying
# on ephemeral per-chat memory).

MASTER_ACTIONS: dict[str, str] = {
    "reduce_input":   "Reduce sensory input",
    "postpone":       "Stop or postpone one non-essential demand",
    "quieter_place":  "Move somewhere quieter",
    "rest_20":        "Rest for 20-30 minutes",
    "pain_strategy":  "Use your normal pain/regulation strategy",
    "move_5":         "Move for 5-10 minutes",
    "music_on":       "Put music on",
    "bounded_task":   "Choose one interesting bounded task",
    "change_env":     "Change environment",
    "talk_briefly":   "Talk to someone briefly",
    "reduce_physical":"Reduce physical demand",
    "pain_mgmt":      "Use agreed pain-management strategies",
    "change_posture": "Change posture / position",
    "pace_not_push":  "Pace rather than push",
    "protect_recovery":"Protect recovery time",
    "one_task":       "Pick one task only",
    "first_action":   "Break it into the first physical action",
    "remove_optional":"Remove optional decisions",
    "use_timer":      "Use a timer",
    "defer_admin":    "Defer low-value admin",
    "stop_performing":"Where can you stop performing today?",
    "cancel_unnecessary":"Cancel something unnecessary",
    "reduce_social":  "Reduce social interaction",
    "work_directly":  "Work more directly",
    "drop_eye_contact":"Stop forcing eye contact or conversation where safe",
    "ask_dont_guess": "Ask for clarity instead of guessing",
    "simplify_expect":"Simplify expectations",
    "take_recovery":  "Take recovery time",
    "maintain":       "Maintain — no need to add load just because capacity is available",
    "early_reduce":   "What can you reduce, regulate, or change before this becomes red?",
}

MASTER_ACTIONS_SHORT: dict[str, str] = {
    "reduce_input": "Reduce input", "postpone": "Postpone task", "quieter_place": "Quieter space",
    "rest_20": "Rest 20 min", "pain_strategy": "Pain strategy", "move_5": "Move 5 min",
    "music_on": "Music on", "bounded_task": "Bounded task", "change_env": "Change env.",
    "talk_briefly": "Talk briefly", "reduce_physical": "Reduce physical", "pain_mgmt": "Pain mgmt",
    "change_posture": "Change posture", "pace_not_push": "Pace, don't push",
    "protect_recovery": "Protect recovery", "one_task": "One task only", "first_action": "First action",
    "remove_optional": "Remove optional", "use_timer": "Use timer", "defer_admin": "Defer admin",
    "stop_performing": "Stop performing?", "cancel_unnecessary": "Cancel task",
    "reduce_social": "Reduce social", "work_directly": "Work directly",
    "drop_eye_contact": "Drop eye contact", "ask_dont_guess": "Ask, don't guess",
    "simplify_expect": "Simplify expect.", "take_recovery": "Take recovery",
    "maintain": "Maintain", "early_reduce": "Reduce early?",
}


# ── Central rendering utility (V02 WP01 — spec §3.4) ──────────────────────────
# Single place that turns (question, full-wording options) into a message
# body. Buttons are built separately and only ever carry "N · short label".

def render_question(question: str, full_options: list[str]) -> str:
    """Full question + full numbered option wording, always shown in the
    message body regardless of how buttons render."""
    lines = [question, ""]
    lines += [f"{i}. {opt}" for i, opt in enumerate(full_options, 1)]
    return "\n".join(lines)


def render_multiselect_question(question: str, full_options: list[str], selected: str) -> str:
    """Same as render_question but marks selected items — used for every
    multi-select screen so the full list (not just the current button
    page) is always visible, per spec §3.3."""
    sel_set = set((selected or "").split(",")) if selected else set()
    lines = [question, ""]
    for i, opt in enumerate(full_options):
        mark = "✅" if str(i) in sel_set else "▫️"
        lines.append(f"{i + 1}. {mark} {opt}")
    lines.append("")
    lines.append("Tap a number below to toggle it, then Continue.")
    return "\n".join(lines)


def _select_rows(base: str, key: str, options: list[tuple[str, str]],
                  shorts: dict[str, str], per_row: int = 2) -> list[list[InlineKeyboardButton]]:
    """Compact numbered buttons for a single-select question — button text
    is never the full label, only 'N · short'. Order matches render_question's
    numbering exactly (both iterate `options` in the same order)."""
    buttons = [
        InlineKeyboardButton(f"{i} · {shorts[code]}", callback_data=f"{base}|{key}={code}")
        for i, (code, _label) in enumerate(options, 1)
    ]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


# ── Keyboard builders ──────────────────────────────────────────────────────────

def q_sleep() -> str:
    return render_question("How much sleep did you get last night?",
                            [label for _, label in SLEEP_OPTIONS])


def kb_sleep() -> InlineKeyboardMarkup:
    """Always the true start of the flow when shown (once per day, before
    capacity_state is even asked) — no prior fields to carry, base is
    always bare "ct"."""
    buttons = [InlineKeyboardButton(f"{i} · {SLEEP_SHORT[code]}", callback_data=f"ct|sl={code}")
               for i, (code, _label) in enumerate(SLEEP_OPTIONS, 1)]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def q_capacity() -> str:
    return render_question("MY CAPACITY TODAY\n\nHow is your capacity right now?",
                            [label for _, label in CAPACITY_OPTIONS])


def kb_capacity(f: dict | None = None) -> InlineKeyboardMarkup:
    """`f` carries `sl` forward when /capacity's optional sleep question
    was just answered (base_from() rebuilds "ct|sl=X"); omitted (or with
    no `sl` key) on every subsequent check-in today, same as always."""
    base = base_from(f) if f else "ct"
    return InlineKeyboardMarkup(_select_rows(base, "c", CAPACITY_OPTIONS, CAPACITY_SHORT, per_row=3))


def _done_row(prefix_state: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("✅ Done for now", callback_data=f"{prefix_state}|done=1")]


def q_stimulation() -> str:
    return render_question("Where is your stimulation level?",
                            [label for _, label in STIMULATION_OPTIONS])


def kb_stimulation(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = _select_rows(base, "t", STIMULATION_OPTIONS, STIMULATION_SHORT, per_row=3)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_pain() -> str:
    return render_question("How is your pain compared with your usual baseline?",
                            [label for _, label in PAIN_OPTIONS])


def kb_pain(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = _select_rows(base, "p", PAIN_OPTIONS, PAIN_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_pain_score() -> str:
    return "Pain intensity right now? (optional, 0=none · 10=worst)"


def kb_pain_score(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = [
        [InlineKeyboardButton(str(i), callback_data=f"{base}|ps={i}") for i in range(0, 6)],
        [InlineKeyboardButton(str(i), callback_data=f"{base}|ps={i}") for i in range(6, 11)],
        [InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|ps=skip")],
    ]
    return InlineKeyboardMarkup(rows)


def q_regulation() -> str:
    return render_question("How activated or overloaded does your system feel?",
                            [label for _, label in REGULATION_OPTIONS])


def kb_regulation(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = _select_rows(base, "r", REGULATION_OPTIONS, REGULATION_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_emotional() -> str:
    return render_question("How much emotional load are you carrying right now?",
                            [label for _, label in EMOTIONAL_OPTIONS])


def kb_emotional(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = _select_rows(base, "em", EMOTIONAL_OPTIONS, EMOTIONAL_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_executive_function() -> str:
    return render_question("How easy is it to think, decide, start, and switch tasks?",
                            [label for _, label in EF_OPTIONS])


def kb_executive_function(f: dict) -> InlineKeyboardMarkup:
    base = base_from(f)
    rows = _select_rows(base, "e", EF_OPTIONS, EF_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_social() -> str:
    return render_question("How much social capacity do you have right now?",
                            [label for _, label in SOCIAL_OPTIONS])


def kb_social(base: str) -> InlineKeyboardMarkup:
    """Phase 2 (id-based, write-through) — same shape as kb_compensation."""
    rows = _select_rows(base, "so", SOCIAL_OPTIONS, SOCIAL_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def _toggle_list(current: str, idx: int) -> str:
    sel = [x for x in current.split(",") if x] if current else []
    s = str(idx)
    if s in sel:
        sel.remove(s)
    else:
        sel.append(s)
    return ",".join(sel)


def q_active_loads(selected: str) -> str:
    return render_multiselect_question("What's taking the most capacity right now?",
                                        ACTIVE_LOADS, selected)


def q_identified_needs(selected: str) -> str:
    return render_multiselect_question("What would help your system most right now?",
                                        IDENTIFIED_NEEDS, selected)


def kb_multiselect(base: str, key: str, options: list[str], shorts: list[str],
                    selected: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated toggle-list keyboard (spec §3.3). `base` already contains
    every prior field; `key` is this step's callback-data key. The full
    option list is always in the message body (render_multiselect_question)
    — only the BUTTON rows paginate, PAGE_SIZE per page. Selections and the
    current page both round-trip through callback data so Prev/Next never
    lose a prior tap."""
    start = page * PAGE_SIZE
    page_indices = list(range(start, min(start + PAGE_SIZE, len(options))))
    sel_set = set((selected or "").split(",")) if selected else set()

    buttons = []
    for i in page_indices:
        mark = "✅" if str(i) in sel_set else "▫️"
        new_val = _toggle_list(selected, i)
        buttons.append(InlineKeyboardButton(
            f"{mark} {i + 1} · {shorts[i]}",
            callback_data=f"{base}|{key}={new_val}|pg={page}",
        ))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data=f"{base}|{key}={selected}|pg={page - 1}"))
    if start + PAGE_SIZE < len(options):
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"{base}|{key}={selected}|pg={page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➡️ Continue", callback_data=f"{base}|{key}={selected}|next=1")])
    rows.append([InlineKeyboardButton("✅ Done for now", callback_data=f"{base}|{key}={selected}|done=1")])
    return InlineKeyboardMarkup(rows)


def q_compensation() -> str:
    return render_question("How much are you having to push, mask, or compensate today?",
                            [label for _, label in COMPENSATION_OPTIONS])


def kb_compensation(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "cp", COMPENSATION_OPTIONS, COMPENSATION_SHORT, per_row=2)
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def q_actions(interventions: list[dict]) -> str:
    """V02 WP06 — `interventions` are ranked rows from
    intervention_engine.rank_interventions(), not the old static
    MASTER_ACTIONS codes."""
    if not interventions:
        return "No ranked suggestions available right now — tap Done to finish."
    return render_question(
        "What would help your system most right now?\n\nOne small thing you can do next:",
        [row["title"] for row in interventions],
    )


def kb_actions(base: str, interventions: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{i} · {row['button_label']}", callback_data=f"{base}|act={row['intervention_id']}")]
        for i, row in enumerate(interventions, 1)
    ]
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|act=skip")])
    return InlineKeyboardMarkup(rows)


def kb_go_deeper(row_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Go deeper", callback_data=f"ctd|id={row_id}")],
        [InlineKeyboardButton("⏰ Remind me", callback_data=f"ctr|id={row_id}")],
        [InlineKeyboardButton("Done", callback_data="ct|noop=1")],
    ])


# ── Remind me later (spec §2, "optionally allow") ────────────────────────────
# No existing generic reminder mechanism in this bot to integrate with —
# built as a one-off python-telegram-bot JobQueue.run_once, in-memory only:
# if the bot restarts before it fires, the reminder is lost. Acceptable for a
# same-day nudge; not durable enough for anything longer (spec §13).

REMIND_OPTIONS = [("15", "15 min"), ("45", "45 min"), ("120", "2 hours")]


def q_remind_duration() -> str:
    return render_question("Remind you in how long?", [label for _, label in REMIND_OPTIONS])


def kb_remind_duration(row_id: str) -> InlineKeyboardMarkup:
    base = f"ctr|id={row_id}"
    buttons = [InlineKeyboardButton(f"{i} · {label}", callback_data=f"{base}|m={mins}")
               for i, (mins, label) in enumerate(REMIND_OPTIONS, 1)]
    return InlineKeyboardMarkup([buttons])


# ── Deep check-in (spec §4) ───────────────────────────────────────────────────
# All 8 questions: load_category, unexpected change, masking present, what
# was skipped (recovery_factors), recovery duration, what helped, what made
# things worse (buttons — index-coded multi-select, same convention as the
# quick check-in's active_loads/identified_needs), and a final free-text
# note covering both "what happened before" (trigger) and anything else
# (notes) — one text reply rather than two, to keep this bounded (spec §11.8:
# "no long forms"). Written via cmd_message's pending-state hook in app.py.

RECOVERY_DURATION_OPTIONS = [
    ("n",  "No recovery needed"),
    ("30", "Under 30 minutes"),
    ("2h", "1-2 hours"),
    ("hd", "Half a day"),
    ("fd", "Full day"),
    ("md", "Multiple days"),
]
RECOVERY_DURATION_SHORT = {
    "n": "No recovery", "30": "<30 min", "2h": "1-2h",
    "hd": "Half day", "fd": "Full day", "md": "Multi-day",
}
_RD_CODE_TO_LABEL = dict(RECOVERY_DURATION_OPTIONS)

# index-coded multi-select, same convention as ACTIVE_LOADS/IDENTIFIED_NEEDS —
# spec §4 Q5 ("did you skip food, movement, rest, medication, sleep, or
# recovery?"), stored as recovery_factors (what got skipped, not what helped).
RECOVERY_FACTORS = [
    "Food", "Movement", "Rest", "Medication", "Sleep", "Recovery time", "Nothing skipped",
]
RECOVERY_FACTORS_SHORT = [
    "Food", "Movement", "Rest", "Meds", "Sleep", "Recovery time", "None skipped",
]

# spec §4 Q6 "what helped?" — same set as the evening reflection's
# DAY_WIN_HELPED_OPTIONS list minus its "nothing helped" catch-all, which
# reads oddly for a mid-episode question.
HELPFUL_ACTIONS_OPTIONS = [o for o in DAY_WIN_HELPED_OPTIONS if o != "Nothing clearly helped"]
HELPFUL_ACTIONS_SHORT = [o for o in DAY_WIN_HELPED_SHORT if o != "None helped"]

# spec §4 Q7 "what made things worse?" — deliberately its own list rather
# than reusing HELPFUL_ACTIONS_OPTIONS; "what helped" and "what hurt" are not
# symmetric (e.g. "time pressure" has no helpful-list counterpart).
UNHELPFUL_ACTIONS_OPTIONS = [
    "Noise / sensory input", "Being interrupted", "Time pressure", "Uncertainty / change",
    "Social demands", "Physical exertion", "Skipping rest or food", "Pushing through pain",
    "Nothing made it worse",
]
UNHELPFUL_ACTIONS_SHORT = [
    "Noise", "Interrupted", "Time pressure", "Uncertainty", "Social demands",
    "Physical", "Skipped needs", "Pushed pain", "None worse",
]


def q_deep_load_category() -> str:
    return render_question("What was the main load?",
                            [label.capitalize() for _, label in LOAD_CATEGORY_OPTIONS])


def kb_deep_load_category(row_id: str) -> InlineKeyboardMarkup:
    base = f"ctd|id={row_id}"
    shorts = {code: label.capitalize() for code, label in LOAD_CATEGORY_OPTIONS}
    rows = _select_rows(base, "lc", LOAD_CATEGORY_OPTIONS, shorts, per_row=2)
    return InlineKeyboardMarkup(rows)


def kb_deep_yesno(base: str, key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes", callback_data=f"{base}|{key}=y"),
        InlineKeyboardButton("No", callback_data=f"{base}|{key}=n"),
    ]])


# ── V3 burnout-tier questions (TJR_Human_Systems_Workbench_V3_Mission_and_
# Change_Proposal.md Mission 1 Part D) — inserted after masking_present,
# before recovery_duration. Four optional deep-check-tier questions:
# user_burnout_framing (single-select), compensation_type (multiselect),
# body_signal_clarity (single-select), predictability (single-select).
# Every option is itself a "not sure" / "I don't know" value (spec §24 —
# "the user must be able to answer 'I don't know'"), so none of these
# needs a separate Skip button the way the quick check-in's yes/no steps
# don't either. Columns: migration 0153_capacity_checkins_burnout_
# semantic_fields.sql.
#
# id-based, write-through per tap (same convention as rf/ha/ua below, NOT
# the lc/uc/mp/rd string-accumulation above it) — chaining four more
# fields (one of them an 8-option multiselect) onto lc/uc/mp's
# already-accumulated prefix would risk the same 64-byte callback_data
# overflow already documented above kb_multiselect for the quick
# check-in's own Phase 1 -> Phase 2 switch. app.py's mp handler now writes
# lc/uc/mp to the row immediately (instead of waiting for rd) so every
# step from here on can use a bare `ctd|id={row_id}` base.

BURNOUT_FRAMING_OPTIONS = [
    ("ib", "I identify this period as autistic burnout"),
    ("mb", "I think I may be in burnout"),
    ("rb", "I am recovering from burnout"),
    ("nl", "I don't want a label"),
    ("ns", "Not sure / skip for now"),
]
BURNOUT_FRAMING_SHORT = {
    "ib": "Identify burnout", "mb": "May be burnout", "rb": "Recovering",
    "nl": "No label", "ns": "Not sure",
}
BURNOUT_FRAMING_CODE_TO_STATE = {
    "ib": "identify_as_burnout", "mb": "may_be_in_burnout", "rb": "recovering_from_burnout",
    "nl": "no_label", "ns": "not_set",
}

# Canonical values match migration 0153's comment
# (core/health/burnout_trajectory.py and api/human-systems/route.ts read
# these as plain frequency counts, not the display label text — unlike
# active_loads/identified_needs, which store the label itself).
COMPENSATION_TYPE_OPTIONS = [
    "Suppressing movement / stimming", "Suppressing sensory needs",
    "Performing expected social behaviour", "Forcing speech",
    "Hiding pain or fatigue", "Hiding need for solitude",
    "Pretending to understand / process immediately",
    "Suppressing need for routine or predictability",
]
COMPENSATION_TYPE_SHORT = [
    "Suppress movement", "Suppress sensory", "Perform social", "Force speech",
    "Hide pain/fatigue", "Hide need solitude", "Pretend understand", "Suppress routine",
]
COMPENSATION_TYPE_VALUES = [
    "suppressing_movement", "suppressing_sensory_needs", "performing_social", "forcing_speech",
    "hiding_pain_fatigue", "hiding_need_for_solitude", "pretending_to_understand",
    "suppressing_need_for_routine",
]

BODY_CLARITY_OPTIONS = [
    ("cl", "Clear"), ("sc", "Somewhat clear"), ("hi", "Hard to interpret"), ("ni", "No idea"),
]
BODY_CLARITY_SHORT = {"cl": "Clear", "sc": "Somewhat clear", "hi": "Hard to interpret", "ni": "No idea"}
BODY_CLARITY_CODE_TO_STATE = {"cl": "clear", "sc": "somewhat_clear", "hi": "hard_to_interpret", "ni": "no_idea"}

PREDICTABILITY_OPTIONS = [
    ("cp", "Clear / predictable"), ("su", "Some uncertainty"),
    ("ch", "Lots changing"), ("dk", "I don't know what happens next"),
]
PREDICTABILITY_SHORT = {"cp": "Clear/predictable", "su": "Some uncertainty", "ch": "Lots changing", "dk": "Don't know"}
PREDICTABILITY_CODE_TO_STATE = {
    "cp": "clear_predictable", "su": "some_uncertainty", "ch": "lots_changing", "dk": "dont_know",
}

# ── V3 Mission 3 (TJR_Human_Systems_Workbench_V3_Mission_and_Change_
# Proposal.md §10 "Sensory Regulation Upgrade" + §11 "Natural Regulation
# Response") — inserted after predictability (pd), before recovery_duration
# (rd). Migration 0158_capacity_checkins_sensory_regulation.sql.
#
# Sensory channels — interaction-design tradeoff (documented per the
# mission brief): §10 lists 8 channels x 5 responses = 40 combinations,
# too many for one screen and a clear violation of §24 ("must not become a
# 50-question assessment") if asked as 8 separate mandatory questions.
# Chosen design: (1) one skippable multiselect ("did any specific channels
# stand out?") using the SAME kb_deep_multiselect/generic ct.q_deep_
# multiselect convention as cpt/rf/ha/ua — flag only what stood out, 0
# flags is a valid, fully-skippable answer; then (2) a short one-
# question-per-flagged-channel follow-up loop (q_sensory_channel_response/
# kb_sensory_channel_response below), since the doc's own worked example
# ("auditory load is high") needs a RESPONSE per channel, not just a flag,
# and the doc explicitly says "most check-ins will only flag 1-2 channels,
# not all 8" — so the realistic loop length is 1-2 taps, not 8. The
# remaining-channel queue rides in callback data as bare indices
# (sci=current, scq=remaining csv), never accumulating full channel names/
# responses in the callback string (same 64-byte-limit discipline
# documented above kb_deep_yesno) — each tap writes straight to the row's
# sensory_channels jsonb (write_deep_sensory_channel()) instead.
# Alternative considered and rejected: collapsing to a single combined
# "how did today's sensory input feel overall" question — rejected because
# it would just re-ask stimulation_state (already captured every quick
# check-in) instead of adding the genuinely new per-channel signal §10
# asks for.

SENSORY_CHANNELS = [
    ("auditory", "🔊 Auditory (sound)"),
    ("visual", "👁️ Visual (light / visual clutter)"),
    ("touch", "✋ Touch / texture"),
    ("smell", "👃 Smell"),
    ("movement", "🌀 Movement / vestibular"),
    ("pressure", "🤲 Pressure / proprioceptive"),
    ("temperature", "🌡️ Temperature"),
    ("environmental_complexity", "🏙️ Environmental complexity"),
]
SENSORY_CHANNEL_KEYS = [key for key, _label in SENSORY_CHANNELS]
SENSORY_CHANNEL_LABELS = [label for _key, label in SENSORY_CHANNELS]
SENSORY_CHANNEL_SHORT = [
    "Auditory", "Visual", "Touch", "Smell", "Movement", "Pressure", "Temperature", "Env. complexity",
]

SENSORY_RESPONSE_OPTIONS = [
    ("ra", "Reduce / avoid"), ("nu", "Neutral"), ("sh", "Seek / helpful"),
    ("cd", "Context dependent"), ("uk", "Unknown"),
]
SENSORY_RESPONSE_SHORT = {
    "ra": "Reduce/avoid", "nu": "Neutral", "sh": "Seek/helpful", "cd": "Context dep.", "uk": "Unknown",
}
SENSORY_RESPONSE_CODE_TO_VALUE = {
    "ra": "reduce_avoid", "nu": "neutral", "sh": "seek_helpful", "cd": "context_dependent", "uk": "unknown",
}

# Natural regulation response (V3 doc §11) — single-select, 14 options
# (including "I don't know"), same _select_rows convention as
# BURNOUT_FRAMING_OPTIONS above, just more rows (per_row=2, no pagination —
# single-select screens don't paginate in this codebase, only multiselects
# do; 14 short buttons across 7 rows is well within Telegram's per-message
# limits, same as the option-count precedent COMPENSATION_TYPE_OPTIONS (8)
# already sets for a *multiselect*).
NATURAL_REGULATION_OPTIONS = [
    ("li", "Less input"), ("mi", "More input"), ("mv", "Move"), ("fr", "Fidget / repeat"),
    ("qt", "Quiet"), ("st", "Stop talking"), ("ba", "Be alone"),
    ("cs", "Connect with someone safe"), ("sf", "Something familiar"),
    ("si", "Something interesting"), ("pc", "Pressure / sensory comfort"),
    ("gt", "Get thoughts out"), ("rs", "Rest"), ("dk", "I don't know"),
]
NATURAL_REGULATION_SHORT = {
    "li": "Less input", "mi": "More input", "mv": "Move", "fr": "Fidget/repeat",
    "qt": "Quiet", "st": "Stop talking", "ba": "Be alone", "cs": "Connect safe",
    "sf": "Familiar", "si": "Interesting", "pc": "Pressure/comfort",
    "gt": "Thoughts out", "rs": "Rest", "dk": "Don't know",
}
NATURAL_REGULATION_CODE_TO_STATE = {
    "li": "less_input", "mi": "more_input", "mv": "move", "fr": "fidget_repeat",
    "qt": "quiet", "st": "stop_talking", "ba": "be_alone", "cs": "connect_with_someone_safe",
    "sf": "something_familiar", "si": "something_interesting", "pc": "pressure_sensory_comfort",
    "gt": "get_thoughts_out", "rs": "rest", "dk": "dont_know",
}


def q_burnout_framing() -> str:
    return render_question("How would you frame this period, if at all? (optional)",
                            [label for _, label in BURNOUT_FRAMING_OPTIONS])


def kb_burnout_framing(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "bf", BURNOUT_FRAMING_OPTIONS, BURNOUT_FRAMING_SHORT, per_row=1)
    return InlineKeyboardMarkup(rows)


def q_body_signal_clarity() -> str:
    return render_question("How clear are your body's signals right now?",
                            [label for _, label in BODY_CLARITY_OPTIONS])


def kb_body_signal_clarity(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "bc", BODY_CLARITY_OPTIONS, BODY_CLARITY_SHORT, per_row=2)
    return InlineKeyboardMarkup(rows)


def q_predictability() -> str:
    return render_question("How predictable does what's ahead feel?",
                            [label for _, label in PREDICTABILITY_OPTIONS])


def kb_predictability(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "pd", PREDICTABILITY_OPTIONS, PREDICTABILITY_SHORT, per_row=2)
    return InlineKeyboardMarkup(rows)


# ── Sensory channel follow-up loop (V3 doc §10, see the design-tradeoff
# comment above SENSORY_CHANNELS) ────────────────────────────────────────

def q_sensory_channel_response(channel_idx: str) -> str:
    label = SENSORY_CHANNEL_LABELS[int(channel_idx)]
    return render_question(f"How does {label} feel right now?",
                            [label for _, label in SENSORY_RESPONSE_OPTIONS])


def kb_sensory_channel_response(row_id: str, channel_idx: str, remaining_csv: str) -> InlineKeyboardMarkup:
    """`channel_idx` is the channel currently being asked about;
    `remaining_csv` is the still-to-ask queue (both indices into
    SENSORY_CHANNELS) — carried in the callback base so the handler knows
    which channel to write this tap's response against and what to ask
    next. No prior fields chain here beyond that (write-through per tap,
    same convention as the cpt/bc/pd steps above)."""
    base = f"ctd|id={row_id}|sci={channel_idx}|scq={remaining_csv}"
    rows = _select_rows(base, "scr", SENSORY_RESPONSE_OPTIONS, SENSORY_RESPONSE_SHORT, per_row=2)
    return InlineKeyboardMarkup(rows)


# ── Natural regulation response (V3 doc §11) ─────────────────────────────

def q_natural_regulation() -> str:
    return render_question("What does your system seem to want right now? (optional)",
                            [label for _, label in NATURAL_REGULATION_OPTIONS])


def kb_natural_regulation(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "nr", NATURAL_REGULATION_OPTIONS, NATURAL_REGULATION_SHORT, per_row=2)
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|nr=skip")])
    return InlineKeyboardMarkup(rows)


def q_suppressed_regulation() -> str:
    return ("Are you stopping yourself from doing something that might help, because it feels "
            "inappropriate, inconvenient, or noticeable? (optional — this is for spotting where "
            "compensation is costing you, not a prompt to correct anything.)")


def kb_suppressed_regulation(base: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes", callback_data=f"{base}|sr=y"),
        InlineKeyboardButton("No", callback_data=f"{base}|sr=n"),
        InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|sr=skip"),
    ]])


def q_deep_recovery_duration() -> str:
    return render_question("How long did recovery take?",
                            [label for _, label in RECOVERY_DURATION_OPTIONS])


def kb_deep_recovery_duration(base: str) -> InlineKeyboardMarkup:
    rows = _select_rows(base, "rd", RECOVERY_DURATION_OPTIONS, RECOVERY_DURATION_SHORT, per_row=2)
    return InlineKeyboardMarkup(rows)


def q_deep_multiselect(question: str, options: list[str], selected: str) -> str:
    return render_multiselect_question(question, options, selected)


def kb_deep_multiselect(row_id: str, key: str, options: list[str], shorts: list[str],
                         selected: str, page: int = 0) -> InlineKeyboardMarkup:
    """Same paginated shape as kb_multiselect, but for the deep-check steps
    that come after lc/uc/mp/rd are already saved to the row — base is
    always just the row id (write-through per tap)."""
    base = f"ctd|id={row_id}"
    start = page * PAGE_SIZE
    page_indices = list(range(start, min(start + PAGE_SIZE, len(options))))
    sel_set = set((selected or "").split(",")) if selected else set()

    buttons = []
    for i in page_indices:
        mark = "✅" if str(i) in sel_set else "▫️"
        sel = [x for x in (selected.split(",") if selected else []) if x]
        s = str(i)
        if s in sel:
            sel.remove(s)
        else:
            sel.append(s)
        new_val = ",".join(sel)
        buttons.append(InlineKeyboardButton(
            f"{mark} {i + 1} · {shorts[i]}",
            callback_data=f"{base}|{key}={new_val}|pg={page}",
        ))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data=f"{base}|{key}={selected}|pg={page - 1}"))
    if start + PAGE_SIZE < len(options):
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"{base}|{key}={selected}|pg={page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➡️ Continue", callback_data=f"{base}|{key}={selected}|next=1")])
    rows.append([InlineKeyboardButton("✅ Done for now", callback_data=f"{base}|{key}={selected}|done=1")])
    return InlineKeyboardMarkup(rows)


def kb_deep_note_prompt(row_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭ Skip / save now", callback_data=f"ctd|id={row_id}|final=1"),
    ]])


# ── Evening reflection (spec §5) ─────────────────────────────────────────────

EVENING_TRAJECTORY_OPTIONS = [("u", "⬆️ Improved"), ("s", "➡️ About the same"), ("d", "⬇️ Declined")]
EVENING_TRAJECTORY_SHORT = {"u": "Improved", "s": "About same", "d": "Declined"}

EVENING_DEBT_OPTIONS = [("n", "No"), ("m", "Maybe"), ("y", "Yes")]
EVENING_DEBT_SHORT = {"n": "No", "m": "Maybe", "y": "Yes"}


def q_evening_trajectory() -> str:
    return render_question("Did your capacity improve, stay the same, or decline today?",
                            [label for _, label in EVENING_TRAJECTORY_OPTIONS])


def kb_evening_trajectory() -> InlineKeyboardMarkup:
    rows = _select_rows("cte", "dt", EVENING_TRAJECTORY_OPTIONS, EVENING_TRAJECTORY_SHORT, per_row=3)
    return InlineKeyboardMarkup(rows)


def q_evening_helpful() -> str:
    return render_question("What helped most?", DAY_WIN_HELPED_OPTIONS)


def kb_evening_helpful(dt: str) -> InlineKeyboardMarkup:
    base = f"cte|dt={dt}"
    buttons = [InlineKeyboardButton(f"{i} · {short}", callback_data=f"{base}|hf={i - 1}")
               for i, short in enumerate(DAY_WIN_HELPED_SHORT, 1)]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def q_evening_debt() -> str:
    return render_question("Did you borrow capacity from tomorrow?",
                            [label for _, label in EVENING_DEBT_OPTIONS])


def kb_evening_debt(dt: str, hf: str) -> InlineKeyboardMarkup:
    base = f"cte|dt={dt}|hf={hf}"
    rows = _select_rows(base, "cd", EVENING_DEBT_OPTIONS, EVENING_DEBT_SHORT, per_row=3)
    return InlineKeyboardMarkup(rows)


# ── Therapy summary window selector ─────────────────────────────────────────

THERAPY_WINDOW_OPTIONS = [("1", "1 week"), ("2", "2 weeks"), ("4", "4 weeks")]
THERAPY_WINDOW_SHORT = {"1": "1 week", "2": "2 weeks", "4": "4 weeks"}


def q_therapy_window() -> str:
    return render_question("Therapy summary — how far back?",
                            [label for _, label in THERAPY_WINDOW_OPTIONS])


def kb_therapy_window() -> InlineKeyboardMarkup:
    rows = _select_rows("cty", "w", THERAPY_WINDOW_OPTIONS, THERAPY_WINDOW_SHORT, per_row=3)
    return InlineKeyboardMarkup(rows)


# ── Parsing ─────────────────────────────────────────────────────────────────

def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


_FIELD_ORDER = ["sl", "c", "t", "p", "ps", "r", "em", "e", "ld", "cp", "so", "nd"]


def base_from(f: dict, keys: list[str] | None = None) -> str:
    """Rebuild a `ct|...` callback-data prefix from parsed fields, in
    canonical order, restricted to `keys` if given. Used to reconstruct the
    base string for the next screen instead of slicing the raw callback
    string (robust regardless of which button produced `f`)."""
    order = keys if keys is not None else _FIELD_ORDER
    parts = ["ct"] + [f"{k}={f[k]}" for k in order if f.get(k) is not None]
    return "|".join(parts)


def _idx_list(csv: str | None, options: list[str]) -> list[str]:
    if not csv:
        return []
    out = []
    for tok in csv.split(","):
        if tok.isdigit() and int(tok) < len(options):
            out.append(options[int(tok)])
    return out


def _idx_values(csv: str | None, values: list[str]) -> list[str]:
    """Same index-decoding as _idx_list(), but returns the canonical
    snake_case VALUE at each position rather than the display label —
    used for compensation_type (migration 0153), which stores canonical
    codes, not label text (unlike active_loads/identified_needs)."""
    return _idx_list(csv, values)


# ── Writes ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(_TZ).isoformat()


def _time_of_day_label() -> str:
    h = datetime.now(_TZ).hour
    if 5 <= h < 12:
        return "Morning"
    if 12 <= h < 17:
        return "Afternoon"
    if 17 <= h < 21:
        return "Evening"
    return "Night"


async def write_quick_checkin(db, f: dict) -> tuple[bool, dict | None, str | None]:
    """Insert (or, if `id` already present, update) a capacity check-in row
    from parsed callback fields. Returns (saved, row, err_msg)."""
    if not db:
        return False, None, "Supabase unavailable (check SUPABASE_KEY)"

    payload: dict = {"checkin_type": "capacity", "source": "telegram"}
    if f.get("sl"):
        payload["sleep_state"] = SLEEP_CODE_TO_STATE.get(f["sl"])
    if f.get("c"):
        payload["capacity_state"] = CAPACITY_CODE_TO_STATE.get(f["c"])
    if f.get("t"):
        payload["stimulation_state"] = STIM_CODE_TO_STATE.get(f["t"])
    if f.get("p"):
        payload["pain_state"] = PAIN_CODE_TO_STATE.get(f["p"])
    if f.get("ps") and f["ps"] != "skip":
        try:
            payload["pain_score"] = int(f["ps"])
        except ValueError:
            pass
    if f.get("r"):
        payload["regulation_state"] = REG_CODE_TO_STATE.get(f["r"])
    if f.get("em"):
        payload["emotional_state"] = EMOTIONAL_CODE_TO_STATE.get(f["em"])
    if f.get("e"):
        payload["executive_function"] = EF_CODE_TO_STATE.get(f["e"])
    if f.get("ld") is not None:
        loads = _idx_list(f["ld"], ACTIVE_LOADS)
        payload["active_loads"] = loads
    if f.get("cp"):
        payload["compensation_load"] = COMP_CODE_TO_STATE.get(f["cp"])
    if f.get("so"):
        payload["social_state"] = SOCIAL_CODE_TO_STATE.get(f["so"])
    if f.get("nd") is not None:
        needs = _idx_list(f["nd"], IDENTIFIED_NEEDS)
        payload["identified_needs"] = needs
    if f.get("act") and f["act"] != "skip":
        payload["selected_action"] = MASTER_ACTIONS.get(f["act"], f["act"])

    row_id = f.get("id")
    try:
        if row_id:
            payload["updated_at"] = _now_iso()
            res = db.table(TABLE).update(payload).eq("id", row_id).execute()
        else:
            payload["time_of_day"] = _time_of_day_label()
            res = db.table(TABLE).insert(payload).execute()
        row = (res.data or [None])[0]
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat(TABLE, status="ok", detail=f"checkin_type=capacity source=telegram")
        except Exception:
            pass
        return True, row, None
    except Exception as exc:
        log.error("capacity_checkins write failed: %s | payload=%s", exc, payload)
        return False, None, str(exc)


async def fetch_checkin(db, row_id: str) -> dict | None:
    if not db:
        return None
    try:
        res = db.table(TABLE).select("*").eq("id", row_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.error("capacity_checkins fetch by id failed: %s", exc)
        return None


async def write_deep_checkin(db, row_id: str, f: dict) -> tuple[bool, str | None]:
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    payload: dict = {"updated_at": _now_iso()}
    if f.get("lc"):
        cat_map = {c: label for c, label in LOAD_CATEGORY_OPTIONS}
        payload["load_category"] = cat_map.get(f["lc"])
    if f.get("uc"):
        payload["unexpected_change"] = f["uc"] == "y"
    if f.get("mp"):
        payload["masking_present"] = f["mp"] == "y"
    # V3 burnout-tier fields (migration 0153) — see the section above
    # kb_deep_yesno for why these are written through individually rather
    # than accumulated with lc/uc/mp above.
    if f.get("bf"):
        payload["user_burnout_framing"] = BURNOUT_FRAMING_CODE_TO_STATE.get(f["bf"])
    if f.get("cpt") is not None:
        payload["compensation_type"] = _idx_values(f["cpt"], COMPENSATION_TYPE_VALUES)
    if f.get("bc"):
        payload["body_signal_clarity"] = BODY_CLARITY_CODE_TO_STATE.get(f["bc"])
    if f.get("pd"):
        payload["predictability"] = PREDICTABILITY_CODE_TO_STATE.get(f["pd"])
    # V3 Mission 3 fields (migration 0158) — natural_regulation_response/
    # suppressed_regulation_response. sensory_channels is NOT written here:
    # it's merged in incrementally, one channel per tap, by
    # write_deep_sensory_channel() below (a plain payload["sensory_
    # channels"] = ... here would clobber previously-flagged channels
    # since supabase-py has no partial-jsonb-key update).
    if f.get("nr") and f["nr"] != "skip":
        payload["natural_regulation_response"] = NATURAL_REGULATION_CODE_TO_STATE.get(f["nr"])
    if f.get("sr") and f["sr"] != "skip":
        payload["suppressed_regulation_response"] = f["sr"] == "y"
    if f.get("rd"):
        payload["recovery_duration"] = _RD_CODE_TO_LABEL.get(f["rd"], f["rd"])
    if f.get("rf") is not None:
        payload["recovery_factors"] = _idx_list(f["rf"], RECOVERY_FACTORS)
    if f.get("ha") is not None:
        payload["helpful_actions"] = _idx_list(f["ha"], HELPFUL_ACTIONS_OPTIONS)
    if f.get("ua") is not None:
        payload["unhelpful_actions"] = _idx_list(f["ua"], UNHELPFUL_ACTIONS_OPTIONS)
    if f.get("tn"):
        payload["trigger_note"] = f["tn"]
    if f.get("nt"):
        payload["notes"] = f["nt"]
    try:
        db.table(TABLE).update(payload).eq("id", row_id).execute()
        return True, None
    except Exception as exc:
        log.error("capacity_checkins deep-check update failed: %s", exc)
        return False, str(exc)


async def write_deep_sensory_channel(db, row_id: str, channel_key: str, value: str) -> tuple[bool, str | None]:
    """Read-merge-write a single channel into the row's sensory_channels
    jsonb. supabase-py/PostgREST has no partial-jsonb-key update, so each
    per-channel tap in the follow-up loop (see the design-tradeoff comment
    above SENSORY_CHANNELS) reads the column's current value, merges in
    just this channel, and writes the whole object back — safe here
    because sensory_channels holds at most 8 keys."""
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    try:
        res = db.table(TABLE).select("sensory_channels").eq("id", row_id).limit(1).execute()
        rows = res.data or []
        current = dict((rows[0].get("sensory_channels") if rows else None) or {})
        current[channel_key] = value
        db.table(TABLE).update({"sensory_channels": current, "updated_at": _now_iso()}).eq("id", row_id).execute()
        return True, None
    except Exception as exc:
        log.error("capacity_checkins sensory_channels write failed: %s", exc)
        return False, str(exc)


async def write_evening(db, f: dict) -> tuple[bool, str | None]:
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    hf_idx = f.get("hf")
    helpful_factor = None
    if hf_idx is not None and hf_idx.isdigit() and int(hf_idx) < len(DAY_WIN_HELPED_OPTIONS):
        helpful_factor = DAY_WIN_HELPED_OPTIONS[int(hf_idx)]
    payload = {
        "checkin_type": "evening",
        "source": "telegram",
        "time_of_day": _time_of_day_label(),
        "day_trajectory": {"u": "improved", "s": "same", "d": "declined"}.get(f.get("dt")),
        "helpful_factor": helpful_factor,
        "capacity_debt": {"n": "no", "m": "maybe", "y": "yes"}.get(f.get("cd")),
    }
    try:
        db.table(TABLE).insert(payload).execute()
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat(TABLE, status="ok", detail="checkin_type=evening source=telegram")
        except Exception:
            pass
        return True, None
    except Exception as exc:
        log.error("capacity_checkins evening write failed: %s", exc)
        return False, str(exc)


# ── Summary rendering (spec §3) ─────────────────────────────────────────────

def render_summary(row: dict) -> str:
    lines = ["MY CAPACITY TODAY", ""]
    if row.get("sleep_state"):
        lines.append(f"Sleep: {SLEEP_LABEL.get(row['sleep_state'], row['sleep_state'])}")
    if row.get("capacity_state"):
        lines.append(f"Capacity: {CAPACITY_LABEL.get(row['capacity_state'], row['capacity_state'])}")
    if row.get("stimulation_state"):
        lines.append(f"Stimulation: {STIMULATION_LABEL.get(row['stimulation_state'], row['stimulation_state'])}")
    if row.get("pain_state"):
        lines.append(f"Pain: {PAIN_LABEL.get(row['pain_state'], row['pain_state'])}")
    if row.get("regulation_state"):
        lines.append(f"System: {REGULATION_LABEL.get(row['regulation_state'], row['regulation_state'])}")
    if row.get("emotional_state"):
        lines.append(f"Emotional load: {EMOTIONAL_LABEL.get(row['emotional_state'], row['emotional_state'])}")
    if row.get("executive_function"):
        lines.append(f"Executive function: {EF_LABEL.get(row['executive_function'], row['executive_function'])}")
    if row.get("compensation_load"):
        lines.append(f"Compensation: {COMPENSATION_LABEL.get(row['compensation_load'], row['compensation_load'])}")
    if row.get("social_state"):
        lines.append(f"Social capacity: {SOCIAL_LABEL.get(row['social_state'], row['social_state'])}")
    loads = row.get("active_loads") or []
    if loads:
        lines += ["", "Main loads:"] + [f"  {l}" for l in loads]
    needs = row.get("identified_needs") or []
    if needs:
        lines += ["", "What I need:"] + [f"  {n}" for n in needs]
    if row.get("selected_action"):
        lines += ["", f"Next action: {row['selected_action']}"]
    lines += ["", "Today is about management, not proving what you can tolerate."]
    return "\n".join(lines)


# ── Trend / pattern analysis (spec §7 — no causal language) ────────────────

async def fetch_recent(db, days: int) -> list[dict]:
    if not db:
        return []
    since = (datetime.now(_TZ).date() - timedelta(days=days)).isoformat()
    try:
        res = (
            db.table(TABLE)
            .select("*")
            .gte("log_date", since)
            .order("captured_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.error("capacity_checkins fetch_recent failed: %s", exc)
        return []


def render_trend_summary(rows: list[dict], label: str) -> str:
    quick = [r for r in rows if r.get("checkin_type") == "capacity"]
    evenings = [r for r in rows if r.get("checkin_type") == "evening"]
    if not quick and not evenings:
        return f"{label}\n\nNo check-ins logged in this window yet."

    zone_counts = Counter(r["capacity_state"] for r in quick if r.get("capacity_state"))
    total_zones = sum(zone_counts.values()) or 1
    load_counts = Counter(l for r in quick for l in (r.get("active_loads") or []))
    need_counts = Counter(n for r in quick for n in (r.get("identified_needs") or []))
    action_counts = Counter(r["selected_action"] for r in quick if r.get("selected_action"))
    debt_counts = Counter(e["capacity_debt"] for e in evenings if e.get("capacity_debt"))

    lines = [label, ""]
    if zone_counts:
        lines.append("Capacity:")
        for state, cd in (("green", "Green"), ("orange", "Orange"), ("red", "Red")):
            if zone_counts.get(state):
                pct = round(100 * zone_counts[state] / total_zones)
                lines.append(f"  {cd}: {pct}%")
        lines.append("")

    if load_counts:
        lines.append("Most common loads:")
        for i, (load, _) in enumerate(load_counts.most_common(3), 1):
            lines.append(f"  {i}. {load}")
        lines.append("")

    red_rows = [r for r in quick if r.get("capacity_state") == "red"]
    if red_rows:
        pre = Counter()
        for r in red_rows:
            if r.get("pain_state") in ("elevated", "high"):
                pre["elevated pain"] += 1
            if r.get("stimulation_state") == "high":
                pre["high sensory load"] += 1
            if r.get("compensation_load") in ("high", "extreme"):
                pre["high compensation"] += 1
        if pre:
            top = ", ".join(k for k, _ in pre.most_common(3))
            lines.append(f"Possible pattern: red-capacity check-ins often co-occurred with {top}.")
            lines.append("")

    if need_counts:
        lines.append("What helped most (needs identified most often):")
        for i, (need, _) in enumerate(need_counts.most_common(3), 1):
            lines.append(f"  {i}. {need}")
        lines.append("")

    if action_counts:
        lines.append("Most-used actions:")
        for i, (act, _) in enumerate(action_counts.most_common(3), 1):
            lines.append(f"  {i}. {act}")
        lines.append("")

    if debt_counts:
        total_evenings = len(evenings)
        yes_maybe = debt_counts.get("yes", 0) + debt_counts.get("maybe", 0)
        lines.append(f"Capacity debt: {yes_maybe} of {total_evenings} evening reflections")
        lines.append("")

    lines.append("(Patterns here are simple frequency counts, not clinical claims — worth testing, not treating as fact.)")
    return "\n".join(lines).rstrip()


def render_therapy_summary(rows: list[dict], weeks: int) -> str:
    quick = [r for r in rows if r.get("checkin_type") == "capacity"]
    evenings = [r for r in rows if r.get("checkin_type") == "evening"]
    lines = [f"THERAPY SUMMARY — LAST {weeks} WEEK{'S' if weeks != 1 else ''}", ""]

    if not quick:
        lines.append("No check-ins logged in this window yet.")
        return "\n".join(lines)

    zone_counts = Counter(r["capacity_state"] for r in quick if r.get("capacity_state"))
    total = sum(zone_counts.values()) or 1
    dominant = zone_counts.most_common(1)[0][0] if zone_counts else None
    dom_label = {"green": "green (sustainable)", "orange": "orange (stretched)", "red": "red (depleted)"}.get(dominant, "mixed")
    lines.append(f"Capacity: most check-ins were {dom_label}, with {zone_counts.get('red', 0)} red periods "
                  f"out of {total}.")
    lines.append("")

    load_counts = Counter(l for r in quick for l in (r.get("active_loads") or []))
    if load_counts:
        lines.append("Common contributors:")
        for load, _ in load_counts.most_common(4):
            lines.append(f"  - {load}")
        lines.append("")

    comp_rows = [r for r in quick if r.get("compensation_load")]
    if comp_rows:
        high_comp = sum(1 for r in comp_rows if r.get("compensation_load") in ("high", "extreme"))
        pct = round(100 * high_comp / len(comp_rows))
        lines.append(f"Compensation: high or extreme on {pct}% of check-ins.")
        lines.append("")

    high_pain = sum(1 for r in quick if r.get("pain_state") in ("elevated", "high"))
    if high_pain:
        lines.append(f"Pain: elevated or high on {high_pain} of {len(quick)} check-ins.")
        lines.append("")

    action_counts = Counter(r["selected_action"] for r in quick if r.get("selected_action"))
    if action_counts:
        lines.append("What helped:")
        for act, _ in action_counts.most_common(4):
            lines.append(f"  - {act}")
        lines.append("")

    debt_yes = sum(1 for e in evenings if e.get("capacity_debt") in ("yes", "maybe"))
    if evenings:
        lines.append(f"Capacity debt: {debt_yes} of {len(evenings)} evening reflections flagged borrowing from tomorrow.")
        lines.append("")

    lines.append("Questions to explore:")
    lines.append("  1. What early signals indicate a move from orange to red?")
    lines.append("  2. Where is masking happening that may not be necessary?")
    lines.append("  3. Which environmental changes could reduce baseline load?")

    return "\n".join(lines)
