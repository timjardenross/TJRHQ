"""Health watch and coverage blocks for the Morning brief (both default OFF)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
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
    matched, safety = bh.select(rows, bh.load_watchlist())
    assert len(matched) == bh.MAX_MATCHED and len(safety) == bh.MAX_SAFETY
    assert matched[0].title == "ADHD study 8"


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
    assert lines[0].startswith("HEALTH WATCH") and "2 signals checked" in lines[0]
    assert lines[1].startswith("- SAFETY") and lines[2].startswith("- Neurodivergence") and "RCT · n=120" in lines[2]


def test_health_quiet_says_so(monkeypatch):
    monkeypatch.setenv(bh.MASTER_FLAG, "true")
    lines = bh.health_lines(fake_sb({"health_signals": [sig("Statin therapy in older adults")]}), now=NOW)
    assert lines[1] == "- Nothing new in your monitored conditions."


def test_health_load_failure_is_unavailable_not_quiet(monkeypatch):
    monkeypatch.setenv(bh.MORNING_FLAG, "1")
    for src in ([], RuntimeError("db down")):
        lines = bh.health_lines(fake_sb({"health_signals": src}), now=NOW)
        assert "Unavailable" in lines[1] and "quiet" in lines[1]


def test_health_pages_until_a_short_page(monkeypatch):
    calls = []

    def get(table, query=""):
        calls.append(query)
        return [sig(f"ADHD {len(calls)}-{i}") for i in range(bh.PAGE_SIZE)] if len(calls) < 3 else [sig("ADHD last")]
    assert len(bh.load_signals(get, now=NOW)) == 2 * bh.PAGE_SIZE + 1 and len(calls) == 3


# ── coverage ─────────────────────────────────────────────────────────────────────────────────────────────────────
REG = [{"source_id": "a", "source_name": "ABC News", "content_expectation": "continuous"},
       {"source_id": "b", "source_name": "ASIC News Centre", "content_expectation": "continuous"},
       {"source_id": "c", "source_name": "Quarterly report", "content_expectation": "periodic"}]


def alerts(*sevs):
    return lambda limit=500: [{"severity": s, "jurisdiction": j} for s, j in sevs]


def test_coverage_flag_off_is_empty():
    assert bc.coverage_lines(fake_sb({}), alerts()) == []


def test_coverage_counts_and_names_silent_continuous_sources_only(monkeypatch):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    sb = fake_sb({"intelligence_source_registry": REG, "intelligence_events": [{"source_id": "a"}] * 40})
    lines = bc.coverage_lines(sb, alerts(), now=NOW)
    assert "40 reports from 1 of 3 active sources" in lines[1]
    assert "1 continuous sources produced nothing: ASIC News Centre." in lines[1]       # the periodic source is not 'silent'
    assert "Quarterly report" not in lines[1]


def test_coverage_caps_the_named_silent_sources(monkeypatch):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    reg = [{"source_id": str(i), "source_name": f"S{i:02d}", "content_expectation": "continuous"} for i in range(12)]
    sb = fake_sb({"intelligence_source_registry": reg, "intelligence_events": [{"source_id": "0"}]})
    assert "and 5 more" in bc.coverage_lines(sb, alerts(), now=NOW)[1]


def test_warnings_use_official_wording_most_severe_first(monkeypatch):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    line = bc.warnings_line(alerts(("advice", "VIC"), ("emergency_warning", "NSW"), ("advice", "NSW"), ("watch_and_act", "QLD"), ("bogus", "WA")))
    assert line == ("- Official warnings active (Emergency Alert Hub): 1 Emergency Warning, 1 Watch and Act, 2 Advice, 1 Unknown severity "
                    "across NSW, QLD, VIC, WA.")


def test_no_warnings_and_failed_hub_are_different_statements():
    assert "none active" in bc.warnings_line(alerts())

    def boom(limit=500):
        raise RuntimeError("hub down")
    assert "not an all-clear" in bc.warnings_line(boom)


def test_coverage_load_failure_is_unavailable_not_zero(monkeypatch):
    monkeypatch.setenv(bc.MORNING_FLAG, "1")
    lines = bc.coverage_lines(fake_sb({"intelligence_source_registry": RuntimeError("x")}), alerts(), now=NOW)
    assert "unavailable" in lines[1] and "0 reports" not in lines[1]
    lines = bc.coverage_lines(fake_sb({"intelligence_source_registry": REG, "intelligence_events": []}), alerts(), now=NOW)
    assert "unavailable" in lines[1]


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
    assert any("unavailable" in x.lower() for x in coverage), coverage
