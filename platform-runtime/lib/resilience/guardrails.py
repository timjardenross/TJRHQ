"""Deterministic pre-checks run before any text reaches a model.

These back up — not replace — the guardrails in
``specialists/knowledge-packs/Operational-Resilience-Advisor-Knowledge.md``.
They catch the obvious cases cheaply: personal identifiers in the input, and
requests for outputs the advisor must never draft.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_TFN_RE = re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{3}\b")
_BSB_ACCOUNT_RE = re.compile(r"\b\d{3}-\d{3}\s+\d{6,10}\b")

_PROHIBITED_REQUESTS = (
    (re.compile(r"\b(draft|write|prepare)\b.{0,40}\b(response|reply|letter)\b.{0,30}\b(apra|regulator|supervisor|examiner)\b", re.IGNORECASE),
     "drafting a formal response to a regulator"),
    (re.compile(r"\b(remediation plan|action plan)\b.{0,40}\b(finding|mra|mria|supervisory)\b", re.IGNORECASE),
     "drafting a remediation plan for a supervisory finding"),
    (re.compile(r"\b(legal advice|legal opinion|is (this|it) legal)\b", re.IGNORECASE),
     "legal advice or a legal opinion"),
    (re.compile(r"\b(draft|write|state|prepare)\b.{0,30}\bofficial position\b", re.IGNORECASE),
     "stating an entity's official position"),
)


@dataclass(frozen=True)
class ScreenResult:
    allowed: bool
    reasons: tuple[str, ...] = ()


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def screen_input(text: str) -> ScreenResult:
    reasons: list[str] = []
    if _EMAIL_RE.search(text):
        reasons.append("contains an email address — remove personal identifiers")
    for m in _CARD_CANDIDATE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            reasons.append("contains what looks like a card number")
            break
    if _BSB_ACCOUNT_RE.search(text):
        reasons.append("contains what looks like a BSB and account number")
    elif _TFN_RE.search(text):
        reasons.append("contains a 9-digit identifier (possible TFN)")
    for pattern, label in _PROHIBITED_REQUESTS:
        if pattern.search(text):
            reasons.append(f"asks for {label}, which this advisor must not draft")
    return ScreenResult(allowed=not reasons, reasons=tuple(reasons))
