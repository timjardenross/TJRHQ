"""Captain's final V1 corrections: scope, hazards/forecasts, grouping regressions, comms fields, weekly change detection, evidence terms."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

NOW = datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc)


def e(i, title, src="ABC News", h=2):
    return {"id": i, "title": title, "source": src, "geography": "AU", "url": f"https://x.test/{i}",
            "collected_at": (NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def prio(title, src="ABC News"):
    return ed.run([e("t", title, src)], now=NOW)[0].priority


# 1. escalation scope
def test_overseas_military_casualties_and_weather_cancellations_not_escalated():
    for t in ("Three soldiers killed in overseas military strike", "Storm cancels dozens of flights at Sydney airport",
              "Hurricane forecast prompts flight cancellations across Florida"):
        assert prio(t) != "ESCALATE", t


def test_major_international_tech_incident_with_systemic_impact_still_escalates():
    assert prio("Global cloud provider outage disrupts banks and airlines across Australia and Europe") == "ESCALATE"


# 2. hazards, warnings, forecasts
def test_warnings_and_forecasts_are_watch_not_outages():
    for t in ("Emergency warning issued for bushfire near Perth", "AEMO issues Lack Of Reserve Level 2 (LOR2) notice for SA on 25/11/2026",
              "Magnitude 5.6 earthquake strikes near Darwin", "Ambulance delays reported across Victoria as demand surges"):
        assert prio(t) == "WATCH", t


def test_forecast_is_labelled_not_a_stated_outage():
    d = ed.run([e("f", "AEMO issues Lack Of Reserve Level 2 (LOR2) notice for SA on 25/11/2026", "AEMO Market Notices")], now=NOW)[0]
    assert d.group.members[0].status in ("forecast", "warning")


def test_water_contamination_recognised():
    assert prio("Do not drink water notice issued after contamination in town supply") in ("ESCALATE", "VERIFY")


# 3. grouping regressions
def _fixture_groups():
    fx = json.loads((_REPO / "tests/fixtures/grouping_regression_events.json").read_text())
    return ed.run(fx["events"], now=NOW)


def _group_of(decs, prefix):
    return next(d for d in decs if any(m.event_id.startswith(prefix) for m in d.group.members))


def test_eyre_peninsula_reports_form_one_incident():
    decs = _fixture_groups()
    g = _group_of(decs, "735f411c")
    ids = {m.event_id[:8] for m in g.group.members}
    assert {"735f411c", "4893fe2f", "12dbf4fb", "75657c62"} <= ids


def test_m365_reports_form_one_incident_with_confidence_and_refs():
    g = _group_of(_fixture_groups(), "d1f78bc2")
    assert {m.event_id[:8] for m in g.group.members} >= {"d1f78bc2", "5faa0a3f", "cd458e26", "1d9cd2a4", "55d3fe5f"}
    assert g.group.grouping_confidence > 0 and g.group.pairs                       # original references and confidence preserved
    assert set(ed.escalation_record(g)["report_ids"]) >= {m.event_id for m in g.group.members}


def test_unrelated_incidents_of_same_organisation_not_merged():
    decs = ed.run([e("a", "Telstra outage leaves 20,000 customers without mobile service in Queensland", h=60),
                   e("b", "Telstra reports half-year profit rise as dividend lifted", h=2)], now=NOW)
    assert not any({"a", "b"} <= {m.event_id for m in d.group.members} for d in decs)


# 6. evidence-status terminology
def test_evidence_status_vocabulary_and_syndication():
    one = ed.run([e("a", "Coles Group investigating a cyber incident")], now=NOW)[0]
    assert ed.evidence_status(one.group)[0] in ("reported", "unverified")
    synd = ed.run([e("a", "Power outage hits 20,000 customers in SA", "ABC News"),
                   e("b", "Power outage hits 20,000 customers in SA - ABC News", "Yahoo News")], now=NOW)
    assert all(ed.evidence_status(d.group)[0] != "corroborated" for d in synd)


def test_no_headline_keyword_confirmed_label():
    ev = be.build_evidence([e("a", "Confirmed: cyber attack hits retailer")], now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(ev) + be.weekly_view(ev))
    assert "OFFICIALLY CONFIRMED or CORROBORATED" in text
    assert "officially confirmed ·" not in text


# 5. weekly change detection with SnapshotStore-style payloads
def test_weekly_change_not_assessable_without_prior_snapshot():
    ev = be.build_evidence([e("a", "Power still out for 20,000 customers after towers crushed")], now=NOW, window_hours=72)
    assert "Change cannot be assessed" in "\n".join(be.weekly_view(ev, None))


def test_weekly_change_new_continuing_resolved(tmp_path):
    prev_ev = be.build_evidence([e("a", "Power still out for 20,000 customers after towers crushed", h=80),
                                 e("z", "Telstra outage leaves 50,000 customers without service", h=80)], now=NOW - timedelta(days=7), window_hours=168)
    cur_ev = be.build_evidence([e("a", "Power still out for 20,000 customers after towers crushed", h=80),
                                e("n", "Optus outage cuts mobile service for 30,000 customers", h=3)], now=NOW, window_hours=168)
    text = "\n".join(be.weekly_view(cur_ev, be.snapshot_payload(prev_ev)))
    low = text.lower()
    assert "1 new, 1 continuing" in low and "no longer reported" in low and "resolution not assessed" in low and "cannot be assessed" not in low


def test_snapshot_roundtrip(tmp_path):
    ev = be.build_evidence([e("a", "Power still out for 20,000 customers after towers crushed")], now=NOW - timedelta(days=7), window_hours=72)
    p = str(tmp_path / "s.json")
    assert be.record_snapshot(p, ev)
    assert be.load_previous_snapshot(p, NOW) is not None


# 4. comms fields
def test_comms_fields_and_never_ready_when_unsupported():
    ev = be.build_evidence([e("a", "Microsoft platforms suffering widespread outages, including Outlook", "BBC News")], now=NOW, window_hours=72)
    text = "\n".join(be.comms_view(ev, pillar_fn=lambda t: "Operational Resilience", similarity_fn=lambda t, ex: 0.0, existing_titles=["x"]))
    for field in ("Proposed headline", "audience", "central argument", "why now", "evidence and provenance", "what only you can add",
                  "originality", "publication readiness", "evidence gaps"):
        assert field in text, field
    assert "ready to draft" not in text and "Hypothesis (unsupported" in text


def test_comms_flags_duplicate_of_existing_title():
    ev = be.build_evidence([e("a", "Power still out for 20,000 customers after towers crushed - AEMO update", "AEMO Market Notices")], now=NOW, window_hours=72)
    text = "\n".join(be.comms_view(ev, pillar_fn=lambda t: "Operational Resilience", similarity_fn=lambda t, ex: 0.9, existing_titles=["same"]))
    assert "hold — duplicates existing content" in text
