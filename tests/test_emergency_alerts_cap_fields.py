"""CAP urgency/certainty/severity/event retention. On by default (migration 0250 is applied); EMERGENCY_ALERTS_CAP_FIELDS=0/false/off/no strips them."""

from __future__ import annotations

import re
import sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters import (
    act_esa,
    bom_warnings,
    nsw_rfs,
    qld_fire,
    sa_cfs,
    tas_fire,
    vic_emergency,
    wa_dfes,
)
from intelligence.ingestion.emergency_alert_adapters.base import (
    CanonicalAlert,
)
from tests.emergency_alert_helpers import (  # noqa: F401
    block_network,
    fixture_bytes,
    fixture_json,
)

CAP = ("cap_urgency", "cap_certainty", "cap_severity", "cap_event")
MIGRATIONS = REPO / "core" / "infrastructure" / "supabase" / "migrations"


# ---- CanonicalAlert ---------------------------------------------------------------------

def test_cap_fields_default_to_none():
    alert = CanonicalAlert(source_key="s", jurisdiction="X", headline="h", event_key="e")
    assert [getattr(alert, f) for f in CAP] == [None, None, None, None]
    assert {f.name for f in fields(CanonicalAlert)} >= set(CAP)


# ---- population: only sources that carry CAP --------------------------------------------

@pytest.mark.usefixtures("block_network")
def test_sa_cfs_populates_cap_fields_from_the_snapshot():
    alerts = sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml"))
    assert len(alerts) == 3
    for alert in alerts:
        assert (alert.cap_urgency, alert.cap_certainty, alert.cap_severity, alert.cap_event) == ("Unknown", "Observed", "Unknown", "Grass Fire")


@pytest.mark.usefixtures("block_network")
def test_vic_warning_populates_cap_fields_from_the_snapshot():
    (alert,) = vic_emergency.parse_warnings(fixture_json("vic_emergency", "warnings.json"))
    assert (alert.cap_urgency, alert.cap_certainty, alert.cap_severity, alert.cap_event) == ("Expected", "Unknown", "Minor", "Riverine Flood")


@pytest.mark.usefixtures("block_network")
def test_vic_incident_rows_carry_no_cap():
    for alert in vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json")):
        assert [getattr(alert, f) for f in CAP] == [None] * 4


@pytest.mark.usefixtures("block_network")
def test_no_cap_is_inferred_for_any_other_source():
    others = (
        nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json"))
        + qld_fire.parse(fixture_json("qld_fire", "feed.json"))
        + act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"))
        + wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml"))
        + tas_fire.parse(fixture_json("tas_fire", "feed.json"), 1793944320000)
        + bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml"))
    )
    assert len(others) > 50
    assert all(getattr(a, f) is None for a in others for f in CAP)


def test_vic_warning_with_a_string_cap_block_yields_none():
    data = {"features": [{"properties": {"feedType": "warning", "id": "1", "category1": "Advice", "cap": "oops"}}]}
    (alert,) = vic_emergency.parse_warnings(data)
    assert [getattr(alert, f) for f in CAP] == [None] * 4


def test_empty_cap_values_become_none_not_empty_strings():
    data = {"features": [{"properties": {"feedType": "warning", "id": "1", "category1": "Advice", "cap": {"urgency": "", "event": "Flood"}}}]}
    (alert,) = vic_emergency.parse_warnings(data)
    assert alert.cap_urgency is None and alert.cap_event == "Flood"


# ---- orchestrator: stored by default, stripped only when explicitly switched off ----------

def _upsert_body(alerts, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("EMERGENCY_ALERTS_CAP_FIELDS", raising=False)
    else:
        monkeypatch.setenv("EMERGENCY_ALERTS_CAP_FIELDS", flag)
    adapter = SimpleNamespace(fetch=lambda: alerts)
    sent = []
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_supabase_request", side_effect=lambda m, p, body=None, extra_headers=None, timeout=15: sent.append((p, body))), \
         patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat"):
        ea.run_source("x_src")
    (body,) = [b for p, b in sent if p.startswith("alerts?on_conflict")]
    return body


def _cap_alert():
    return CanonicalAlert(source_key="x_src", jurisdiction="SA", headline="h", event_key="e",
                          cap_urgency="Expected", cap_certainty="Likely", cap_severity="Minor", cap_event="Flood")


@pytest.mark.parametrize("flag", ["0", "false", "FALSE", "off", "Off", "no", " 0 "])
def test_cap_keys_are_stripped_from_the_upsert_only_when_explicitly_switched_off(monkeypatch, flag):
    (row,) = _upsert_body([_cap_alert()], monkeypatch, flag)
    assert not set(CAP) & set(row), "an unknown column would fail the whole source's upsert on a database without 0250"


@pytest.mark.parametrize("flag", [None, "", "1", "true", "yes", "on", "2", "anything"])
def test_cap_keys_are_stored_by_default_and_for_any_non_off_value(monkeypatch, flag):
    (row,) = _upsert_body([_cap_alert()], monkeypatch, flag)
    assert [row[f] for f in CAP] == ["Expected", "Likely", "Minor", "Flood"]


def test_other_columns_are_identical_with_the_flag_on_or_off(monkeypatch):
    off = _upsert_body([_cap_alert()], monkeypatch, "0")[0]
    on = _upsert_body([_cap_alert()], monkeypatch, None)[0]
    assert {k: v for k, v in on.items() if k not in CAP and k != "last_seen_at"} == {k: v for k, v in off.items() if k != "last_seen_at"}


def test_flag_is_read_per_run_not_at_import(monkeypatch):
    assert "cap_event" in _upsert_body([_cap_alert()], monkeypatch, None)[0]
    assert "cap_event" not in _upsert_body([_cap_alert()], monkeypatch, "0")[0]
    assert "cap_event" in _upsert_body([_cap_alert()], monkeypatch, None)[0]


def test_default_row_keys_include_all_four_cap_columns_for_a_source_without_cap(monkeypatch):
    """Sources with no CAP data send the four keys as null, which the columns accept."""
    (row,) = _upsert_body([CanonicalAlert(source_key="x_src", jurisdiction="NSW", headline="h", event_key="e")], monkeypatch, None)
    assert set(row) == {"source_key", "jurisdiction", "headline", "event_key", "alert_type", "severity", "description", "location",
                        "issued_at", "updated_at_src", "expiry", "canonical_url", "raw_text", "latitude", "longitude",
                        "status", "is_active", "last_seen_at", *CAP}
    assert [row[f] for f in CAP] == [None] * 4


def test_switched_off_row_keys_are_exactly_the_pre_cap_columns(monkeypatch):
    (row,) = _upsert_body([CanonicalAlert(source_key="x_src", jurisdiction="NSW", headline="h", event_key="e")], monkeypatch, "0")
    assert set(row) == {"source_key", "jurisdiction", "headline", "event_key", "alert_type", "severity", "description", "location",
                        "issued_at", "updated_at_src", "expiry", "canonical_url", "raw_text", "latitude", "longitude",
                        "status", "is_active", "last_seen_at"}


# ---- migration 0250 ---------------------------------------------------------------------

def _migration_text() -> str:
    return (MIGRATIONS / "0250_alerts_cap_fields.sql").read_text(encoding="utf-8")


def test_migration_adds_four_nullable_text_columns_and_nothing_else():
    sql = _migration_text()
    # strip comments and quoted strings first: the column comments contain ';' and doubled quotes
    code = re.sub(r"'(?:[^']|'')*'", "''", re.sub(r"--[^\n]*", "", sql))
    statements = [s for s in code.split(";") if s.strip()]
    adds = [s for s in statements if re.search(r"\balter\s+table\s+alerts\s+add\s+column", s, re.IGNORECASE)]
    assert [re.search(r"if not exists\s+(\w+)\s+text", s, re.IGNORECASE).group(1) for s in adds] == list(CAP)
    assert not [s for s in adds if re.search(r"not\s+null|default|check|references", s, re.IGNORECASE)]
    others = [s for s in statements if s not in adds]
    assert all(re.match(r"\s*comment\s+on\s+column\s+alerts\.cap_", s, re.IGNORECASE) for s in others)
    assert not re.search(r"\b(drop|delete|update|insert|truncate)\b", code, re.IGNORECASE)


def test_migration_is_the_next_number_and_recorded_as_applied():
    assert sorted(p.name for p in MIGRATIONS.glob("0250_*.sql")) == ["0250_alerts_cap_fields.sql"]
    text = _migration_text()
    assert "NOT APPLIED" not in text and "APPLIED 2026-11-06" in text
    assert "EMERGENCY_ALERTS_CAP_FIELDS" in text


def test_alert_schema_drift_guard_is_unaffected_by_the_migration():
    """0250 adds columns only: it must not redefine the severity / alert_type CHECKs."""
    sql = _migration_text()
    assert "alerts_alert_type_check" not in sql and "alerts_severity_check" not in sql
