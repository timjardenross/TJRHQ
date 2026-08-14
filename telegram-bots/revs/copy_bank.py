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
#
# REG-002 itself isn't in any repo I have access to (TJRHQ / USSTJROS /
# tjrmindbody_public — checked 2026-08-14), so this is still not a
# REG-002-verified sign-off. What changed 2026-08-14: a best-practices
# research pass (polyvagal-informed practice, OT sensory regulation, and
# ME-CFS/PEM-specific sources — Bateman Horne Center, RTHM, MEAction) that
# specifically checked each technique against THIS population's actual
# constraint: standard regulation advice often assumes physical capacity
# or "deep breathing" that this audience doesn't have and can worsen.
# Five of seven were confirmed as already-correct picks and left
# unchanged (somatic, grounding, sound, connection, cognitive). Two
# changed:
#   breath   -> added "gentle" — unqualified "deep/full breathing" advice
#               risks hyperventilation-pattern worsening in this
#               population (RTHM); the extended-exhale ratio itself was
#               already correct and is unchanged.
#   movement -> dropped "walk the length of the room" as a co-equal
#               option. Any walking risks a PEM crash regardless of how
#               short — this was the one instruction in the set that
#               quietly contradicted the bot's own PEM principle (never
#               suggest increasing activity). Rocking/swaying is
#               zero-exertion and does the same parasympathetic-toning
#               job (rhythmic, predictable movement) without that risk.
#
# Technique mapped per category (not shown to users — bot copy stays
# plain, no jargon):
#   somatic    -> mammalian dive reflex (facial cold-water contact —
#                 face/wrists only, not full immersion; full immersion
#                 is contraindicated for dysautonomia/POTS, common
#                 comorbidities in this population)
#   breath     -> extended-exhale paced breathing, ~4-6 breaths/min
#   grounding  -> 5-4-3-2-1 sensory grounding, trimmed to 3 senses —
#                 deliberately not the full 5-sense version, which is
#                 more cognitive load than this audience needs
#   movement   -> rhythmic/rocking movement, zero-exertion by design
#   sound      -> self-selected calming audio, no prescribed content
#   connection -> low-stakes social contact, deliberately not "talk
#                 about it" — protects against the explain-yourself
#                 burden this population reports as a real stressor
#   cognitive  -> affect labeling ("name it to tame it") rather than
#                 analysing the state
#
# Noted but not added as an 8th category (would touch APPROACH_LABELS and
# the /tools "Something else" layout — bigger change than this pass):
# humming/vocal toning (direct vagal stimulation via voice), gentle
# self-touch, and weighted/proprioceptive pressure all came up as solid
# secondary options worth having available once users personalise their
# own three tools in REGULATE.
DEFAULT_REGULATION = {
    "somatic": "Cold water on your face and wrists. Thirty seconds.",
    "breath": "Gentle exhales longer than inhales. Four in, six out. Ten times.",
    "grounding": "Five things you can see. Four you can hear. Three you can touch.",
    "movement": "Rock gently side to side, or sway. Slow. Sitting or standing.",
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
