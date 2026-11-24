"""Performance scorecard: offline, fake data source, no network."""
from __future__ import annotations

import csv
import json
import socket
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools" / "intelligence"))

import performance_scorecard as ps  # noqa: E402

REF_PATH = _REPO / "knowledge" / "intelligence-reference-set" / "reference_set.json"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


class FakeSource:
    def __init__(self, events=None, briefs=None, ratings=None):
        self._e, self._b, self._r = events, briefs, ratings

    def events(self):
        return self._e

    def briefs(self):
        return self._b

    def ratings(self):
        return self._r


def inc(iid, regex, mat="high", neg=False, first="2026-11-12T00:00:00Z", end=None, verif="verified", pair=None,
        embedded=None):
    return {"id": iid, "title": iid, "is_negative_example": neg, "verification_status": verif,
            "australian_materiality": {"level": mat, "reason": "t"},
            "first_public_report_time": {"value": first, "source": "t"},
            "start_time_utc": {"value": first, "source": "t", "confidence": "low"},
            "end_time_utc": {"value": end, "source": "t"}, "correlation_trap": pair, "reviewed_by_human": False,
            "tjr_detection": dict({"match": {"title_regex": regex, "published_from": "2026-11-10", "published_to": "2026-11-20"}},
                                  **(embedded or {}))}


def ev(i, title, source="ABC News", pub="2026-11-12T01:00:00Z", col="2026-11-12T03:00:00Z", **kw):
    return dict({"event_id": i, "raw_title": title, "source_name": source, "published_at": pub, "collected_at": col}, **kw)


def ref(*incs):
    return {"name": "t", "created_utc": "2026-11-24T00:00:00Z", "incidents": list(incs)}


def test_detected_missed_and_time_to_detection():
    r = ref(inc("A", r"\mAlpha\M outage"), inc("B", r"Beta outage"))
    events = [ev("1", "Alpha outage hits users", col="2026-11-12T05:00:00Z"),
              ev("2", "Alphabet outage unrelated word-boundary check", col="2026-11-12T02:00:00Z")]
    c = ps.compute_scorecard(r, FakeSource(events))
    m = c["material_incidents"]
    assert (m["total"], m["detected"], m["missed"], m["missed_ids"]) == (2, 1, 1, ["B"])
    assert c["time_to_first_detection_hours"]["by_incident"]["A"] == 5.0  # \m \M translated, 'Alphabet' not matched


def test_unverified_material_is_not_scored_but_listed():
    r = ref(inc("A", "Alpha", verif="unverified"), inc("N", "Nope", mat="low"))
    c = ps.compute_scorecard(r, FakeSource([]))
    assert c["material_incidents"]["total"] == 0
    assert c["material_incidents"]["unverified_material_not_scored"] == ["A"]


def test_false_escalation_by_brief_id_and_brief_text():
    r = ref(inc("N1", "Routine notice", neg=True, mat="low"), inc("N2", "Old story", neg=True, mat="none"),
            inc("N3", "Quiet thing", neg=True, mat="none"))
    events = [ev("1", "Routine notice A", brief_id="b1"), ev("2", "Old story again"), ev("3", "Quiet thing")]
    briefs = [{"brief_date": "2026-11-13", "brief_type": "morning", "brief_text": "Today: old story again resurfaced"}]
    c = ps.compute_scorecard(r, FakeSource(events, briefs))
    fe = c["false_escalation"]
    assert fe["negatives_total"] == 3 and sorted(fe["ids"]) == ["N1", "N2"]


def test_corroboration_excludes_aggregators_and_dedupes_publisher_families():
    r = ref(inc("A", "Alpha"), inc("B", "Beta"), inc("C", "Gamma"))
    events = [
        # A: two real publishers -> corroborated
        ev("1", "Alpha outage", "ABC News"), ev("2", "Alpha outage", "Guardian Australia"),
        # B: ABC plus a Google News copy of ABC -> NOT independent
        ev("3", "Beta outage", "ABC News"), ev("4", "Beta outage - Australian Broadcasting Corporation", "Google News - Telstra"),
        # C: aggregator only
        ev("5", "Gamma outage - The Age", "Google News - Telstra"), ev("6", "Gamma outage - Reuters", "Google News - Telstra"),
    ]
    c = ps.compute_scorecard(ref(*r["incidents"]), FakeSource(events))
    ic = c["independent_corroboration"]
    assert ic["corroborated"] == 1 and ic["uncorroborated_ids"] == ["B", "C"]
    assert ic["share"] == pytest.approx(1 / 3, abs=1e-3)


def test_false_recovery_claim_before_reference_end():
    r = ref(inc("A", "Alpha", end="2026-11-13T00:00:00Z"))
    events = [ev("1", "Alpha outage begins", pub="2026-11-12T01:00:00Z"),
              ev("2", "Alpha services restored", pub="2026-11-12T10:00:00Z"),   # 14h early: false recovery
              ev("3", "Alpha services restored for real", pub="2026-11-13T00:30:00Z")]  # within tolerance
    c = ps.compute_scorecard(r, FakeSource(events))
    assert c["false_recovery"]["claims_by_incident"] == {"A": 1}


def test_source_contribution_is_more_than_first_detection():
    r = ref(inc("A", "Alpha"))
    events = [ev("1", "Alpha outage", "ARN - Australian IT Channel", col="2026-11-12T02:00:00Z"),
              ev("2", "Alpha outage confirmed", "ABC News", col="2026-11-12T03:00:00Z"),
              ev("3", "Alpha services restored", "Guardian Australia", col="2026-11-13T03:00:00Z"),
              ev("4", "Alpha: what we know about the cause", "BBC News", col="2026-11-13T04:00:00Z")]
    c = ps.compute_scorecard(r, FakeSource(events))
    by = {s["source"]: s for s in c["source_contribution"]}
    assert by["ARN - Australian IT Channel"]["first_report"] == 1
    assert by["ABC News"]["confirmation"] == 1
    assert by["Guardian Australia"]["restoration_evidence"] == 1 and by["Guardian Australia"]["sole_role_incidents"] >= 1
    assert by["BBC News"]["chronology"] == 1


def test_incorrect_correlation_detected_when_unrelated_pair_shares_signal():
    pa = {"pair_id": "P", "expected_relationship": "unrelated", "partner": "B"}
    pb = {"pair_id": "P", "expected_relationship": "unrelated", "partner": "A"}
    r = ref(inc("A", "Alpha", pair=pa), inc("B", "Beta", pair=pb))
    events = [ev("1", "Alpha outage", canonical_signal_id="S1"), ev("2", "Beta outage", canonical_signal_id="S1")]
    assert ps.compute_scorecard(r, FakeSource(events))["incorrect_correlation"]["wrongly_correlated"] == ["P"]
    events[1]["canonical_signal_id"] = "S2"
    assert ps.compute_scorecard(r, FakeSource(events))["incorrect_correlation"]["wrongly_correlated"] == []


def test_week_window_filters_incidents_by_first_public_report():
    r = ref(inc("A", "Alpha", first="2026-11-12T00:00:00Z"), inc("B", "Beta", first="2026-11-20T00:00:00Z"))
    c = ps.compute_scorecard(r, FakeSource([]), "2026-11-17", "2026-11-24")
    assert c["reference_set"]["incidents_scored"] == 1 and c["material_incidents"]["missed_ids"] == ["B"]


def test_ratings_csv_parsing_and_validation(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("date,brief_usefulness_1to5,noise_count,manual_verification_minutes,notes\n"
                 "2026-11-18,4,2,15,\n2026-11-19,5,0,5,\n2026-11-20,9,1,x,bad\n2026-11-01,1,50,500,outside window\n")
    rows = ps.FileSource(ratings=str(p)).ratings()
    s = ps.summarise_ratings(rows, ps._day("2026-11-17"), ps._day("2026-11-24"))
    assert s["rows"] == 3 and s["brief_usefulness_mean_1to5"] == 4.5
    assert s["noise_count"] == 3 and s["manual_verification_minutes"] == 20.0
    assert len(s["warnings"]) == 2
    assert ps.summarise_ratings(None, None, None)["provided"] is False


def test_embedded_baseline_mode_when_no_events():
    emb = {"appeared": True, "first_collected_at": "2026-11-12T05:00:00Z", "first_source": "ABC News",
           "n_non_aggregator_sources": 3, "events_with_brief_id": 1}
    c = ps.compute_scorecard(ref(inc("A", "Alpha", embedded=emb)), FakeSource(None))
    assert c["mode"] == "embedded_baseline" and c["material_incidents"]["detected"] == 1
    assert c["time_to_first_detection_hours"]["median"] == 5.0
    assert c["independent_corroboration"]["corroborated"] == 1 and c["source_contribution"] is None


def test_cli_runs_from_exported_json(tmp_path, capsys):
    (tmp_path / "ref.json").write_text(json.dumps(ref(inc("A", "Alpha"))))
    (tmp_path / "ev.json").write_text(json.dumps([ev("1", "Alpha outage")]))
    assert ps.main(["--reference", str(tmp_path / "ref.json"), "--events", str(tmp_path / "ev.json"),
                    "--format", "json", "--out", str(tmp_path / "o.json")]) == 0
    assert json.loads((tmp_path / "o.json").read_text())["material_incidents"]["detected"] == 1
    assert '"detected": 1' in capsys.readouterr().out


class TestReferenceSetIntegrity:
    @pytest.fixture()
    def doc(self):
        return json.loads(REF_PATH.read_text())

    def test_ids_unique_and_unreviewed(self, doc):
        ids = [i["id"] for i in doc["incidents"]]
        assert len(ids) == len(set(ids))
        assert all(i["reviewed_by_human"] is False for i in doc["incidents"])

    def test_required_fields_and_negatives(self, doc):
        need = {"id", "title", "start_time_utc", "first_public_report_time", "end_time_utc", "sectors",
                "australian_materiality", "sources", "is_negative_example", "negative_reason", "tjr_detection"}
        for i in doc["incidents"]:
            assert need <= set(i), i["id"]
            if i["is_negative_example"]:
                assert i["negative_reason"]
        assert sum(i["is_negative_example"] for i in doc["incidents"]) >= 8
        assert any(i["discovered_via"] == "web_search" and not i["tjr_detection"]["appeared"]
                   and not i["is_negative_example"] for i in doc["incidents"])

    def test_baseline_runs(self, doc):
        c = ps.compute_scorecard(doc, FakeSource(None))
        assert c["material_incidents"]["total"] >= 5
