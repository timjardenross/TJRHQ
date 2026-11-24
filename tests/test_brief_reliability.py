"""Offline tests: misfire grace, missed-brief deadman, gap-aware lookback (9-13 Sep 2026 pattern)."""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from intelligence import brief_reliability as br
from intelligence import captains_brief as cb

NOW = datetime(2026, 9, 12, 21, 0, tzinfo=timezone.utc)   # 13 Sep 07:00 AEST: first brief attempt after the gap


def _gen(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


# -- (1) misfire grace -----------------------------------------------------------------------------------------------------------
def test_job_kwargs_are_generous_and_coalesced():
    kw = br.job_kwargs(br.MORNING_GRACE_SECONDS)
    assert kw == {"coalesce": True, "max_instances": 1, "misfire_grace_time": 10800}
    assert br.MORNING_GRACE_SECONDS > 1 and br.EOD_GRACE_SECONDS >= 3600


def test_scheduler_brief_jobs_register_grace_and_deadman():
    import inspect

    from intelligence import scheduler
    src = inspect.getsource(scheduler._start_scheduler)
    for jid in ("captains_morning_brief", "captains_midday_check", "captains_eod_brief", "captains_weekly_brief", "captains_brief_deadman"):
        block = src.split(f'id="{jid}"', 1)[1].split(")", 2)[0] + src.split(f'id="{jid}"', 1)[1][:200]
        assert "job_kwargs" in block, jid


def test_apscheduler_late_job_runs_within_grace_but_not_default():
    import pytest
    pytest.importorskip("apscheduler.schedulers.background")  # a stubbed top-level package (other tests) must not defeat the skip
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger

    s = BackgroundScheduler()
    late = datetime.now(timezone.utc) - timedelta(minutes=30)
    ran = []
    s.add_job(lambda: ran.append("grace"), DateTrigger(run_date=late), id="a", **br.job_kwargs(br.MORNING_GRACE_SECONDS))
    s.add_job(lambda: ran.append("default"), DateTrigger(run_date=late), id="b")
    s.start()
    import time
    time.sleep(1.0)
    s.shutdown()
    assert ran == ["grace"]


# -- (2) deadman -----------------------------------------------------------------------------------------------------------------
def _sb(rows, calls=None):
    def f(table, query=""):
        if calls is not None:
            calls.append(query)
        if isinstance(rows, Exception):
            raise rows
        return rows
    return f


def test_deadman_alerts_once_when_row_missing():
    sent, seen = [], set()
    assert br.check_missed_brief(_sb([]), lambda t: sent.append(t) or True, "2026-09-10", alerted=seen) == "alerted"
    assert br.check_missed_brief(_sb([]), lambda t: sent.append(t) or True, "2026-09-10", alerted=seen) == "already_alerted"
    assert len(sent) == 1 and "2026-09-10" in sent[0]
    assert br.check_missed_brief(_sb([]), lambda t: sent.append(t) or True, "2026-09-11", alerted=seen) == "alerted"


def test_deadman_quiet_when_row_exists_or_unverifiable_or_deliberate_skip(monkeypatch):
    sent = []
    n = lambda t: sent.append(t) or True
    assert br.check_missed_brief(_sb([{"brief_date": "x"}]), n, "2026-09-10", alerted=set()) == "ok"
    assert br.check_missed_brief(_sb(RuntimeError("db down")), n, "2026-09-10", alerted=set()) == "unverified"
    monkeypatch.setenv("BRIEF_DEADMAN_SKIP_DATES", "2026-12-25, 2026-09-10")
    assert br.check_missed_brief(_sb([]), n, "2026-09-10", alerted=set()) == "skipped"
    assert sent == []


def test_deadman_retries_if_alert_delivery_failed():
    seen = set()
    assert br.check_missed_brief(_sb([]), lambda t: False, "2026-09-10", alerted=seen) == "unverified"
    assert br.check_missed_brief(_sb([]), lambda t: True, "2026-09-10", alerted=seen) == "alerted"


def test_brief_date_matches_persist_convention():
    assert br.brief_date_aest(datetime(2026, 9, 12, 22, 0, tzinfo=timezone.utc)) == "2026-09-13"


# -- (4) gap-aware lookback ------------------------------------------------------------------------------------------------------
def test_normal_cycle_is_exactly_24h():
    for h in (23.9, 24.0, 25.0, 29.9):
        assert br.compute_gap(NOW - timedelta(hours=h), NOW).lookback_hours == 24
    assert not br.compute_gap(NOW - timedelta(hours=24), NOW).missed
    assert br.get_gap(_sb([]), "2026-09-13", NOW) is br.NO_GAP
    assert br.get_gap(_sb(RuntimeError("x")), "2026-09-13", NOW) is br.NO_GAP


def test_gap_extends_and_caps_at_72h():
    g = br.compute_gap(NOW - timedelta(hours=48), NOW, "2026-09-08")   # 9-12 Sep pattern: last brief 8 Sep morning (~97h would cap)
    assert g.lookback_hours == 50 and g.missed and not g.capped
    g = br.compute_gap(NOW - timedelta(hours=97), NOW, "2026-09-08")
    assert g.lookback_hours == 72 and g.capped


def test_coverage_note_text():
    assert br.coverage_note(br.NO_GAP) == []
    g = br.compute_gap(NOW - timedelta(hours=97), NOW, "2026-09-08")
    note = " ".join(br.coverage_note(g, "intelligence_collection reported a failure"))
    assert "COVERAGE LIMITED" in note and "since 2026-09-08" in note and "72h" in note and "capped" in note and "intelligence_collection" in note


# -- morning brief integration ---------------------------------------------------------------------------------------------------
def _events(now):
    def ev(title, hours_ago, rank, rel):
        ts = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"raw_title": title, "event_type": "outage", "geography": "AU", "operational_relevance": rel, "confidence": 0.9,
                "rank_score": rank, "raw_summary": "", "collected_at": ts, "intelligence_source_registry": {"source_name": "iTnews"}}
    return [ev("Optus network outage hits triple-zero", 30, 5.0, 0.95), ev("Routine vendor patch", 3, 1.0, 0.7)]


def _fake_get(events):
    def f(table, query=""):
        if table != "intelligence_events":
            return []
        since = urllib.parse.parse_qs(query.replace("&", "&"))["collected_at"][0].replace("gte.", "")
        return [e for e in events if e["collected_at"] >= since]
    return f


def _render(gap, events, now):
    real = cb._get_recent_signals

    def recent(hours=24, limit=12):
        with patch.object(cb, "_sb_get", _fake_get(events)), patch("intelligence.captains_brief.datetime") as dt:
            dt.now.side_effect = lambda tz=None: now.astimezone(tz) if tz else now
            return real(hours=hours, limit=limit)
    with patch.object(cb, "_get_latest_ori_brief", return_value=None), \
         patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", side_effect=recent) as rs, \
         patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "_now_aest", return_value=now.astimezone(timezone(timedelta(hours=10)))), \
         patch.object(cb, "build_daily_digest", None), \
         patch.object(cb, "_evidence_lines", return_value=[]), patch.object(cb, "_theme_lines", return_value=[]), \
         patch.object(cb, "_health_lines", return_value=[]), patch.object(cb, "_coverage_lines", return_value=[]):
        return cb.generate_morning_brief(gap), rs


def test_optus_event_from_gap_appears_in_first_brief_after_gap_and_not_with_24h_window():
    events = _events(NOW)   # Optus item collected 30h ago, i.e. during the missed 12 Sep morning
    text24, rs24 = _render(br.NO_GAP, events, NOW)
    assert "Optus" not in text24 and rs24.call_args.kwargs["hours"] == 24      # today's behaviour: silently lost
    gap = br.compute_gap(NOW - timedelta(hours=97), NOW, "2026-09-08")
    text72, rs72 = _render(gap, events, NOW)
    assert "Optus network outage" in text72 and rs72.call_args.kwargs["hours"] == 72
    assert "COVERAGE LIMITED" in text72


def test_no_gap_output_is_byte_identical_to_default_path():
    events = _events(NOW)
    explicit, _ = _render(br.NO_GAP, events, NOW)
    # a normal prior brief (24h ago) resolves to NO-GAP-equivalent window, text and call args
    normal = br.compute_gap(NOW - timedelta(hours=24), NOW, "2026-09-12")
    again, rs = _render(normal, events, NOW)
    assert again == explicit and rs.call_args.kwargs["hours"] == 24
    assert "COVERAGE LIMITED" not in explicit and "⚠️" not in explicit
    assert "Routine vendor patch" in explicit


# -- (6) startup catch-up ----------------------------------------------------------------------------------------------------------
def _cu(rows, now, done=None, sent=None):
    sent = [] if sent is None else sent
    return br.catch_up_morning(_sb(rows), lambda: sent.append(1) or True, now, done=set() if done is None else done), sent


def test_catch_up_fires_once_after_cron_time_with_no_row():
    done, sent = set(), []
    now = datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc)   # 10:30 AEST
    assert _cu([], now, done, sent)[0] == "sent"
    assert _cu([], now, done, sent)[0] == "already_done"
    assert sent == [1]


def test_catch_up_does_nothing_when_row_exists_early_late_or_unverified():
    sent = []
    assert _cu([{"brief_date": "x"}], datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc), sent=sent)[0] == "exists"
    assert _cu([], datetime(2026, 9, 12, 20, 30, tzinfo=timezone.utc), sent=sent)[0] == "too_early"   # 06:30 AEST
    assert _cu([], datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc), sent=sent)[0] == "too_late"      # 12:00 AEST
    assert _cu(RuntimeError("db"), datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc), sent=sent)[0] == "unverified"
    assert sent == []


def test_catch_up_brief_is_marked_late_and_default_is_unchanged():
    default, _ = _render(br.NO_GAP, _events(NOW), NOW)
    assert "LATE BRIEF" not in default and "⚠️" not in default
    with patch.object(cb, "_get_latest_ori_brief", return_value=None), patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", return_value=[]), patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "build_daily_digest", None), patch.object(cb, "_evidence_lines", return_value=[]), \
         patch.object(cb, "_theme_lines", return_value=[]), patch.object(cb, "_health_lines", return_value=[]), \
         patch.object(cb, "_coverage_lines", return_value=[]):
        late = cb.generate_morning_brief(br.NO_GAP, None, catch_up=True)
    assert "LATE BRIEF" in late
