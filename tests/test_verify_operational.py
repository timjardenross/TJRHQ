"""Offline tests for tools/intelligence/verify_operational.py: PASS needs evidence, 'not yet observable' stays separate."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.intelligence import verify_operational as vo

FIXTURE = Path(__file__).parent / "fixtures" / "verify_operational" / "production_2026-11-24.json"
DEPLOYED = datetime(2026, 11, 24, 6, 26, 32, tzinfo=timezone.utc)
NOW_LIVE = datetime(2026, 11, 24, 6, 59, 14, tzinfo=timezone.utc)


def live():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(results, now=NOW_LIVE, deployed=DEPLOYED):
    return {r.name: r for r in vo.evaluate(results, now=now, deployed_at=deployed, current=vo.read_checklist())}


def check(res, cap, cid):
    return next(c for c in res[cap].checks if c.id == cid)


# ── live snapshot (24 Nov 2026 07:00Z production export) ─────────────────────────────────────────────────────
def test_live_snapshot_verdicts_never_pass_without_evidence():
    res = run(live())
    assert {n: r.verdict for n, r in res.items()} == {
        "Discovery and collection": vo.FAIL,
        "Authoritative Australian and international sources": vo.FAIL,
        "Collection reliability and timeliness": vo.NYO,
        "Daily executive brief": vo.NYO,
        "Missed-brief detection and recovery": vo.NYO,
        "Live-cycle outputs (provenance labels, new-source rows, products, health, brief evidence)": vo.FAIL,   # ASIC/OAIC rows fail in this snapshot
        "Provenance and verified freshness": vo.NYO,
    }
    for r in res.values():
        for c in r.checks:
            assert c.verdict != vo.PASS or c.evidence, c.id


def test_live_snapshot_specifics():
    res = run(live())
    # ATO delivers, ASIC and OAIC do not, Optus/RBA were activated after the last sweep so are only 'not yet observable'
    assert check(res, "Authoritative Australian and international sources", "auth:ATO Online Services for Agents Status").verdict == vo.PASS
    assert check(res, "Authoritative Australian and international sources", "auth:ASIC News Centre").verdict == vo.FAIL
    assert check(res, "Authoritative Australian and international sources", "auth:OAIC").verdict == vo.FAIL
    assert check(res, "Authoritative Australian and international sources", "auth:Optus National Outage Register").verdict == vo.NYO
    assert check(res, "Authoritative Australian and international sources", "auth:RBA Media Releases").verdict == vo.NYO
    assert check(res, "Authoritative Australian and international sources", "firecrawl").verdict == vo.PASS
    # the 07:01 brief predates the release: its defects are informational only
    brief = res["Daily executive brief"]
    assert check(res, "Daily executive brief", "brief_row").verdict == vo.PASS
    for cid in ("brief_window", "false_live", "hist_guard"):
        c = check(res, "Daily executive brief", cid)
        assert c.verdict == vo.NYO and "before the release" in c.detail and "Informational: FAIL" in c.detail
    assert brief.verdict == vo.NYO
    # NVD paging cannot be judged before a post-release run
    for cid in ("nvd_volume", "nvd_duplicates", "nvd_newest"):
        assert check(res, "Discovery and collection", cid).verdict == vo.NYO
    assert check(res, "Discovery and collection", "feed_ceiling").verdict == vo.PASS
    assert check(res, "Provenance and verified freshness", "provenance").verdict == vo.NYO


def test_checklist_update_text_and_statuses():
    res = vo.evaluate(live(), now=NOW_LIVE, deployed_at=DEPLOYED, current=vo.read_checklist())
    text = vo.render(res, NOW_LIVE, DEPLOYED)
    assert "VERIFIED (PASS, evidenced): 0" in text and "NOT YET OBSERVABLE: 4" in text and "FAIL (defect observed): 3" in text
    assert "CHECKLIST UPDATE" in text
    status = {r.name: vo.propose(r)[0] for r in res}
    assert status["Daily executive brief"] == "Operational (no change)"      # currently Operational; not demoted on pre-release evidence
    assert status["Discovery and collection"] == "Partial"
    assert status["Provenance and verified freshness"] == "Partial (no change)"


def test_missing_results_are_not_yet_observable():
    res = run({})
    assert all(r.verdict == vo.NYO for r in res.values())
    assert all(c.verdict == vo.NYO for r in res.values() for c in r.checks)


def test_pass_without_evidence_is_downgraded():
    c = vo.Check("x", "t", vo.PASS, "looks fine", [])
    assert c.verdict == vo.NYO and "no evidence rows" in c.detail


def test_connector_wrapper_is_accepted():
    wrapped = "Below is the result\n<untrusted-data-abc>\n[{\"as_of\": \"2026-11-24 06:59:14+00\"}]\n</untrusted-data-abc>\nUse this data"
    assert vo.rows({"as_of": wrapped}, "as_of") == [{"as_of": "2026-11-24 06:59:14+00"}]


# ── a fully healthy scenario promotes on evidence ────────────────────────────────────────────────────────────
NOW_OK = datetime(2026, 11, 25, 5, 0, tzinfo=timezone.utc)      # after the 24 Nov 19:00Z sweep window and the 25 Nov 20:01Z brief of 24 Nov


def healthy():
    r = live()
    sweep = "2026-11-24 19:00:00+00"
    r["as_of"] = [{"as_of": "2026-11-25 05:00:00+00"}]
    r["_meta"] = {"window_events_complete": True, "sources_complete": True}
    r["sweep_days"] = [{"sweep_start": sweep, "checks": 400, "sources": 111, "ok": 396, "not_ok": 4}] + r["sweep_days"][1:]
    r["sweep_items"] = [{"sweep_start": sweep, "items": 150, "sources": 22}] + r["sweep_items"][1:]
    r["sweep_failures"] = [{"source_name": "Melbourne Airport", "status": "degraded", "items_retrieved": 0, "content_valid": False, "error": "no items"}]
    r["heartbeats"] = [{"checked_at": "2026-11-24 19:01:30+00", "status": "ok", "detail": "sources=111 items=1200", "error_message": ""}]
    for s in r["sources"]:
        if s["source_name"] in ("ASIC News Centre", "ASIC Enforcement Activity", "Optus National Outage Register", "RBA Media Releases",
                                "ATO Online Services for Agents Status"):
            s.update(active=True, checks72=3, ok72=3, last_status="ok", last_valid=True, last_error="", n7=5, n24=5, last_items=5)
        if s["source_name"].startswith("OAIC"):
            s.update(active=False)
    r["nvd_runs"] = [{"run_minute": "2026-11-24 19:00:00+00", "items": 60, "distinct_hash": 60, "distinct_url": 60,
                      "oldest_published": "2026-11-23 01:00:00+00", "newest_published": "2026-11-24 18:30:00+00"}]
    r["nvd_totals"] = [{"total": 220, "distinct_hash": 220, "distinct_url": 220, "post_deploy_items": 60}]
    base = datetime(2026, 11, 24, 7, 0, tzinfo=timezone.utc)
    r["itnews_checks"] = [{"checked_at": (base + timedelta(minutes=90 * i)).isoformat(), "status": "ok", "items_retrieved": 20} for i in range(5)]
    r["briefs"].insert(0, {**r["briefs"][0], "brief_date": "2026-11-25", "generated_at": "2026-11-24 20:01:09+00"})
    text = ("EVIDENCE-BASED PICTURE\nBased on reports from the last 24 hours.\n\nOperational situation: none.\n"
            "OTHER SIGNALS (24h; not evidence-checked)\n  \U0001F534 ABC News: Storms hit Qld coast\n")
    r["latest_morning_brief"] = [{"brief_type": "morning", "brief_date": "2026-11-25", "generated_at": "2026-11-24 20:01:09+00",
                                  "evidence_window_hours": 24, "collection_caveat": None, "brief_text": text}]
    r["window_events"] = [
        {"event_id": "a1", "raw_title": "Storms hit Qld coast", "raw_summary": "", "geography": "AU", "collected_at": "2026-11-24 10:00:00+00",
         "published_at": "2026-11-24 09:30:00+00", "suppressed": False, "signal_status": "SCORED", "source_name": "ABC News"},
        {"event_id": "a2", "raw_title": "Optus outage of 3 October resolved after fault", "raw_summary": "", "geography": "AU",
         "collected_at": "2026-11-24 12:00:00+00", "published_at": "2026-10-03 12:00:00+00", "suppressed": False, "signal_status": "SCORED",
         "source_name": "Optus National Outage Register"},
        {"event_id": "a3", "raw_title": "ASIC release from three weeks ago about a penalty", "raw_summary": "", "geography": "AU",
         "collected_at": "2026-11-24 12:05:00+00", "published_at": "2026-11-03 02:00:00+00", "suppressed": False, "signal_status": "SCORED",
         "source_name": "ASIC News Centre"},
    ]
    r["high_line_events"] = []
    r["provenance_days"] = [{"collected_day": "2026-11-24 00:00:00+00", "total": 300, "publisher_domain": 300, "publisher_family": 300,
                             "published_at_basis": 300, "published_at_precision": 300, "published_at_confidence": 300},
                            {"collected_day": "2026-11-23 00:00:00+00", "total": 300, "publisher_domain": 10, "publisher_family": 10,
                             "published_at_basis": 300, "published_at_precision": 300, "published_at_confidence": 300}]
    r["external_fetch_usage"] = [{"provider": "firecrawl", "billing_cycle_start": "2026-11-09", "billing_cycle_end": "2026-12-09", "call_count": 600,
                                  "updated_at": "2026-11-25 04:50:00+00"}]
    r["deadman_journal"] = [{"line": "Nov 24 21:00:01 intelligence-scheduler: Brief deadman: ok"}]
    return r


def test_healthy_scenario_promotes_discovery_and_brief():
    res = run(healthy(), now=NOW_OK)
    assert res["Discovery and collection"].verdict == vo.PASS, [(c.id, c.verdict, c.detail) for c in res["Discovery and collection"].checks]
    assert vo.propose(res["Discovery and collection"])[0] == "Operational"
    assert res["Daily executive brief"].verdict == vo.PASS, [(c.id, c.verdict, c.detail) for c in res["Daily executive brief"].checks]
    guard = check(res, "Daily executive brief", "hist_guard")
    assert "2 retrospective row(s)" in guard.detail
    assert res["Collection reliability and timeliness"].verdict == vo.PASS
    assert res["Provenance and verified freshness"].verdict == vo.PASS      # one full day after the first populated day, >=95%
    assert vo.propose(res["Provenance and verified freshness"])[0] == "Partial"   # activation/approval are decisions: never auto-Operational


def test_authoritative_pass_is_partial_not_operational():
    res = run(healthy(), now=NOW_OK)
    auth = res["Authoritative Australian and international sources"]
    assert check(run(healthy(), now=NOW_OK), auth.name, "auth:OAIC").verdict == vo.NYO     # inactive: not judged
    assert auth.verdict == vo.NYO
    # not yet observable: the proposal never changes the checklist status, whatever the live checklist currently says
    assert vo.propose(auth)[0] == f"{auth.current} (no change)"
    # covers_all is False: even a clean PASS only ever proposes Partial
    forced = vo.CapResult(auth.name, vo.PASS, [vo.Check("c", "t", vo.PASS, "d", [{"k": 1}])], False, "Telstra etc.")
    assert vo.propose(forced)[0] == "Partial"


# ── historical-import guard / false live lines / URGENT ─────────────────────────────────────────────────────
def test_guard_fails_when_a_retrospective_title_is_in_the_brief():
    r = healthy()
    r["latest_morning_brief"][0]["brief_text"] += "\n  \U0001F534 Optus outage of 3 October resolved after fault\n"
    res = run(r, now=NOW_OK)
    g = check(res, "Daily executive brief", "hist_guard")
    assert g.verdict == vo.FAIL and "appear in the stored brief text" in g.detail
    assert res["Daily executive brief"].verdict == vo.FAIL


def test_guard_not_yet_observable_without_any_historical_row():
    r = healthy()
    r["window_events"] = r["window_events"][:1]
    assert check(run(r, now=NOW_OK), "Daily executive brief", "hist_guard").verdict == vo.NYO


def test_false_live_high_line_for_old_item_fails():
    r = healthy()
    r["latest_morning_brief"][0]["brief_text"] += "\n  \U0001F534 ASIC News Centre: ASIC release from three weeks ago about a penalty\n"
    c = check(run(r, now=NOW_OK), "Daily executive brief", "false_live")
    assert c.verdict == vo.FAIL


def test_unmatched_high_line_cannot_pass():
    r = healthy()
    r["latest_morning_brief"][0]["brief_text"] += "\n  \U0001F534 Mystery headline nobody exported\n"
    assert check(run(r, now=NOW_OK), "Daily executive brief", "false_live").verdict == vo.NYO


def test_urgent_section_without_a_qualifying_incident_fails_when_window_complete():
    r = healthy()
    r["latest_morning_brief"][0]["brief_text"] += "\nURGENT TO VERIFY (potentially severe, not yet corroborated)\n- something\n"
    assert check(run(r, now=NOW_OK), "Daily executive brief", "urgent").verdict == vo.FAIL
    r["_meta"]["window_events_complete"] = False
    assert check(run(r, now=NOW_OK), "Daily executive brief", "urgent").verdict == vo.NYO


def test_incomplete_window_never_confirms_absence_of_urgent():
    r = healthy()
    r["_meta"]["window_events_complete"] = False
    assert check(run(r, now=NOW_OK), "Daily executive brief", "urgent").verdict == vo.NYO


def test_missing_window_wording_fails_on_a_post_release_brief():
    r = healthy()
    r["latest_morning_brief"][0]["brief_text"] = r["latest_morning_brief"][0]["brief_text"].replace("Based on reports from the last 24 hours.", "")
    assert check(run(r, now=NOW_OK), "Daily executive brief", "brief_window").verdict == vo.FAIL


# ── missed brief ─────────────────────────────────────────────────────────────────────────────────────────────
def test_missed_brief_exercised_needs_alert_and_extended_lookback():
    r = healthy()
    r["briefs"] = [dict(r["briefs"][0]), {**r["briefs"][1], "brief_date": "2026-11-23"}, {**r["briefs"][1], "brief_date": "2026-11-21"}]
    r["briefs"][0].update(brief_date="2026-11-25", evidence_window_hours=48)
    r["briefs"][1]["evidence_window_hours"] = 48
    r["deadman_journal"] = [{"line": "Brief deadman: alerted 2026-11-22"}, {"line": "Brief deadman: ok"}]
    # 22 Nov missing: alert present, next brief (23 Nov) extended to 48h
    assert check(run(r, now=NOW_OK), "Missed-brief detection and recovery", "miss_exercised").verdict == vo.PASS
    r["deadman_journal"] = [{"line": "Brief deadman: ok"}]
    assert check(run(r, now=NOW_OK), "Missed-brief detection and recovery", "miss_exercised").verdict == vo.FAIL
    del r["deadman_journal"]
    assert check(run(r, now=NOW_OK), "Missed-brief detection and recovery", "miss_exercised").verdict == vo.NYO


def test_deadman_alert_with_brief_row_present_fails():
    r = healthy()
    r["deadman_journal"] = [{"line": "MISSED BRIEF: no morning brief exists for 2026-11-25"}]
    assert check(run(r, now=NOW_OK), "Missed-brief detection and recovery", "deadman_quiet").verdict == vo.FAIL


def test_brief_row_missing_after_deadman_hour_fails_but_early_is_nyo():
    r = healthy()
    r["briefs"] = []
    late = datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc)      # 09:00 AEST on the 25th
    assert check(run(r, now=late), "Missed-brief detection and recovery", "brief_row").verdict == vo.FAIL
    early = datetime(2026, 11, 24, 20, 30, tzinfo=timezone.utc)    # 06:30 AEST
    assert check(run(r, now=early), "Missed-brief detection and recovery", "brief_row").verdict == vo.NYO


# ── NVD / sweep / firecrawl / provenance ───────────────────────────────────────────────────────────────────
def test_nvd_stale_newest_and_duplicates_fail():
    r = healthy()
    r["nvd_runs"][0]["newest_published"] = "2026-11-15 22:17:18+00"
    assert check(run(r, now=NOW_OK), "Discovery and collection", "nvd_newest").verdict == vo.FAIL
    r["nvd_totals"][0]["distinct_hash"] = 200
    assert check(run(r, now=NOW_OK), "Discovery and collection", "nvd_duplicates").verdict == vo.FAIL
    r["nvd_runs"][0]["items"] = 400
    assert check(run(r, now=NOW_OK), "Discovery and collection", "nvd_volume").verdict == vo.FAIL


def test_sweep_missing_after_window_fails_and_open_window_is_nyo():
    r = healthy()
    r["sweep_days"][0]["checks"] = 0
    assert check(run(r, now=NOW_OK), "Discovery and collection", "sweep_ran").verdict == vo.FAIL
    assert check(run(r, now=datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)), "Discovery and collection", "sweep_ran").verdict == vo.NYO


def test_priority_source_failing_in_sweep_fails_even_when_ratio_is_high():
    r = healthy()
    r["sweep_failures"] = [{"source_name": "RBA Media Releases", "status": "failed", "items_retrieved": 0, "content_valid": None, "error": "403"}]
    c = check(run(r, now=NOW_OK), "Discovery and collection", "source_health")
    assert c.verdict == vo.FAIL and "RBA Media Releases" in c.detail


@pytest.mark.parametrize(("count", "updated", "expected"), [
    (1800, "2026-11-25 04:50:00+00", vo.FAIL),          # over ceiling
    (1500, "2026-11-25 04:50:00+00", vo.FAIL),          # projected over ceiling
    (600, "2026-11-20 04:50:00+00", vo.NYO),            # counter stale: not metered live
    (600, "2026-11-25 04:50:00+00", vo.PASS),
])
def test_firecrawl_ceiling(count, updated, expected):
    r = healthy()
    r["external_fetch_usage"][0].update(call_count=count, updated_at=updated)
    assert check(run(r, now=NOW_OK), "Authoritative Australian and international sources", "firecrawl").verdict == expected


def test_provenance_pass_fail_nyo():
    r = healthy()
    r["provenance_days"] = r["provenance_days"][:1]
    assert check(run(r, now=NOW_OK), "Provenance and verified freshness", "provenance").verdict == vo.NYO   # activation day only
    r = healthy()
    r["provenance_days"][1].update(collected_day="2026-11-22 00:00:00+00")
    r["provenance_days"].append({"collected_day": "2026-11-23 00:00:00+00", "total": 300, "publisher_domain": 299, "publisher_family": 299,
                                 "published_at_basis": 300, "published_at_precision": 300, "published_at_confidence": 300})
    assert check(run(r, now=NOW_OK), "Provenance and verified freshness", "provenance").verdict == vo.PASS
    r["provenance_days"][-1]["publisher_domain"] = 100
    assert check(run(r, now=NOW_OK), "Provenance and verified freshness", "provenance").verdict == vo.FAIL


def test_source_states_not_judged_on_a_narrowed_export():
    r = live()
    assert check(run(r), "Collection reliability and timeliness", "source_states").verdict == vo.NYO
    r["_meta"]["sources_complete"] = True
    c = check(run(r), "Collection reliability and timeliness", "source_states")
    assert c.verdict == vo.PASS and "BROKEN" in c.detail


# ── SQL and CLI ───────────────────────────────────────────────────────────────────────────────────────────────
def test_all_printed_sql_is_select_only():
    for sub in (False, True):
        for name, sql in vo.build_queries(subset=sub).items():
            low = sql.strip().lower()
            assert low.startswith(("select", "with")), name
            for bad in (" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " create ", " grant "):
                assert bad not in f" {low} ", (name, bad)
    assert "pg_" not in " ".join(vo.build_queries().values()).lower()


def test_followup_sql_targets_high_lines_and_escapes_quotes():
    r = live()
    q = vo.followup_sql(r)["high_line_events"]
    assert q.lower().startswith("select") and "ilike any" in q and "storms to hit south-western qld" in q
    r["latest_morning_brief"][0]["brief_text"] = "\U0001F534 ABC: It's 100% a test_title"
    q = vo.followup_sql(r)["high_line_events"]
    assert "it''s 100\\% a test\\_title" in q


def test_cli_print_sql_and_results(tmp_path, capsys):
    assert vo.main(["--print-sql"]) == 0
    out = capsys.readouterr().out
    assert out.count("-- name:") == len(vo.build_queries()) and "-- name: window_events" in out
    guard = hashlib.sha256(vo.CHECKLIST.read_bytes()).hexdigest()
    assert vo.main(["--results", str(FIXTURE), "--json"]) == 1                  # FAIL present -> exit 1
    data = json.loads(capsys.readouterr().out)
    assert {c["verdict"] for c in data["capabilities"]} == {vo.FAIL, vo.NYO}
    assert all("proposed_status" in c and "evidence_summary" in c for c in data["capabilities"])
    assert vo.main(["--results", str(FIXTURE)]) == 1
    assert "CHECKLIST UPDATE" in capsys.readouterr().out
    assert hashlib.sha256(vo.CHECKLIST.read_bytes()).hexdigest() == guard    # the checklist is never edited


def test_cli_exit_zero_without_failures(tmp_path, capsys):
    p = tmp_path / "r.json"
    p.write_text(json.dumps(copy.deepcopy(healthy())), encoding="utf-8")
    code = vo.main(["--results", str(p), "--now", "2026-11-25T05:00:00Z"])
    out = capsys.readouterr().out
    assert code == 0 and "FAIL (defect observed): 0" in out and "VERIFIED (PASS, evidenced): 4" in out
    assert "? Missed-brief detection and recovery" in out and "? Authoritative Australian" in out
