"""Provenance v1: timestamp/source provenance on collected items, and four freshness states in the readers.

Captain's clarification under test: an unverified publication time must NOT establish confirmed freshness (never live restoration
evidence, never 'confirmed current' wording), but must NOT stop a potentially severe emerging incident being surfaced for urgent
verification. Known-stale reports never surface as urgent. Everything is optional: absent provenance behaves exactly as before.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be
from intelligence import event_detection as ed
from intelligence import provenance as pv
from intelligence.models import IntelligenceItem

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
HEADING = "URGENT TO VERIFY (potentially severe, not yet corroborated)"
OUTAGE = "Eyre Peninsula blackout: 20,000 customers without power after transmission towers crushed"
FEED = {"published_at_basis": "feed", "published_at_precision": "second", "published_at_confidence": "feed"}
CLAIMED = {"published_at_basis": "aggregator_claimed", "published_at_precision": "second", "published_at_confidence": "claimed"}


def ts(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(i, title=OUTAGE, *, src="Some Blog", pub=2, coll=2, prov=None):
    row = {"id": i, "title": title, "summary": "", "source": src, "geography": "AU", "collected_at": ts(coll), "url": f"https://x.test/{i}"}
    if pub is not None:
        row["published_at"] = ts(pub)
    row.update(prov or {})
    return row


# ── collectors: one test per basis ─────────────────────────────────────────────────────────────────────────────
def test_basis_feed_for_ordinary_rss():
    p = pv.rss_provenance(published=NOW, feed_url="https://www.abc.net.au/rss", entry={"link": "https://abc.net.au/a"})
    assert (p["published_at_basis"], p["published_at_confidence"], p["published_at_precision"]) == ("feed", "feed", "second")
    assert p["publisher_domain"] == "abc.net.au"


def test_basis_aggregator_claimed_and_publisher_from_google_news_source_element():
    feedparser = pytest.importorskip("feedparser")
    xml = ('<?xml version="1.0"?><rss version="2.0"><channel><title>g</title><item><title>Optus outage - ABC News</title>'
           '<link>https://news.google.com/rss/articles/CBM123</link><pubDate>Mon, 23 Nov 2026 20:00:00 GMT</pubDate>'
           '<source url="https://www.abc.net.au">ABC News</source></item></channel></rss>')
    entry = feedparser.parse(xml).entries[0]
    p = pv.rss_provenance(published=NOW, feed_url="https://news.google.com/rss/search?q=optus", entry=entry)
    assert p["published_at_basis"] == "aggregator_claimed" and p["published_at_confidence"] == "claimed"
    assert p["publisher_domain"] == "abc.net.au" and p["publisher_family"] == "ABC News"


def test_google_news_without_a_date_is_unknown_not_claimed():
    p = pv.rss_provenance(published=None, feed_url="https://news.google.com/rss/x", entry={})
    assert p["published_at_basis"] == "unknown" and p["published_at_confidence"] == "unknown"


def test_basis_feed_for_api_and_date_only_for_kev():
    assert pv.api_provenance(published=NOW, endpoint="https://status.example.com/api")["published_at_basis"] == "feed"
    kev = pv.api_provenance(published=NOW, endpoint="https://cisa.gov/kev.json", date_only=True)
    assert (kev["published_at_basis"], kev["published_at_precision"], kev["published_at_confidence"]) == ("date_only", "day", "claimed")


def test_scrape_header_time_in_source_tz_is_feed_corrected_utc_and_bare_date_is_date_only():
    t = pv.scrape_provenance(published=NOW, page_url="https://www.aemo.com.au/x", date_only=False, basis_tz="AEMO Market Notices")
    assert (t["published_at_basis"], t["published_at_precision"]) == ("feed_corrected_utc", "minute")
    d = pv.scrape_provenance(published=NOW, page_url="https://www.aemo.com.au/x", date_only=True, basis_tz="AEMO Market Notices")
    assert (d["published_at_basis"], d["published_at_precision"]) == ("date_only", "day")
    assert pv.scrape_provenance(published=None, page_url=None, date_only=True)["published_at_basis"] == "unknown"


def test_scrape_adapter_marks_aemo_item_provenance():
    bs4 = pytest.importorskip("bs4")
    from intelligence.ingestion import scrape_adapter as sa
    from intelligence.models import SourceRecord
    a = sa.ScrapeAdapter(SourceRecord(source_id="s1", source_name="AEMO Market Notices", category="critical_infrastructure", priority_rank=1,
                                      url="https://www.aemo.com.au/market-notices", source_type="scrape", jurisdiction="AU",
                                      confidence_weight=0.9, active=True))
    html = "".join(f"<div class='item'><h3>RECLASSIFY CONTINGENCY notice {n}</h3><p>{d}</p></div>" for n, d in
                  ((1, "24/11/2026 05:53:57 AM"), (2, "23/11/2026")))
    soup = bs4.BeautifulSoup(f"<div class='items'>{html}</div>", "html.parser")
    items = a._extract_items(soup)
    by_title = {i.raw_title: i.provenance for i in items}
    assert by_title["RECLASSIFY CONTINGENCY notice 1"]["published_at_basis"] == "feed_corrected_utc"
    assert by_title["RECLASSIFY CONTINGENCY notice 2"]["published_at_basis"] == "date_only"


def test_twilio_scheduled_window_text_becomes_an_event_window_not_a_publication_time():
    s, e = pv.parse_event_window("Scheduled maintenance 2026-12-02 02:00 - 04:00 UTC")
    assert (s, e) == (datetime(2026, 12, 2, 2, tzinfo=timezone.utc), datetime(2026, 12, 2, 4, tzinfo=timezone.utc))
    s, e = pv.parse_event_window("window 2026-12-02 22:00 UTC to 2026-12-03 01:00 UTC")
    assert e - s == timedelta(hours=3)
    assert pv.parse_event_window("maintenance next week") == (None, None)


def test_rss_adapter_keeps_future_scheduled_start_as_event_window():
    feedparser = pytest.importorskip("feedparser")
    from intelligence.ingestion import rss_adapter as ra
    from intelligence.models import SourceRecord
    a = ra.RSSAdapter(SourceRecord(source_id="s1", source_name="Twilio Status", category="cloud_technology", priority_rank=3,
                                   url="https://status.twilio.com", source_type="rss", jurisdiction="GLOBAL", confidence_weight=0.85, active=True))
    future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = feedparser.parse(f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><entry><id>x</id><title>e</title>'
                             f"<published>{future}</published></entry></feed>").entries[0]
    start = a._future_scheduled_start(entry)
    assert start is not None and a._parse_date(entry) is None       # not a publication time
    assert pv.rss_provenance(published=None, feed_url=a._feed_url, entry=entry, scheduled_start=start)["event_window_start"] == start


# ── persistence: columns absent => identical row ───────────────────────────────────────────────────────────────
def test_row_fields_empty_while_flag_off(monkeypatch):
    monkeypatch.delenv("INTEL_PROVENANCE_COLUMNS", raising=False)
    p = pv.build_provenance(basis="feed", precision="second", confidence="feed", publisher_domain="abc.net.au")
    assert pv.provenance_row_fields(p) == {}
    assert pv.select_columns() == ""


def test_row_fields_present_only_when_flag_on(monkeypatch):
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "1")
    p = pv.build_provenance(basis="aggregator_claimed", precision="second", confidence="claimed", publisher_domain="ABC.net.au",
                            event_window_start=NOW)
    row = pv.provenance_row_fields(p)
    assert set(row) == set(pv.COLUMNS) and row["publisher_domain"] == "abc.net.au" and row["event_window_start"] == NOW.isoformat()
    assert pv.provenance_row_fields(None) == {}
    assert pv.select_columns().startswith(",publisher_domain")


def test_save_event_merges_provenance_only_through_the_gated_helper(monkeypatch):
    from intelligence.persistence import intelligence_store as store
    monkeypatch.delenv("INTEL_PROVENANCE_COLUMNS", raising=False)
    assert store.provenance_row_fields({"published_at_basis": "feed"}) == {}      # flag off: nothing added to the row
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "1")
    assert store.provenance_row_fields({"published_at_basis": "feed"})["published_at_basis"] == "feed"


def test_invalid_enum_values_degrade_to_unknown():
    p = pv.build_provenance(basis="nonsense", precision="week", confidence="certain")
    assert (p["published_at_basis"], p["published_at_precision"], p["published_at_confidence"]) == ("unknown", "unknown", "unknown")


def test_item_dataclass_carries_provenance_default_none():
    item = IntelligenceItem(source_id="s", source_name="n", source_priority=1, source_confidence_weight=0.5, source_category="c",
                            raw_title="t", collected_at=NOW)
    assert item.provenance is None


# ── readers: four freshness states ─────────────────────────────────────────────────────────────────────────────
def _cand(**kw):
    return ed.detect_candidate(ev("a", **kw))


def test_freshness_verified_no_provenance_and_feed_basis():
    assert ed.report_freshness(_cand(pub=2), NOW) == "VERIFIED"           # legacy row: unchanged meaning
    assert ed.report_freshness(_cand(pub=2, prov=FEED), NOW) == "VERIFIED"
    assert ed.report_freshness(_cand(pub=2, prov={**FEED, "published_at_basis": "feed_corrected_utc", "published_at_precision": "minute"}), NOW) == "VERIFIED"


@pytest.mark.parametrize("prov", [CLAIMED,
                                  {"published_at_basis": "date_only", "published_at_precision": "day", "published_at_confidence": "claimed"},
                                  {"published_at_basis": "unknown", "published_at_confidence": "unknown"}])
def test_freshness_claimed_for_unverified_provenance(prov):
    assert ed.report_freshness(_cand(pub=2, prov=prov), NOW) == "CLAIMED"


def test_freshness_unknown_without_a_publication_time():
    assert ed.report_freshness(_cand(pub=None, coll=2), NOW) == "UNKNOWN"
    assert ed.report_freshness(_cand(pub=None, coll=2, prov={"published_at_basis": "collected_fallback"}), NOW) == "UNKNOWN"


def test_freshness_known_stale_whatever_the_provenance():
    for kw in ({"pub": 30}, {"pub": 30, "prov": CLAIMED}, {"pub": None, "coll": 30}):
        assert ed.report_freshness(_cand(**kw), NOW) == "KNOWN STALE"


def test_claimed_time_later_than_collection_is_not_trusted_as_a_time_at_all():
    assert ed.report_freshness(_cand(pub=-5, coll=2, prov=CLAIMED), NOW) == "UNKNOWN"


def test_publisher_domain_alone_never_changes_trust_or_independence():
    c1 = _cand(pub=2, prov={"publisher_domain": "abc.net.au"})
    c2 = _cand(pub=2)
    assert c1.time_verified == c2.time_verified and c1.family == c2.family and c1.kind == c2.kind


# ── urgent-to-verify interaction (#693) and restoration (#692) ─────────────────────────────────────────────────
def _one(events):
    es = be.build_evidence(events, now=NOW)
    assert len(es.incidents) == 1
    return es, es.incidents[0]


@pytest.mark.parametrize("prov,pub,fresh", [(None, 2, "VERIFIED"), (FEED, 2, "VERIFIED"), (CLAIMED, 2, "CLAIMED"), (None, None, "UNKNOWN")])
def test_claimed_and_unknown_fresh_reports_still_surface_as_urgent_to_verify(prov, pub, fresh):
    es, inc = _one([ev("a", pub=pub, prov=prov)])
    assert inc.freshness == fresh
    assert inc.urgent_verify and inc.priority == "VERIFY"
    section = "\n".join(be.morning_view(es))
    assert HEADING in section


def test_known_stale_never_urgent_even_with_claimed_recent_collection():
    _, inc = _one([ev("a", pub=30, coll=1, prov=CLAIMED)])       # aggregator claims a time 30h old; we merely collected it recently
    assert inc.freshness == "KNOWN STALE" and not inc.urgent_verify


def test_urgent_wording_states_unverified_time_and_never_confirmed_current():
    es, _ = _one([ev("a", pub=2, prov=CLAIMED)])
    text = "\n".join(be.morning_view(es))
    assert "publication time only claimed" in text
    assert "confirmed current" not in text.lower()
    es2, _ = _one([ev("a", pub=None)])
    assert "publication time unknown" in "\n".join(be.morning_view(es2))


def test_verified_urgent_line_has_no_time_caveat():
    es, _ = _one([ev("a", pub=2, prov=FEED)])
    assert "publication time" not in "\n".join(be.morning_view(es))


def test_claimed_continuation_cue_is_not_live_evidence_for_restoration():
    title = "Optus outage continues across Sydney, thousands of customers still without service"
    legacy = ed.escalation_record(ed.run([ev("a", title, pub=2)], now=NOW)[0], now=NOW)["restoration_status"]
    claimed = ed.escalation_record(ed.run([ev("a", title, pub=2, prov=CLAIMED)], now=NOW)[0], now=NOW)["restoration_status"]
    assert legacy == "ongoing"          # trusted time: unchanged
    assert claimed == "unknown"         # claimed time: cannot establish that the disruption is live
    unknown_time = ed.escalation_record(ed.run([ev("a", title, pub=None)], now=NOW)[0], now=NOW)["restoration_status"]
    assert unknown_time == "unknown"


def test_claimed_fresh_report_cannot_reopen_or_hold_ongoing_via_fresh_stated_rule():
    title = "Optus customers without service in Sydney"
    rec = ed.escalation_record(ed.run([ev("a", title, pub=1, prov=CLAIMED)], now=NOW)[0], now=NOW)
    assert rec["restoration_status"] == "unknown"


# ── columns absent: identical behaviour ────────────────────────────────────────────────────────────────────────
def _snapshot(events):
    es = be.build_evidence(events, now=NOW)
    return [(i.headline, i.priority, i.urgent_verify, i.record["restoration_status"], i.evidence_status, i.reasons) for i in es.incidents]


def test_absent_provenance_is_identical_to_trusted_feed_provenance_and_to_legacy():
    rows = [ev("a", pub=2), ev("b", "Optus outage continues across Sydney", pub=3, src="ABC News"), ev("c", "Qantas systems down", pub=None)]
    legacy = _snapshot(rows)
    fed = _snapshot([{**r, **FEED} if r.get("published_at") else r for r in rows])
    assert legacy == fed


def test_load_events_query_and_rows_unchanged_while_flag_off(monkeypatch):
    monkeypatch.delenv("INTEL_PROVENANCE_COLUMNS", raising=False)
    seen = {}

    def sb_get(table, qs):
        seen["qs"] = qs
        return [{"event_id": "1", "raw_title": "t", "raw_summary": "", "geography": "AU", "collected_at": ts(1), "published_at": ts(2),
                 "canonical_url": "u", "intelligence_source_registry": {"source_name": "X"}, "published_at_basis": "aggregator_claimed"}]
    out = be.load_events(sb_get, hours=24, now=NOW)
    assert "published_at_basis" not in seen["qs"]           # the query is byte-identical to today's while the flag is off
    monkeypatch.setenv("INTEL_PROVENANCE_COLUMNS", "1")
    out = be.load_events(sb_get, hours=24, now=NOW)
    assert "published_at_basis" in seen["qs"] and out[0]["published_at_basis"] == "aggregator_claimed"


# ── replay-style: realistic mixed feed ─────────────────────────────────────────────────────────────────────────
def test_replay_realistic_mixed_items():
    gn = {**CLAIMED, "publisher_domain": "abc.net.au", "publisher_family": "ABC News"}
    events = [
        # fresh Google News claim of a severe AU incident (2 aggregator copies): must be surfaced for urgent verification, not confirmed
        ev("g1", "Optus triple-zero outage leaves millions of Australian customers without service - ABC News", src="Google News: Optus", pub=1, coll=1, prov=gn),
        ev("g2", "Optus triple-zero outage leaves millions of Australian customers without service - 9News", src="Google News: Optus", pub=1, coll=1,
           prov={**gn, "publisher_domain": "9news.com.au", "publisher_family": "9News"}),
        # a Google News re-run of a 3-day-old story collected just now: known stale, never urgent
        ev("g3", "Telstra network outage leaves 50,000 customers without service - SMH", src="Google News: Telstra", pub=72, coll=1, prov=gn),
        # primary feed, verified, ongoing
        ev("p1", "Ausgrid: 12,000 customers without power in Newcastle after storm", src="Ausgrid Outages", pub=1, coll=1, prov=FEED),
    ]
    es = be.build_evidence(events, now=NOW)
    by_id = {r["report_id"]: i for i in es.incidents for r in i.reports}
    assert by_id["g3"].freshness == "KNOWN STALE" and not by_id["g3"].urgent_verify
    assert by_id["g1"] is by_id["g2"]
    assert by_id["g1"].freshness == "CLAIMED"
    assert by_id["g1"].record["restoration_status"] != "ongoing"
    assert by_id["g1"].independent_publishers < 2 or by_id["g1"].evidence_status != "corroborated"   # same aggregator: domains are not independence
    assert by_id["p1"].freshness == "VERIFIED"
    text = "\n".join(be.morning_view(es))
    assert "confirmed current" not in text.lower()
