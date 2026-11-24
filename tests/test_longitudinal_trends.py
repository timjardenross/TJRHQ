"""Longitudinal trend measures (wk-trends/0.1.0-prototype): bucketing, denominators, coverage handling, repeats, emerging terms, product."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import longitudinal_trends as lt
from intelligence import trends_product as tp

MON = date(2026, 10, 5)          # a Monday


def ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def at(week_offset: int, day: int = 0, hour: int = 12) -> datetime:
    return datetime(MON.year, MON.month, MON.day, hour, tzinfo=timezone.utc) + timedelta(weeks=week_offset, days=day)


def ev(i, title, source="ABC News", pub=None, coll=None, geo="AU", summary=""):
    return {"id": str(i), "title": title, "source": source, "geography": geo, "summary": summary,
            "published_at": ts(pub) if pub else None, "collected_at": ts(coll or pub or at(0))}


def inc(i, week, terms, publishers=("a", "b", "c"), day=0, subject=None, etype="outage", first=None, head_source="ABC News",
        new=True, restored=None):
    first = first or at(week, day)
    return {"incident_id": str(i), "headline": f"headline {i}", "event_type": etype, "impact_status": "stated", "sector": "telecom",
            "au_relevance": "operational", "au_reason": "x", "priority": "WATCH", "members": 1, "member_ids": [str(i)],
            "publishers": list(publishers), "independent_publishers": len(publishers), "source_classes": ["mainstream"],
            "first_published": first.isoformat(), "week": lt._iso(lt.week_start(first)), "restored_at": restored.isoformat() if restored else None,
            "restoration_evidence": None, "subject": subject, "head_source": head_source, "new_disruption": new, "terms": sorted(terms)}


class TestFlag:
    def test_default_off_and_gate(self, monkeypatch):
        monkeypatch.delenv(lt.FLAG, raising=False)
        assert lt.enabled() is False
        res = lt.build_trends([], window=("2026-10-05", "2026-10-12"), data_start="2026-10-01", data_end="2026-10-20")
        assert res["enabled"] is False and "off" in res["reason"]

    def test_opt_in(self, monkeypatch):
        monkeypatch.setenv(lt.FLAG, "1")
        assert lt.enabled() is True

    def test_not_imported_by_production_code(self):
        for p in list((_REPO / "intelligence").glob("*.py")) + list((_REPO / "platform-runtime").glob("*.py")):
            if p.name in ("longitudinal_trends.py", "trends_product.py"):
                continue
            assert "longitudinal_trends" not in p.read_text(encoding="utf-8"), p


class TestBucketing:
    def test_week_start_is_monday_utc(self):
        assert lt.week_start(date(2026, 10, 11)) == MON               # Sunday belongs to the Monday before
        assert lt.week_start(datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)) == date(2026, 10, 12)

    def test_published_time_not_collection_time_decides_the_week(self):
        e = ev(1, "x", pub=at(0, 1), coll=at(3, 1))                  # published week 0, collected three weeks later
        assert lt.week_start(lt.publication_time(e)) == MON

    def test_undated_and_future_dated_reports_are_never_placed_by_collection_time(self):
        assert lt.publication_time(ev(1, "x", pub=None, coll=at(2))) is None
        future = ev(2, "x", pub=at(2), coll=at(0))                    # published later than collected: not a real publication time
        assert lt.publication_time(future) is None


class TestVolume:
    def test_denominators_by_week_and_class_and_undated(self):
        events = [ev(1, "a", "ABC News", pub=at(0), coll=at(0)), ev(2, "b", "Bloomberg", pub=at(0, 1), coll=at(1)),
                  ev(3, "c", "Inc. Magazine — Leadership", pub=None, coll=at(1)), ev(4, "d", "CISA Alerts", pub=at(0, 2), coll=at(0, 2))]
        weeks = lt.week_range(MON, MON + timedelta(days=7))
        v = lt.volume_denominators(events, weeks)
        w0, w1 = lt._iso(weeks[0]), lt._iso(weeks[1])
        assert v[w0]["published"] == 3 and v[w0]["collected"] == 2 and v[w0]["published_by_class"]["mainstream"] == 2
        assert v[w1]["collected"] == 2 and v[w1]["undated"] == 1 and v[w1]["published"] == 0

    def test_events_outside_the_window_are_not_counted(self):
        v = lt.volume_denominators([ev(1, "a", pub=at(9))], lt.week_range(MON, MON))
        assert v[lt._iso(MON)]["published"] == 0


class TestCoverage:
    def _steady(self, source, weeks, per_week, start=0):
        return [ev(f"{source}{w}-{n}", "t", source, pub=at(w, n % 7), coll=at(w, n % 7)) for w in range(start, weeks) for n in range(per_week)]

    def test_constant_sources_drop_gappy_stepped_and_late_sources(self):
        events = (self._steady("Steady", 10, 5) + self._steady("Late", 10, 5, start=4)
                  + [ev(f"g{w}", "t", "Gappy", pub=at(w), coll=at(w)) for w in (0, 1, 2, 9)]
                  + [ev(f"s{w}-{n}", "t", "Stepped", pub=at(w, n % 7), coll=at(w, n % 7)) for w in range(10) for n in range(5 if w < 5 else 25)])
        changes = ({"date": (MON + timedelta(weeks=5)).isoformat(), "kind": "rate", "note": "step"},)
        res = lt.constant_sources(events, lt.week_range(MON, MON + timedelta(weeks=9)), changes=changes)
        assert res["sources"] == ["Steady"]
        assert "stepped" in res["excluded"]["Stepped"] and "Gappy" in res["excluded"] and "Late" in res["excluded"]

    def test_week_reliability_flags_partial_changes_and_volume_outliers(self):
        events = []
        for w in range(8):
            events += self._steady(f"S{w}", w + 1, 0)
        weeks = lt.week_range(MON, MON + timedelta(weeks=7))
        vol = {lt._iso(w): {"collected": 100, "published": 100, "undated": 0} for w in weeks}
        vol[lt._iso(weeks[4])]["collected"] = 30                                   # outage-like dip
        changes = ({"date": (MON + timedelta(weeks=6, days=2)).isoformat(), "kind": "rate", "note": "step"},)
        cov = {lt._iso(w): {"partial": i == 0, "changes": [c for c in changes if w <= date.fromisoformat(c["date"]) <= w + timedelta(days=6)]}
               for i, w in enumerate(weeks)}
        rel = lt.week_reliability(vol, cov, changes)
        assert not rel[lt._iso(weeks[0])]["reliable"] and "partial" in rel[lt._iso(weeks[0])]["reasons"][0]
        assert not rel[lt._iso(weeks[4])]["reliable"] and "regime median" in rel[lt._iso(weeks[4])]["reasons"][0]
        assert not rel[lt._iso(weeks[6])]["reliable"]
        assert rel[lt._iso(weeks[2])]["reliable"]

    def test_multi_day_change_marks_every_week_it_touches(self):
        c = {"date": "2026-10-02", "end": "2026-10-04", "kind": "outage", "note": "gap"}
        assert lt.change_overlaps(c, date(2026, 9, 28), date(2026, 10, 4))
        assert not lt.change_overlaps(c, date(2026, 10, 5), date(2026, 10, 11))

    def test_transient_outage_confounds_only_weeks_it_touches_and_flagged_false_changes_never(self):
        outage = {"date": "2026-10-02", "end": "2026-10-04", "kind": "outage", "note": "gap"}
        step = {"date": "2026-09-06", "kind": "rate", "note": "step"}
        quiet = {"date": "2026-11-06", "kind": "sources", "confounds": False, "note": "dup retired"}
        used = ["2026-09-07", "2026-09-14", "2026-10-05"]                 # the outage week 2026-09-28 was excluded from the baseline
        assert lt._spans_change("2026-09-07", "2026-10-05", (outage, step, quiet), used=used) == []
        assert lt._spans_change("2026-08-24", "2026-10-05", (outage, step, quiet), used=["2026-08-24", *used]) == [step]
        assert lt._spans_change("2026-09-28", "2026-10-05", (outage,), used=["2026-09-28", "2026-10-05"]) == [outage]

    def test_zero_collection_day_is_derived_from_the_data_and_flags_its_week(self):
        events = [ev(f"d{d}-{n}", "t", "S", pub=at(0, d), coll=at(0, d)) for d in (0, 1, 3, 4, 5, 6) for n in range(70)]   # nothing on day 2
        days = lt.derive_zero_collection_days(events, MON, MON + timedelta(days=6))
        assert days == [((MON + timedelta(days=2)).isoformat(), 0)]

    def test_derived_gaps_find_silent_source(self):
        events = [ev(f"a{n}", "t", "Quiet", pub=at(0, n % 7), coll=at(0, n % 7)) for n in range(12)]
        events += [ev(f"b{w}", "t", "Live", pub=at(w), coll=at(w)) for w in range(8)]
        gaps = lt.derive_silent_gaps(events)
        assert any(g["source"] == "Quiet" and g["gap_to"] is None for g in gaps)


class TestRepeats:
    def test_three_distinct_episodes_in_28_days_flagged_with_evidence(self):
        incs = [inc(1, 0, [], subject="cloudflare", head_source="Cloudflare Status", day=0),
                inc(2, 0, [], subject="cloudflare", head_source="Cloudflare Status", day=3),
                inc(3, 1, [], subject="cloudflare", head_source="Cloudflare Status", day=2)]
        out = lt.repeat_disruptions(incs)
        assert len(out) == 1 and out[0]["subject"] == "cloudflare" and out[0]["episodes_in_final_window"] == 3
        assert [e["incident_id"] for e in out[0]["evidence"]] == ["1", "2", "3"]

    def test_two_episodes_or_wide_spacing_or_no_subject_are_not_repeats(self):
        two = [inc(1, 0, [], subject="x", head_source="X Status"), inc(2, 1, [], subject="x", head_source="X Status")]
        spread = [inc(i, w, [], subject="x", head_source="X Status") for i, w in enumerate((0, 3, 6))]
        nameless = [inc(i, 0, [], subject=None, day=i * 2) for i in range(4)]
        assert lt.repeat_disruptions(two) == [] and lt.repeat_disruptions(spread) == [] and lt.repeat_disruptions(nameless) == []

    def test_follow_ups_of_one_news_outage_are_not_separate_episodes(self):
        base = at(0)
        incs = [inc(i, 0, [], subject="optus", first=base + timedelta(hours=h), head_source="Google News - Telstra") for i, h in enumerate((0, 20, 31))]
        assert lt.repeat_disruptions(incs) == []                                  # 96 h gap rule for news-headed episodes

    def test_aftermath_and_planned_work_headlines_are_not_new_disruptions(self):
        for t in ("Telstra users face 60-hour outage during Yornup upgrade", "How did Telstra miss the red flags before its outage?",
                  "After Optus and Telstra outages, telcos issue new advice", "Senate inquiry: Telstra outage review"):
            assert lt._NOT_NEW_RX.search(t), t
        assert not lt._NOT_NEW_RX.search("Optus mobile outage blocks Triple Zero calls")

    def test_overlapping_windows_merge_into_one_record(self):
        incs = [inc(i, 0, [], subject="s", head_source="S Status", day=0, first=at(0) + timedelta(days=5 * i)) for i in range(6)]
        out = lt.repeat_disruptions(incs)
        assert len(out) == 1 and out[0]["episodes"] == 6 and out[0]["episodes_in_final_window"] <= 6


class TestRestoration:
    def test_median_only_with_enough_evidence_and_implausible_dropped(self):
        w = at(0)
        incs = [inc(1, 0, [], restored=w + timedelta(hours=2)), inc(2, 0, [], restored=w + timedelta(hours=4)),
                inc(3, 0, [], restored=w + timedelta(hours=6)), inc(4, 0, [], restored=w + timedelta(days=30)), inc(5, 0, [])]
        out = lt.restoration_durations(incs, [lt.week_start(w)])[lt._iso(lt.week_start(w))]
        assert out["outage_incidents"] == 5 and out["with_restoration_evidence"] == 3 and out["dropped_implausible"] == 1
        assert out["median_hours"] == 4.0 and out["note"] is None

    def test_withheld_when_evidence_is_thin(self):
        w = at(0)
        out = lt.restoration_durations([inc(1, 0, [], restored=w + timedelta(hours=3))], [lt.week_start(w)])[lt._iso(lt.week_start(w))]
        assert out["median_hours"] is None and "insufficient" in out["note"]


class TestEmerging:
    WEEKS = lt.week_range(MON, MON + timedelta(weeks=7))

    def _base(self, per_week=8):
        return [inc(f"b{w}-{n}", w, ["alpha"] if n == 0 else [f"noise{n}"], day=n % 5) for w in range(7) for n in range(per_week)]

    def _eligible(self, bad=()):
        return {lt._iso(w): lt._iso(w) not in bad for w in self.WEEKS}

    def test_binom_tail_matches_exact_and_survives_large_n(self):
        assert lt.binom_tail(8, 10, 0.5) == pytest.approx(0.0546875)
        assert 0 < lt.binom_tail(80, 3000, 0.01) < 1e-6
        assert lt.binom_tail(0, 5, 0.3) == 1.0

    def test_term_with_strong_rise_and_enough_evidence_is_flagged(self):
        week7 = [inc(f"n{k}", 7, ["fridge"], publishers=("a", "b", "c"), day=k % 3) for k in range(6)] + \
                [inc(f"o{k}", 7, [f"other{k}"], day=k % 3) for k in range(6)]
        out = lt.emerging_terms(self._base() + week7, self.WEEKS, self._eligible())
        assert [r["term"] for r in out] == ["fridge"] and out[0]["incidents"] == 6 and out[0]["week_incidents"] == 12

    def test_minimum_evidence_rule_blocks_thin_signals(self):
        few = [inc(f"n{k}", 7, ["fridge"], day=k % 3) for k in range(3)] + [inc(f"o{k}", 7, [f"x{k}"]) for k in range(9)]
        one_pub = [inc(f"n{k}", 7, ["fridge"], publishers=("a",), day=k % 3) for k in range(6)] + [inc(f"o{k}", 7, [f"x{k}"]) for k in range(6)]
        one_day = [inc(f"n{k}", 7, ["fridge"], day=0) for k in range(6)] + [inc(f"o{k}", 7, [f"x{k}"]) for k in range(6)]
        for last in (few, one_pub, one_day):
            assert lt.emerging_terms(self._base() + last, self.WEEKS, self._eligible()) == []

    def test_unreliable_week_is_neither_tested_nor_used_as_baseline(self):
        week7 = [inc(f"n{k}", 7, ["fridge"], day=k % 3) for k in range(6)] + [inc(f"o{k}", 7, [f"x{k}"]) for k in range(6)]
        assert lt.emerging_terms(self._base() + week7, self.WEEKS, self._eligible(bad={lt._iso(self.WEEKS[7])})) == []
        assert lt.emerging_terms(self._base() + week7, self.WEEKS, self._eligible(bad={lt._iso(w) for w in self.WEEKS[:5]})) == []   # <4 baseline weeks

    def test_a_term_already_common_in_the_baseline_is_not_emerging(self):
        base = [inc(f"b{w}-{n}", w, ["alpha"], day=n % 5) for w in range(7) for n in range(6)]
        week7 = [inc(f"n{k}", 7, ["alpha"], day=k % 3) for k in range(6)]
        assert lt.emerging_terms(base + week7, self.WEEKS, self._eligible()) == []

    def test_generic_words_and_outlet_suffixes_are_not_terms(self):
        t = lt._terms("Another major outage hits government - ABC News & Headlines - Australian Broadcasting Corporation")
        assert not t & {"another", "major", "government", "headline", "abc", "news"}


    def test_outlet_names_never_become_entities(self):
        e = lt._entity_terms("Coles investigates cyber attack - ABC News & Headlines - Australian Broadcasting Corporation")
        assert "coles" in e and not {x for x in e if "abc" in x or "headlines" in x or "broadcasting" in x}


class TestIncidentsEndToEnd:
    def test_status_feed_incident_gets_subject_week_and_restoration(self):
        events = [ev("s1", "Cloudflare Status: Workers degraded (investigating)", "Cloudflare Status", pub=at(0, 1, 3), coll=at(0, 1, 3), geo=""),
                  ev("s2", "Cloudflare Status: Workers degraded (resolved)", "Cloudflare Status", pub=at(0, 1, 6), coll=at(0, 1, 6), geo="")]
        incidents = lt.build_incidents(events)
        assert len(incidents) == 1
        i = incidents[0]
        assert i["subject"] == "cloudflare" and i["week"] == lt._iso(MON) and i["event_type"] == "outage"
        assert i["restored_at"] is not None
        res = lt.restoration_durations(incidents, [MON])[lt._iso(MON)]
        assert res["with_restoration_evidence"] == 1 and res["note"]                   # one duration is below the n>=3 median rule

    def test_collection_date_never_places_an_incident(self):
        events = [ev("u1", "Optus outage leaves customers without service", "ABC News", pub=None, coll=at(2), geo="AU")]
        assert all(i["week"] is None for i in lt.build_incidents(events))

    def test_earthquake_feed_and_vulnerability_advisories_are_not_service_incidents(self):
        events = [ev("q1", "M 5.1 earthquake near Perth", "Geoscience Australia Earthquakes", pub=at(0), coll=at(0)),
                  ev("v1", "CVE-2026-1234 vulnerability in Cisco router actively exploited", "Cisco Security Advisories", pub=at(0), coll=at(0))]
        assert lt.build_incidents(events) == []


class TestProduct:
    def _result(self):
        weeks = [lt._iso(w) for w in lt.week_range(MON, MON + timedelta(weeks=5))]
        mk = lambda: {w: {"total": 3, "by_sector": {"telecom": 3}, "by_au": {"operational": 3}, "by_type": {"outage": 3}} for w in weeks}
        vol = {w: {"collected": 500, "published": 480, "undated": 5, "collected_by_class": {}, "published_by_class": {"mainstream": 300}} for w in weeks}
        cov = {w: {"active_sources": 40, "active_by_class": {"mainstream": 5}, "new_sources": [], "went_silent": [], "changes": [], "known_broken": [], "partial": False}
               for w in weeks}
        rel = {w: {"reliable": True, "reasons": []} for w in weeks}
        side = lambda: {"counts": mk(), "restoration": {w: {"outage_incidents": 3, "with_restoration_evidence": 0, "dropped_implausible": 0,
                        "median_hours": None, "note": "insufficient evidence (n=0, need 3)", "n_durations": 0} for w in weeks},
                        "repeats": [], "emerging": [], "incidents": []}
        return {"enabled": True, "method": lt.METHOD_VERSION, "weeks": weeks, "volume": vol, "constant_volume": vol, "coverage": cov, "reliability": rel,
                "constant_sources": {"sources": ["a", "b"], "excluded": {"c": "gappy"}, "window": [weeks[0], weeks[-1]]},
                "coverage_changes": list(lt.COVERAGE_CHANGES), "known_broken": list(lt.KNOWN_BROKEN), "data_range": ["2026-07-12", "2026-11-24"],
                "all": side(), "constant": side()}

    def test_four_labelled_sections_denominator_and_weak_signal_statement(self):
        res = self._result()
        md = tp.render_trends_markdown(res, week=res["weeks"][-1], generated_on="2026-11-24")
        for label in tp.SECTIONS:
            assert f"## {label}" in md
        assert "GENERATED FROM THE REAL STORED HISTORY" in md and "Only weak signals" in md
        assert "Reports published (dated)" in md and "480" in md
        assert "No term met the minimum-evidence rule" in md and "None met the rule this week" in md

    def test_disabled_result_renders_a_stub(self):
        assert "Not generated" in tp.render_trends_markdown({"enabled": False, "reason": "flag off"}, week="2026-10-05")

    def test_rate_change_needs_baseline_and_evidence(self):
        res = self._result()
        r = tp.rate_change(res["all"], res["volume"], res["weeks"][-1], res["weeks"], res["reliability"], "all")
        assert r["state"].startswith("no change")
        res["all"]["counts"][res["weeks"][-1]]["total"] = 40
        r2 = tp.rate_change(res["all"], res["volume"], res["weeks"][-1], res["weeks"], res["reliability"], "all")
        assert r2["state"] == "higher than baseline"
        early = tp.rate_change(res["all"], res["volume"], res["weeks"][1], res["weeks"], res["reliability"], "all")
        assert early["state"].startswith("not assessed")
