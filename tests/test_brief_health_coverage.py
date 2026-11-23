"""Health watch and coverage blocks for the Morning brief (both default OFF)."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_coverage as bc
from intelligence import brief_health as bh

NOW = datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for f in (bh.MASTER_FLAG, bh.MORNING_FLAG, bc.MASTER_FLAG, bc.MORNING_FLAG):
        monkeypatch.delenv(f, raising=False)


def sig(title, desc="", rank=0.5, safety=False, fda=False, source="Europe PMC", collected="2026-11-22T00:00:00Z", **kw):
    return {"signal_id": title, "title": title, "description": desc, "rank_score": rank, "safety_relevance": safety, "fda_flagged": fda,
            "collected_at": collected, "health_source_registry": {"source_name": source}, **kw}


# ── health: selection ────────────────────────────────────────────────────────────────────────────────────────────
def test_only_monitored_conditions_are_selected_not_generic_mental_health():
    rows = [sig("Virtual reality for ICU patients: a meta-analysis", "anxiety and depression outcomes"),
            sig("Music therapy for nursing students", "stress"),
            sig("Methylphenidate and executive function in adults with ADHD", rank=0.7),
            sig("Pregabalin for neuropathic pain: trial results", rank=0.6)]
    matched, safety = bh.select(rows, bh.load_watchlist())
    assert [m.condition for m in matched] == ["Neurodivergence", "Chronic pain"]
    assert not safety


@pytest.mark.parametrize("title", ["Fibromyalgia and sleep", "Autistic masking in adults", "AuDHD diagnosis in women", "CPAP adherence in sleep apnoea",
                                   "Burnout among clinicians", "Chronic pain self-management", "Sensory processing differences"])
def test_each_monitored_term_matches(title):
    matched, _ = bh.select([sig(title)], bh.load_watchlist())
    assert len(matched) == 1


@pytest.mark.parametrize("title", ["Mask mandates and respiratory infection", "Cuttlefish camouflage patterns", "Statin therapy in older adults",
                                   "Virtual reality for ICU patients", "Oral health in children"])
def test_unrelated_titles_do_not_match(title):
    matched, _ = bh.select([sig(title)], bh.load_watchlist())
    assert matched == []


@pytest.mark.parametrize("title", ["Limitations of transmucosal ketamine for chronic pain in dogs", "Fibromyalgia-like pain in a mouse model",
                                   "ADHD-like behaviour in rats"])
def test_animal_studies_are_excluded(title):
    matched, _ = bh.select([sig(title)], bh.load_watchlist())
    assert matched == []


def test_a_flagged_animal_study_still_shows_as_safety():
    _, safety = bh.select([sig("Adverse events in dogs given drug X", safety=True)], bh.load_watchlist())
    assert len(safety) == 1


def test_safety_signals_always_show_even_without_a_monitored_term():
    rows = [sig("Serious adverse events reported for drug X", safety=True), sig("Recall of device Y", fda=True),
            sig("ADHD medication shortage and adverse events", safety=True)]
    matched, safety = bh.select(rows, bh.load_watchlist())
    assert len(safety) == 3 and not matched
    assert {p.condition for p in safety} == {None, "Neurodivergence"}


def test_a_signal_appears_once_and_duplicates_collapse():
    rows = [sig("ADHD in adults: new trial", rank=0.4), sig("ADHD in Adults - New Trial!", rank=0.9, source="Other")]
    matched, _ = bh.select(rows, bh.load_watchlist())
    assert len(matched) == 1 and matched[0].source == "Other"      # the higher-ranked copy wins


def test_limits_and_ranking():
    rows = [sig(f"ADHD study {i}", rank=i / 10) for i in range(9)] + [sig(f"Safety item {i}", safety=True) for i in range(6)]
    matched, safety = bh.select(rows, bh.load_watchlist(), NOW)
    assert len(safety) == bh.MAX_SAFETY and matched[0].title == "ADHD study 8"
    lines = bh.format_lane(matched, safety)
    assert sum(1 for x in lines if x.startswith("- Neurodivergence")) == bh.MAX_MATCHED
    assert sum(1 for x in lines if x.startswith("- SAFETY")) == bh.MAX_SAFETY


def test_newer_wins_among_equal_ranks():
    rows = [sig("ADHD old", collected="2026-11-10T00:00:00Z"), sig("ADHD new", collected="2026-11-22T00:00:00Z")]
    matched, _ = bh.select(rows, bh.load_watchlist())
    assert matched[0].title == "ADHD new"


# ── health: lines, flag, failure ─────────────────────────────────────────────────────────────────────────────────
def fake_sb(rows_by_table):
    def get(table, query=""):
        v = rows_by_table.get(table)
        if isinstance(v, Exception):
            raise v
        return v if v is not None else []
    return get


def test_health_flag_off_is_empty(monkeypatch):
    assert bh.health_lines(fake_sb({"health_signals": [sig("ADHD x")]})) == []


def test_health_lines_when_on(monkeypatch):
    monkeypatch.setenv(bh.MORNING_FLAG, "1")
    lines = bh.health_lines(fake_sb({"health_signals": [sig("ADHD and executive function", study_design="RCT", sample_size=120),
                                                       sig("Drug X adverse events", safety=True)]}), now=NOW)
    assert lines[0].startswith("HEALTH WATCH")
    assert lines[1].startswith("- SAFETY") and lines[2].startswith("- Neurodivergence") and "randomised trial, 120 people" in lines[2]
    assert "RCT" not in "\n".join(lines) and "n=" not in "\n".join(lines) and "signals checked" not in lines[0]


# ── freshness and plain wording ───────────────────────────────────────────────────────────────────────────────
def test_fresh_items_come_first_and_old_ones_are_left_out_when_there_is_news():
    rows = [sig("ADHD old but top ranked", rank=0.9, collected="2026-11-10T00:00:00Z"),
            sig("ADHD fresh study", rank=0.2, collected="2026-11-23T10:00:00Z")]
    lines = bh.format_lane(*bh.select(rows, bh.load_watchlist(), NOW))
    assert any("ADHD fresh study" in x for x in lines)
    assert not any("old but top ranked" in x for x in lines)           # yesterday's top item does not repeat when something is new


def test_a_quiet_two_days_says_so_then_shows_the_most_recent_older_items():
    rows = [sig(f"Fibromyalgia study {i}", rank=i / 10, collected="2026-11-12T00:00:00Z") for i in range(6)]
    lines = bh.format_lane(*bh.select(rows, bh.load_watchlist(), NOW))
    assert "Nothing new in the last two days" in lines[1]
    assert sum(1 for x in lines if x.startswith("  - Chronic pain")) == bh.MAX_OLDER


def test_the_two_day_boundary():
    inside = sig("ADHD inside", collected="2026-11-21T22:30:00Z")        # 47.5h before NOW
    outside = sig("ADHD outside", collected="2026-11-21T21:00:00Z")      # 49h before NOW
    m, _ = bh.select([inside, outside], bh.load_watchlist(), NOW)
    assert {p.title: p.fresh for p in m} == {"ADHD inside": True, "ADHD outside": False}


@pytest.mark.parametrize("row,expected", [
    ({"description": "Status: NOT_YET_RECRUITING. Conditions: Autism.", "sample_size": 680}, "registered trial, not yet recruiting, 680 people"),
    ({"description": "Status: RECRUITING. Conditions: ADHD.", "sample_size": None}, "registered trial, now recruiting"),
    ({"description": "Status: COMPLETED. Conditions: Fibromyalgia.", "sample_size": 100}, "registered trial, completed, 100 people"),
    ({"description": "Status: ACTIVE_NOT_RECRUITING.", "sample_size": 131}, "registered trial, under way, 131 people"),
    ({"description": "", "study_design": "meta_analysis", "sample_size": 709}, "review of many studies"),
    ({"description": "x", "study_design": "RCT", "sample_size": 90}, "randomised trial, 90 people"),
    ({"description": "x", "study_design": "observational", "sample_size": None}, "observational study"),
    ({"description": "x", "study_design": None, "sample_size": None}, "study"),
])
def test_evidence_is_described_in_words(row, expected):
    assert bh._kind(row) == expected


def test_the_time_formats_the_database_returns_are_understood():
    want = datetime(2026, 11, 22, 2, 0, 48, tzinfo=timezone.utc)
    for v in ("2026-11-22 02:00:48+00", "2026-11-22T02:00:48Z", "2026-11-22T02:00:48+00:00", "2026-11-22 02:00:48"):
        assert bh._parse_time(v) == want, v
    assert bh._parse_time("2026-11-22 02:00:48.584851+00") == want.replace(microsecond=584851)
    assert bh._parse_time(None) is None and bh._parse_time("junk") is None


# ── coverage ─────────────────────────────────────────────────────────────────────────────────────────────────────
def ago(hours):
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(sid, hours):
    return {"source_id": sid, "collected_at": ago(hours)}


def reg(*pairs):
    """(id, name) or (id, name, category)"""
    return [{"source_id": p[0], "source_name": p[1], "category": p[2] if len(p) > 2 else "media"} for p in pairs]


def busy(sid, today=3, base=6):
    """A source that reports regularly: `base` reports across the earlier days, `today` in the last 24 hours."""
    return [ev(sid, 30 + 10 * i) for i in range(base)] + [ev(sid, 2 + i) for i in range(today)]


def checks(sid, statuses):
    return [{"source_id": sid, "status": st} for st in statuses]


def alerts(*sevs):
    return lambda limit=500: [{"severity": s, "jurisdiction": j} for s, j in sevs]


def cov(monkeypatch, registry, events, health=None, alert_rows=()):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    sb = fake_sb({"intelligence_source_registry": registry, "intelligence_events": events, "intelligence_source_health": health or []})
    return bc.coverage_lines(sb, alerts(*alert_rows), now=NOW)


def test_coverage_flag_off_is_empty():
    assert bc.coverage_lines(fake_sb({}), alerts()) == []


def test_a_normal_day_says_so_with_no_numbers(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("b", "Bloomberg")), busy("a") + busy("b"), checks("a", ["ok"] * 5))
    assert lines[0].startswith("COVERAGE") and lines[1] == "- Collection is normal today across your sources."
    assert not re.search(r"\d", "\n".join(lines[1:]))


def test_a_source_that_normally_reports_and_went_quiet_is_named(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("b", "Bloomberg")), busy("a") + busy("b", today=0))
    assert "Normally active but quiet in the last 24 hours: Bloomberg." in "\n".join(lines)
    assert "Collection is normal" not in "\n".join(lines)


def test_a_status_feed_that_is_quiet_because_nothing_is_wrong_is_not_a_gap(monkeypatch):
    # never reports (or only rarely): quiet is its normal state, so it must not be named
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("s", "Cloudflare Status"), ("r", "Rare Feed")),
                busy("a") + [ev("r", 40), ev("r", 60)], checks("a", ["ok"] * 4) + checks("s", ["ok"] * 4))
    text = "\n".join(lines)
    assert "Cloudflare Status" not in text and "Rare Feed" not in text and "Collection is normal today" in text


def test_feeds_failing_for_days_are_named_and_not_called_quiet(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("z", "ASIC News Centre")), busy("a") + busy("z", today=0),
                checks("z", ["failed", "degraded", "failed", "failed"]))
    text = "\n".join(lines)
    assert "Feeds failing for days (their silence is not good news): ASIC News Centre." in text
    assert "Normally active but quiet" not in text           # reported once, not twice


def test_a_feed_is_failing_only_if_every_recent_check_was_bad_and_there_were_enough(monkeypatch):
    registry = reg(("a", "ABC News"), ("x", "One Good Check"), ("y", "Only Two Checks"))
    lines = cov(monkeypatch, registry, busy("a"), checks("x", ["failed", "failed", "ok", "failed"]) + checks("y", ["failed", "failed"]))
    assert "Feeds failing for days" not in "\n".join(lines)


def test_wellness_feeds_going_quiet_are_not_a_coverage_gap(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("b", "Bloomberg"), ("w", "Greater Good Magazine", "wellness"), ("m", "Mindful.org", "wellness"),
                                 ("t", "MIT Sloan Management Review", "thought_leadership"), ("f", "Failing Wellness", "wellness")),
                busy("a") + busy("b") + busy("w", today=0) + busy("m", today=0) + busy("t", today=0) + busy("f", today=0),
                checks("a", ["ok"] * 4) + checks("b", ["ok"] * 4) + checks("f", ["failed"] * 4))
    text = "\n".join(lines)
    for name in ("Greater Good", "Mindful", "MIT Sloan", "Failing Wellness"):
        assert name not in text, name
    assert "Collection is normal today" in text


def test_a_thin_day_is_called_out(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("b", "Bloomberg")),
                [ev(s, 30 + 10 * i) for s in "ab" for i in range(6)] * 3 + [ev("a", 3)])
    assert "Collection is thin today" in lines[1]


def test_named_sources_are_capped(monkeypatch):
    registry = reg(*[(f"s{i}", f"S{i:02d}") for i in range(10)] + [("ok", "Reporter")])
    events = busy("ok") + [e for i in range(10) for e in busy(f"s{i}", today=0)]
    assert "and 4 more" in "\n".join(cov(monkeypatch, registry, events))


def test_unreadable_feed_health_is_stated_not_assumed_fine(monkeypatch):
    lines = cov(monkeypatch, reg(("a", "ABC News")), busy("a"), health=[])
    assert "- Feed health could not be checked." in lines
    assert "Collection is normal today" not in "\n".join(lines)


def test_unreadable_registry_or_events_is_could_not_be_checked_never_zero(monkeypatch):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    for tables in ({"intelligence_source_registry": RuntimeError("x")}, {"intelligence_source_registry": reg(("a", "A")), "intelligence_events": []}):
        lines = bc.coverage_lines(fake_sb(tables), alerts(), now=NOW)
        assert "could not be checked" in lines[1] and "normal" not in lines[1]


def test_warnings_name_where_and_the_most_serious_in_official_words():
    line = bc.warnings_line(alerts(("advice", "VIC"), ("watch_and_act", "TAS"), ("advice", "NSW"), ("unknown", "WA")))
    assert line == "- Official warnings are active in NSW, TAS, VIC, WA. Most serious: Watch and Act (TAS). Some have no stated severity."
    assert not re.search(r"\d", line)


def test_emergency_warning_outranks_the_rest():
    line = bc.warnings_line(alerts(("advice", "VIC"), ("emergency_warning", "NSW"), ("emergency_warning", "QLD"), ("watch_and_act", "TAS")))
    assert "Most serious: Emergency Warning (NSW, QLD)." in line


def test_only_advice_and_only_unknown_severities():
    assert "Most serious: Advice (WA)." in bc.warnings_line(alerts(("advice", "WA")))
    assert bc.warnings_line(alerts(("unknown", "SA"))) == "- Official warnings are active in SA, none with a stated severity."


def test_no_warnings_and_failed_hub_are_different_statements():
    assert bc.warnings_line(alerts()) == "- Official warnings: none active."

    def boom(limit=500):
        raise RuntimeError("hub down")
    assert "not an all-clear" in bc.warnings_line(boom)


def test_database_timestamp_formats_are_understood():
    want = datetime(2026, 11, 22, 2, 0, 48, tzinfo=timezone.utc)
    for v in ("2026-11-22 02:00:48+00", "2026-11-22T02:00:48Z", "2026-11-22T02:00:48+00:00", "2026-11-22 02:00:48"):
        assert bc._parse(v) == want, v
    assert bc._parse(None) is None and bc._parse("junk") is None


def test_morning_brief_hooks_add_nothing_when_flags_are_off():
    from intelligence import captains_brief as cb
    assert cb._health_lines() == [] and cb._coverage_lines() == []


def test_morning_brief_hooks_never_raise_when_on(monkeypatch):
    from intelligence import captains_brief as cb
    monkeypatch.setenv(bh.MORNING_FLAG, "1")
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    monkeypatch.setattr(cb, "_sb_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    health, coverage = cb._health_lines(), cb._coverage_lines()
    assert any("unavailable" in x.lower() for x in health), health          # a failed lane says so, it does not vanish or look quiet
    assert any("could not" in x.lower() for x in coverage), coverage


# ── stale collection and sample_size hygiene ─────────────────────────────────────────────────────────────────────
def _lane(rows, monkeypatch):
    monkeypatch.setenv(bh.MORNING_FLAG, "1")
    return bh.health_lines(fake_sb({"health_signals": rows}), now=NOW)


def test_quiet_message_flags_stale_health_collection(monkeypatch):
    lines = _lane([sig("Unrelated cardiology paper", collected="2026-11-15T00:00:00Z")], monkeypatch)
    assert lines[1].startswith("- Nothing new in your monitored conditions.") and "Health collection looks stale" in lines[1]


def test_quiet_message_is_plain_when_collection_is_fresh(monkeypatch):
    lines = _lane([sig("Unrelated cardiology paper", collected="2026-11-22T20:00:00Z")], monkeypatch)
    assert lines[1] == "- Nothing new in your monitored conditions." and "stale" not in lines[1]


def test_unparseable_collected_at_is_not_fresh_and_never_raises(monkeypatch):
    lines = _lane([sig("Unrelated cardiology paper", collected="garbage")], monkeypatch)
    assert "Health collection looks stale" in lines[1]


def test_non_numeric_sample_size_is_not_rendered():
    for bad in ("abc", "", "0", -5, True, "12abc"):
        assert "people" not in bh._kind({"description": "x", "study_design": "RCT", "sample_size": bad}), bad
    assert bh._kind({"description": "x", "study_design": "RCT", "sample_size": "120"}) == "randomised trial, 120 people"


# ── coverage must not reassure without evidence ──────────────────────────────────────────────────────────────────
GOOD = checks("a", ["ok"] * 4) + checks("b", ["ok"] * 4)
TWO = reg(("a", "ABC News"), ("b", "Bloomberg"))
NORMAL = "- Collection is normal today across your sources."
NO_HISTORY = "- Not enough collection history to judge today."
INCOMPLETE = "- Feed health data is incomplete, so failing feeds may be missing here."


def test_zero_baseline_cannot_judge_not_normal(monkeypatch):
    lines = cov(monkeypatch, TWO, [ev("a", 2), ev("a", 5), ev("b", 8)], GOOD)
    assert NO_HISTORY in lines and NORMAL not in lines


def test_tiny_baseline_or_one_reporting_source_cannot_judge(monkeypatch):
    few = cov(monkeypatch, TWO, busy("a", base=2) + busy("b", base=2), GOOD)
    one = cov(monkeypatch, TWO, busy("a", base=30), GOOD)
    for lines in (few, one):
        assert NO_HISTORY in lines and NORMAL not in lines
    assert bc.MIN_BASELINE_EVENTS >= 1 and bc.MIN_BASELINE_SOURCES >= 2


def test_incomplete_feed_health_is_not_normal(monkeypatch):
    lines = cov(monkeypatch, TWO, busy("a") + busy("b"), checks("a", ["ok"]))      # 0 of 2 sources have enough checks
    assert INCOMPLETE in lines and NORMAL not in lines


def test_half_the_sources_with_enough_checks_is_complete_enough(monkeypatch):
    lines = cov(monkeypatch, TWO, busy("a") + busy("b"), checks("a", ["ok"] * bc.FAILING_MIN_CHECKS))
    assert NORMAL in lines and INCOMPLETE not in lines


def test_stale_status_and_invalid_content_count_as_bad(monkeypatch):
    health = (checks("a", ["ok"] * 4) + [{"source_id": "z", "status": "stale"}] * 3
              + [{"source_id": "y", "status": "ok", "content_valid": False}] * 3 + [{"source_id": "b", "status": "ok", "content_valid": True}] * 4)
    lines = cov(monkeypatch, reg(("a", "ABC News"), ("b", "Bloomberg"), ("z", "Stale Feed"), ("y", "Empty Feed")), busy("a") + busy("b"), health)
    text = "\n".join(lines)
    assert "Empty Feed, Stale Feed" in text and NORMAL not in lines


def test_health_query_selects_content_valid(monkeypatch):
    seen = []
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    tables = {"intelligence_source_registry": TWO, "intelligence_events": busy("a") + busy("b"), "intelligence_source_health": GOOD}
    inner = fake_sb(tables)
    bc.coverage_lines(lambda t, q="": (seen.append((t, q)), inner(t, q))[1], alerts(), now=NOW)
    assert any(t == "intelligence_source_health" and "content_valid" in q for t, q in seen)


def test_events_query_is_newest_first_and_a_full_page_cap_is_flagged(monkeypatch):
    seen = []
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    full = [ev("a" if i % 2 else "b", 2 + (i % 100)) for i in range(bc.PAGE_SIZE)]    # the fake returns this for every page
    tables = {"intelligence_source_registry": TWO, "intelligence_events": full, "intelligence_source_health": GOOD}
    inner = fake_sb(tables)
    lines = bc.coverage_lines(lambda t, q="": (seen.append((t, q)), inner(t, q))[1], alerts(), now=NOW)
    assert any(t == "intelligence_events" and "order=collected_at.desc" in q for t, q in seen)
    assert "- Collection counts may be incomplete." in lines and NORMAL not in lines


def test_normal_thin_and_cannot_judge_are_three_different_outputs(monkeypatch):
    normal = cov(monkeypatch, TWO, busy("a") + busy("b"), GOOD)[1]
    thin = cov(monkeypatch, TWO, [ev(s, 30 + 10 * i) for s in "ab" for i in range(6)] * 3 + [ev("a", 3)], GOOD)[1]
    cannot = cov(monkeypatch, TWO, [ev("a", 2)], GOOD)[1]
    assert len({normal, thin, cannot}) == 3 and normal == NORMAL and "thin" in thin and cannot == NO_HISTORY
