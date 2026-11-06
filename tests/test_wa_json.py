"""WA DFES JSON enrichment: issue time, CAP fields and incident status are filled onto the RSS-derived alerts by exact id,
never change which alerts exist, and an outage keeps them RSS-only. Offline, on live-captured fixtures."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters import wa_dfes, wa_json
from intelligence.ingestion.emergency_alert_adapters.base import DropLedger
from tests.emergency_alert_helpers import block_network, fixture_bytes  # noqa: F401

pytestmark = pytest.mark.usefixtures("block_network")

WARNINGS_JSON = fixture_bytes("wa_dfes", "warnings_api.json")
INCIDENTS_JSON = fixture_bytes("wa_dfes", "incidents_api.json")
FILLED = {"issued_at", "description", "cap_urgency", "cap_certainty", "cap_severity", "cap_event"}


def _rss_alerts(ledger=None):
    return wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml"), ledger or DropLedger())


def test_parse_reads_cap_status_and_place():
    by_id = wa_json.parse(WARNINGS_JSON, INCIDENTS_JSON)
    warning = next(f for f in by_id.values() if f.get("cap_event"))
    assert warning["issued_at"] and warning["cap_urgency"] in {"Immediate", "Expected", "Future", "Past", "Unknown"}
    assert " - " not in warning["cap_severity"]  # DFES's gloss ("Minor - minimal threat") is dropped
    incident = next(f for f in by_id.values() if f.get("description"))
    assert incident["issued_at"] and incident["description"].split(" · ")[0] in {"Active", "Monitoring", "On scene"}


def test_enrich_fills_empty_fields_only_and_never_changes_which_alerts_exist():
    plain, enriched = _rss_alerts(), _rss_alerts()
    n = wa_json.enrich(enriched, WARNINGS_JSON, INCIDENTS_JSON)
    assert n >= 1
    assert [a.event_key for a in plain] == [a.event_key for a in enriched]
    for before, after in zip(plain, enriched):
        changed = {k for k, v in asdict(after).items() if v != asdict(before)[k]}
        assert changed <= FILLED
        assert after.severity == before.severity and after.headline == before.headline  # tier and title stay RSS-derived
    assert any(a.issued_at for a in enriched) and any(a.cap_urgency for a in enriched) and any(a.description for a in enriched)


def test_an_existing_value_is_never_overwritten():
    alerts = _rss_alerts()
    for a in alerts:
        a.issued_at = "2026-01-01T00:00:00+08:00"
    wa_json.enrich(alerts, WARNINGS_JSON, INCIDENTS_JSON)
    assert all(a.issued_at == "2026-01-01T00:00:00+08:00" for a in alerts)


@pytest.mark.parametrize("bad", [b"not json", b"", b'{"warnings": "x"}', b'{"other": []}', b"[]"])
def test_unreadable_json_never_raises_and_changes_nothing(bad, caplog):
    alerts = _rss_alerts()
    with caplog.at_level(logging.WARNING):
        assert wa_json.enrich(alerts, bad, bad) == 0
    assert all(a.issued_at is None and a.cap_urgency is None for a in alerts)


def test_a_failed_fetch_keeps_the_alerts_and_logs(caplog):
    alerts = _rss_alerts()
    with patch.object(wa_json, "http_get", side_effect=OSError("down")), caplog.at_level(logging.WARNING):
        assert wa_json.enrich(alerts) == 0
    assert "DFES JSON enrichment unavailable" in caplog.text and all(a.issued_at is None for a in alerts)


def test_fetch_with_ledger_enriches_and_keeps_the_ledger_invariant():
    def serve(url, timeout=20):
        return {
            wa_dfes._WARNINGS_URL: fixture_bytes("wa_dfes", "warnings.xml"), wa_dfes._INCIDENTS_URL: fixture_bytes("wa_dfes", "incidents.xml"),
            wa_json._WARNINGS_JSON_URL: WARNINGS_JSON, wa_json._INCIDENTS_JSON_URL: INCIDENTS_JSON,
        }[url]

    with patch.object(wa_dfes, "http_get", serve), patch.object(wa_json, "http_get", serve):
        alerts, ledger = wa_dfes.fetch_with_ledger()
    assert any(a.issued_at for a in alerts)
    assert ledger.items_seen == len(alerts) + ledger.excluded_total + ledger.invalid_total


def test_a_json_outage_raises_field_drift_not_a_failure():
    def serve(url, timeout=20):
        if "json" in url or url.endswith(("/v1/warnings", "/v1/incidents")):
            raise OSError("down")
        return fixture_bytes("wa_dfes", "warnings.xml") if "warnings" in url else fixture_bytes("wa_dfes", "incidents.xml")

    with patch.object(wa_dfes, "http_get", serve), patch.object(wa_json, "http_get", serve):
        alerts, ledger = wa_dfes.fetch_with_ledger()
    assert alerts and all(a.issued_at is None for a in alerts)
    assert any(n.startswith("FIELD DRIFT: issued_at") for n in ea._integrity_notes(wa_dfes, alerts, ledger))


def test_json_fixture_is_valid_json_with_the_expected_envelope():
    assert "warnings" in json.loads(WARNINGS_JSON) and "incidents" in json.loads(INCIDENTS_JSON)
