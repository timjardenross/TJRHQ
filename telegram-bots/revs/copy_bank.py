"""Shared copy bank — §7 of REVS_Telegram_Prompt_Library.md. Flow-specific
message text lives next to the handler that sends it (onboarding.py,
daily.py, weekly.py, commands.py); this module holds only the pieces
reused across more than one flow, plus §7.4's default regulation
instructions.

Global copy rules (§ "Global copy rules", apply everywhere):
  - under 40 words for scheduled messages
  - every prompt answerable with one tap; free text is additive, never required
  - state before output
  - no streaks, no scores, no missed-day guilt — silence passes silently
  - "skip" is a real answer, never followed by a nudge
  - no prompt answerable by "try harder"
  - no message predicts a named user's future state — population-level only
  - every branch has a defined response
  - never use the §7.3 word list (see safety.NEVER_SAY)
"""

from __future__ import annotations

NOTED = "Noted."

# §7.1 Standard responses
STANDARD = {
    "skipped": None,  # no message
    "apologises_for_missing": "Nothing to apologise for. Missed days are usually information.",
    "good_week": "Good. Worth noticing what made it possible.",
    "bad_week": "Rough week. It's data, not a verdict.",
    "doing_it_right": "There isn't a right. This is a sequencing tool, not a judgement of you.",
    "self_critical": "You're describing depletion, not character.",
}

# §7.1 "wants to do more" — gated by stage and pem_flag, never a global row.
WANTS_MORE = {
    "expand_eligible": "What would the smallest version of that look like?",
    "not_yet_eligible": "Noted. Worth holding onto — the useful move first is getting the rhythm steady enough to grow from.",
    "pem": "Noted. With your pattern the useful move isn't a smaller version of more — it's a clearer picture of the envelope. Want the Energy & Fatigue piece on why?",
}

# §7.4 — default regulation instructions for pre-REGULATE users with no
# stored tools. NOTE (per doc): placeholders pending Tim's review against
# REG-002 — they exist so /tools is never empty, not a final content sign-off.
DEFAULT_REGULATION = {
    "somatic": "Cold water on your face and wrists. Thirty seconds.",
    "breath": "Breathe out longer than you breathe in. Four in, six out. Ten rounds.",
    "grounding": "Five things you can see. Four you can hear. Three you can touch.",
    "movement": "Stand and rock, or walk the length of the room and back. Slow.",
    "sound": "One track you know well, low volume, eyes closed.",
    "connection": "Message one person. Doesn't have to be about this.",
    "cognitive": "Name what's happening out loud: 'my system is activated.' Nothing more.",
}

APPROACH_LABELS = {
    "somatic": "Somatic",
    "breath": "Breath",
    "grounding": "Grounding",
    "movement": "Movement",
    "sound": "Sound",
    "connection": "Connection",
    "cognitive": "Cognitive",
}

STAGE_LABELS = {
    "RECOGNISE": "Recognise",
    "REGULATE": "Regulate",
    "REBUILD": "Rebuild",
    "REDESIGN": "Redesign",
}

# §5.4a — crisis language-trigger response body (locale resources injected
# by the caller via safety.locale_resources()).
def crisis_language_response(locale_resources: str) -> str:
    return (
        "That sounds really hard, and it's more than this bot should be "
        "handling.\n\n"
        f"{locale_resources}\n\n"
        "I'll stay quiet unless you want me. /tools still works."
    )


# §5.4c — 24h re-contact, one message, no demand.
def crisis_recontact(locale_resources: str) -> str:
    return (
        "Checking in, no answer needed.\n\n"
        f"{locale_resources}\n\n"
        "I'll pick the check-ins back up whenever you want — /resume."
    )


# §5.4b — non-text trigger (five consecutive depleted, or /setback twice in 14 days).
def crisis_nontext(crisis_line_short: str) -> str:
    return (
        "It's been a hard stretch.\n\n"
        "Nothing needed here. But if it's more than tiredness right now, "
        f"{crisis_line_short} is there and they're good."
    )
