"""V1 shared evidence foundation across the three briefs: one identity/materiality/provenance, flag-gated, legacy unchanged when off."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be

NOW = datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc)


def ev(i, title, source="ABC News", hours_ago=2, geo="AU", url=None):
    t = NOW - timedelta(hours=hours_ago)
    return {"id": i, "title": title, "source": source, "geography": geo, "collected_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": url or f"https://example.test/{i}"}


EVENTS = [
    ev("p1", "Breaking: Transmission towers 'crushed', knocking out power to 20,000 customers", hours_ago=3),
    ev("p2", "Power still out for 20,000 customers after towers crushed - AEMO update", "AEMO Market Notices", hours_ago=2),
    ev("c1", "Coles Group investigating a cyber incident", hours_ago=5),
    ev("m1", "Microsoft platforms suffering widespread outages, including Outlook", "BBC News", hours_ago=30),
    ev("f1", "STPASA - Update of the Forecast Lack Of Reserve Level 1 (LOR1) in the TAS Region on 24/11/2026", "AEMO Market Notices", hours_ago=6),
    ev("r1", "Fed's Logan seeks clearer separation of market operations", "Bloomberg", hours_ago=4),
]


@pytest.fixture(scope="module")
def evset():
    return be.build_evidence(EVENTS, now=NOW, window_hours=72)


def test_identity_is_stable_and_shared(evset):
    again = be.build_evidence(list(reversed(EVENTS)), now=NOW, window_hours=72)
    assert {i.incident_id for i in evset.incidents} == {i.incident_id for i in again.incidents}
    ids = {i.incident_id for i in evset.incidents}
    text = "\n".join(be.morning_view(evset) + be.weekly_view(evset) + be.comms_view(evset))
    shown = {w for w in text.replace(";", " ").replace("[", " ").replace("]", " ").split() if w.startswith("inc-")}
    assert shown and shown <= ids                       # every cited identity exists in the one shared set


def test_every_incident_line_cites_incident_and_reports(evset):
    for view in (be.morning_view(evset), be.weekly_view(evset), be.comms_view(evset)):
        for line in view:
            if line.startswith(("- [ESCALATE", "- [VERIFY", "- [WATCH")):
                assert "[inc-" in line and "report(s)" in line


def test_implication_line_names_tier_not_characters(evset):
    text = "\n".join(be.morning_view(evset))
    assert "tier 1: energy" in text


def test_materiality_is_the_same_object_across_briefs(evset):
    sa = next(i for i in evset.incidents if "p1" in i.report_ids)
    assert sa.priority == "ESCALATE" and sa.materiality == "high" and set(sa.report_ids) >= {"p1", "p2"}
    assert any(sa.incident_id in line for line in be.morning_view(evset))
    assert any(sa.incident_id in line for line in be.weekly_view(evset))


def test_morning_separates_confirmed_from_verification_and_has_forward_watch(evset):
    text = "\n".join(be.morning_view(evset))
    confirmed, rest = text.split("IMPACT NOT YET ESTABLISHED", 1)
    assert "OFFICIALLY CONFIRMED or CORROBORATED" in confirmed and "confirmed" not in rest.split("WARNINGS")[0].lower().replace("unconfirmed", "")
    assert "20,000 customers" in confirmed and "Coles" not in confirmed
    assert "Coles Group investigating" in rest
    watch = text.split("Forward watch", 1)[1]
    assert "Ongoing" in watch and "24/11/2026" in watch


def test_morning_ignores_incidents_older_than_a_day_in_the_confirmed_list(evset):
    text = "\n".join(be.morning_view(evset)).split("IMPACT NOT YET ESTABLISHED")[0]
    assert "Microsoft platforms" not in text


def test_weekly_lists_major_incident_and_open_decision_without_causal_claims(evset):
    text = "\n".join(be.weekly_view(evset))
    assert "Major incidents" in text and "20,000 customers" in text
    assert "DECIDE: confirm or stand down provisional escalation" in text
    for causal in ("caused by", "because of", "led to", "resulted in"):
        assert causal not in text


def test_comms_view_is_recommendation_only_and_gates_on_pillar_and_readiness(evset):
    lines = be.comms_view(evset, pillar_fn=lambda t: "Operational Resilience" if "power" in t.lower() or "outage" in t.lower() else None,
                          similarity_fn=lambda t, ex: 0.0, existing_titles=["x"])
    text = "\n".join(lines)
    assert "approval-only" in lines[0]
    assert "20,000 customers" in text and "Fed's Logan" not in text and "Coles" not in text
    assert "publication readiness" in text and "evidence gaps" in text and "what only you can add" in text


def test_flags_default_off(monkeypatch):
    for k in (be.MASTER_FLAG, *be.FLAGS.values()):
        monkeypatch.delenv(k, raising=False)
    assert not any(be.enabled(b) for b in be.FLAGS)
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_WEEKLY", "1")
    assert be.enabled("weekly") and not be.enabled("morning")
    monkeypatch.setenv(be.MASTER_FLAG, "true")
    assert all(be.enabled(b) for b in be.FLAGS)


def test_legacy_briefs_unchanged_when_flags_off(monkeypatch):
    for k in (be.MASTER_FLAG, *be.FLAGS.values()):
        monkeypatch.delenv(k, raising=False)
    from intelligence import captains_brief as cb
    assert cb._evidence_lines("morning", 72) == [] and cb._evidence_lines("weekly", 168) == []
    from lib.comms import weekly
    assert weekly.evidence_lines_for([]) == []
    assert weekly.compose_weekly_brief([]) == weekly._compose_weekly_brief_core([])


def test_load_events_fails_soft_and_maps_rows():
    def boom(*a, **k):
        raise RuntimeError("db down")
    assert be.load_events(boom, hours=24) == []
    rows = [{"event_id": "e1", "raw_title": "T", "raw_summary": None, "geography": "AU", "collected_at": "2026-11-22T00:00:00Z",
             "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "ABC News"}}]
    out = be.load_events(lambda *a, **k: rows, hours=24)
    assert out == [{"id": "e1", "title": "T", "summary": "", "source": "ABC News", "geography": "AU",
                    "collected_at": "2026-11-22T00:00:00Z", "published_at": None, "url": "https://x"}]


def test_flagged_hook_adds_a_block_and_a_failure_does_not_break_the_brief(monkeypatch):
    from intelligence import captains_brief as cb
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    monkeypatch.setattr(cb, "_sb_get", lambda *a, **k: [])
    assert "EVIDENCE COVERAGE INSUFFICIENT" in cb._evidence_lines("morning", 72)[0]   # no events: labelled insufficient, never silent
    rows = [{"event_id": "p1", "raw_title": EVENTS[0]["title"], "raw_summary": "", "geography": "AU",
             "collected_at": (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "ABC News"}}]
    monkeypatch.setattr(cb, "_sb_get", lambda *a, **k: rows)
    out = "\n".join(cb._evidence_lines("morning", 72))
    assert "EVIDENCE-BASED PICTURE" in out and "inc-" in out
    monkeypatch.setattr(be, "build_evidence", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = cb._evidence_lines("morning", 72)                # failure: never raises, labelled insufficient
    assert "EVIDENCE COVERAGE INSUFFICIENT" in failed[0] and "evidence layer unavailable" in failed[0]


def test_aggregator_only_evidence_is_never_ready_to_draft_and_is_labelled():
    evs = [ev("g1", "Microsoft outage disrupts services worldwide - Reuters", "Google News - Cloud outages", hours_ago=3),
           ev("g2", "Microsoft outage disrupts services worldwide - Bloomberg", "Google News - Tech", hours_ago=2)]
    es = be.build_evidence(evs, now=NOW, window_hours=72)
    inc = es.incidents[0]
    assert inc.priority == "VERIFY"                       # aggregator-only evidence never reaches ESCALATE
    text = "\n".join(be.comms_view(es, pillar_fn=lambda t: "Operational Resilience", similarity_fn=lambda t, ex: 0.0, existing_titles=["x"]))
    assert "ready to draft" not in text


# ── plain-language wording (no dashboard statistics on the page) ──────────────────────────────────────────────────
@pytest.mark.parametrize("c,expected", [(0.95, "high confidence"), (0.75, "high confidence"), (0.74, "moderate confidence"),
                                        (0.5, "moderate confidence"), (0.49, "low confidence"), (0.0, "low confidence")])
def test_confidence_is_shown_in_words(c, expected):
    assert be._confidence_words(c) == expected


def test_the_morning_picture_has_no_method_string_counts_or_raw_confidence():
    text = "\n".join(be.morning_view(be.build_evidence(EVENTS, now=NOW, window_hours=72)))
    assert "EVIDENCE-BASED PICTURE" in text and "Based on reports from the last 72 hours" in text
    assert "method wk-detect" not in text and "assessed from" not in text and "incident(s)" not in text
    assert not re.search(r"confidence \d", text) and re.search(r"(high|moderate|low) confidence", text)


# ── header consistency between the 24h marker and the window ─────────────────────────────────────────────────────
def _header(events, window):
    lines = be.morning_view(be.build_evidence(events, now=NOW, window_hours=window))
    i = next(k for k, l in enumerate(lines) if "EVIDENCE-BASED PICTURE" in l)
    return lines, lines[i + 1]


def test_header_admits_no_reports_in_24h_when_window_is_72():
    lines, header = _header([ev("o1", "Microsoft platforms suffering widespread outages, including Outlook", "BBC News", hours_ago=30)], 72)
    assert any("EVIDENCE COVERAGE INSUFFICIENT" in l for l in lines)
    assert header == "Based on reports from the last 72 hours; none were collected in the last 24 hours, so this is not a current picture."


def test_header_says_newest_within_24h_when_reports_arrived():
    lines, header = _header(EVENTS, 72)
    assert not any("EVIDENCE COVERAGE INSUFFICIENT" in l for l in lines)
    assert header == "Based on reports from the last 72 hours (newest within 24 hours)."


def test_header_for_a_24h_window_has_no_contradiction():
    _, header = _header(EVENTS, 24)
    assert header == "Based on reports from the last 24 hours."
    lines, header = _header([], 24)
    assert "none were collected in the last 24 hours" in header and any("EVIDENCE COVERAGE INSUFFICIENT" in l for l in lines)
