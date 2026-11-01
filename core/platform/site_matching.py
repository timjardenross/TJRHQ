"""Match emergency alerts to the organisation's own sites (migration 0240).

The question this answers is "which of our sites might this alert affect?",
not "is there an alert somewhere in Australia". Two methods, never blended
silently — every match says how it was made so a reader can judge it:

  distance  the alert has a coordinate and the site is geocoded. An alert
            point is where an incident was reported, not its extent, so the
            match radius is generous (see _RADIUS_KM) and widened by the
            site's own geocode uncertainty (_QUALITY_PAD_KM): a suburb
            centroid is not a rooftop.
  text      the alert has no coordinate (BOM warnings are regional, some
            fire feeds omit one) or the site is not geocoded. The site's
            suburb, or its 4-digit postcode, appears in the alert's
            headline/location text AND the alert is in the site's state.

An alert that matches no site is NOT proof that no site is affected — a
regional BOM warning names a district, not a suburb. Callers show that gap
(see `states_without_site_match`) instead of a reassuring "none affected".

Pure functions, like alert_silences._matches: the network fetch
(`list_active_sites`) is separate so a caller fetches the register once
per run and passes it in. Mirrored client-side by
lcars-portal/src/lib/siteMatching.ts — keep the two in step (radii,
quality padding, priority order).
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heartbeat import supabase_get

# Search radius around an alert point, by severity. Wider for the tiers where
# a missed site costs more; a fire warning's footprint is far larger than its
# reported incident point.
_RADIUS_KM = {"emergency_warning": 30.0, "watch_and_act": 30.0, "advice": 15.0, "unknown": 15.0}
# Extra reach to cover how imprecise the SITE's coordinate is.
_QUALITY_PAD_KM = {"address": 0.0, "street": 1.0, "suburb": 5.0, "postcode": 8.0, "none": 0.0}
_PRIORITY_ORDER = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}
_POSTCODE_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_MIN_SUBURB_LEN = 4  # shorter names ("Ayr", "Eli") collide with ordinary words


@dataclass(frozen=True)
class SiteMatch:
    site: dict
    method: str  # "distance" | "text"
    distance_km: float | None
    reason: str


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _alert_text(alert: dict) -> str:
    return " ".join(str(alert.get(k) or "") for k in ("headline", "location"))


def _suburb_in_text(suburb: str, text: str) -> bool:
    if len(suburb) < _MIN_SUBURB_LEN:
        return False
    return re.search(rf"(?<![A-Za-z]){re.escape(suburb)}(?![A-Za-z])", text, re.IGNORECASE) is not None


def match_alert(alert: dict, sites: list[dict]) -> list[SiteMatch]:
    """Sites this one alert may affect, highest-priority then nearest first."""
    lat, lon = alert.get("latitude"), alert.get("longitude")
    radius = _RADIUS_KM.get(alert.get("severity") or "unknown", _RADIUS_KM["unknown"])
    text = _alert_text(alert)
    postcodes = set(_POSTCODE_RE.findall(text))
    matches: list[SiteMatch] = []
    for site in sites:
        slat, slon = site.get("latitude"), site.get("longitude")
        quality = site.get("geocode_quality") or "none"
        if lat is not None and lon is not None and slat is not None and slon is not None:
            dist = haversine_km(lat, lon, slat, slon)
            if dist <= radius + _QUALITY_PAD_KM.get(quality, 0.0):
                matches.append(SiteMatch(site, "distance", round(dist, 1), f"{dist:.0f} km from reported incident point"))
            continue
        if alert.get("jurisdiction") != site.get("state"):
            continue
        if site.get("postcode") in postcodes:
            matches.append(SiteMatch(site, "text", None, f"postcode {site['postcode']} named in alert"))
        elif _suburb_in_text(site.get("suburb") or "", text):
            matches.append(SiteMatch(site, "text", None, f"suburb {site['suburb']} named in alert"))
    matches.sort(key=lambda m: (_PRIORITY_ORDER.get(m.site.get("priority"), 9), m.distance_km if m.distance_km is not None else 1e9, m.site.get("name") or ""))
    return matches


def states_without_site_match(alerts: list[dict], sites: list[dict]) -> dict[str, int]:
    """Active alerts that matched NO site, grouped by jurisdiction, restricted
    to states where we actually have sites. This is the honest remainder:
    these alerts could still affect us (regional warnings name a district,
    not a suburb) so the UI must not present "no site matches" as "clear"."""
    site_states = {s.get("state") for s in sites}
    out: dict[str, int] = {}
    for alert in alerts:
        state = alert.get("jurisdiction")
        if state in site_states and not match_alert(alert, sites):
            out[state] = out.get(state, 0) + 1
    return out


def list_active_sites() -> list[dict]:
    return supabase_get(
        "alert_sites?active=eq.true&select=id,site_type,name,address,suburb,state,postcode,priority,latitude,longitude,geocode_quality"
        "&limit=2000"
    )
