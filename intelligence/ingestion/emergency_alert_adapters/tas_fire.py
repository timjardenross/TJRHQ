"""TasALERT — warnings, from the Tasmanian Government's LIST map service.

Found live 2026-11-01. alert.tas.gov.au itself is a JS-rendered page with no
documented feed, but the state's own LIST ArcGIS service republishes TasALERT
warnings as a public layer ("TasAlert Warnings", layer 72 of
Public/EmergencyManagementPublic, CC-BY, same service the alert.tas.gov.au
map reads):
https://services.thelist.tas.gov.au/arcgis/rest/services/Public/EmergencyManagementPublic/MapServer/72

Per record: ALERT_TYPE / EVENT / ALERT_SUMMARY (headline) / AREA_DESCRIPTION
/ FULL_DESCRIPTION / ALERT_INSTRUCTIONS, a stable IDENTIFIER, the TasALERT
link, EFFECTIVE_FROM_DATE and EXPIRES_DATE (epoch ms), and a point geometry —
requested in WGS84 (outSR=4326) so site matching can use it.

Severity: TasALERT's own wording is mapped only where it states an AWS tier
("Emergency Warning" / "Watch and Act" / "Advice"). Anything else stays
'unknown' and is logged — never guessed. Only one record was live when this
was written (a "Smoke Alert"), so the full ALERT_TYPE vocabulary is NOT yet
confirmed; the first real Watch and Act / Emergency Warning will be the test,
and unknown_severity shows on this source's heartbeat detail until then.

Planned burns (backburn / hazard reduction) are dropped at the source, the
same Captain-directed rule as nsw_rfs.py — planned, not emergencies.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

from .base import (
    CanonicalAlert,
    DropLedger,
    FeedShapeError,
    convert_items,
    http_get_json,
    json_items,
    stable_event_key,
)

log = logging.getLogger(__name__)

_LAYER_URL = (
    "https://services.thelist.tas.gov.au/arcgis/rest/services/Public/"
    "EmergencyManagementPublic/MapServer/72/query"
    "?where=1%3D1&outFields=*&outSR=4326&f=json"
)

_SEVERITY_PHRASES = (
    ("emergency warning", "emergency_warning"),
    ("watch and act", "watch_and_act"),
    ("watch & act", "watch_and_act"),
    ("advice", "advice"),
)

SOURCE_INFO = {
    "source_key": "tas_fire",
    "jurisdiction": "TAS",
    "feed_urls": [_LAYER_URL],
    "format": "ArcGIS REST layer query (JSON, WGS84)",
    "fixture_dir": "tests/fixtures/emergency_alerts/tas_fire",
    "severity_field": "phrase in ALERT_TYPE / EVENT / ALERT_SUMMARY text",
    "severity_map": _SEVERITY_PHRASES,
    "alert_type_rule": "keyword in the same text: flood / cyclone / storm / heat -> heatwave / fire or smoke -> bushfire, else 'other'.",
    "exclusions": [
        {"reason": "excluded_expired_at_source", "field": "EXPIRES_DATE", "match": "< now", "decided": "adapter rule: already expired at the source (absence ends any prior record)"},
        {"reason": "excluded_hazard_reduction", "field": "ALERT_TYPE / EVENT / ALERT_SUMMARY / FULL_DESCRIPTION", "match": "planned burn / back-burn / fuel reduction / hazard reduction / prescribed burn", "decided": "Captain-directed (same rule as nsw_rfs); date not recorded in source"},
    ],
    "invalid_reasons": ["invalid_missing_headline"],
    "known_gaps": [
        "Only one record (a 'Smoke Alert') was live when the adapter was written, so the full ALERT_TYPE vocabulary is NOT confirmed; wording that states no AWS tier stays 'unknown' and is counted as unmapped_<ALERT_TYPE>.",
        "A layer-level error object in the response raises (heartbeat fails) rather than reading as 'no alerts'.",
    ],
    "last_verified": "2026-11-01",
}

_PLANNED_BURN_RE = re.compile(r"planned\s+(?:burn|back-?burn|fuel\s+reduction)|back-?burn|hazard\s+reduction|prescribed\s+burn", re.IGNORECASE)

_TYPE_KEYWORDS = (
    ("flood", "flood"),
    ("cyclone", "cyclone"),
    ("storm", "storm"),
    ("heat", "heatwave"),
    ("fire", "bushfire"),
    ("smoke", "bushfire"),
)


def _iso(epoch_ms: int | None) -> str | None:
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()


def _severity(text: str) -> str:
    lowered = text.lower()
    for phrase, severity in _SEVERITY_PHRASES:
        if phrase in lowered:
            return severity
    return "unknown"


def _alert_type(text: str) -> str:
    lowered = text.lower()
    return next((v for kw, v in _TYPE_KEYWORDS if kw in lowered), "other")


def parse(payload: dict, now_ms: int | None = None, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    """Pure parse of the layer's JSON response; separate from fetch() so it
    can be tested without the network. Passing a ledger records every skipped
    record and makes one malformed record count as invalid_unparseable_item
    instead of failing the parse."""
    guard = ledger is not None
    if guard and not isinstance(payload, dict):
        raise FeedShapeError("tas_fire: response is not a JSON object - unexpected feed shape, not an empty feed")
    if payload.get("error"):
        raise RuntimeError(f"TasAlert layer error: {payload['error']}")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    ledger = ledger if ledger is not None else DropLedger()
    return convert_items(json_items(payload, "features", "tas_fire", guard), lambda feature: _to_alert(feature, now_ms, ledger), ledger, guard)


def _to_alert(feature: dict, now_ms: int, ledger: DropLedger) -> CanonicalAlert | None:
    a = feature.get("attributes") or {}
    geom = feature.get("geometry") or {}
    headline = (a.get("ALERT_SUMMARY") or a.get("EVENT") or a.get("ALERT_TYPE") or "").strip()
    if not headline:
        ledger.invalid("missing_headline")
        return None

    expires = a.get("EXPIRES_DATE")
    if expires and expires < now_ms:
        ledger.exclude("expired_at_source")
        return None  # already expired at the source; absence ends any prior record

    description = (a.get("FULL_DESCRIPTION") or "").strip() or None
    label = " ".join(str(a.get(k) or "") for k in ("ALERT_TYPE", "EVENT", "ALERT_SUMMARY"))
    if _PLANNED_BURN_RE.search(f"{label} {description or ''}"):
        ledger.exclude("hazard_reduction")
        return None

    severity = _severity(label)
    if severity == "unknown":
        log.info("[tas_fire] unmapped ALERT_TYPE/EVENT %r — severity left 'unknown'", label.strip())
        ledger.unmapped(str(a.get("ALERT_TYPE") or "blank"))

    instructions = (a.get("ALERT_INSTRUCTIONS") or "").strip()
    raw = description or ""
    if instructions and instructions.lower() != "unknown":
        raw = f"{raw}\n\n{instructions}".strip()

    identifier = a.get("IDENTIFIER") or a.get("TASALERT_LINK")
    return CanonicalAlert(
        source_key="tas_fire",
        jurisdiction="TAS",
        headline=headline,
        event_key=identifier or stable_event_key("TAS", headline, a.get("AREA_DESCRIPTION") or ""),
        alert_type=_alert_type(label),
        severity=severity,
        description=description,
        location=(a.get("AREA_DESCRIPTION") or None),
        issued_at=_iso(a.get("EFFECTIVE_FROM_DATE")),
        expiry=_iso(expires),
        canonical_url=a.get("TASALERT_LINK") or None,
        raw_text=raw or None,
        latitude=geom.get("y"),
        longitude=geom.get("x"),
    )


def fetch() -> list[CanonicalAlert]:
    return parse(http_get_json(_LAYER_URL))


def fetch_with_ledger() -> tuple[list[CanonicalAlert], DropLedger]:
    """fetch() plus an account of every record skipped, and why (see base.DropLedger)."""
    ledger = DropLedger()
    return parse(http_get_json(_LAYER_URL), ledger=ledger), ledger
