"""SA Country Fire Service — Fire Incident Information (CAP-AU) feed.

https://data.eso.sa.gov.au/prod/cfs/criimson/alertsa-fire.xml — confirmed
live 2026-08-26: an Atom feed whose each <entry><content> embeds one CAP
1.2 (CAP-AU profile) <alert> block. Despite the feed's "warnings" URL, it
carries every incident level SA CFS tracks, not only Advice+ — the CAP
<severity> element itself is frequently literally "Unknown"; the real
alert-level signal is the <parameter valueName="WarningLevel"> entry
(values observed live: "incident", plus SA's advice/watch and
act/emergency warning vocabulary per CAP-AU convention), used here in
preference to <severity>.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from .base import CanonicalAlert, http_get

log = logging.getLogger(__name__)

_FEED_URL = "https://data.eso.sa.gov.au/prod/cfs/criimson/alertsa-fire.xml"

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

_SEVERITY_MAP = {
    "advice": "advice",
    "watch and act": "watch_and_act",
    "emergency warning": "emergency_warning",
}


def _cap_text(alert_el, tag: str) -> str | None:
    info = alert_el.find(f"{_CAP_NS}info")
    if info is None:
        return None
    el = info.find(f"{_CAP_NS}{tag}")
    return el.text.strip() if el is not None and el.text else None


def _cap_parameter(alert_el, name: str) -> str | None:
    info = alert_el.find(f"{_CAP_NS}info")
    if info is None:
        return None
    for param in info.findall(f"{_CAP_NS}parameter"):
        value_name = param.find(f"{_CAP_NS}valueName")
        value = param.find(f"{_CAP_NS}value")
        if value_name is not None and value_name.text == name and value is not None:
            return (value.text or "").strip() or None
    return None


def fetch() -> list[CanonicalAlert]:
    raw = http_get(_FEED_URL)
    root = ET.fromstring(raw)
    out: list[CanonicalAlert] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        content = entry.find(f"{_ATOM_NS}content")
        if content is None:
            continue
        alert_el = content.find(f"{_CAP_NS}alert")
        if alert_el is None:
            continue

        identifier_el = alert_el.find(f"{_CAP_NS}identifier")
        identifier = identifier_el.text.strip() if identifier_el is not None and identifier_el.text else None
        headline = _cap_text(alert_el, "headline") or _cap_text(alert_el, "event") or "—"
        warning_level = (_cap_parameter(alert_el, "WarningLevel") or "").strip().lower()

        # Captain-directed exclusion 2026-08-26: this feed carries non-fire
        # CAP categories too (confirmed live: <category>CBRNE</category>
        # <event>Hazardous Materials</event>) — drop using the real CAP
        # category/event fields, not a headline-text guess.
        cap_category = (_cap_text(alert_el, "category") or "").strip().lower()
        cap_event = (_cap_text(alert_el, "event") or "").strip().lower()
        # Widened 2026-08-26: HAYBOROUGH slipped through — its CAP
        # category/event were "Transport"/"Oil Spill" (not CBRNE), but SA's
        # own CAP <headline> field (the same one used for `headline` above)
        # already reads "HAYBOROUGH : Hazardous Materials" — SA's own
        # display categorisation, not a title guess we invented.
        if cap_category == "cbrne" or "hazardous materials" in cap_event or "hazardous materials" in headline.lower():
            continue

        # Captain-flagged 2026-08-26: this feed keeps closed incidents in
        # place with <parameter valueName="Status"> flipped to COMPLETE
        # rather than dropping them — the orchestrator's default
        # absence-based expiry never sees that, so it's read here from the
        # feed's own structured Status parameter (not the free-text
        # description) and passed through as `closed`.
        incident_status = (_cap_parameter(alert_el, "Status") or "").strip().upper()
        closed = incident_status == "COMPLETE" if incident_status else None

        area_el = alert_el.find(f"{_CAP_NS}info/{_CAP_NS}area/{_CAP_NS}areaDesc")
        location = area_el.text.strip() if area_el is not None and area_el.text else _cap_parameter(alert_el, "Location")

        circle_el = alert_el.find(f"{_CAP_NS}info/{_CAP_NS}area/{_CAP_NS}circle")
        lat = lon = None
        if circle_el is not None and circle_el.text:
            coords = circle_el.text.split()[0].split(",")
            if len(coords) == 2:
                try:
                    lat, lon = float(coords[0]), float(coords[1])
                except ValueError:
                    pass

        out.append(CanonicalAlert(
            source_key="sa_cfs",
            jurisdiction="SA",
            headline=headline,
            event_key=identifier or headline,
            alert_type="bushfire",
            severity=_SEVERITY_MAP.get(warning_level, "unknown"),
            description=_cap_text(alert_el, "description"),
            location=location,
            issued_at=_cap_text(alert_el, "effective") or _cap_text(alert_el, "sent"),
            updated_at_src=_cap_text(alert_el, "sent"),
            expiry=_cap_text(alert_el, "expires"),
            # <web> in this feed is the CFS/MFS public-warnings landing page,
            # identical across every incident — not a real per-item URL (same
            # collision risk as qld_fire.py's dashboard link). Omit; dedupe
            # relies on (source_key, event_key) via the CAP identifier.
            canonical_url=None,
            raw_text=_cap_text(alert_el, "description"),
            closed=closed,
            latitude=lat,
            longitude=lon,
        ))
    return out
