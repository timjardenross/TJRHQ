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


def test_citation_shows_publisher_and_short_id_and_a_short_publisher_url():
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url="https://example.test/a/1")])
    c = be._cite(i)
    assert "ABC News #rep-1 <https://example.test/a/1>" in c          # readable publisher, short id, the publisher's own short URL
    assert c.startswith(f"[{i.incident_id};")                          # the incident id and report count are kept
    assert "1 report(s)" in c


def test_uuid_report_ids_are_shortened_to_eight_characters():
    uuid = "1d9cd2a4-00cd-442e-8936-8ced62bfa3b7"
    _, i = incident([ev(uuid, "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    c = be._cite(i)
    assert "#1d9cd2a4" in c and uuid not in c
    assert be.evidence_refs(i)[0]["report_id"] == uuid                  # the full id stays in the evidence data


def test_report_without_a_url_is_cited_by_publisher_and_id_alone():
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    c = be._cite(i)
    assert "ABC News #rep-1" in c
    assert "None" not in c and "<>" not in c


def test_long_and_redirect_urls_are_not_shown_but_are_kept_whole_in_the_evidence_data():
    long_url = "https://example.test/" + "very-long-path-segment/" * 12 + "article?id=12345"
    redirect = "https://news.google.com/rss/articles/CBMi" + "A" * 300 + "?oc=5"
    _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url=long_url),
                     ev("rep-2", "Telstra mobile network outage across Australia, customers unable to make calls", "Google News - Telstra", 1, url=redirect)])
    c = be._cite(i)
    assert "<https://" not in c                                         # neither is shown inline
    assert "ABC News #rep-1" in c                                        # but both reports are still cited
    urls = {r["report_id"]: r["url"] for r in be.evidence_refs(i)}
    assert urls["rep-1"] == long_url and urls["rep-2"] == redirect        # complete, never truncated
    assert {r["report_id"]: r["url"] for r in i.reports} == urls          # and the underlying report records are unchanged


def test_a_url_is_shown_whole_or_not_at_all():
    for n in (60, 119, 120, 121, 300):
        url = "https://example.test/" + "p" * (n - len("https://example.test/"))
        _, i = incident([ev("rep-1", "Telstra mobile outage leaves customers unable to make calls", "ABC News", url=url)])
        c = be._cite(i)
        assert (f"<{url}>" in c) == (len(url) <= be._CITE_URL_MAX)
        assert "<http" not in c.replace(f"<{url}>", "")                   # never a partial URL


def test_colliding_short_ids_are_lengthened_until_they_are_distinct():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    a, b = "abcdef12-0000-4000-8000-000000000001", "abcdef12-0000-4000-8000-000000000002"
    i.reports = [_report(a), _report(b)]
    c = be._cite(i)
    assert f"#{a}" in c and f"#{b}" in c                                # they differ only in the last character
    i.reports = [_report("abcdef12-0000-4000-8000-000000000001"), _report("abcdef12-1111-4000-8000-000000000002")]
    c = be._cite(i)
    refs = [x.split("#")[1].split(" ")[0] for x in c.split("evidence: ")[1].rstrip("]").split(", ")]
    assert len(set(refs)) == 2 and all(r.startswith("abcdef12-") for r in refs)    # lengthened just enough to be distinct
    assert max(len(r) for r in refs) < len("abcdef12-0000-4000-8000-000000000001")  # and not all the way to the full id


def test_the_citation_is_much_shorter_than_the_full_url_format():
    redirect = "https://news.google.com/rss/articles/CBMi" + "A" * 300 + "?oc=5"
    _, i = incident([ev("1d9cd2a4-00cd-442e-8936-8ced62bfa3b7", "Telstra mobile outage leaves customers unable to make calls", "Google News - Telstra", url=redirect)])
    assert len(be._cite(i)) < 120


def _report(rid, role="original", kind="mainstream", url=True):
    return {"report_id": rid, "publisher": rid, "source_name": rid, "source_kind": kind, "title": "t",
            "url": f"https://example.test/{rid}" if url else None, "collected_at": None, "role": role}


def test_citation_is_bounded_and_says_how_many_more():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    i.reports = [_report(f"r{n}") for n in range(6)]
    c = be._cite(i)
    assert "6 report(s)" in c
    assert f"+{6 - be._CITE_REFS} more" in c
    assert c.count("<https://") == be._CITE_REFS                       # short publisher URLs are shown


def test_originals_and_primary_sources_are_cited_first():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    i.reports = [_report("z-comm", "commentary", "unknown"), _report("y-synd", "syndicated"),
                 _report("b-orig"), _report("a-prim", "original", we_primary())]
    c = be._cite(i)
    shown = c.split("evidence:")[1]
    assert shown.index("#a-prim") < shown.index("#b-orig") < shown.index("#y-synd")
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


# ── Codex review of #675 ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_displayed_short_id_never_collides_with_a_hidden_report():
    """Codex P2: a fourth, hidden report sharing the 8-character prefix of a displayed one made '#abcdef12' ambiguous."""
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    shown_a = "abcdef12-0000-4000-8000-000000000001"
    hidden = "abcdef12-1111-4000-8000-000000000002"
    i.reports = [_report(shown_a), _report("11111111-0000-4000-8000-000000000003"), _report("22222222-0000-4000-8000-000000000004"),
                 _report(hidden, role="syndicated")]
    c = be._cite(i)
    assert "#abcdef12 " not in c and "#abcdef12," not in c and not c.endswith("#abcdef12")       # pre-fix: the ambiguous '#abcdef12'
    refs = {r["report_id"]: r["short_id"] for r in be.evidence_refs(i)}
    assert len(set(refs.values())) == len(refs)                       # unique across ALL reports, shown or not
    assert f"#{refs[shown_a]}" in c


def test_evidence_refs_short_ids_match_the_citation():
    _, i = incident([ev("seed", "Telstra mobile outage leaves customers unable to make calls", "ABC News")])
    i.reports = [_report("abcdef12-0000-4000-8000-000000000001"), _report("abcdef12-1111-4000-8000-000000000002")]
    c = be._cite(i)
    for r in be.evidence_refs(i):
        assert f"#{r['short_id']}" in c


def test_redirect_hosts_are_filtered_whatever_the_url_form():
    """Codex P2: an explicit port or an upper-case scheme bypassed the string-based host check."""
    for url in ("https://news.google.com:443/rss/articles/abc", "HTTPS://news.google.com/rss/articles/abc",
                "https://NEWS.GOOGLE.COM/rss/articles/abc", "https://user@news.google.com/rss/articles/abc",
                "https://sub.news.google.com/x"):
        assert be._url_for_display(url) is None, url
    assert be._url_for_display("HTTPS://www.abc.net.au/news/x") == "HTTPS://www.abc.net.au/news/x"
    assert be._url_for_display("https://www.abc.net.au:8443/news/x") == "https://www.abc.net.au:8443/news/x"
    assert be._url_for_display("https://[::1") is None               # a malformed URL is not shown rather than raising
