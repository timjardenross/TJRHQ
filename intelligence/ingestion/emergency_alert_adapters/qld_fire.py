"""Queensland Fire Department — Bushfire Warnings feed.

Real download URL resolved live 2026-08-26 via data.qld.gov.au's resource_show
API (the dataset landing page is not the raw file):
https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json
GeoJSON FeatureCollection; properties.WarningLevel is one of Advice /
Watch and Act / Emergency Warning (confirmed live), with clean ISO 8601
timestamps already provided (ItemDateTimeLocal_ISO / PublishDateLocal_ISO /
ItemExpiryDateTimeLocal_ISO) — no date-format guessing needed here.
"""

from __future__ import annotations

import logging

from .base import (
    CanonicalAlert,
    DropLedger,
    convert_items,
    http_get_json,
    json_items,
    stable_event_key,
)

log = logging.getLogger(__name__)

_FEED_URL = "https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json"

_SEVERITY_MAP = {
    "advice": "advice",
    "watch and act": "watch_and_act",
    "emergency warning": "emergency_warning",
}


SOURCE_INFO = {
    "source_key": "qld_fire",
    "jurisdiction": "QLD",
    "feed_urls": [_FEED_URL],
    "format": "GeoJSON FeatureCollection",
    "fixture_dir": "tests/fixtures/emergency_alerts/qld_fire",
    "severity_field": "properties.WarningLevel (Advice / Watch and Act / Emergency Warning)",
    "severity_map": _SEVERITY_MAP,
    "alert_type_rule": "Always 'bushfire' (Bushfire Warnings feed).",
    "exclusions": [
        {"reason": "excluded_information", "field": "properties.WarningLevel", "match": "== 'Information' (case-insensitive)", "decided": "Captain-directed 2026-08-26"},
        {"reason": "excluded_hazard_reduction", "field": "properties.CallToAction", "match": "contains 'hazard reduction' (case-insensitive)", "decided": "Captain-directed 2026-08-26 (widened)"},
        {"reason": "excluded_superseded", "field": "event_key (area + local date)", "match": "a second warning for the same area on the same local day; the highest tier is kept", "decided": "2026-11-06, with the stable incident key"},
    ],
    "invalid_reasons": [],
    "stale_after_hours": None,
    "expected_fields": ['issued_at', 'updated_at_src'],
    "known_gaps": [
        "No per-item URL in the feed (every warning shares one dashboard page), so canonical_url is left empty and dedupe relies on (source_key, event_key) only.",
        "The feed gives every RE-ISSUE of a warning a new UniqueID and warnings carry no stable incident id (MIN_ID is only on 'Information' items). From 2026-11-06 event_key is the warning AREA plus the local date, so one fire's re-issues update one row (an escalation emails an UPDATE) instead of creating a row, and an email, each time. Two warnings for the same area on the same day are collapsed to the highest tier (counted excluded_superseded). A fire that runs past midnight local time gets one new row, and one new email, at the date change.",
        "A WarningLevel outside Advice / Watch and Act / Emergency Warning / Information is kept at severity 'unknown' and counted as unmapped_<label>.",
    ],
    "last_verified": "2026-08-26",
}


def fetch() -> list[CanonicalAlert]:
    return parse(http_get_json(_FEED_URL))


def fetch_with_ledger() -> tuple[list[CanonicalAlert], DropLedger]:
    """fetch() plus an account of every item skipped, and why (see base.DropLedger)."""
    ledger = DropLedger()
    return parse(http_get_json(_FEED_URL), ledger), ledger


def parse(data: dict, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    """Pure parse of the Bushfire Warnings GeoJSON FeatureCollection; separate
    from fetch() so it can be tested against a captured snapshot offline.
    Passing a ledger records every skipped item and makes one malformed
    feature count as invalid_unparseable_item instead of failing the parse."""
    guard = ledger is not None
    ledger = ledger if ledger is not None else DropLedger()
    alerts = convert_items(json_items(data, "features", "qld_fire", guard), lambda feature: _to_alert(feature, ledger), ledger, guard)
    return _collapse_by_incident(alerts, ledger)


_TIER_RANK = {"unknown": 0, "advice": 1, "watch_and_act": 2, "emergency_warning": 3}


def _collapse_by_incident(alerts: list[CanonicalAlert], ledger: DropLedger) -> list[CanonicalAlert]:
    """One alert per event_key. Two features can share a key (same area, same local day); the upsert is one request
    per source and a duplicated key would fail every row in it, so keep the highest tier (then the newest) and
    count the rest as excluded_superseded, which keeps items_seen == accepted + excluded + invalid."""
    best: dict[str, CanonicalAlert] = {}
    for alert in alerts:
        kept = best.get(alert.event_key)
        if kept is None:
            best[alert.event_key] = alert
            continue
        wins = (_TIER_RANK.get(alert.severity, 0), alert.issued_at or "") > (_TIER_RANK.get(kept.severity, 0), kept.issued_at or "")
        loser = kept if wins else alert
        ledger.exclude("superseded", sample=loser.headline)
        if wins:
            best[alert.event_key] = alert
    return list(best.values())


def _incident_key(p: dict) -> str:
    """Stable across re-issues of the same warning: the area plus the local calendar date of the item time."""
    area = " ".join((p.get("WarningArea") or "").lower().split())
    day = (p.get("ItemDateTimeLocal_ISO") or "")[:10]
    if not area or not day:
        return p.get("UniqueID") or str(p.get("OBJECTID"))
    return "qld:" + stable_event_key(area, day)


def _to_alert(feature: dict, ledger: DropLedger) -> CanonicalAlert | None:
    p = feature.get("properties", {}) or {}
    level = (p.get("WarningLevel") or "").strip().lower()
    ledger.observe(p.get("PublishDateLocal_ISO"))
    title = p.get("WarningTitle") or p.get("Header")

    # Captain-directed exclusion 2026-08-26: QLD's own WarningLevel has a
    # 4th real tier below the 3-tier Advice/Watch and Act/Emergency
    # Warning vocabulary — "Information" (FYI-only, no action expected).
    # Drop at the source using that real field, not a "Information -"
    # title-text guess.
    if level == "information":
        ledger.exclude("information", sample=title)
        return None

    # Captain-directed exclusion 2026-08-26, widened: Hazard Reduction
    # Burn is planned, not an emergency — same category already dropped
    # for NSW/ACT/WA. QLD's own CallToAction field (confirmed live:
    # "Avoid Smoke (Hazard Reduction Burn)") flags these Advice-level
    # smoke warnings distinctly from a real bushfire Advice.
    if "hazard reduction" in (p.get("CallToAction") or "").lower():
        ledger.exclude("hazard_reduction", sample=title)
        return None

    severity = _SEVERITY_MAP.get(level)
    if severity is None:
        ledger.unmapped(level or "blank")
        severity = "unknown"

    return CanonicalAlert(
        source_key="qld_fire",
        jurisdiction="QLD",
        headline=p.get("WarningTitle") or p.get("Header") or "—",
        event_key=_incident_key(p),
        alert_type="bushfire",
        severity=severity,
        description=p.get("WarningText"),
        location=p.get("WarningArea"),
        issued_at=p.get("ItemDateTimeLocal_ISO"),
        updated_at_src=p.get("PublishDateLocal_ISO"),
        expiry=p.get("ItemExpiryDateTimeLocal_ISO"),
        # No per-item URL in this feed — every warning shares the same
        # dashboard page, so setting it as canonical_url would collide
        # on alerts.idx_alerts_canonical_url (unique) across unrelated
        # warnings. Dedupe here relies on (source_key, event_key) only.
        canonical_url=None,
        raw_text=p.get("WarningText"),
        latitude=p.get("Latitude"),
        longitude=p.get("Longitude"),
    )
