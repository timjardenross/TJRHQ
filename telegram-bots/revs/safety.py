"""Safety layer — §3.3 and Part 5/7 of REVS_Telegram_Prompt_Library.md.

⚠ PILOT-SCOPE NOTE, launch blocker: the crisis classifier below is a
deliberately high-recall keyword/phrase matcher, not an ML classifier. Per
the doc's own principle (§0.2's citation note, applied here to a much
higher-stakes surface): being wrong toward "flagged, but wasn't a crisis"
costs the user one extra gentle message; being wrong the other way costs
everything. The list is intentionally broad — false positives are the
acceptable failure mode, and that bias is itself the field's recognized
practice for this tier of detection (Crisis Text Line, Trevor Project,
and the academic literature on AI-based crisis detection all treat
recall over precision as correct here — see research summary linked from
README.md's blocker #2), not a shortcut this bot is uniquely taking.

Pattern list expanded 2026-08-14 from a best-practices research pass
(README.md blocker #2). Categories below map to that research's taxonomy.
Deliberately excluded: bare method/acquisition nouns ("pills", "rope",
"bought") — too generic to regex without context and a major
false-positive source; that disambiguation is exactly what a Layer 2
LLM-based confirmation pass would be for (recommended by the research,
not yet built — see README.md). Still a keyword/regex layer only.

⚠ This still needs the adversarial review the doc's §8.3 checklist calls
for before this bot talks to a real stranger — a wider pattern list is
not the same thing as a reviewed one.
"""

from __future__ import annotations

import re
from typing import Optional

# §5.4a — runs on ALL free text, before any other classification, before
# storage, before any scheduled send. Biased toward over-triggering.
_CRISIS_PATTERNS = [
    # --- Direct ideation ---
    r"\bkill (myself|me)\b",
    r"\bkilling myself\b",
    r"\bsuicid\w*\b",
    r"\bend (it|my life|everything)\b",
    r"\bwant(ed)? to die\b",
    r"\bwish(ed)? (i was|i'?d be|to be) dead\b",
    r"\brather be dead\b",
    r"\btake my (own )?life\b",

    # --- Indirect / euphemistic ideation ---
    r"\bdon'?t want to (be here|live|exist) anymore\b",
    r"\bno (point|reason) (in )?(living|to live|keep going|going on)\b",
    r"\bnothing (left )?to live for\b",
    r"\bcan'?t (go on|do this anymore|keep going|take (it|this) anymore)\b",
    r"\bbetter off (dead|without me)\b",
    r"\bi (give up|'?m done)\b",
    r"\bwish i(\'d| had) never been born\b",
    r"\bno way out\b",

    # --- Chronic-illness / disability-specific despair — the population
    #     this bot actually serves; the research flagged this as the
    #     single most likely gap in a generic list. ---
    r"\brather die than (keep )?liv(e|ing) like this\b",
    r"\bnot (a life )?worth living (like this|with this)\b",
    r"\b(this is )?not a life\b",
    r"\bbetter to be dead than\b",
    r"\bjust waiting to die\b",
    r"\bburden (to|on) (my )?(family|everyone|them)\b",
    r"\b(they'?d|everyone would) be better off without me\b",
    r"\bi'?m (just )?a burden\b",
    r"\bi'?m (just )?dragging (them|everyone) down\b",
    r"\bonly (going to |gonna )?get(s)? worse from here\b",
    r"\bi'?ll never (get better|recover|be normal again)\b",

    # --- Self-harm (distinct from suicidal ideation) ---
    r"\bhurt(ing)? myself\b",
    r"\bself[\s-]?harm\w*\b",
    r"\bcutting myself\b",
    r"\bwant to (cut|hurt) myself\b",
    r"\bneed to (feel pain|cut|bleed)\b",
    r"\bpunish myself\b",

    # --- Coded / euphemistic online language ---
    r"\bunalive\b",
    r"\bfinally (be free|rest|escape)\b",
    r"\b(the )?pain will (stop|be over)\b",
    r"\bit'?ll (all )?be over soon\b",

    # --- Finality / goodbye behavioural signals ---
    r"\bgoodbye forever\b",
    r"\bsaying goodbye to everyone\b",
    r"\bgetting my affairs in order\b",
    r"\blast time (we|i)('ll)?\b",

    # --- Planning language (kept to compound phrases, not bare nouns,
    #     to avoid drowning in false positives from single words) ---
    r"\bplan(ning)? to (die|end it|kill myself)\b",
    r"\bhave a plan\b.{0,20}\b(end|die|kill)\b",
    r"\bnot (safe|okay) (right now|tonight)\b",

    # --- Caregiver strain — a caregiver messaging about the patient they
    #     support can be at elevated risk themselves and easy to miss
    #     because keyword lists usually assume the patient is speaking. ---
    r"\bi can'?t keep caring for (him|her|them)\b",
    r"\bhaven'?t slept in \d+ days\b",
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
        "Lifeline 13 11 14 · lifeline.org.au\n"
        "13YARN 13 92 76 · 13yarn.org.au\n"
        "Beyond Blue 1300 22 4636 · beyondblue.org.au"
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
