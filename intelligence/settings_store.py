"""TJR HQ Settings — Intelligence monitoring-preference overlay.

Settings Page Redesign mission §14 ("Intelligence Preference Architecture"):
the Captain's chosen monitoring priorities live in Supabase (user_settings,
migration 0196, renumbered from 0189), written by the Next.js Settings page
(lcars-portal/src/app/api/settings/route.ts). This module is the read side
for the Python ingestion pipeline — it does NOT define or duplicate the
taxonomy itself (category keys/labels/keywords stay in
config/osint_intelligence_missions.json, the one source of truth per
OSINT_MISSION_CONFIG_DESIGN.md); it only tells the relevance gates which of
those existing categories/tags the Captain currently wants monitored.

Same "never block ingestion" discipline as relevance_gate.py and
priority_domains.py: any read failure (network, missing table, malformed
row) returns None, which every caller here treats as "no filter — every
category/tag stays enabled" — a missing or unreachable settings row must
never silently suppress ALL intelligence, only narrow it when the Captain
has explicitly narrowed it.

Loaded once per process (module-level, mirroring relevance_gate.py's
_CONFIG and priority_domains.py's PRIORITY_DOMAINS) — ingestion runs as
periodic scheduled jobs (systemd timers), each a fresh process, so a
one-time load at import avoids a network round trip per event without
needing a TTL/cache invalidation scheme. A Settings change takes effect on
the next ingestion run, not mid-run — acceptable for a monitoring-interest
preference, unlike e.g. a safety bypass.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from intelligence.config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


def _load_enabled_sets() -> Optional[dict]:
    """Returns {"technical_categories": frozenset|None, "health_tags": frozenset|None}
    or None entirely on failure. An empty list in the stored settings means
    "every category/tag enabled" (Settings' own default) — represented here
    as None so callers can use `enabled is None or key in enabled` uniformly.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/user_settings?id=eq.hq&select=data"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        logger.warning("settings_store: user_settings read failed, no filter applied: %s", exc)
        return None

    if not rows:
        return None

    data = rows[0].get("data") or {}
    intelligence = data.get("intelligence") or {}

    technical_list = (intelligence.get("technical") or {}).get("enabledCategories") or []
    health_list = (intelligence.get("health") or {}).get("enabledTags") or []

    return {
        "technical_categories": frozenset(technical_list) if technical_list else None,
        "health_tags": frozenset(health_list) if health_list else None,
    }


_ENABLED = _load_enabled_sets()


def enabled_technical_categories() -> Optional[frozenset[str]]:
    """None means "no filter" (every priority_categories key stays eligible)."""
    return _ENABLED["technical_categories"] if _ENABLED else None


def enabled_health_tags() -> Optional[frozenset[str]]:
    """None means "no filter" (every domain_tiers tag stays eligible)."""
    return _ENABLED["health_tags"] if _ENABLED else None
