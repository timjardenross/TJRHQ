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

from .base import CanonicalAlert, DropLedger, convert_items, http_get_json

log = logging.getLogger(__name__)

_FEED_URL = "https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json"

_SEVERITY_MAP = {
    "advice": "advice",
    "watch and act": "watch_and_act",
    "emergency warning": "emergency_warning",
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
    return convert_items(data.get("features", []), lambda feature: _to_alert(feature, ledger), ledger, guard)


def _to_alert(feature: dict, ledger: DropLedger) -> CanonicalAlert | None:
    p = feature.get("properties", {}) or {}
    level = (p.get("WarningLevel") or "").strip().lower()

    # Captain-directed exclusion 2026-08-26: QLD's own WarningLevel has a
    # 4th real tier below the 3-tier Advice/Watch and Act/Emergency
    # Warning vocabulary — "Information" (FYI-only, no action expected).
    # Drop at the source using that real field, not a "Information -"
    # title-text guess.
    if level == "information":
        ledger.exclude("information")
        return None

    # Captain-directed exclusion 2026-08-26, widened: Hazard Reduction
    # Burn is planned, not an emergency — same category already dropped
    # for NSW/ACT/WA. QLD's own CallToAction field (confirmed live:
    # "Avoid Smoke (Hazard Reduction Burn)") flags these Advice-level
    # smoke warnings distinctly from a real bushfire Advice.
    if "hazard reduction" in (p.get("CallToAction") or "").lower():
        ledger.exclude("hazard_reduction")
        return None

    severity = _SEVERITY_MAP.get(level)
    if severity is None:
        ledger.unmapped(level or "blank")
        severity = "unknown"

    return CanonicalAlert(
        source_key="qld_fire",
        jurisdiction="QLD",
        headline=p.get("WarningTitle") or p.get("Header") or "—",
        event_key=p.get("UniqueID") or str(p.get("OBJECTID")),
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
