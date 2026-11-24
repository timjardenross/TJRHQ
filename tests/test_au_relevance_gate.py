"""AU relevance gate (AU_RELEVANCE_DISRUPTION_GATE_V1, default OFF): HIGH operational relevance needs a stated disruption signal."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from intelligence.classification import classifier as clf
from intelligence.models import IntelligenceItem

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/conversion_integration/ref_event_relevance_20261124.tsv"
EXPORT = ROOT / "knowledge/intelligence-reference-set/events_export_2026-11-24.json"
REF = ROOT / "knowledge/intelligence-reference-set/reference_set_v1.json"


def item(title, summary=""):
    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    return IntelligenceItem(source_id="s", source_name="x", source_priority=1, source_confidence_weight=0.8, source_category="media",
                            raw_title=title, raw_summary=summary, canonical_url="https://example.test/a", published_at=now, collected_at=now)


def rel(title, summary=""):
    return clf.classify(item(title, summary)).operational_relevance


APRA_STATS = "APRA releases monthly authorised deposit-taking institution statistics for October"
SPEECH = "APRA Chair remarks to the Australian Financial Review summit on prudential policy"
NAB_OUTAGE = "NAB customers experiencing phone and internet banking outages"


def test_default_off_scores_are_unchanged(monkeypatch):
    monkeypatch.delenv(clf.AU_GATE_FLAG, raising=False)
    assert not clf.au_gate_enabled()
    assert rel(APRA_STATS) >= clf.HIGH_RELEVANCE            # the measured inflation: base 0.70 + AU lift 0.15 = 0.85
    assert rel(SPEECH) >= clf.HIGH_RELEVANCE


def test_flag_on_caps_institution_mention_without_disruption(monkeypatch):
    monkeypatch.setenv(clf.AU_GATE_FLAG, "1")
    assert rel(APRA_STATS) < clf.HIGH_RELEVANCE
    assert rel(SPEECH) < clf.HIGH_RELEVANCE
    assert rel("Telstra appoints new chief executive for its network division") < clf.HIGH_RELEVANCE


def test_flag_on_keeps_stated_disruption_high(monkeypatch):
    monkeypatch.setenv(clf.AU_GATE_FLAG, "1")
    assert clf.has_disruption_signal(NAB_OUTAGE)
    assert rel("Coles investigates cyber attack on its systems") >= clf.HIGH_RELEVANCE


def test_flag_read_at_call_time(monkeypatch):
    monkeypatch.delenv(clf.AU_GATE_FLAG, raising=False)
    before = rel(APRA_STATS)
    monkeypatch.setenv(clf.AU_GATE_FLAG, "true")
    assert rel(APRA_STATS) < before
    monkeypatch.setenv(clf.AU_GATE_FLAG, "0")
    assert rel(APRA_STATS) == before


def test_gate_never_raises_a_score(monkeypatch):
    titles = [APRA_STATS, SPEECH, NAB_OUTAGE, "Optus network outage disrupts mobile services nationwide", "Qantas systems failure grounds flights"]
    monkeypatch.delenv(clf.AU_GATE_FLAG, raising=False)
    off = [rel(t) for t in titles]
    monkeypatch.setenv(clf.AU_GATE_FLAG, "1")
    assert all(on <= o for on, o in zip([rel(t) for t in titles], off))


def _fixture():
    rows = {}
    for line in FIX.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        i, o, g, sf, st = line.split("\t")
        rows[i] = {"o": float(o), "geo": g, "sig_full": sf == "1", "sig_title": st == "1"}
    return rows


def test_python_pattern_matches_the_postgres_measurement_on_titles():
    """The A/B counts were produced by running this pattern in PostgreSQL; the same pattern in Python must agree row for row (titles)."""
    rows = _fixture()
    events = {e["event_id"]: e for e in json.loads(EXPORT.read_text())["events"]}
    assert len(rows) == 70
    for eid, r in rows.items():
        assert clf.has_disruption_signal(events[eid]["raw_title"]) == r["sig_title"], (eid, events[eid]["raw_title"])


def test_recall_on_frozen_reference_material_incidents():
    """Confirmed material reference records keep at least one HIGH event; the one lost HIGH event is a vulnerability advisory (RS-031)."""
    rows = _fixture()
    ref = {r["id"]: r["status"] for r in json.loads(REF.read_text())["incidents"]}
    events = [e for e in json.loads(EXPORT.read_text())["events"] if e["event_id"] in rows]
    material = [e for e in events if ref[e["incident_id"]] == "confirmed_material"]
    high = [e for e in material if rows[e["event_id"]]["o"] >= clf.HIGH_RELEVANCE]
    kept = [e for e in high if rows[e["event_id"]]["sig_full"]]
    lost = [(e["incident_id"], e["event_id"]) for e in high if not rows[e["event_id"]]["sig_full"]]
    assert (len(high), len(kept)) == (20, 19)
    assert lost == [("RS-031", "4a65276c")]
    for rec in {e["incident_id"] for e in high}:
        assert any(rows[e["event_id"]]["sig_full"] for e in high if e["incident_id"] == rec), f"{rec} lost all HIGH events"
    nonmat_high = [e for e in events if ref[e["incident_id"]] != "confirmed_material" and rows[e["event_id"]]["o"] >= clf.HIGH_RELEVANCE]
    assert nonmat_high == []


@pytest.mark.parametrize("text", ["Planned maintenance window announced", "Annual report released", "APRA statistics for September"])
def test_non_disruption_text_has_no_signal(text):
    assert not clf.has_disruption_signal(text)
