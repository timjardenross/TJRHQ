"""Original-publisher / original-date verification (default OFF, not wired)."""
import pathlib
from datetime import datetime, timezone

from intelligence import original_publisher as op

NOW = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
GN = "Google News - Telstra"
T = "Government in emergency talks after crushed transmission towers cut power to 20,000 homes in South Australia"


def _item(**kw):
    base = {"id": "1", "title": T + " - ABC News & Headlines", "summary": "20,000 customers without power after transmission towers were crushed",
            "source": GN, "geography": "AU", "published_at": "2026-11-19T09:56:15+00:00",
            "collected_at": "2026-11-23T10:00:00+00:00", "url": "https://news.google.com/rss/articles/AAA?oc=5"}
    base.update(kw)
    return base


def test_publisher_from_suffix_reuses_family_table():
    r = op.resolve_publisher(GN, "Storm hits grid - Australian Broadcasting Corporation")
    assert r.family == "abc news" and r.known and r.basis == "title_suffix"
    assert r.clean_title == "Storm hits grid"
    assert r.independence == "unproven"          # a name is never proof of independence


def test_no_suffix_is_unknown_publisher_not_guessed():
    r = op.resolve_publisher(GN, "Storm hits grid")
    assert (r.family, r.known, r.basis) == ("aggregator", False, "none")


def test_direct_feed_is_its_own_publisher():
    r = op.resolve_publisher("BBC News", "Some headline - with dash")
    assert r.family == "bbc news" and r.basis == "feed_name" and r.clean_title == "Some headline - with dash"


def test_aggregator_date_is_a_claim_and_collection_time_never_substituted():
    c = op.label_date(GN, "2026-11-19T09:56:15+00:00", "2026-11-23T10:00:00+00:00")
    assert (c.basis, c.confidence) == ("aggregator_claimed", "claimed") and c.value.day == 19
    none = op.label_date(GN, None, "2026-11-23T10:00:00+00:00")
    assert none.value is None and none.confidence == "unknown"
    assert op.label_date("iTnews", "2026-11-19T09:56:15+00:00").confidence == "feed"


def test_reconcile_uses_earliest_direct_same_title():
    it = _item(published_at="2026-11-19T12:00:00+00:00")
    direct = [{"title": T, "published_at": "2026-11-19T09:00:00+00:00", "source": "BBC News"},
              {"title": T + " ", "published_at": "2026-11-19T07:30:00+00:00", "source": "Guardian Australia"},
              {"title": T, "published_at": "2026-11-18T01:00:00+00:00", "source": "Google News - Origin Energy"},  # aggregator ignored
              {"title": "Different story entirely about something else", "published_at": "2026-11-01T00:00:00+00:00", "source": "BBC News"}]
    r = op.reconcile_with_direct_feeds(it, direct)
    assert r.matched and r.direct_source == "Guardian Australia" and r.delta_hours == 4.5 and r.direct_count == 2


def test_reconcile_no_match_and_short_title():
    assert not op.reconcile_with_direct_feeds(_item(), []).matched
    short = op.reconcile_with_direct_feeds(_item(title="Outage - ABC"),
                                           [{"title": "Outage", "published_at": "2026-11-19T00:00:00Z", "source": "BBC News"}])
    assert not short.matched


def test_eligibility_high_recent_au_only():
    assert op.eligible(_item(), now=NOW)
    assert not op.eligible(_item(title="Quarterly dividend announced - Kalkine", summary=""), now=NOW)   # not material
    assert not op.eligible(_item(source="BBC News"), now=NOW)                                            # not an aggregator
    old = _item(published_at="2026-09-01T00:00:00+00:00", collected_at="2026-09-02T00:00:00+00:00")
    assert not op.eligible(old, now=NOW)
    assert op.eligible(_item(published_at="2026-09-01T00:00:00+00:00"), now=NOW)   # old claim, fresh collection: still checked


def test_classify_verified_date_and_delta():
    f = {"url": "https://www.abc.net.au/news/x", "metadata": {"article:published_time": "2026-11-19T06:59:07+00:00"}}
    v = op.classify_fetch(_item(), f, now=NOW)
    assert v.outcome == op.VERIFIED_DATE and v.publisher_host == "www.abc.net.au" and v.delta_hours == 2.95


def test_classify_modified_only_is_not_verified():
    meta = {"modifiedTime": "2026-11-16T14:55:30+00:00", "article:modified_time": "2026-11-16T14:55:30+00:00"}
    v = op.classify_fetch(_item(), {"url": "https://beinsure.com/news/x/", "metadata": meta}, now=NOW)
    assert v.outcome == op.PUBLISHER_KNOWN_DATE_UNVERIFIED and v.published_at is None


def test_classify_unresolved_and_aggregator_landing():
    assert op.classify_fetch(_item(title=T), None, now=NOW).outcome == op.UNRESOLVED                    # no suffix, no fetch
    assert op.classify_fetch(_item(), None, now=NOW).outcome == op.PUBLISHER_KNOWN_DATE_UNVERIFIED      # suffix only
    g = {"url": "https://news.google.com/rss/articles/AAA", "metadata": {"article:published_time": "2026-11-19T06:59:07+00:00"}}
    assert op.classify_fetch(_item(), g, now=NOW).outcome == op.UNRESOLVED


def test_future_dates_are_not_verified():
    fut = {"url": "https://www.abc.net.au/x", "metadata": {"publishedTime": "2026-12-30T00:00:00+00:00"}}
    assert op.classify_fetch(_item(), fut, now=NOW).outcome == op.PUBLISHER_KNOWN_DATE_UNVERIFIED


def test_batch_is_off_by_default(monkeypatch):
    monkeypatch.delenv(op.FLAG, raising=False)
    calls = []
    assert op.verify_batch([_item()], lambda u: calls.append(u), now=NOW) == {} and calls == []


def test_batch_budget_and_failures(monkeypatch):
    monkeypatch.setenv(op.FLAG, "1")
    items = [_item(id=str(i), url=f"https://news.google.com/rss/articles/{i}") for i in range(10)]
    seen = []

    def fetcher(u):
        seen.append(u)
        if u.endswith("/1"):
            raise RuntimeError("boom")
        return {"url": "https://www.abc.net.au/n", "metadata": {"article:published_time": "2026-11-19T06:59:07+00:00"}}

    out = op.verify_batch(items, fetcher, max_fetches=3, now=NOW)
    assert len(seen) == 3 and set(out) == {"0", "1", "2"}
    assert out["1"].outcome == op.PUBLISHER_KNOWN_DATE_UNVERIFIED          # failure -> outcome class, never raises
    assert out["0"].outcome == op.VERIFIED_DATE


def test_not_wired():
    root = pathlib.Path(__file__).resolve().parents[1]
    users = [p for p in (root / "intelligence").rglob("*.py") if "original_publisher" in p.read_text(errors="ignore")
             and p.name != "original_publisher.py"]
    assert users == []


def _page(**meta):
    return {"url": "https://www.example.com.au/news/a", "metadata": meta}


def test_date_only_or_zoneless_published_time_is_never_verified():
    """Rehearsal 2026-11-24: 'datePublished: 2026-11-21' (day precision) and a zone-less time were labelled verified_date, giving a
    midnight/guessed instant. Verified needs a time of day AND a timezone."""
    for meta in ({"datePublished": "2026-11-21"}, {"article:published_time": "2026-11-21"},
                 {"article:published_time": "2026-11-21T10:17:48"}, {"publishedTime": "21 November 2026"}):
        v = op.classify_fetch(_item(), _page(**meta), now=NOW)
        assert v.outcome == op.PUBLISHER_KNOWN_DATE_UNVERIFIED and v.published_at is None and v.delta_hours is None, meta
        assert "timezone" in v.reason and "date-only" in v.reason


def test_full_timestamps_with_a_zone_still_verify_and_a_later_full_key_beats_an_earlier_date_only_key():
    for raw in ("2026-11-21T10:17:48Z", "2026-11-21T10:17:48+00:00", "2026-11-21T21:17:48+11:00", "2026-11-21T10:17:48+0000"):
        v = op.classify_fetch(_item(), _page(**{"article:published_time": raw}), now=NOW)
        assert v.outcome == op.VERIFIED_DATE and v.published_at is not None, raw
    v = op.classify_fetch(_item(), _page(**{"article:published_time": "2026-11-21", "publishedTime": "2026-11-21T10:17:48+00:00"}), now=NOW)
    assert v.outcome == op.VERIFIED_DATE and v.published_at == datetime(2026, 11, 21, 10, 17, 48, tzinfo=timezone.utc)
