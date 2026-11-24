"""Ingestion wiring of original-publisher / original-date verification (intelligence/ingestion/publisher_verification.py).

The flag INTEL_ORIGINAL_PUBLISHER_VERIFY is already on in production, so these tests pin the safety properties: bounded, failure-safe,
idempotent, claimed-date semantics unchanged by default, 'verified' only from a timezone-aware publisher timestamp."""
import contextlib
import json
import pathlib
import threading
import time
from datetime import datetime, timezone

import pytest

from intelligence import original_publisher as op
from intelligence import provenance as prov_mod
from intelligence.ingestion import publisher_verification as pv
from intelligence.models import RankedEvent

NOW = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
GN = "Google News - Telstra"
TITLE = "Government in emergency talks after crushed transmission towers cut power to 20,000 homes in South Australia"
SUMMARY = "20,000 customers without power after transmission towers were crushed"
CLAIM = datetime(2026, 11, 19, 9, 56, 15, tzinfo=timezone.utc)
FIX = pathlib.Path(__file__).parent / "fixtures" / "rendered_pages"


def page(name):
    return json.loads((FIX / name).read_text())


def ev(i=0, *, source=GN, title=TITLE + " - ABC News & Headlines", summary=SUMMARY, url=None, geography="AU", published=CLAIM,
       collected=datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc), rank=10.0, suppressed=False, provenance="gn"):
    if provenance == "gn":
        provenance = prov_mod.build_provenance(basis="aggregator_claimed", precision="second", confidence="claimed", publisher_domain="abc.net.au",
                                               publisher_family="ABC News")
    e = RankedEvent(event_id=f"e{i}", source_id="s", source_name=source, source_priority=1, source_confidence_weight=1.0, source_category="media",
                    raw_title=title, raw_summary=summary, canonical_url=url or f"https://news.google.com/rss/articles/A{i}?oc=5",
                    published_at=published, collected_at=collected, dedup_hash=f"h{i}", event_type="outage", geography=geography, sector="energy",
                    operational_relevance=0.8, customer_impact="high", banking_relevance="low", cps230_relevance=False, dependency_risk=False,
                    confidence=0.8, suppressed=suppressed, rank_score=rank, provenance=provenance)
    return e


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(op.FLAG, "1")
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "1")
    for k in ("INTEL_PUBVERIFY_MAX_PER_RUN", "INTEL_PUBVERIFY_MAX_PER_DAY", "INTEL_PUBVERIFY_FETCH_TIMEOUT_S", "INTEL_PUBVERIFY_RUN_DEADLINE_S",
              "INTEL_PUBVERIFY_MAX_BUDGET_PCT", pv.PROMOTE_FLAG):
        monkeypatch.delenv(k, raising=False)
    pv.reset_state()
    yield
    pv.reset_state()


class Fetcher:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    def __call__(self, url, timeout):
        self.calls.append(url)
        if self.exc:
            raise self.exc
        return self.result if self.result is not None else page("abc_eyre_peninsula.json")


def run(events, fetcher, *, day_used=0, budget=10.0, **kw):
    return pv.annotate_events(events, fetcher=fetcher, day_count_fn=lambda d: day_used, budget_pct_fn=lambda: budget, now=NOW, **kw)


def untouched(e, snapshot):
    return (e.published_at, dict(e.provenance or {})) == snapshot


def snap(e):
    return (e.published_at, dict(e.provenance or {}))


# ── eligibility ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_eligible_aggregator_items_are_fetched():
    good = ev(0)
    direct = ev(1, source="BBC News")                                             # not an aggregator
    low = ev(2, title="Local bake sale raises funds - Example", summary="cake")      # not HIGH materiality
    foreign = ev(3, geography="US", title="Storm cuts power to Texas homes - Example", summary="outage in Texas")
    old = ev(4, published=datetime(2026, 9, 1, tzinfo=timezone.utc), collected=datetime(2026, 9, 2, tzinfo=timezone.utc))
    supp = ev(5, suppressed=True)
    nourl = ev(6)
    nourl.canonical_url = None
    others = [direct, low, foreign, old, supp, nourl]
    before = [snap(e) for e in others]
    f = Fetcher()
    s = run([good, *others], f)
    assert f.calls == [good.canonical_url] and s["attempted"] == 1
    assert all(untouched(e, b) for e, b in zip(others, before, strict=True))


# ── caps ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_per_run_cap_defaults_to_5_and_highest_rank_first():
    events = [ev(i, rank=float(i)) for i in range(12)]
    f = Fetcher()
    s = run(events, f)
    assert s["attempted"] == 5 == len(f.calls)
    assert f.calls == [events[i].canonical_url for i in (11, 10, 9, 8, 7)]


def test_per_run_cap_env_and_hard_clamp(monkeypatch):
    monkeypatch.setenv("INTEL_PUBVERIFY_MAX_PER_RUN", "2")
    assert run([ev(i) for i in range(6)], Fetcher())["attempted"] == 2
    pv.reset_state()
    monkeypatch.setenv("INTEL_PUBVERIFY_MAX_PER_RUN", "9999")
    monkeypatch.setenv("INTEL_PUBVERIFY_MAX_PER_DAY", "9999")
    c = pv.limits()
    assert (c.per_run, c.per_day) == (pv.HARD_MAX_PER_RUN, pv.HARD_MAX_PER_DAY)
    monkeypatch.setenv("INTEL_PUBVERIFY_MAX_PER_RUN", "garbage")
    assert pv.limits().per_run == pv.DEFAULT_MAX_PER_RUN
    assert pv.DEFAULT_MAX_PER_RUN == 5 and pv.DEFAULT_MAX_PER_DAY == 20


def test_per_day_cap_uses_db_count_and_remaining_allowance():
    f = Fetcher()
    assert run([ev(i) for i in range(8)], f, day_used=18)["attempted"] == 2          # 20 - 18
    f2 = Fetcher()
    s = run([ev(i + 50) for i in range(8)], f2, day_used=20)
    assert f2.calls == [] and s["skipped"] == "day_cap_reached"


def test_per_day_cap_is_also_tracked_in_process_when_db_undercounts():
    f = Fetcher()
    for k in range(5):                                                              # 4 runs x 5 would be 20; DB claims 0 each time
        run([ev(100 * k + i) for i in range(5)], f, day_used=0)
    f2 = Fetcher()
    s = run([ev(900 + i) for i in range(5)], f2, day_used=0)
    assert len(f.calls) == 20 and f2.calls == [] and s["skipped"] == "day_cap_reached"


def test_day_count_unreadable_fails_closed():
    f = Fetcher()
    e = ev(0)
    b = snap(e)
    s = pv.annotate_events([e], fetcher=f, day_count_fn=lambda d: (_ for _ in ()).throw(RuntimeError("db down")), budget_pct_fn=lambda: 1.0, now=NOW)
    assert f.calls == [] and s["skipped"] == "day_count_unavailable" and untouched(e, b)


# ── budget ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_budget_block_stops_the_step_and_leaves_events_untouched():
    events = [ev(i) for i in range(3)]
    before = [snap(e) for e in events]
    f = Fetcher(exc=pv.BudgetBlocked("firecrawl at its safe ceiling"))
    s = run(events, f)
    assert len(f.calls) == 1 and s["skipped"] == "budget_blocked" and s["attempted"] == 0
    assert all(untouched(e, b) for e, b in zip(events, before, strict=True))


def test_budget_headroom_reserved_for_core_adapters():
    f = Fetcher()
    s = run([ev(0)], f, budget=71.0)
    assert f.calls == [] and s["skipped"] == "budget_headroom_reserved"
    assert run([ev(1)], f, budget=70.0)["attempted"] == 1


def test_budget_unreadable_fails_closed():
    f = Fetcher()
    s = pv.annotate_events([ev(0)], fetcher=f, day_count_fn=lambda d: 0, budget_pct_fn=lambda: (_ for _ in ()).throw(RuntimeError("x")), now=NOW)
    assert f.calls == [] and s["skipped"] == "budget_unreadable"


def test_default_fetcher_goes_through_the_shared_budget_breaker(monkeypatch):
    """The real fetcher is firecrawl_client.scrape, which calls external_fetch_budget.check_and_increment before every request; a
    refusal surfaces as BudgetBlocked (event untouched), a success returns the final URL and page metadata."""
    from intelligence.ingestion import external_fetch_budget as efb
    from intelligence.ingestion import firecrawl_client as fc

    def refuse(*a, **k):
        raise efb.FetchBudgetExceeded("ceiling")
    monkeypatch.setattr(fc, "scrape", refuse)
    with pytest.raises(pv.BudgetBlocked):
        pv._firecrawl_fetcher("https://news.google.com/rss/articles/x", 5)
    monkeypatch.setattr(fc, "scrape", lambda url, formats=None, timeout=None: {"metadata": {"url": "https://www.abc.net.au/a", "sourceURL": url}})
    assert pv._firecrawl_fetcher("https://news.google.com/x", 5)["url"] == "https://www.abc.net.au/a"


# ── timeout and exception safety ────────────────────────────────────────────────────────────────────────────────────────────
def test_slow_fetch_times_out_and_stops_the_step_quickly():
    release = threading.Event()

    def slow(url, timeout):
        release.wait(10)
        return page("abc_eyre_peninsula.json")
    events = [ev(i) for i in range(3)]
    t0 = time.monotonic()
    cfg = pv.Limits(per_run=5, per_day=20, fetch_timeout_s=1, run_deadline_s=30, max_budget_pct=70, promote_date=False)
    s = run(events, slow, cfg=cfg)
    release.set()
    assert time.monotonic() - t0 < 4
    assert s["skipped"] == "timeout" and s["failed"] == 1 and s["attempted"] == 1
    rec = events[0].provenance[pv.RECORD_KEY]
    assert rec["outcome"] == op.UNRESOLVED and events[0].published_at == CLAIM
    assert pv.RECORD_KEY not in events[1].provenance                            # the rest were not attempted


def test_total_run_deadline_is_enforced():
    def slowish(url, timeout):
        time.sleep(0.6)
        return page("abc_eyre_peninsula.json")
    cfg = pv.Limits(per_run=5, per_day=20, fetch_timeout_s=5, run_deadline_s=2, max_budget_pct=70, promote_date=False)
    t0 = time.monotonic()
    s = run([ev(i) for i in range(5)], slowish, cfg=cfg)
    assert time.monotonic() - t0 < 4 and s["attempted"] < 5 and s["skipped"] == "run_deadline"


def test_fetch_exception_is_an_unresolved_outcome_and_the_item_keeps_its_claimed_date():
    e = ev(0)
    f = Fetcher(exc=RuntimeError("render failed"))
    s = run([e], f)
    assert s["failed"] == 1
    assert e.published_at == CLAIM
    assert e.provenance["published_at_confidence"] == "claimed" and e.provenance["published_at_basis"] == "aggregator_claimed"
    assert e.provenance[pv.RECORD_KEY]["outcome"] == op.UNRESOLVED and e.provenance[pv.RECORD_KEY]["date_status"] == "claimed"


def test_annotate_never_raises_on_garbage_or_internal_failure(monkeypatch):
    assert pv.annotate_events([object(), None, ev(0, provenance=None)], fetcher=Fetcher(), day_count_fn=lambda d: 0, budget_pct_fn=lambda: 0, now=NOW)
    monkeypatch.setattr(pv, "_candidates", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    s = pv.annotate_events([ev(0)], fetcher=Fetcher(), now=NOW)
    assert s["skipped"].startswith("error")


def test_flag_off_and_columns_off_do_nothing(monkeypatch):
    f = Fetcher()
    e = ev(0)
    b = snap(e)
    monkeypatch.setenv(op.FLAG, "0")
    assert run([e], f)["skipped"] == "flag_off"
    monkeypatch.setenv(op.FLAG, "1")
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "0")
    assert run([e], f)["skipped"] == "provenance_columns_off"
    assert f.calls == [] and untouched(e, b)


# ── idempotence and dedupe ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_not_reverified_and_deduped_by_canonical_url():
    a, dup = ev(0, url="https://news.google.com/rss/articles/SAME?oc=5"), ev(1, url="https://news.google.com/rss/articles/SAME?oc=5")
    f = Fetcher()
    run([a, dup], f)
    assert len(f.calls) == 1
    run([a, dup], f)                                                             # same run objects again: record present
    assert len(f.calls) == 1
    again = ev(2, url="https://news.google.com/rss/articles/SAME?oc=5")          # a later run, same URL, fresh object
    run([again], f)
    assert len(f.calls) == 1


def test_already_verified_item_is_skipped():
    done = ev(0, provenance=prov_mod.build_provenance(basis="feed", precision="second", confidence="verified", label="publication"))
    f = Fetcher()
    run([done], f)
    assert f.calls == []


# ── date semantics ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_default_keeps_claimed_date_and_records_page_date_and_delta():
    e = ev(0)
    run([e], Fetcher(result=page("abc_eyre_peninsula.json")))
    p, rec = e.provenance, e.provenance[pv.RECORD_KEY]
    assert e.published_at == CLAIM                                               # unchanged: brief freshness is unaffected
    assert (p["published_at_basis"], p["published_at_confidence"], p["published_at_precision"]) == ("aggregator_claimed", "claimed", "second")
    assert p["published_at_label"] is None                                       # never 'verified' for a claimed date
    assert p["publisher_domain"] == "abc.net.au" and p["publisher_family"] == "ABC News"
    assert rec["outcome"] == op.VERIFIED_DATE and rec["page_date_verified"] is True and rec["promoted"] is False and rec["date_status"] == "claimed"
    assert rec["page_published_at"].startswith("2026-11-19T06:59:07") and rec["delta_hours"] == pytest.approx(2.95, abs=0.01)
    assert rec["independence"] == "unproven"


def test_promotion_needs_the_flag_and_a_timezone_aware_publisher_time(monkeypatch):
    monkeypatch.setenv(pv.PROMOTE_FLAG, "1")
    e = ev(0)
    run([e], Fetcher(result=page("abc_eyre_peninsula.json")))
    p = e.provenance
    assert e.published_at == datetime(2026, 11, 19, 6, 59, 7, tzinfo=timezone.utc) and e.published_at.utcoffset() is not None
    assert (p["published_at_basis"], p["published_at_confidence"], p["published_at_label"]) == ("feed", "verified", "publication")
    assert p[pv.RECORD_KEY]["promoted"] is True and p[pv.RECORD_KEY]["date_status"] == "verified"
    for name in ("zoneless_published_time.json", "yahoo_microsoft_no_published_time.json", "still_on_google.json"):
        pv.reset_state()
        z = ev(7)
        run([z], Fetcher(result=page(name)))
        assert z.published_at == CLAIM and z.provenance["published_at_confidence"] == "claimed", name
        assert z.provenance[pv.RECORD_KEY]["promoted"] is False and z.provenance[pv.RECORD_KEY]["date_status"] == "claimed"


def test_verified_page_date_later_than_collection_is_not_promoted(monkeypatch):
    monkeypatch.setenv(pv.PROMOTE_FLAG, "1")
    e = ev(0, collected=datetime(2026, 11, 18, tzinfo=timezone.utc))
    run([e], Fetcher(result=page("abc_eyre_peninsula.json")))                    # page 19 Nov, collected 18 Nov: implausible
    assert e.published_at == CLAIM and e.provenance[pv.RECORD_KEY]["promoted"] is False


@pytest.mark.parametrize("fixture,outcome,domain,delta", [
    ("tradersunion_coles.json", op.VERIFIED_DATE, "tradersunion.com", None),
    ("techbusinessnews_telstra.json", op.VERIFIED_DATE, "techbusinessnews.com.au", None),
    ("yahoo_microsoft_no_published_time.json", op.PUBLISHER_KNOWN_DATE_UNVERIFIED, "au.finance.yahoo.com", None),
    ("zoneless_published_time.json", op.PUBLISHER_KNOWN_DATE_UNVERIFIED, "example.com.au", None),
    ("still_on_google.json", op.UNRESOLVED, "abc.net.au", None),
])
def test_rendered_page_fixtures_aggregator_vs_original_publisher(fixture, outcome, domain, delta):
    e = ev(0)
    run([e], Fetcher(result=page(fixture)))
    rec = e.provenance[pv.RECORD_KEY]
    assert rec["outcome"] == outcome
    assert e.provenance["publisher_domain"] == domain                             # resolved original publisher, or the feed's own when unresolved
    assert rec["publisher_host"] not in ("news.google.com",)
    assert e.published_at == CLAIM


# ── persistence: where the outcome is stored ────────────────────────────────────────────────────────────────────────────────
def test_storage_row_has_publisher_columns_and_record_but_unchanged_claimed_date():
    e = ev(0)
    run([e], Fetcher(result=page("techbusinessnews_telstra.json")))
    row = {"published_at": e.published_at.isoformat(), "score_provenance": {"method": "heuristic"}}
    row.update(prov_mod.provenance_row_fields(e.provenance))
    prov_mod.merge_verification_record(row, e.provenance)
    assert row["publisher_domain"] == "techbusinessnews.com.au" and row["published_at_confidence"] == "claimed"
    assert row["published_at_label"] is None and row["published_at"] == CLAIM.isoformat()
    sp = row["score_provenance"]
    assert sp["method"] == "heuristic" and sp[pv.RECORD_KEY]["outcome"] == op.VERIFIED_DATE
    assert sp[pv.RECORD_KEY]["prior_publisher_domain"] == "abc.net.au"
    assert set(row) <= {"published_at", "score_provenance", *prov_mod.COLUMNS}      # no stray keys reach PostgREST


def test_event_without_record_produces_an_identical_row(monkeypatch):
    row = {"published_at": "x", "score_provenance": {"method": "heuristic"}}
    before = json.dumps(row, sort_keys=True)
    prov_mod.merge_verification_record(row, prov_mod.build_provenance(basis="feed"))
    prov_mod.merge_verification_record(row, None)
    assert json.dumps(row, sort_keys=True) == before
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "0")
    r2 = {"published_at": "x"}
    prov_mod.merge_verification_record(r2, {pv.RECORD_KEY: {"outcome": "x"}})
    assert r2 == {"published_at": "x"}                                             # columns off: nothing added


def test_save_event_posts_the_record_with_phase_a_scoring_provenance(monkeypatch):
    from intelligence.persistence import intelligence_store as store
    posted = {}
    monkeypatch.setattr(store, "_post", lambda table, row, on_conflict=None: posted.update(row=row) or {"event_id": "id1"})
    for name in ("_publish_core_event", "_maybe_push_outage_alert"):
        monkeypatch.setattr(store, name, lambda *a, **k: None)
    e = ev(0)
    run([e], Fetcher(result=page("abc_eyre_peninsula.json")))
    with contextlib.suppress(Exception):                                             # post-save side effects are irrelevant here
        store.save_event(e, phase_a={"source_tier": 3, "signal_status": "SCORED", "score_provenance": {"method": "heuristic"}})
    sp = posted["row"]["score_provenance"]
    assert sp["method"] == "heuristic" and sp[pv.RECORD_KEY]["outcome"] == op.VERIFIED_DATE
    assert posted["row"]["published_at"] == CLAIM.isoformat() and posted["row"]["published_at_confidence"] == "claimed"


# ── wiring ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_wired_after_rank_and_before_persistence_in_every_collection_job():
    src = (pathlib.Path(__file__).resolve().parents[1] / "intelligence" / "scheduler.py").read_text()
    rank = "ranked = rank(classified, period_start=datetime.now(timezone.utc) - timedelta(days=1))\n"
    assert src.count(rank) == 4
    for chunk in src.split(rank)[1:]:
        assert chunk.lstrip().startswith("_annotate_publisher_verification(ranked)")
        assert chunk.index("_annotate_publisher_verification(ranked)") < chunk.index("enrich_and_save")


def test_scheduler_helper_swallows_any_failure(monkeypatch):
    from intelligence import scheduler
    monkeypatch.setattr(pv, "annotate_events", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    scheduler._annotate_publisher_verification([ev(0)])                             # must not raise
