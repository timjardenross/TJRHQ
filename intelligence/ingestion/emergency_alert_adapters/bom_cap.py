"""BoM CAP-AU enrichment of the bom_* alerts (via the WMO alert hub).

https://severeweather.wmo.int/v2/cap-alerts/au-bom-en/rss.xml is the WMO's mirror of the Bureau of
Meteorology's CAP-AU alert stream: an RSS index (500 items, ~8 days) whose items link to one CAP 1.2
message each. Measured 2026-11-06: 120/120 sampled messages validate against the OASIS CAP 1.2 XSD and
carry the CAP-AU profile markers; there are no polygons (geography is BoM area codes only), and the
index is a STREAM of every issue/update/cancel, not a list of what is currently active.

This is an enrichment, not a source. The BoM state RSS feeds (bom_warnings.py) stay the source of truth
for which alerts exist; this copies four CAP fields (event, urgency, certainty, severity) onto the alerts
that bom_warnings already produces. BoM's CAP severity is a different scale from our Advice / Watch and
Act / Emergency Warning tier and is never used for it.

The join is the hard part. The state RSS items carry no product code (the bulletin pages don't either),
so an alert is matched to the newest CAP message by:
  1. warning TYPE (thunderstorm, flood, fire weather, ...), and
  2. the RSS item's location words all appearing in the CAP headline, or, failing that,
     exactly one CAP message of that type sent within 90 s of the RSS pubDate whose BoM product code
     belongs to the same state.
Anything ambiguous or unmatched is left WITHOUT CAP fields; a wrong enrichment is worse than none.
Measured 2026-11-06 against the live feeds: 18 of 24 non-marine items matched, none wrongly (the rest were
older QLD flood warnings outside the index window). Marine wind summaries have no CAP equivalent.

Best effort and never raises: if the WMO feed is down, changed shape, or the flag is off, alerts keep
their RSS-only shape. Personal-use only (the Captain's call, 2026-11-06): BoM's RSS terms limit reuse.
Set EMERGENCY_ALERTS_BOM_CAP=0 to switch it off.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import defusedxml.ElementTree as ET  # nosec B314 - defused parser, safe against XXE/entity-expansion on external feed XML

from .base import CanonicalAlert, http_get

log = logging.getLogger(__name__)

_INDEX_URL = "https://severeweather.wmo.int/v2/cap-alerts/au-bom-en/rss.xml"
_CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
_GUID_RE = re.compile(r"^AusBoM-(ID[A-Z]\d{5})-(.+)$")
_INDEX_TTL_S = 120  # one WMO index fetch is shared by all eight state adapters in a run
_TIME_WINDOW_S = 90

# BoM product-code third letter -> the jurisdictions whose RSS may list that product.
_CODE_STATES = {"D": {"NT"}, "N": {"NSW", "ACT"}, "Q": {"QLD"}, "S": {"SA"}, "T": {"TAS"}, "V": {"VIC"}, "W": {"WA"}}

# Order matters: first keyword that appears wins. 'thunderstorm' before 'severe weather', etc.
_TYPES = (
    ("thunderstorm", "thunderstorm"), ("fire weather", "fire_weather"), ("surf", "surf"), ("heatwave", "heatwave"),
    ("sheep graziers", "sheep"), ("bushwalkers", "bushwalkers"), ("bush walkers", "bushwalkers"),
    ("road weather", "road"), ("flood", "flood"), ("severe weather", "severe_weather"), ("wind", "wind"),
)
_STOP = {"the", "of", "and", "for", "to", "at", "river", "creek", "warning", "warnings", "forecast", "districts", "district", "fire", "parts", "in"}


@dataclass(frozen=True)
class CapRef:
    code: str
    sent: datetime
    title: str
    link: str
    type: str | None
    location: frozenset[str]


_index_cache: tuple[float, list[CapRef]] | None = None
_message_cache: dict[str, dict[str, str | None]] = {}


def enabled() -> bool:
    return os.environ.get("EMERGENCY_ALERTS_BOM_CAP", "").strip().lower() not in {"0", "false", "off", "no"}


def _type_of(text: str) -> str | None:
    lowered = text.lower()
    return next((name for keyword, name in _TYPES if keyword in lowered), None)


def _location_words(title: str) -> frozenset[str]:
    flat = re.sub(r"\s+", " ", title).strip()
    flat = re.sub(r"^\d{2}/\d{2}:\d{2}\s+\w+\s+", "", flat)  # BoM RSS "DD/HH:MM TZ " prefix
    match = re.search(r" for (.*)$", flat)
    location = match.group(1) if match else flat
    location = re.sub(r"\(([A-Za-z]{2,3})\)", r" \1 ", location)  # "(QLD)" -> a word
    return frozenset(w for w in re.findall(r"[a-z]+", location.lower()) if w not in _STOP and len(w) > 2)


def parse_index(raw: bytes) -> list[CapRef]:
    """WMO RSS index -> one CapRef per item that has a BoM product code and a valid sent time."""
    refs: list[CapRef] = []
    for item in ET.fromstring(raw).findall(".//item"):
        guid = (item.findtext("guid") or "").strip()
        link = (item.findtext("link") or "").strip()
        match = _GUID_RE.match(guid)
        if not (match and link):
            continue
        try:
            sent = datetime.fromisoformat(match.group(2))
        except ValueError:
            continue
        title = re.sub(r"\s+", " ", item.findtext("title") or "").strip()
        refs.append(CapRef(match.group(1), sent, title, link, _type_of(title), _location_words(title)))
    return refs


def parse_message(raw: bytes) -> dict[str, str | None]:
    """One CAP message -> {cap_event, cap_urgency, cap_certainty, cap_severity}. Raises on a non-CAP document."""
    alert = ET.fromstring(raw)
    info = alert.find(_CAP + "info")
    if alert.tag != _CAP + "alert" or info is None:
        raise ValueError("not a CAP alert with an <info> block")

    def text(tag: str) -> str | None:
        value = (info.findtext(_CAP + tag) or "").strip()
        return value or None

    return {"cap_event": text("event"), "cap_urgency": text("urgency"), "cap_certainty": text("certainty"), "cap_severity": text("severity")}


def match(headline: str, jurisdiction: str, pub: datetime | None, refs: list[CapRef]) -> CapRef | None:
    """The newest CAP message for this RSS item, or None when there is no single unambiguous answer."""
    warning_type = _type_of(headline)
    if warning_type is None:
        return None
    words = _location_words(headline)
    candidates = [r for r in refs if r.type == warning_type and words and words <= r.location]
    if pub is not None:
        candidates = [r for r in candidates if r.sent <= pub + timedelta(minutes=3)]
    if not candidates and pub is not None:
        candidates = [
            r for r in refs
            if r.type == warning_type and abs((r.sent - pub).total_seconds()) <= _TIME_WINDOW_S and jurisdiction in _CODE_STATES.get(r.code[2], set())
        ]
    if not candidates or len({r.code for r in candidates}) > 1:
        return None
    return max(candidates, key=lambda r: r.sent)


def _index() -> list[CapRef]:
    global _index_cache
    now = time.monotonic()
    if _index_cache is None or now - _index_cache[0] > _INDEX_TTL_S:
        _index_cache = (now, parse_index(http_get(_INDEX_URL)))
    return _index_cache[1]


def _message(ref: CapRef) -> dict[str, str | None]:
    if ref.link not in _message_cache:
        _message_cache[ref.link] = parse_message(http_get(ref.link))
    return _message_cache[ref.link]


def enrich(alerts: list[CanonicalAlert], jurisdiction: str, index_raw: bytes | None = None) -> int:
    """Copy CAP fields onto matching alerts in place; returns how many were enriched. Never raises.

    index_raw=None fetches the live WMO index (cached 2 min across states)."""
    if not alerts or not enabled():
        return 0
    try:
        refs = parse_index(index_raw) if index_raw is not None else _index()
    except Exception as exc:  # noqa: BLE001 - CAP is an optional enrichment; an outage must never cost the primary BoM RSS alerts
        log.warning("[bom_cap] WMO CAP index unavailable (%s alerts kept without CAP fields): %s", jurisdiction, exc)
        return 0
    enriched = 0
    for alert in alerts:
        try:
            pub = datetime.fromisoformat(alert.updated_at_src) if alert.updated_at_src else None
            ref = match(alert.headline, jurisdiction, pub, refs)
            if ref is None:
                continue
            for name, value in _message(ref).items():
                if value:
                    setattr(alert, name, value)
            enriched += 1
        except Exception as exc:  # noqa: BLE001 - one unreadable CAP message must not stop the rest
            log.warning("[bom_cap] could not enrich %r: %s", alert.headline[:60], exc)
    log.info("[bom_cap] %s: %d of %d alerts enriched with CAP fields", jurisdiction, enriched, len(alerts))
    return enriched
