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

# 2026-08-09 gap-closure: status-page/statuspage.io-style sources
# (cloud_technology/critical_infrastructure category — Cloudflare, GitHub,
# AWS, Telstra, TPG, etc.) mix real incidents with routine SCHEDULED
# maintenance notices in the same feed. Live-checked Cloudflare's actual
# feed: 14 of the last 15 entries were maintenance windows, not incidents
# ("SSL/TLS Certificate Management Maintenance", "EWR (Newark) on
# 2026-09-02" — one per-datacenter maintenance notice per window). Scoped
# to this category specifically, not a blanket "maintenance" keyword
# suppression — "maintenance" means something entirely different in a
# transport/infrastructure news headline.
_STATUS_PAGE_CATEGORIES = {"cloud_technology", "critical_infrastructure"}
_MAINTENANCE_SIGNALS = ["maintenance", "scheduled downtime", "planned downtime"]
# Cloudflare's per-datacenter maintenance format: "EWR (Newark) on 2026-09-02"
# — an airport-style location code + city + a bare future date, no incident
# language at all, so the keyword check above can't catch it.
_DATACENTER_MAINTENANCE_PATTERN = re.compile(
    r"^[A-Z]{2,4}\s*\([^)]+\)\s+on\s+\d{4}-\d{2}-\d{2}$"
)

# 2026-08-10 gap-closure: Captain flagged the weekly OSINT exec summary as
# "heavily dominated by Cloudflare Status reports" of narrow scope — single
# component or single region ("network performance problems in various
# global locations", "specific functionality failures within Workers and
# R2"). These are genuine (non-maintenance) incidents, so the maintenance
# rule above doesn't catch them. Statuspage.io's JSON incidents API (see
# api_adapter.py's _parse_statuspage_incidents, 2026-08-10) carries the
# feed's own real severity field — impact: none/minor/major/critical — and
# now tags it onto raw_summary as "[Impact: <level>]". This suppresses only
# none/minor; major/critical (genuinely widespread) still flows to scoring.
# Sources still on the RSS/Atom variant of the same feed (no JSON migration
# yet) never produce this tag and are unaffected — fail-open, not
# fail-closed. Live-checked against Cloudflare's real feed 2026-08-10: 40/50
# recent incidents are "minor", 8/50 "none" (exactly the blips the Captain
# named), 2/50 "major", 0 "critical".
_STATUSPAGE_IMPACT_PATTERN = re.compile(r"^\[impact:\s*(none|minor|major|critical)\]", re.IGNORECASE)
_STATUSPAGE_LOW_IMPACT = {"none", "minor"}

# General media: suppress if no direct OR signals in title
_MEDIA_OR_SIGNALS = [
    "outage", "breach", "cyber", "ransomware", "payment", "banking", "apra",
    "asic", "rba", "regulation", "compliance", "cps 230", "resilience",
    "disruption", "incident", "cloud", "aws", "azure", "google cloud",
    "npp", "swift", "clearing", "settlement", "third party", "outsourc",
    "critical infrastructure", "vulnerability", "exploit",
]

# 2026-08-22: the banking/cyber keyword allowlist above (plus the
# banking_relevance/cps230_relevance requirement below) is the right bar for
# an OSINT/resilience source, but was being applied to EVERY category
# — including the literal "media" category and every low-priority-ranked
# source regardless of category — killing 100% of wellness/thought_leadership
# items (they were never going to carry banking_relevance or
# cps230_relevance) AND every general-news "media" item that didn't happen
# to mention a bank or a CVE. That second part matters more than it looks:
# general world news IS the content the daily-digest brief exists to carry,
# not noise to be filtered out. Scope the banking-specific bar to the
# categories that are actually about banking/operational resilience;
# "media" and everything else still has to clear the generic
# _MIN_OP_RELEVANCE floor below, just not this stricter one.
_OR_SPECIFIC_MEDIA_CATEGORIES = {
    "regulatory", "cybersecurity", "banking_payments",
    "critical_infrastructure", "emergency_management", "transport",
}

_MIN_TITLE_LENGTH = 10
_MIN_OP_RELEVANCE = 0.20

# Non-AU earthquake locations that should always be filtered out
_NON_AU_EARTHQUAKE_LOCATIONS = [
    "hawaii", "alaska", "california", "montana", "idaho", "wyoming",
    "washington", "oregon", "nevada", "utah", "colorado", "new mexico",
    "mexico", "central america", "south sandwich", "sandwich islands",
    "new zealand", "fiji", "samoa", "tonga", "vanuatu", "solomon",
    "japan", "philippines", "indonesia", "chile", "peru", "argentina",
    "iceland", "greenland", "mediterranean", "turkey",
]


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

    # ── Earthquakes outside AU (not relevant to AU banking resilience) ─────────
    # Geoscience Australia's earthquake API includes global seismic data. Non-AU
    # earthquakes have zero operational relevance for banking resilience unless
    # the event has explicit banking/infrastructure keywords (undersea cable breaks,
    # data centre impacts, telecom outages). Suppress by default.
    if "earthquake" in title_lower or "seismic" in title_lower:
        # Keep AU earthquakes; suppress non-AU earthquakes unless they have operational relevance
        au_earthquake = event.geography == "AU"
        if not au_earthquake:
            # Check for operational relevance keywords (only these justify non-AU earthquakes)
            has_op_keywords = any(kw in title_lower for kw in [
                "banking", "critical infrastructure", "undersea cable", "submarine cable",
                "telecommunications", "telecom", "power grid", "financial", "stock exchange",
                "payment system", "data centre", "data center", "infrastructure", "cable break"
            ])
            if not has_op_keywords:
                return True, "non_au_earthquake_suppressed"

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

    # ── Status-page scheduled maintenance noise ────────────────────────────────
    if event.source_category in _STATUS_PAGE_CATEGORIES:
        if any(sig in title_lower for sig in _MAINTENANCE_SIGNALS):
            return True, "status_page_scheduled_maintenance"
        if _DATACENTER_MAINTENANCE_PATTERN.match(title):
            return True, "status_page_datacenter_maintenance_window"

    # ── Status-page real impact/severity field (non-maintenance incidents) ────
    if event.raw_summary:
        m = _STATUSPAGE_IMPACT_PATTERN.match(event.raw_summary)
        if m and m.group(1).lower() in _STATUSPAGE_LOW_IMPACT:
            return True, f"status_page_low_impact_{m.group(1).lower()}"

    # ── OSINT-category sources: suppress if no direct OR signal in title ──────
    # Only applies to categories that are actually OSINT/resilience-specific
    # (see _OR_SPECIFIC_MEDIA_CATEGORIES above, 2026-08-22). General "media"
    # (mainstream news) and every non-OSINT category now fall through to the
    # generic _MIN_OP_RELEVANCE floor instead — they're the world-news
    # content the daily digest is meant to carry, not noise.
    if event.source_category in _OR_SPECIFIC_MEDIA_CATEGORIES and event.source_priority >= 4:
        if not any(sig in title_lower for sig in _MEDIA_OR_SIGNALS):
            return True, "media_no_or_signal"
        # Fleet Engineering Review 2026-08-11: a title-level keyword match
        # alone was letting any media item through once one OR-signal word
        # appeared, even generic mentions with no real structured relevance
        # behind them — this check never looked at banking_relevance/
        # cps230_relevance at all. Media items get a higher bar than the
        # generic operational_relevance floor below: require the pipeline's
        # own structured relevance classification (banking_relevance=="high"
        # or cps230_relevance is True), not just a keyword appearing in the
        # headline.
        if event.banking_relevance != "high" and not event.cps230_relevance:
            return True, "media_source_low_relevance"

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
