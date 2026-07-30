"""Human Systems — Evidence & Safety Layer (HSF-001 §3, §5, §6).

This module is the safety floor of the Human Systems Framework. Every Captain-
facing output (command reply, proactive push, dashboard recommendation) should
pass through it.

Responsibilities:
  - Detect red-flag signals in free text and produce calm escalation language.
  - Enforce the doctrine's language rules (catch banned diagnostic / absolutist
    phrasing before it reaches the Captain).
  - Frame recommendations as evidence-informed, non-diagnostic, reversible.

Nothing here diagnoses. Escalation always points to a real professional and
never interprets what a signal "is".
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ── Red-flag escalation (doctrine §3) ─────────────────────────────────────────

@dataclass(frozen=True)
class RedFlag:
    category: str
    # regex patterns (case-insensitive) that may indicate this red flag
    patterns: tuple[str, ...]
    # calm, non-diagnostic escalation directing to professional support
    escalation: str
    # urgent flags are surfaced first and trigger the emergency banner tone
    urgent: bool = False


# Ordered by severity. Mental-health crisis and cardiac/respiratory are urgent.
RED_FLAGS: tuple[RedFlag, ...] = (
    RedFlag(
        category="mental_health_crisis",
        patterns=(
            r"\bsuicid", r"\bkill myself\b", r"\bend (my|it all|my life)\b",
            r"\bself[- ]?harm", r"\bharm myself\b", r"\bwant to die\b",
            r"\bcan'?t keep (myself|me) safe\b", r"\bno reason to (live|go on)\b",
        ),
        escalation=(
            "This is the priority over everything else. Please reach out now — "
            "call 999, the Samaritans on 116 123, or a crisis line. You do not "
            "have to manage this alone."
        ),
        urgent=True,
    ),
    RedFlag(
        category="cardiac_respiratory",
        patterns=(
            r"\bchest pain\b", r"\bchest tight", r"\bcan'?t breathe\b",
            r"\bshort(ness)? of breath\b", r"\bstruggling to breathe\b",
            r"\bheart (racing|pounding) and\b",
        ),
        escalation=(
            "Chest pain or breathing difficulty should be treated as an "
            "emergency. Please call 999 / emergency services now rather than "
            "waiting."
        ),
        urgent=True,
    ),
    RedFlag(
        category="neurological",
        patterns=(
            r"\bnew (numbness|weakness|tingling)\b", r"\bbladder (control|incontinen)",
            r"\bbowel (control|incontinen)", r"\bsaddle (numbness|anaesthesia)\b",
            r"\bcan'?t feel my (legs|feet)\b", r"\bsudden weakness\b",
            r"\bloss of (sensation|feeling)\b",
        ),
        escalation=(
            "New or worsening neurological symptoms warrant urgent medical "
            "assessment. Please contact your GP today, or A&E / 999 if this is "
            "rapidly worsening or involves loss of bladder or bowel control."
        ),
        urgent=True,
    ),
    RedFlag(
        category="infection",
        patterns=(
            r"\bfever\b", r"\bhigh temperature\b", r"\bshiver", r"\bsweats and\b",
            r"\binfection\b", r"\bfeverish\b",
        ),
        escalation=(
            "Signs of fever or infection are worth checking the same day. "
            "Please contact your GP or NHS 111."
        ),
    ),
    RedFlag(
        category="wound",
        patterns=(
            r"\bwound (open|opening|red|leaking|discharg|infect)",
            r"\b(surgical|scar) site (red|hot|swollen|leaking|discharg)",
            r"\bspreading redness\b", r"\bpus\b",
        ),
        escalation=(
            "A significant change to a surgical wound or site is worth prompt "
            "review. Please contact your GP or surgical team."
        ),
    ),
    RedFlag(
        category="severe_unexplained_pain",
        patterns=(
            r"\bworst pain (ever|of my life)\b", r"\bsudden severe pain\b",
            r"\bunexplained (severe |)pain\b", r"\bpain (unlike|not like) (the |my )?usual\b",
        ),
        escalation=(
            "Severe, sudden, or unfamiliar pain is worth same-day medical "
            "advice. Please contact your GP or NHS 111."
        ),
    ),
    RedFlag(
        category="medication",
        patterns=(
            r"\b(side effect|reaction) (from|to) (my |the )?(meds|medication|tablets)\b",
            r"\bdouble (dose|dosed)\b", r"\bmissed (several|multiple) doses\b",
            r"\bmedication (interaction|interact)", r"\boverdose",
        ),
        escalation=(
            "For anything about medication — doses, side effects, or "
            "interactions — please speak to a pharmacist or GP. Avoid adjusting "
            "medication on system advice alone."
        ),
    ),
)


@dataclass(frozen=True)
class RedFlagHit:
    category: str
    escalation: str
    urgent: bool


def scan_red_flags(text: str | None) -> list[RedFlagHit]:
    """Return red-flag hits found in free text, urgent first.

    Pure and side-effect free. Empty / None text yields no hits.
    """
    if not text:
        return []
    lowered = text.lower()
    hits: list[RedFlagHit] = []
    for flag in RED_FLAGS:
        for pattern in flag.patterns:
            if re.search(pattern, lowered):
                hits.append(
                    RedFlagHit(
                        category=flag.category,
                        escalation=flag.escalation,
                        urgent=flag.urgent,
                    )
                )
                break  # one hit per category is enough
    # urgent first, preserve declaration order otherwise
    hits.sort(key=lambda h: (not h.urgent))
    return hits


def escalation_banner(hits: list[RedFlagHit]) -> str | None:
    """Render a calm, non-diagnostic escalation banner for any hits.

    Returns None when there are no hits.
    """
    if not hits:
        return None
    urgent = any(h.urgent for h in hits)
    header = (
        ":rotating_light: *Please seek professional support*"
        if urgent
        else ":warning: *Worth checking with a professional*"
    )
    lines = [header, ""]
    seen: set[str] = set()
    for hit in hits:
        if hit.category in seen:
            continue
        seen.add(hit.category)
        lines.append(f"• {hit.escalation}")
    lines += [
        "",
        "_This is a prompt to involve a real clinician — not a diagnosis. "
        "You remain the decision-maker._",
    ]
    return "\n".join(lines)


# ── Language rules (doctrine §5) ──────────────────────────────────────────────

# Diagnostic / absolutist / shaming phrasing that must never reach the Captain.
BANNED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\byou have (a |an |)\b(?!to\b)", "diagnostic 'you have…'"),
    (r"\bthis proves\b", "certainty 'this proves'"),
    (r"\bdiagnosis is\b", "diagnostic 'diagnosis is'"),
    (r"\byou must\b", "absolutist 'you must'"),
    (r"\byou need to\b", "absolutist 'you need to'"),
    (r"\bwill cure\b", "treatment claim 'will cure'"),
    (r"\bwill fix you\b", "treatment claim 'will fix you'"),
    (r"\bbelow target\b", "shaming 'below target'"),
    (r"\bstreak broken\b", "shaming 'streak broken'"),
    (r"\bfailed to meet\b", "shaming 'failed to meet'"),
    (r"\byou should have\b", "shaming 'you should have'"),
)


def check_language(text: str | None) -> list[str]:
    """Return descriptions of any banned-phrase violations in text.

    Used by tests and as a self-check guard on generated copy. Empty list means
    the text is compliant with the doctrine's language rules.
    """
    if not text:
        return []
    lowered = text.lower()
    violations: list[str] = []
    for pattern, label in BANNED_PATTERNS:
        if re.search(pattern, lowered):
            violations.append(label)
    return violations


# ── Evidence framing (doctrine §4) ────────────────────────────────────────────

SAFETY_FOOTER = (
    "_Evidence-informed and non-diagnostic. Practical and reversible where "
    "possible. You remain the decision-maker, and clinicians remain the right "
    "call for anything medical._"
)

# Output classes the framework labels its proactive intelligence with.
OUTPUT_CLASSES = ("information", "trend", "risk_signal", "action")

_CLASS_LABEL = {
    "information": "ℹ️ Information",
    "trend": "📈 Trend",
    "risk_signal": "⚠️ Risk signal",
    "action": "✅ Action",
}


def label_output_class(output_class: str) -> str:
    """Return a human label for one of the four doctrine output classes."""
    return _CLASS_LABEL.get(output_class, output_class)


def frame(text: str, *, with_footer: bool = True) -> str:
    """Attach the evidence/safety footer to a Captain-facing message body."""
    if with_footer:
        return f"{text}\n\n{SAFETY_FOOTER}"
    return text
