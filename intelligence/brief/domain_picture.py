"""
Deterministic domain grouping of a brief's top events (Section 12).

Groups top_events into a small fixed domain taxonomy derived from
event_type (already assigned by intelligence/classification/classifier.py —
nothing new is inferred here). This is genuine cross-domain structure over
the domains the OSINT collector actually covers today (technical/cyber
infrastructure, regulatory, environmental/severe-weather, payments), NOT a
claim of full Technical/Health/Emergency fusion — Health OSINT and the
Emergency Alert Hub are separate pipelines not yet feeding
intelligence_events (see BRIEFS_CANONICAL_UPLIFT.md), so they are
deliberately absent here rather than silently implied.
"""

from __future__ import annotations

from typing import Optional

_RISK_ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2, "UNKNOWN": -1}

_DOMAIN_BUCKETS = {
    "technical": {"cyber", "technology_outage", "telecom_outage", "energy_disruption"},
    "regulatory": {"regulatory"},
    "environmental": {"severe_weather"},
    "payments": {"payments_disruption"},
}

_DOMAIN_LABELS = {
    "technical": "Technical",
    "regulatory": "Regulatory",
    "environmental": "Environmental",
    "payments": "Payments",
    "health": "Health",
    "emergency": "Emergency Alerts",
    "other": "Other",
}


def _bucket_for(event_type: str) -> str:
    normalised = (event_type or "").strip().lower().replace(" ", "_")
    for bucket, types in _DOMAIN_BUCKETS.items():
        if normalised in types:
            return bucket
    return "other"


def compute_domain_picture(
    top_events: list[dict],
    external_signals: Optional[list[dict]] = None,
) -> Optional[dict]:
    """
    top_events: list shaped like intelligence_briefs.top_events (title,
    event_type, risk_rating, summary, ...) — bucketed by event_type via
    _bucket_for().
    external_signals: list shaped like
    intelligence/brief/external_domains.py::ExternalDomainSignal.to_dict()
    — already-assessed Health OSINT / Emergency Alert Hub items, which
    already know their own domain (health/emergency) and are bucketed
    directly rather than through the OSINT event_type taxonomy.
    Returns {bucket_key: {"label": str, "count": int, "worst_risk": str,
    "events": [{"title", "risk_rating"}]}}, or None if there is nothing to
    group at all (nothing fabricated for an empty brief).
    """
    if not top_events and not external_signals:
        return None

    picture: dict[str, dict] = {}

    def _add(bucket: str, title: Optional[str], risk_rating: Optional[str]) -> None:
        entry = picture.setdefault(bucket, {
            "label": _DOMAIN_LABELS.get(bucket, bucket.title()),
            "count": 0, "worst_risk": "GREEN", "events": [],
        })
        entry["count"] += 1
        entry["events"].append({"title": title, "risk_rating": risk_rating})
        risk = (risk_rating or "GREEN").upper()
        if _RISK_ORDER.get(risk, 0) > _RISK_ORDER.get(entry["worst_risk"], 0):
            entry["worst_risk"] = risk

    for event in top_events or []:
        _add(_bucket_for(event.get("event_type", "")), event.get("title"), event.get("risk_rating"))

    for signal in external_signals or []:
        _add(signal.get("domain") or "other", signal.get("title"), signal.get("risk_rating"))

    return picture or None
