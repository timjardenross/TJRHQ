"""Tests for tools/intelligence/effectiveness_measures.py (offline, read-only, no database, no network)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from tools.intelligence import effectiveness_measures as em

REF = Path(__file__).resolve().parents[1] / "knowledge" / "intelligence-reference-set"


def _ops_rows():
    m = json.loads((REF / "measurements_v3-2026-11-24.json").read_text(encoding="utf-8"))
    return [{"row": r} for r in m["detection_rows"]], [{"row": r} for r in m["conversion_rows"]]


def test_all_queries_are_select_only_and_cover_every_measure():
    q = em.build_queries()
    for name in ("funnel", "health_zero_item_ok", "health_invalid_content", "health_unswept", "duplicate_rows", "brief_duplication",
                 "recall_conversion", "replay_events", "storage_size", "storage_growth", "recall_detection_0", "recall_detection_2"):
        assert name in q
    for name, sql in q.items():
        body = re.sub(r"'[^']*'", "''", sql)
        assert not re.search(r"\b(insert|update|delete|drop|alter|create|truncate|grant)\b\s", body, re.IGNORECASE), name
        assert re.match(r"\s*(--[^\n]*\n\s*)*(with|select)\b", sql, re.IGNORECASE), name


def test_sweep_start_must_be_a_timestamp():
    import pytest
    with pytest.raises(ValueError):
        em.build_queries("2026-11-24'; drop table x; --")


def test_funnel_reproduces_pack_chain():
    f = em.compute_funnel([{"sources": 115, "items": 2413, "ok_sources": 115, "not_ok_sources": 0, "events": 230, "suppressed": 124, "relevant": 3, "briefed": 1}])
    assert f["chain"] == [2413, 230, 3]                    # briefed is no longer a chain stage
    assert "pct_items_to_events" not in f and "pct_relevant_to_briefed" not in f
    assert f["briefed_events"] == 1 and f["briefed"]["ori_brief_id_events"] == 1
    assert f["briefed"]["disposition_brief_or_escalate"] == em.NOT_MEASURED and f["briefed"]["morning_brief_incident_ids"] == em.NOT_MEASURED
    assert "ORI" in f["briefed"]["definition"] and "not a conversion" in f["items_vs_events_note"] or "no conversion" in f["items_vs_events_note"]


def test_briefed_by_path_side_by_side_and_markdown_has_no_items_to_events_percentage():
    row = {"sources": 115, "items": 2413, "ok_sources": 115, "not_ok_sources": 0, "events": 230, "suppressed": 124, "relevant": 3, "briefed": 1,
           "disp_brief": 59, "relevant_disp_brief": 12}
    bd = {"status": "MEASURED", "latest_morning_with_incident_ids": {"brief_date": "2026-11-25", "ids": 9, "mentions": 21}}
    f = em.compute_funnel([row], bd)
    assert f["briefed"]["ori_brief_id_events"] == 1 and f["briefed"]["disposition_brief_or_escalate"] == 59 and f["briefed"]["morning_brief_incident_ids"] == 9
    md = em.render_markdown(em.compute_all({"funnel": [row], "brief_duplication": []}))
    assert "9.5%" not in md and "items to events 9" not in md and "ORI brief_id events 1" in md


def test_recall_regexes_are_bounded_and_do_not_cross_lines():
    import re
    rx = em.bound_regex(r"\mNAB\M.*(outage|down|restor|disrupt)")
    assert ".*" not in rx
    far = "NAB announces results.\n" + "x" * 500 + " the market is down today"
    near = "NAB app outage hits customers"
    py = lambda t: re.search(rx.replace("\\m", r"\b").replace("\\M", r"\b"), t, re.IGNORECASE)
    assert py(near) and not py(far)
    assert ".*" not in "".join(sp[1] for sp in em._recall_specs()[1])


def test_emitted_recall_sql_has_no_unbounded_gap():
    q = em.build_queries()
    for k in ("recall_detection_0", "recall_conversion"):
        assert "[^\\n]{0,60}" in q[k]
        assert ".*" not in q[k].replace("[^\\n]{0,60}", "")


def test_recall_reproduces_15_of_27_from_frozen_measurement_rows():
    det, conv = _ops_rows()
    r = em.compute_recall(det, conv)
    assert (r["reached_a_brief"], r["records"]) == (15, 27)
    assert [round(x, 2) for x in r["wilson_95"]] == [0.37, 0.72]
    assert {"RS-062", "RS-079", "RS-081"} <= set(r["not_reached"])


def test_missing_rows_are_not_measured_never_estimated():
    assert em.compute_funnel(None)["status"] == em.NOT_MEASURED
    assert em.compute_recall(None, None)["status"] == em.NOT_MEASURED
    assert em.compute_replay(None)["status"] == em.NOT_MEASURED
    m = em.compute_all({})
    assert all(m[k]["status"] == em.NOT_MEASURED for k in ("funnel", "selection_recall", "duplicate_rows", "replay", "brief_duplication", "storage_growth"))


def test_brief_duplication_ratio_and_truncation_flag():
    b = em.compute_brief_duplication([{"brief_date": "2026-11-25", "brief_type": "morning", "stored_length": 8000, "mentions": 21, "ids": 9},
                                      {"brief_date": "2026-11-24", "brief_type": "eod", "stored_length": 2000, "mentions": 0, "ids": 0}])
    lt = b["latest_morning_with_incident_ids"]
    assert (lt["mentions"], lt["ids"], lt["ratio"], lt["possibly_truncated"]) == (21, 9, 2.33, True)
    assert b["briefs"][1]["ratio"] is None


def test_duplicates_acceptance_depends_only_on_defect_checks():
    rows = [{"chk": "a", "kind": "defect", "n_keys": 0, "extra_rows": 0}, {"chk": "b", "kind": "informational", "n_keys": 5, "extra_rows": 5}]
    assert em.compute_duplicates(rows, None)["acceptance_zero_duplicate_rows"] is True
    rows[0].update(n_keys=1, extra_rows=2)
    assert em.compute_duplicates(rows, None)["acceptance_zero_duplicate_rows"] is False


def test_health_lists_flag_unswept_tier_1():
    h = em.compute_health([{"source_name": "Z"}], [{"source_name": "I"}, {"source_name": "I"}],
                          [{"source_name": "GitHub Status", "reliability_tier": "TIER_1", "last_health_at": "x"}])
    assert h["zero_item_ok_sources"]["n"] == 1 and h["invalid_content_sources"]["n"] == 1
    assert h["active_sources_not_swept"]["tier_1_unswept"] == ["GitHub Status"]


def test_replay_runs_current_tier_rules_offline():
    rows = [{"rid": "RS-081", "id": "e1", "source": "ABC News", "title": "Homes without power around Mildura after car hits power pole",
             "published_at": "2026-09-21 01:23:52+00", "collected_at": "2026-09-21 02:38:04+00", "brief_id": None, "suppressed": False,
             "disposition": "REFERENCE", "mission_relevance": "LOW_CONFIDENCE", "risk_rating": "LOW", "rank_score": "2.0", "geography": "GLOBAL"}]
    out = em.compute_replay(rows)
    rec = out["records"]["RS-081"]
    assert rec["status"] == "REPLAYED" and rec["events"] == 1 and rec["incident_tiers"]
    assert out["records"]["RS-062"]["status"] == "NO_EVENTS_MATCHED"


def test_markdown_states_the_effectiveness_caveat_and_tool_has_no_write_path():
    md = em.render_markdown(em.compute_all({}))
    assert "do not establish" in md and "source counts" in md
    src = Path(em.__file__).read_text(encoding="utf-8")
    for banned in ("requests", "urllib", "supabase", "psycopg", "socket", "subprocess", "os.environ", ".env"):
        assert banned not in src, banned
    assert "sweep_window" in em.compute_all({})
