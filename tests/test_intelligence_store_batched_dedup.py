"""filter_unpersisted_events replaces 1-2 GETs per collected item with
batched `in.(...)` lookups (~10k requests/day before)."""

import urllib.parse
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.persistence import intelligence_store as store


def _ev(h, url=None, title="t", published=None):
    return SimpleNamespace(dedup_hash=h, canonical_url=url, raw_title=title, published_at=published)


def _fake_get(existing):
    """Answer `?select=col&col=in.(...)` from `existing` = {col: set}."""
    calls = []

    def _get(path):
        calls.append(path)
        query = urllib.parse.unquote(path.split("?", 1)[1])
        col = query.split("&", 1)[0].removeprefix("select=")
        operand = query.split("=in.", 1)[1]
        values = [v.strip('"').replace('\\"', '"') for v in operand[1:-1].split('","')]
        return [{col: v} for v in values if v in existing.get(col, set())]

    return _get, calls


def test_filters_known_hashes_and_urls_in_two_requests():
    events = [_ev(f"h{i}", url=f"https://x.test/a,b({i})") for i in range(50)]
    get, calls = _fake_get({"dedup_hash": {"h1"}, "canonical_url": {"https://x.test/a,b(2)"}})
    with patch.object(store, "_get", side_effect=get):
        fresh = store.filter_unpersisted_events(events)
    assert [e.dedup_hash for e in fresh] == [f"h{i}" for i in range(50) if i not in (1, 2)]
    assert len(calls) == 2
    assert all("select=" in c for c in calls)


def test_long_batches_are_chunked_under_url_limit():
    events = [_ev("%064x" % i) for i in range(400)]
    get, calls = _fake_get({"dedup_hash": {"%064x" % 399}})
    with patch.object(store, "_get", side_effect=get):
        fresh = store.filter_unpersisted_events(events)
    assert len(fresh) == 399
    assert 1 < len(calls) < 10
    assert all(len(c) < 6200 for c in calls)


def test_no_url_falls_back_to_title_date_check():
    published = datetime(2026, 9, 27, tzinfo=timezone.utc)
    get, _ = _fake_get({})
    with patch.object(store, "_get", side_effect=get), \
         patch.object(store, "event_title_date_exists", return_value=True) as title_check:
        assert store.filter_unpersisted_events([_ev("h", published=published)]) == []
    title_check.assert_called_once()


def test_lookup_failure_fails_open():
    with patch.object(store, "_get", return_value=[]):
        events = [_ev("h1", url="https://x.test/1")]
        assert store.filter_unpersisted_events(events) == events
