"""Historical imports must not read as new developments (2026-11-24).

A newly activated or repaired source back-fills old publications on its first run (ASIC releases from weeks ago); a statutory
outage register publishes only after the outage is rectified. Neither is a live signal for the morning brief.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be

NOW = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)


def _row(eid, source, published, title="Regulator action announced"):
    return {"event_id": eid, "raw_title": title, "raw_summary": "", "geography": "AU", "collected_at": "2026-11-24T19:03:00+00:00",
            "published_at": published, "canonical_url": f"https://example.test/{eid}", "intelligence_source_registry": {"source_name": source}}


def _load(rows, hours=72):
    return be.load_events(lambda table, q: rows, hours=hours, now=NOW)


def test_old_publications_from_a_back_fill_keep_their_dates_but_leave_the_window():
    ev = _load([_row("a", "ASIC News Centre", "2026-11-23T00:00:00+00:00"),      # 1 day old: kept
                _row("b", "ASIC News Centre", "2026-11-10T00:00:00+00:00"),      # two weeks old: a back-fill, not news
                _row("c", "ASIC News Centre", None)])                              # no date: absence is not evidence of age
    assert {e["id"] for e in ev} == {"a", "c"}
    assert next(e for e in ev if e["id"] == "a")["published_at"] == "2026-11-23T00:00:00+00:00"   # original date preserved


def test_outage_register_entries_are_never_incident_seeds():
    ev = _load([_row("r1", "Optus National Outage Register", "2026-11-24T00:00:00+00:00", "Optus outage register: Mobile outage - X"),
                _row("n1", "ABC News", "2026-11-24T00:00:00+00:00", "Optus mobile outage reported")])
    assert [e["id"] for e in ev] == ["n1"]


def test_window_is_the_evidence_window_not_a_fixed_age():
    rows = [_row("x", "ABC News", "2026-11-23T10:00:00+00:00")]                 # 34h old
    assert len(_load(rows, hours=24)) == 0 and len(_load(rows, hours=72)) == 1


def test_outage_register_rows_never_reach_other_signals_or_midday_alerts():
    from intelligence import captains_brief as cb
    rows = [{"raw_title": "Optus outage register: Mobile outage - Springlands", "operational_relevance": 0.9, "event_type": "outage", "geography": "AU",
             "confidence": 0.9, "rank_score": 90, "raw_summary": "Restored.", "intelligence_source_registry": {"source_name": "Optus National Outage Register"}},
            {"raw_title": "Telstra mobile outage hits Adelaide", "operational_relevance": 0.9, "event_type": "outage", "geography": "AU",
             "confidence": 0.9, "rank_score": 90, "raw_summary": "", "intelligence_source_registry": {"source_name": "ABC News"}}]
    out = cb._with_risk_label(rows)
    assert [r["raw_title"] for r in out] == ["Telstra mobile outage hits Adelaide"]
