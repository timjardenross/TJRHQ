"""Capacity Bot — /helpme (V02 WP04 + WP05: Intervene + Reassess).

"Something is difficult right now. Help me do something about it."
Extremely low friction (spec §6-§9): identify state -> offer ONE
intervention -> user tries it -> reassess -> learn. Never a 12-question
assessment (spec §7).

Ranking goes through intervention_engine.rank_interventions() — the same
engine /capacity Q9 (WP06) and /guide (WP08) use, per spec §4 ("do not
build three independent recommendation systems").

Cross-message state for the browsing part of the flow (which help_state,
which interventions already shown/declined, the optional triage context)
lives in context.user_data, not callback_data — same pattern this bot
already uses for the deep check-in's pending free-text note. Nothing here
is real capacity data; losing it on a bot restart mid-browse is
acceptable (spec §13's same tolerance for ephemeral reminder state).
Persistent data (the accepted event + its reassessment) always goes
through intervention_engine's DB writes.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bots.capacitybot.capacity_today import (
    CAPACITY_OPTIONS,
    CAPACITY_SHORT,
    PAIN_OPTIONS,
    PAIN_SHORT,
    STIMULATION_OPTIONS,
    STIMULATION_SHORT,
    render_question,
)

log = logging.getLogger(__name__)

# ── Entry (spec §6.1) ─────────────────────────────────────────────────────────

HELP_STATE_OPTIONS = [
    ("overwhelmed", "🌪️ Everything feels like too much"),
    ("cannot_start", "🧱 I can't get started"),
    ("flat", "🪫 I'm flat / nothing interests me"),
    ("racing", "⚡ My brain or body is racing"),
    ("sensory_overload", "🔊 Sensory overload"),
    ("pain_dominant", "🩹 Pain is taking over"),
    ("anxiety", "😰 Anxiety / stuck in my head"),
    ("understimulated", "🥱 I'm bored or understimulated"),
    ("unknown", "❓ I don't know what's wrong"),
]
HELP_STATE_SHORT = {
    "overwhelmed": "Too much", "cannot_start": "Can't start", "flat": "Flat",
    "racing": "Racing", "sensory_overload": "Sensory overload", "pain_dominant": "Pain",
    "anxiety": "Anxiety", "understimulated": "Understim.", "unknown": "Not sure",
}
HELP_STATE_LABEL = dict(HELP_STATE_OPTIONS)


def q_helpme_entry() -> str:
    return render_question("What's happening right now?", [label for _, label in HELP_STATE_OPTIONS])


def kb_helpme_entry() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"{i} · {HELP_STATE_SHORT[code]}", callback_data=f"ch|s={code}")
        for i, (code, _label) in enumerate(HELP_STATE_OPTIONS, 1)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


# ── Optional one-tap context questions (spec §8.1/§8.5/§8.9) ────────────────
# Only 3 of the 9 states get an extra clarifying tap before the engine
# offers an intervention — one that materially changes what "appropriate"
# means for that state. The other 6 go straight from state -> offer,
# matching spec §7's "identify state -> offer one intervention" pattern
# rather than turning every pathway into its own mini-assessment.

REDUCE_FIRST_OPTIONS = [
    ("noise", "🔇 Noise / sensory input"),
    ("people", "👥 People / interaction"),
    ("task", "💼 Task or work demand"),
    ("screens", "📱 Screens / information"),
    ("change", "🔄 Change / uncertainty"),
    ("unclear", "❓ I can't tell"),
]
REDUCE_FIRST_SHORT = {
    "noise": "Noise", "people": "People", "task": "Task",
    "screens": "Screens", "change": "Change", "unclear": "Can't tell",
}

SENSORY_DOMINANT_OPTIONS = [
    ("sound", "Sound"), ("light", "Light / screens"), ("touch", "Touch / clothing"),
    ("people", "People / crowding"), ("smell", "Smell"), ("multiple", "Multiple inputs"),
    ("unknown", "Unknown"),
]
SENSORY_DOMINANT_SHORT = {
    "sound": "Sound", "light": "Light", "touch": "Touch",
    "people": "People", "smell": "Smell", "multiple": "Multiple", "unknown": "Not sure",
}

# unknown-state mini-triage (spec §8.9) — 3 taps, same option tables the
# quick check-in uses, imported by app.py from capacity_today directly so
# this module doesn't duplicate them.


def q_reduce_first() -> str:
    return render_question("What feels easiest to reduce first?",
                            [label for _, label in REDUCE_FIRST_OPTIONS])


def kb_reduce_first(state: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"{i} · {REDUCE_FIRST_SHORT[code]}", callback_data=f"ch|s={state}|c={code}")
        for i, (code, _label) in enumerate(REDUCE_FIRST_OPTIONS, 1)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def q_sensory_dominant() -> str:
    return render_question("Which input is dominant?",
                            [label for _, label in SENSORY_DOMINANT_OPTIONS])


def kb_sensory_dominant(state: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"{i} · {SENSORY_DOMINANT_SHORT[code]}", callback_data=f"ch|s={state}|c={code}")
        for i, (code, _label) in enumerate(SENSORY_DOMINANT_OPTIONS, 1)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


# ── Unknown-state mini-triage (spec §8.9) — reuses capacity_today's own
# capacity/stimulation/pain option tables so the wording is identical to
# /capacity's Q1-Q3, but with a `ch|s=unknown|...` callback prefix so it
# routes back into this flow, not the quick-check-in one.

def kb_triage_capacity() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(CAPACITY_SHORT[code], callback_data=f"ch|s=unknown|cap={code}")
               for code, _label in CAPACITY_OPTIONS]
    return InlineKeyboardMarkup([buttons])


def kb_triage_stimulation(cap: str) -> InlineKeyboardMarkup:
    base = f"ch|s=unknown|cap={cap}"
    buttons = [InlineKeyboardButton(STIMULATION_SHORT[code], callback_data=f"{base}|stim={code}")
               for code, _label in STIMULATION_OPTIONS]
    return InlineKeyboardMarkup([buttons])


def kb_triage_pain(cap: str, stim: str) -> InlineKeyboardMarkup:
    base = f"ch|s=unknown|cap={cap}|stim={stim}"
    buttons = [InlineKeyboardButton(PAIN_SHORT[code], callback_data=f"{base}|pain={code}")
               for code, _label in PAIN_OPTIONS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


# ── The offer screen (spec §7-§9) ────────────────────────────────────────────

def render_offer(intervention: dict) -> str:
    lines = [intervention.get("full_description") or intervention["title"]]
    minutes = intervention.get("estimated_minutes")
    if minutes:
        lines.append(f"\n(~{minutes} min)")
    lines.append("\nWorth trying?")
    return "\n".join(lines)


def kb_offer(state: str, intervention_id: str) -> InlineKeyboardMarkup:
    base = f"chi|s={state}|iid={intervention_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I'll do that", callback_data=f"{base}|act=accept")],
        [
            InlineKeyboardButton("🔄 Something else", callback_data=f"{base}|act=skip"),
            InlineKeyboardButton("🚫 Can't do that", callback_data=f"{base}|act=skip"),
        ],
        [InlineKeyboardButton("🛑 Stop", callback_data=f"{base}|act=stop")],
    ])


def render_no_more_options() -> str:
    return (
        "That's everything that fits right now.\n\n"
        "Try /helpme again in a bit, or /capacity for a fuller check-in."
    )


def render_accepted(intervention: dict, reminder_minutes: int | None) -> str:
    lines = [f"✅ {intervention['title']}"]
    if reminder_minutes:
        lines.append(f"\nI'll check back in {reminder_minutes} minutes.")
    return "\n".join(lines)


def render_stopped() -> str:
    return "Okay — stopping here."


# ── Reassessment (spec §12) ──────────────────────────────────────────────────

OUTCOME_OPTIONS = [
    ("better", "👍 Better"), ("same", "➡️ About the same"),
    ("worse", "👎 Worse"), ("not_completed", "🚫 Didn't do it"),
]
CAPACITY_AFTER_OPTIONS = [("green", "🟢 Sustainable"), ("orange", "🟠 Stretched"), ("red", "🔴 Depleted")]
USE_AGAIN_OPTIONS = [("yes", "Yes"), ("maybe", "Maybe"), ("no", "No")]


def q_reassess_outcome() -> str:
    return render_question("Did that help?", [label for _, label in OUTCOME_OPTIONS])


def kb_reassess_outcome(event_id) -> InlineKeyboardMarkup:
    base = f"chr|ev={event_id}"
    buttons = [InlineKeyboardButton(label, callback_data=f"{base}|o={code}") for code, label in OUTCOME_OPTIONS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def q_reassess_capacity_after() -> str:
    return render_question("Where is your capacity now? (optional)",
                            [label for _, label in CAPACITY_AFTER_OPTIONS])


def kb_reassess_capacity_after(event_id, outcome: str) -> InlineKeyboardMarkup:
    base = f"chr|ev={event_id}|o={outcome}"
    buttons = [InlineKeyboardButton(label, callback_data=f"{base}|ca={code}")
               for code, label in CAPACITY_AFTER_OPTIONS]
    rows = [buttons]
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|ca=skip")])
    return InlineKeyboardMarkup(rows)


def q_reassess_use_again() -> str:
    return "Would you use this again in a similar situation? (optional)"


def kb_reassess_use_again(event_id, outcome: str, capacity_after: str) -> InlineKeyboardMarkup:
    base = f"chr|ev={event_id}|o={outcome}|ca={capacity_after}"
    buttons = [InlineKeyboardButton(label, callback_data=f"{base}|ua={code}")
               for code, label in USE_AGAIN_OPTIONS]
    rows = [buttons]
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|ua=skip")])
    return InlineKeyboardMarkup(rows)


def render_reassess_done() -> str:
    return "Logged. Thanks."


# ── Parsing (matches capacity_today.parse_cb's convention exactly) ──────────

def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result
