"""Secure NT — Alerts and Warnings.

No structured extraction yet, same reasoning as wa_dfes.py. Live-checked
2026-08-26: the only confirmed RSS on an NT Government emergency domain is
pfes.nt.gov.au/newsroom/rss-feeds, which is general newsroom content, not
the alerts/warnings feed itself — using it would misrepresent press
releases as emergency alerts. No feed URL discoverable for
securent.nt.gov.au/alerts-warnings via plain fetch.

Re-checked 2026-11-01: securent.nt.gov.au answers automated requests with a
Cloudflare "Just a moment..." challenge (HTTP 403) on every path tried, and
a web search found no public API, ArcGIS service, RSS or CAP feed for NT
alerts (data.nt.gov.au only carries static bushfire-risk datasets). The
challenge is a bot check — do NOT try to get around it. The real route is to
ask NT Government (PFES / Bushfires NT / Secure NT) for a sanctioned feed or
an allowlisted fetch, or the CAP-AU custodian (BoM) for NT's published
CAP-AU feeds. Until then NT fire/emergency alerts are not monitored here;
BOM weather warnings for NT (bom_nt) still are.
"""

from __future__ import annotations

import logging

from .base import CanonicalAlert

log = logging.getLogger(__name__)

NOT_YET_IMPLEMENTED = (
    "nt_securent: no public alerts feed; securent.nt.gov.au blocks automated "
    "access behind a Cloudflare challenge (checked 2026-11-01) — needs a "
    "sanctioned feed from NT Government, see module docstring"
)


SOURCE_INFO = {
    "source_key": "nt_securent",
    "jurisdiction": "NT",
    "feed_urls": [],
    "format": "none (not monitored)",
    "fixture_dir": None,
    "severity_field": "none - NT fire/emergency alerts are not monitored",
    "severity_map": None,
    "alert_type_rule": "n/a (stub returns no alerts; heartbeat is 'skipped').",
    "exclusions": [],
    "invalid_reasons": [],
    "stale_after_hours": None,
    "expected_fields": [],
    "known_gaps": [
        "NOT MONITORED: securent.nt.gov.au answers automated requests with a Cloudflare challenge (HTTP 403) and no public API/RSS/CAP feed was found. The challenge is a bot check and is deliberately NOT bypassed; the route is a sanctioned feed or allowlisted fetch from NT Government (PFES / Bushfires NT / Secure NT) or BoM's CAP-AU.",
        "BOM weather warnings for NT (bom_nt) are still monitored.",
    ],
    "last_verified": "2026-11-01",
}


def fetch() -> list[CanonicalAlert]:
    return []
