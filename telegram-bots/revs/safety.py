"""Safety layer — §3.3 and Part 5/7 of REVS_Telegram_Prompt_Library.md.

⚠ PILOT-SCOPE NOTE, launch blocker: the crisis classifier below is a
deliberately high-recall keyword/phrase matcher, not an ML classifier. Per
the doc's own principle (§0.2's citation note, applied here to a much
higher-stakes surface): being wrong toward "flagged, but wasn't a crisis"
costs the user one extra gentle message; being wrong the other way costs
everything. The list is intentionally broad — false positives are the
acceptable failure mode. This still needs the review the doc's §8.3
checklist calls for ("§5.4a classification confirmed to run before §7.1
matching") before this bot talks to a real stranger.
"""

from __future__ import annotations

import re
from typing import Optional

# §5.4a — runs on ALL free text, before any other classification, before
# storage, before any scheduled send. Biased toward over-triggering.
_CRISIS_PATTERNS = [
    r"\bkill (myself|me)\b",
    r"\bkilling myself\b",
    r"\bsuicid\w*\b",
    r"\bend (it|my life|everything)\b",
    r"\bwant to die\b",
    r"\bdon'?t want to (be here|live|exist)\b",
    r"\bno reason to (live|keep going|go on)\b",
    r"\bcan'?t (go on|do this anymore|keep going)\b",
    r"\bbetter off (dead|without me)\b",
    r"\bhurt(ing)? myself\b",
    r"\bself[\s-]?harm\w*\b",
    r"\bcutting myself\b",
    r"\bnot (safe|okay) (right now|tonight)\b",
    r"\bplan(ning)? to (die|end it)\b",
    r"\bgoodbye forever\b",
    r"\bcan'?t take (it|this) anymore\b",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)


def classify_free_text(text: str) -> bool:
    """§5.4a — returns True if `text` trips the crisis classifier. Runs
    before any §7.1 copy-bank matching and before any write to storage."""
    if not text:
        return False
    return bool(_CRISIS_RE.search(text))


# §1.2b / §5.4a locale resources — emergency number first.
_LOCALE_RESOURCES = {
    "AU": (
        "If you're in immediate danger, call 000.\n"
        "Lifeline 13 11 14 · 13YARN 13 92 76"
    ),
    "UK": (
        "If you're in immediate danger, call 999.\n"
        "Samaritans 116 123"
    ),
    "US": (
        "If you're in immediate danger, call 911.\n"
        "988"
    ),
    "OTHER": (
        "If you're in immediate danger, call your local emergency number.\n"
        "findahelpline.com"
    ),
}

_CRISIS_LINE_SHORT = {
    "AU": "Lifeline (13 11 14)",
    "UK": "Samaritans (116 123)",
    "US": "988",
    "OTHER": "findahelpline.com",
}


def locale_resources(locale: Optional[str]) -> str:
    return _LOCALE_RESOURCES.get((locale or "OTHER").upper(), _LOCALE_RESOURCES["OTHER"])


def crisis_line_short(locale: Optional[str]) -> str:
    return _CRISIS_LINE_SHORT.get((locale or "OTHER").upper(), _CRISIS_LINE_SHORT["OTHER"])


# §5.7 — storage-time screening for the two fields that get replayed
# unprompted later: /tools instructions and setback warning signals.
def screen_for_storage(text: str) -> bool:
    """Returns True if `text` should be stored as non_replayable (still
    stored verbatim — never deleted or altered — just never auto-surfaced
    by §5.2 or /tools)."""
    return classify_free_text(text)


# §7.3 — words that must never appear in bot copy. Used by tests, not at
# runtime (runtime copy is all static/table-driven — this is a build-time
# guard against a future edit reintroducing one of these).
NEVER_SAY = [
    "should", "just", "simply", "easy", "quick win", "push through",
    "no excuses", "smash", "crush", "streak", "you missed", "back on track",
    "fell off", "try harder", "be braver", "make time", "prioritise yourself",
]


# --------------------------------------------------------------- PEM ---

def pem_copy(default: str, pem_variant: Optional[str], pem_flag: bool) -> Optional[str]:
    """§7.2 — exhaustive whitelist, default-suppress. Only messages on the
    whitelist get a PEM variant; everything else renders unchanged
    regardless of pem_flag. Callers pass pem_variant=None for anything not
    on the §7.2 table, and this just returns `default` — the suppression
    behaviour for messages that shouldn't render at all under PEM (e.g.
    "[Ready to nudge it]") is handled by the caller choosing not to call
    this at all, not by this function returning None for "unchanged"."""
    if pem_flag and pem_variant is not None:
        return pem_variant
    return default
