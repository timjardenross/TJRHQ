"""Synthetic end-to-end check for Tasmania: a TasALERT Emergency Warning /
Watch and Act record -> tas_fire.parse -> site match -> the email path.

No real warning has appeared on the live layer yet (only a planned burn and a
smoke alert), so this proves the wiring around the adapter, not that the real
feed uses these exact tier names — the first real warning is still the test of
that. See tas_fire.py's module docstring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters import tas_fire

NOW_MS = 1_793_600_000_000

# Hobart branch (Tier 1) and a Launceston branch (Tier 1), as in alert_sites.
SITES = [
    {"name": "Hobart", "suburb": "Hobart", "state": "TAS", "postcode": "7000", "priority": "Tier 1",
     "latitude": -42.88251, "longitude": 147.32812, "geocode_quality": "suburb", "site_type": "Branch"},
    {"name": "Launceston", "suburb": "Launceston", "state": "TAS", "postcode": "7250", "priority": "Tier 1",
     "latitude": -41.44084, "longitude": 147.13233, "geocode_quality": "street", "site_type": "Branch"},
]


def _feature(alert_type, summary, x, y, ident):
    return {
        "attributes": {
            "ALERT_TYPE": alert_type, "EVENT": "Bushfire", "ALERT_SUMMARY": summary,
            "AREA_DESCRIPTION": "Near Hobart", "FULL_DESCRIPTION": "Fire burning.",
            "ALERT_INSTRUCTIONS": "Leave now", "IDENTIFIER": ident,
            "TASALERT_LINK": f"https://alert.tas.gov.au/?id={ident}",
            "EFFECTIVE_FROM_DATE": NOW_MS - 600_000, "EXPIRES_DATE": NOW_MS + 3_600_000,
        },
        "geometry": {"x": x, "y": y},
    }


def _rows(alerts):
    return [
        {"id": f"row-{i}", "headline": a.headline, "jurisdiction": a.jurisdiction, "alert_type": a.alert_type,
         "location": a.location, "description": a.description, "canonical_url": a.canonical_url,
         "issued_at": a.issued_at, "latitude": a.latitude, "longitude": a.longitude}
        for i, a in enumerate(alerts)
    ]


def test_emergency_warning_near_hobart_emails_with_tier1_site_context():
    payload = {"features": [_feature("Emergency Warning", "Bushfire Emergency Warning - Hobart", 147.30, -42.88, "ew-1")]}
    alerts = tas_fire.parse(payload, now_ms=NOW_MS)
    assert [a.severity for a in alerts] == ["emergency_warning"]

    with patch.object(ea, "supabase_get", return_value=_rows(alerts)), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
         patch.object(ea.site_matching, "list_active_sites", return_value=SITES), \
         patch.object(ea, "send_email", return_value=True) as mock_send, \
         patch.object(ea, "_supabase_request"):
        assert ea._send_emergency_warning_emails("tas_fire") == 1

    subject = mock_send.call_args.kwargs["subject"]
    assert subject.startswith("[EW] TAS - ")
    assert "1 site possibly affected, 1 Tier 1" in subject  # Hobart only, Launceston is ~160 km away
    assert "Hobart" in mock_send.call_args.kwargs["html"]


def test_emergency_warning_survives_a_blanket_silence():
    payload = {"features": [_feature("Emergency Warning", "Bushfire Emergency Warning - Hobart", 147.30, -42.88, "ew-2")]}
    alerts = tas_fire.parse(payload, now_ms=NOW_MS)
    everything = {"id": "sil-all", "reason": "maintenance window"}
    with patch.object(ea, "supabase_get", return_value=_rows(alerts)), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[everything]), \
         patch.object(ea.site_matching, "list_active_sites", return_value=SITES), \
         patch.object(ea, "send_email", return_value=True) as mock_send, \
         patch.object(ea, "_supabase_request"):
        assert ea._send_emergency_warning_emails("tas_fire") == 1
    mock_send.assert_called_once()


def test_watch_and_act_is_parsed_and_matched_but_not_emailed_as_emergency():
    payload = {"features": [_feature("Watch and Act", "Bushfire Watch and Act - Hobart", 147.30, -42.88, "wa-1")]}
    [alert] = tas_fire.parse(payload, now_ms=NOW_MS)
    assert alert.severity == "watch_and_act"
    import site_matching
    matches = site_matching.match_alert({**alert.__dict__, "severity": alert.severity}, SITES)
    assert [m.site["name"] for m in matches] == ["Hobart"]
    # The emergency-email query is severity=eq.emergency_warning, so a Watch and Act
    # never reaches _send_emergency_warning_emails (it appears on the workbench).


def test_untiered_label_stays_unknown_and_sends_no_emergency_email():
    payload = {"features": [_feature("Bushfire - Emergency", "Bushfire near Hobart", 147.30, -42.88, "x-1")]}
    [alert] = tas_fire.parse(payload, now_ms=NOW_MS)
    assert alert.severity == "unknown"  # tier wording we don't recognise is never guessed
