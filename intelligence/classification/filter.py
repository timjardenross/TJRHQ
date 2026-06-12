"""
Suppression filter — determines which classified events to exclude from ranking.
All rules are deterministic. No LLM involved.

A suppressed event is persisted to Supabase with suppressed=True so that
the suppression decision is auditable. It is never silently dropped.
"""

from intelligence.models import ClassifiedEvent

# ─── Suppression rules ────────────────────────────────────────────────────────

_OPINION_SIGNALS = [
    "opinion:", "analysis:", "commentary:", "column:", "editorial:",
    "why i think", "we believe", "my view", "perspective:",
]

_GENERIC_NEWS_SIGNALS = [
    "gallery", "photos from", "watch:", "listen:", "podcast",
    "recipe", "sport", "entertainment", "celebrity", "weather forecast",
    "quiz", "how to cook", "lifestyle",
]

_LOW_SIGNAL_TITLES = [
    "untitled", "no title", "", "loading", "null",
]

_MIN_TITLE_LENGTH = 10
_MIN_OP_RELEVANCE = 0.20


def should_suppress(event: ClassifiedEvent) -> tuple[bool, str]:
    """
    Returns (True, reason) if the event should be suppressed,
    (False, "") otherwise.
    """
    title_lower = event.raw_title.lower().strip()

    # Title quality
    if len(event.raw_title.strip()) < _MIN_TITLE_LENGTH:
        return True, "title_too_short"

    if title_lower in _LOW_SIGNAL_TITLES:
        return True, "placeholder_title"

    # Opinion / commentary
    if any(sig in title_lower for sig in _OPINION_SIGNALS):
        return True, "opinion_or_commentary"

    # Generic non-operational news
    if any(sig in title_lower for sig in _GENERIC_NEWS_SIGNALS):
        return True, "generic_news"

    # Below operational relevance floor
    if event.operational_relevance < _MIN_OP_RELEVANCE:
        return True, f"low_operational_relevance_{event.operational_relevance:.2f}"

    # Media sources: apply stricter filter
    # (media sources have lower base confidence; only pass through if banking/CPS230 relevant)
    if event.source_priority >= 4:
        if event.banking_relevance == "low" and not event.cps230_relevance:
            return True, "media_source_low_relevance"

    return False, ""


def apply_filter(events: list[ClassifiedEvent]) -> list[ClassifiedEvent]:
    """
    Apply suppression rules to all events.
    Updates suppressed/suppression_reason in-place.
    Returns the full list (not filtered — callers use suppressed flag).
    """
    for event in events:
        if not event.suppressed:
            suppressed, reason = should_suppress(event)
            event.suppressed = suppressed
            event.suppression_reason = reason if suppressed else None
    return events
