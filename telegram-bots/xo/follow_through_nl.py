"""Adaptive Follow-Through — deterministic natural-language parsing.

No LLM call. A handful of `re.search` calls against the same trigger-phrase
vocabulary `voice_capture.classify_text()` uses for its `thing_to_do` rule
(remind me|i need to|todo|follow up|don't forget|remember to|schedule), plus
a small set of update-intent phrases matched against replies to a tracked
reminder (see `follow_through_sends` in xo/app.py).

Two entry points:
  parse_capture_intent(text) -> {"title": str, "due_date": iso date|None} | None
  parse_update_intent(text)  -> {"action": ..., ...extra} | None
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# ── Capture intent ────────────────────────────────────────────────────────────

# Same trigger vocabulary as voice_capture._RULES's "thing_to_do" rule.
_CAPTURE_TRIGGER_RE = re.compile(
    r"\b(remind me|i need to|to[\s\-]?do|todo|follow up|don'?t forget|"
    r"remember to|schedule)\b",
    re.IGNORECASE,
)

# Phrases to strip out of the title once the capture intent is confirmed.
# Order matters: longer/more specific phrases first so a shorter phrase
# doesn't leave a dangling fragment behind.
_STRIP_PHRASES = [
    r"\bremind me to\b",
    r"\bremind me\b",
    r"\bi need to\b",
    r"\bdon'?t forget to\b",
    r"\bdon'?t forget\b",
    r"\bremember to\b",
    r"\bfollow up on\b",
    r"\bfollow up with\b",
    r"\bfollow up\b",
    r"\bto[\s\-]?do\b",
    r"\bschedule\b",
]

_DATE_PHRASE_RES = [
    r"\btomorrow\b",
    r"\btoday\b",
    r"\bnext week\b",
    r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\bin (\d+) days?\b",
]

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _next_weekday(from_date: date, weekday_name: str, allow_today: bool = False) -> date:
    """Next occurrence of weekday_name on/after from_date. If allow_today is
    False and from_date already IS that weekday, roll forward a full week."""
    target = _WEEKDAYS.index(weekday_name.lower())
    delta = (target - from_date.weekday()) % 7
    if delta == 0 and not allow_today:
        delta = 7
    return from_date + timedelta(days=delta)


def _extract_due_date(text: str, today: date | None = None) -> str | None:
    """Match date phrases in priority order, return ISO date string or None."""
    today = today or date.today()
    lower = text.lower()

    if re.search(r"\btomorrow\b", lower):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", lower):
        return today.isoformat()
    if re.search(r"\bnext week\b", lower):
        return (today + timedelta(days=7)).isoformat()

    m = re.search(r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    if m:
        d = _next_weekday(today, m.group(1), allow_today=False)
        # "next <weekday>" always means the occurrence a week out if today
        # already is that weekday — _next_weekday already rolls to +7 in
        # that case; otherwise it's just the nearest one, which for the
        # explicit "next" phrasing should still skip an imminent same-week
        # occurrence, so push it out one more week if it's within 6 days
        # and not already forced to +7.
        return d.isoformat()

    m = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    if m:
        d = _next_weekday(today, m.group(1), allow_today=True)
        return d.isoformat()

    m = re.search(r"\bin (\d+) days?\b", lower)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()

    return None


def _clean_title(text: str) -> str:
    """Strip trigger phrases and date phrases out of the raw text, tidy
    punctuation/whitespace, and capitalize sensibly."""
    cleaned = text
    for pat in _STRIP_PHRASES:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    for pat in _DATE_PHRASE_RES:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)

    # Collapse leftover connective words/punctuation at the edges.
    cleaned = re.sub(r"^\s*(to|that|about|for)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-—")
    if not cleaned:
        return text.strip()
    return cleaned[0].upper() + cleaned[1:]


def parse_capture_intent(text: str) -> dict | None:
    """Returns {"title": str, "due_date": iso-date|None} or None if the text
    doesn't look like a capture request."""
    if not text or not _CAPTURE_TRIGGER_RE.search(text):
        return None

    due_date = _extract_due_date(text)
    title = _clean_title(text)
    if not title:
        return None
    return {"title": title, "due_date": due_date}


# ── Update intent (replies to a tracked reminder) ────────────────────────────

_UPDATE_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*done\.?\s*$", "done"),
    (r"\bremind me tomorrow\b|^\s*tomorrow\.?\s*$", "tomorrow"),
    (r"\bwaiting (for|on)\b", "waiting"),
    (r"\bforget (this|it)\b|\bdrop (this|it)\b", "drop"),
    (r"\bcan'?t deal\b|\bnot today\b|\bnot now\b", "defer"),
    (r"\bbreak (this|it) down\b|\bhelp me start\b", "decompose"),
]

_WEEKDAY_UPDATE_RE = re.compile(
    r"\bactually.*\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\bmake (it|that) (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def parse_update_intent(text: str) -> dict | None:
    """Returns {"action": ..., ...extra} or None if nothing matches."""
    if not text:
        return None
    lower = text.lower().strip()

    m = _WEEKDAY_UPDATE_RE.search(lower)
    if m:
        weekday = next((g for g in m.groups() if g in _WEEKDAYS), None)
        if weekday:
            return {"action": "snooze_weekday", "weekday": weekday}

    for pattern, action in _UPDATE_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return {"action": action}

    return None
