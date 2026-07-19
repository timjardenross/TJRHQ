"""
Suppression filter — determines which classified events to exclude from ranking.
All rules are deterministic. No LLM involved.

A suppressed event is persisted to Supabase with suppressed=True so that
the suppression decision is auditable. It is never silently dropped.
"""

import re
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

# Routine APRA/regulatory publications with no operational action required
_ROUTINE_REGULATORY_PATTERNS = [
    r"statistics for (january|february|march|april|may|june|july|august|september|october|november|december)",
    r"quarterly (statistics|data|report|update)",
    r"monthly (statistics|data|authorised deposit)",
    r"(releases|publishes) (quarterly|monthly|annual) (statistics|data)",
    r"statistical (tables|publication|release)",
]

# Speeches and remarks — only suppress if no operational risk keywords present
_SPEECH_PATTERNS = [
    r"(remarks|address|speech|keynote|opening statement) (to|at|for) the",
    r"publishes .{0,30}(remarks|speech|address|keynote)",
    r"(ceo|chair|deputy chair|member) (remarks|address|speech)",
]

# OR keywords that redeem a speech from suppression
_SPEECH_OR_KEYWORDS = [
    "operational risk", "operational resilience", "cps 230", "outsourcing",
    "service provider", "critical operations", "business continuity",
    "cyber", "third party", "technology risk", "cloud", "concentration risk",
]

# Airport/transport website CMS pages — not operational alerts
_TRANSPORT_NOISE_PATTERNS = [
    r"^(shop|dining|terminal|facilities|services|accessibility|security|parking|wifi|lounge)",
    r"(shop online|collection point|disability|accessibility hub|laneway)",
    r"^(flights|book|check.in|baggage|arrivals|departures)$",
]

# Emergency services road/address alerts — specific road pattern
_ROAD_ALERT_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9\s]{2,30}\s+(RD|ST|AVE|DR|CT|CR|HWY|FWY|PL|LANE|BLVD|TCE|GRV|CL|WAY|CRES)$"
)

# General media: suppress if no direct OR signals in title
_MEDIA_OR_SIGNALS = [
    "outage", "breach", "cyber", "ransomware", "payment", "banking", "apra",
    "asic", "rba", "regulation", "compliance", "cps 230", "resilience",
    "disruption", "incident", "cloud", "aws", "azure", "google cloud",
    "npp", "swift", "clearing", "settlement", "third party", "outsourc",
    "critical infrastructure", "vulnerability", "exploit",
]

_MIN_TITLE_LENGTH = 10
_MIN_OP_RELEVANCE = 0.20


def should_suppress(event: ClassifiedEvent) -> tuple[bool, str]:
    """
    Returns (True, reason) if the event should be suppressed,
    (False, "") otherwise.
    """
    title = event.raw_title.strip()
    title_lower = title.lower()

    # ── Title quality ──────────────────────────────────────────────────────────
    if len(title) < _MIN_TITLE_LENGTH:
        return True, "title_too_short"
    if title_lower in _LOW_SIGNAL_TITLES:
        return True, "placeholder_title"

    # ── Opinion / commentary ───────────────────────────────────────────────────
    if any(sig in title_lower for sig in _OPINION_SIGNALS):
        return True, "opinion_or_commentary"

    # ── Generic non-operational news ───────────────────────────────────────────
    if any(sig in title_lower for sig in _GENERIC_NEWS_SIGNALS):
        return True, "generic_news"

    # ── Road/address emergency alerts ──────────────────────────────────────────
    if _ROAD_ALERT_PATTERN.match(title.upper()):
        return True, "road_address_alert"

    # ── Non-AU earthquakes with no Australian operational relevance ────────────
    if "earthquake" in title_lower and event.geography != "AU":
        return True, "non_au_earthquake"

    # ── Airport/transport website CMS pages ────────────────────────────────────
    if event.event_type == "transport_disruption":
        for pat in _TRANSPORT_NOISE_PATTERNS:
            if re.search(pat, title_lower):
                return True, "transport_website_page"

    # ── Routine regulatory statistics and data publications ───────────────────
    for pat in _ROUTINE_REGULATORY_PATTERNS:
        if re.search(pat, title_lower):
            return True, "routine_statistics_publication"

    # ── Speeches and remarks — suppress unless OR-relevant ────────────────────
    is_speech = any(re.search(pat, title_lower) for pat in _SPEECH_PATTERNS)
    if is_speech:
        text = title_lower + " " + (event.raw_summary or "").lower()
        if not any(kw in text for kw in _SPEECH_OR_KEYWORDS):
            return True, "speech_no_or_relevance"

    # ── Media sources: suppress if no direct OR signal in title ───────────────
    if event.source_category == "media" or event.source_priority >= 4:
        if not any(sig in title_lower for sig in _MEDIA_OR_SIGNALS):
            return True, "media_no_or_signal"

    # ── Below operational relevance floor ─────────────────────────────────────
    if event.operational_relevance < _MIN_OP_RELEVANCE:
        return True, f"low_operational_relevance_{event.operational_relevance:.2f}"

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
