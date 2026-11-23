"""#669 (citations): rendered citations carry retrievable references.

Written to FAIL on the pre-fix behaviour: _cite() showed an incident hash, a report count and publisher names but dropped
the report ids and URLs that build_evidence() had collected for every report, so a reader could not retrieve the evidence
behind an escalation or contribution candidate.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be

T0 = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=30)


def ev(i, title, source, hours=0, url=None):
    d = {"id": i, "title": title, "source": source, "geography": "AU", "summary": "",
         "collected_at": (T0 + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if url is not None:
        d["url"] = url
    return d


def incident(events):
    es = be.build_evidence(events, now=NOW, window_hours=72)
    return es, es.incidents[0]


def test_citation_includes_report_id_and_url():
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url="https://example.test/a/1")])
    c = be._cite(i)
    assert "rep-1" in c and "<https://example.test/a/1>" in c
    assert c.startswith(f"[{i.incident_id};")          # the incident id, report count and publishers are kept
    assert "1 report(s)" in c


def test_report_without_a_url_is_cited_by_id_alone():
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    c = be._cite(i)
    assert "rep-1" in c
    assert "None" not in c and "<>" not in c


def test_long_urls_are_never_truncated():
    url = "https://example.test/" + "very-long-path-segment/" * 12 + "article?id=12345"
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url=url)])
    assert f"<{url}>" in be._cite(i)


def _report(rid, role="original", kind="mainstream", url=True):
    return {"report_id": rid, "publisher": rid, "source_name": rid, "source_kind": kind, "title": "t",
            "url": f"https://example.test/{rid}" if url else None, "collected_at": None, "role": role}


def test_citation_is_bounded_and_says_how_many_more():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    i.reports = [_report(f"r{n}") for n in range(6)]
    c = be._cite(i)
    assert "6 report(s)" in c
    assert f"+{6 - be._CITE_REFS} more" in c
    assert c.count("<https://") == be._CITE_REFS


def test_originals_and_primary_sources_are_cited_first():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    i.reports = [_report("z-comm", "commentary", "unknown"), _report("y-synd", "syndicated"),
                 _report("b-orig"), _report("a-prim", "original", we_primary())]
    c = be._cite(i)
    shown = c.split("evidence:")[1]
    assert shown.index("a-prim") < shown.index("b-orig") < shown.index("y-synd")
    assert "z-comm" not in shown                       # the commentary report is the one summarised as "+1 more"
    assert "+1 more" in shown


def we_primary():
    from intelligence import weekly_evidence as we
    return we.PRIMARY


def test_every_citation_in_the_morning_and_weekly_views_carries_an_evidence_reference():
    events = [ev("m1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", 0, "https://example.test/m1"),
              ev("m2", "Telstra mobile network outage across Australia, customers unable to make calls", "The Guardian", 1, "https://example.test/m2"),
              ev("c1", "Coles Group investigating a cyber incident affecting customer data", "ITnews", 2, "https://example.test/c1")]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(es) + be.weekly_view(es))
    cites = re.findall(r"\[inc-[0-9a-f]{10}[^\]]*\]", text)
    assert cites, "the fixture must produce at least one citation"
    assert all("evidence:" in c for c in cites)


def test_snapshot_identity_is_unchanged_by_the_new_citation_format():
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url="https://example.test/a/1")])
    assert i.incident_id == be._incident_id(["rep-1"])
