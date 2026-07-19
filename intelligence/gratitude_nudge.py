"""Gratitude & Small-Change Nudges — twice-daily Telegram pushes.

Inspired by the "150 little ways to make a big change" gratitude-practice
format: one short, concrete micro-action delivered as its own message,
separate from the operational Captain's Brief. Two slots:

  - Morning nudge   — a forward-looking gratitude/intention prompt
  - Afternoon nudge — a reflective pick-me-up for the mid-afternoon lull

Each slot rotates through its own prompt bank, deterministic by day-of-year
(matches the `_pick()` pattern already used in
platform-runtime/lib/human_systems/push.py), so nothing repeats for weeks
and a restart never re-sends the same prompt out of sequence.
"""

from __future__ import annotations

from datetime import date

from core.platform.notification_service import Severity, Transport, notify

_MORNING_PROMPTS = [
    "Name one thing today that's easier because of something you did last week.",
    "Before you check your phone, name one person you're glad is in your life.",
    "Pick one small thing you'll do today purely because it'll make later-you grateful.",
    "What's one thing about your body that's working for you today, even imperfectly?",
    "Notice one comfort you'd miss if it were gone — a bed, a coffee, a quiet room.",
    "Set today's bar at 'one honest effort,' not 'a good day.' That's enough to be grateful for tonight.",
    "Think of someone who helped you and hasn't heard about it. Send them one line today.",
    "What's one skill you have now that past-you would be amazed by?",
    "Choose one task today to do slightly better than the minimum — for no one but you.",
    "Name one thing that went wrong recently that taught you something useful.",
    "What's a small routine you have that quietly makes your day better?",
    "Notice the first pleasant thing that happens today, however minor, and actually register it.",
    "Pick one relationship to invest thirty seconds of appreciation into today.",
    "What's one thing in your space right now that makes life easier?",
    "Today, do one thing you've been putting off — not because it's big, but because it's small enough to finish.",
    "Name a mistake from the past that you've clearly grown past.",
    "What's one thing you get to choose today that others don't have the option to?",
    "Notice something ordinary — a working light switch, hot water — and treat it as remarkable for ten seconds.",
    "Pick one person to assume the best about today, before they've earned it.",
    "What's one small win from yesterday you didn't give yourself credit for?",
    "Set an intention to finish today with one thing you're proud of, however small.",
    "Think of a hard season you got through. What got you through it?",
    "Name one thing about today's plan you're actually looking forward to.",
    "What's a piece of advice someone gave you that turned out to matter?",
    "Notice one thing that's better this year than last year.",
    "Pick a habit you have that your future self will thank you for.",
    "What's one small kindness you received recently that you never acknowledged?",
    "Today, let one thing be 'good enough' on purpose, and notice how that feels.",
    "Name a place that makes you feel calm, even if you can't be there right now.",
    "What's one thing you're capable of today that you couldn't do a year ago?",
]

_AFTERNOON_PROMPTS = [
    "Quick check: what's one thing that's gone right so far today?",
    "Stand up, stretch, and name one thing you're glad isn't on today's list anymore.",
    "You're over halfway. What's one small thing you can do right now that future-you will appreciate?",
    "Notice the energy dip — it's normal. What's one five-minute reset that actually helps?",
    "Name one person who'd be glad to hear from you right now. Consider a one-line message.",
    "What's one thing today that's already easier than you expected this morning?",
    "Take thirty seconds to notice something pleasant in the room you're in right now.",
    "What's the smallest possible version of 'a good rest of the day' you'd actually be happy with?",
    "Recall one thing from this morning you handled well, even if it was small.",
    "What's one thing you can let go of for the rest of today without real consequence?",
    "Notice one thing your body needs right now — water, a stretch, a breath — and give it that.",
    "What's a small comfort you could build into the next hour?",
    "Think of one thing you own that's still doing its job well, quietly, without complaint.",
    "You've made it this far today. What's one thing that made it possible?",
    "What's one thing left on today's list that's actually worth doing, versus just there?",
    "Name a moment from this week, however small, that was genuinely good.",
    "What's one thing about the rest of today you get to decide, that you haven't decided yet?",
    "Notice one sound, smell, or view around you right now that's pleasant.",
    "What's a small act of care you could offer yourself in the next ten minutes?",
    "Recall someone who believed in you before you believed in yourself.",
    "What's one thing today that didn't go to plan but turned out fine anyway?",
    "Take a breath and name one thing you're not dreading about the rest of today.",
    "What's a small tradition or ritual — coffee, a walk, a song — that reliably helps?",
    "Notice one thing that's warmer, softer, or more comfortable than it needs to be.",
    "What's one thing you did today that you'd do again tomorrow without hesitation?",
    "Think of a problem that used to feel large and now feels manageable.",
    "What's one thing about tonight you're quietly looking forward to?",
    "Name one thing today that required less effort than it used to.",
    "What's a small piece of good news, personal or otherwise, from the last few days?",
    "Notice one thing that's gone unnoticed today and give it a moment of attention now.",
]


def _pick(prompts: list[str], *, offset: int = 0) -> str:
    """Deterministic by day-of-year so restarts never desync or repeat early."""
    return prompts[(date.today().toordinal() + offset) % len(prompts)]


def generate_morning_nudge() -> str:
    return f"☀️ Morning Gratitude\n\n{_pick(_MORNING_PROMPTS)}"


def generate_afternoon_nudge() -> str:
    # Offset decorrelates the afternoon slot from the morning one so the two
    # prompts of a given day are never drawn from the same list index.
    return f"🌤 Afternoon Pick-Me-Up\n\n{_pick(_AFTERNOON_PROMPTS, offset=15)}"


def send_morning_nudge() -> bool:
    result = notify(generate_morning_nudge(), template="plain", severity=Severity.INFO, transport=Transport.TELEGRAM)
    return result.ok


def send_afternoon_nudge() -> bool:
    result = notify(generate_afternoon_nudge(), template="plain", severity=Severity.INFO, transport=Transport.TELEGRAM)
    return result.ok


__all__ = [
    "generate_morning_nudge",
    "generate_afternoon_nudge",
    "send_morning_nudge",
    "send_afternoon_nudge",
]
