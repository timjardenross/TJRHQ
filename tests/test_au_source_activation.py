"""AU source activation package (au-sources-2kq): registry dedupe + offline feed parsing. No network."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "tools" / "intelligence"), str(_REPO / "platform-runtime")]

import seed_source_registry as seed

NEW = {"RBA Media Releases", "ATO Online Services for Agents Status", "Google Workspace Status"}
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>RBA</title><link>https://www.rba.gov.au/</link>
<item><title>Statement by the Monetary Policy Board</title><link>https://www.rba.gov.au/media-releases/2026/mr-26-01.html</link>
<pubDate>Tue, 03 Nov 2026 03:30:00 +0000</pubDate><description>Cash rate target.</description></item></channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Okta</title>
<entry><id>i1</id><title>Degraded: Sign-in latency</title><link href="https://status.okta.com/i1"/><updated>2026-11-20T01:00:00Z</updated></entry></feed>"""


def _rows():
    return [s for s in seed.SOURCES if s["source_name"] in NEW]


def test_new_rows_present_and_unique():
    assert {r["source_name"] for r in _rows()} == NEW
    # Whole-registry source_name uniqueness; url uniqueness only for the new rows
    # (pre-existing shared status-page urls are legitimate multi-feed rows).
    assert max(Counter(s["source_name"] for s in seed.SOURCES).values()) == 1
    assert Counter(s["url"] for s in seed.SOURCES if s["source_name"] in NEW).most_common(1)[0][1] == 1
    assert not [s for s in seed.SOURCES if s["source_name"] not in NEW and s["url"] in {r["url"] for r in _rows()}]
    feeds = [r["rss_url"] or r["api_endpoint"] for r in _rows()]
    assert len(feeds) == len(set(feeds)) == 3
    assert len([s for s in seed.SOURCES if (s["rss_url"] or s["api_endpoint"]) in feeds]) == 3


def test_new_rows_share_key_set_and_https_feeds():
    base = set(seed.SOURCES[0])
    for r in _rows():
        assert set(r) == base
        feed = r["rss_url"] or r["api_endpoint"]
        assert r["source_type"] in ("rss", "api") and feed.startswith("https://")


def test_pilot_rows_staged_inactive():
    act = {r["source_name"]: r["active"] for r in _rows()}
    assert act == {"RBA Media Releases": True, "ATO Online Services for Agents Status": True, "Google Workspace Status": False}


class _Resp:
    def __init__(self, b):
        self.b = b

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("name,body,title", [("RBA Media Releases", RSS, "Statement by the Monetary Policy Board"),
                                             ("Google Workspace Status", ATOM, "Degraded: Sign-in latency")])
def test_rssadapter_parses_fixture(name, body, title):
    pytest.importorskip("feedparser")
    from intelligence.ingestion.rss_adapter import RSSAdapter
    from intelligence.models import SourceRecord
    r = next(x for x in _rows() if x["source_name"] == name)
    src = SourceRecord(source_id="t", source_name=name, category=r["category"], priority_rank=r["priority_rank"], url=r["url"],
                       source_type="rss", jurisdiction=r["jurisdiction"], confidence_weight=r["confidence_weight"],
                       active=True, rss_url=r["rss_url"])
    with patch("urllib.request.urlopen", return_value=_Resp(body)):
        items = RSSAdapter(src).collect()
    assert [i.raw_title for i in items] == [title]


def test_ato_statuspage_json_parses_with_existing_dispatch(monkeypatch):
    import json as _json

    from intelligence.ingestion import api_adapter as aa
    from intelligence.models import SourceRecord
    data = _json.loads((Path(__file__).resolve().parent / "fixtures" / "ato_osfa_incidents_20261124.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(aa.APIAdapter, "_fetch_json", lambda self, endpoint: data)
    row = next(r for r in _rows() if r["source_name"].startswith("ATO"))
    src = SourceRecord(source_id="id-ato", source_name=row["source_name"], category=row["category"], priority_rank=row["priority_rank"],
                       url=row["url"], api_endpoint=row["api_endpoint"], source_type="api", jurisdiction="AU",
                       confidence_weight=row["confidence_weight"], active=True)
    items = aa.APIAdapter(src).collect()
    assert len(items) == 3 and items[0].raw_title and items[0].published_at is not None
