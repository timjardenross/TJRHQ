"""#669 audit 3 — one organisation under two names is one publisher; an aggregator re-post of an outlet's story is not corroboration."""
from datetime import datetime, timezone

from intelligence import brief_evidence as be
from intelligence import weekly_evidence as we

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)


def _ev(i, title, source, summary="", hours=3):
    return {"id": f"ev-{i}", "title": title, "summary": summary, "source": source, "geography": "AU",
            "collected_at": f"2026-11-22T{21 - hours // 2:02d}:{10 + i:02d}:00+00:00", "url": f"https://example.org/{i}"}


T1 = "Live: Power still out after SA transmission line downed"
T2 = "Transmission towers crushed, knocking out power to 20,000 in South Australia"
SUM = "20,000 customers without power after transmission towers were crushed in a storm in South Australia."


def test_alias_names_resolve_to_one_family():
    assert we.publisher_family("Google News - Telstra", T2 + " - Australian Broadcasting Corporation") == we.publisher_family("ABC News", T1)
    assert we.publisher_family("ABC News Business", "x") == we.publisher_family("ABC News", "x")
    assert we.publisher_family("Guardian Australia", "x") == we.publisher_family("Google News - x", "t - The Guardian")


def test_unrelated_publishers_stay_distinct():
    assert we.publisher_family("ABC News", "x") != we.publisher_family("Guardian Australia", "x")
    assert we.publisher_family("Google News - x", "t - Some Other Paper") == "some other paper"


def test_aggregator_repost_of_same_outlet_is_not_corroboration():
    events = [_ev(1, T1, "ABC News", SUM), _ev(2, T2 + " - Australian Broadcasting Corporation", "Google News - Telstra", SUM)]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    grouped = [i for i in es.incidents if len(i.reports) >= 2]
    assert grouped, "the two reports should form one incident"
    assert all(i.evidence_status != "corroborated" for i in grouped)


def test_genuinely_independent_publisher_still_corroborates():
    events = [_ev(1, "Eyre Peninsula blackout: 20,000 without power after transmission towers crushed", "ABC News",
                  "Storm cell toppled transmission towers on the Eyre Peninsula line, cutting supply to about 20,000 customers."),
              _ev(2, "South Australia power outage hits 20,000 customers as storm downs transmission towers", "ITnews",
                  "Network operator says restoration will take days after two towers fell in the storm.")]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    assert any(i.evidence_status == "corroborated" and i.independent_publishers == 2 for i in es.incidents)


# ── organisation-prefix rule: several registered feeds of one organisation are one publisher ──

def test_same_organisation_feeds_share_one_family():
    fams = {we.publisher_family(n, "x") for n in ("APRA Media Releases", "APRA Publications", "APRA")}
    assert fams == {"apra"}
    assert we.publisher_family("ASIC Media Releases", "x") == we.publisher_family("ASIC Enforcement", "x") == "asic"
    assert we.publisher_family("CISA Alerts", "x") == we.publisher_family("CISA Known Exploited Vulnerabilities", "x") == "cisa"
    assert we.publisher_family("AEMO Market Notices", "x") == we.publisher_family("AEMO News", "x") == "aemo"
    assert {we.publisher_family(n, "x") for n in ("ACSC Alerts", "ACSC Advisories")} == {"acsc"}
    assert {we.publisher_family(n, "x") for n in ("NIST News", "NIST CSRC")} == {"nist"}
    assert {we.publisher_family(n, "x") for n in ("RBA Media Releases", "RBA Bulletin")} == {"rba"}


def test_aggregator_suffix_maps_to_same_organisation_family():
    assert we.publisher_family("Google News - APRA", "Bank capital rule - APRA Media Releases") == "apra"
    assert we.publisher_family("Google News - APRA", "Bank capital rule - APRA Publications") == "apra"


def test_organisation_prefix_uses_token_boundaries():
    assert we.publisher_family("Cisco Security Advisories", "x") != "cisa"
    assert we.publisher_family("Asian Banker", "x") != "asic"
    assert we.publisher_family("Apraxia News", "x") != "apra"
    assert we.publisher_family("ABC News", "x") == "abc news"
    assert we.publisher_family("Guardian Australia", "x") == "guardian australia"
    assert we.publisher_family("BBC News", "x") == "bbc news"


def test_same_organisation_feeds_do_not_corroborate_each_other():
    es = be.build_evidence([_ev(1, T1, "APRA Media Releases", SUM), _ev(2, T2, "APRA Publications", SUM)], now=NOW, window_hours=72)
    grouped = [i for i in es.incidents if len(i.reports) >= 2]
    assert grouped and all(i.independent_publishers == 1 for i in grouped)


def test_abc_and_guardian_still_corroborate_after_org_rule():
    events = [_ev(1, "Eyre Peninsula blackout: 20,000 without power after transmission towers crushed", "ABC News",
                  "Storm cell toppled transmission towers on the Eyre Peninsula line, cutting supply to about 20,000 customers."),
              _ev(2, "South Australia power outage hits 20,000 customers as storm downs transmission towers", "Guardian Australia",
                  "Network operator says restoration will take days after two towers fell in the storm.")]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    assert any(i.independent_publishers == 2 for i in es.incidents)


# ── review items 8/9: org-prefix needs a known feed suffix; sub-brands of one organisation merge ──

def test_org_prefix_requires_known_feed_suffix():
    for n in ("CISA-Watch Blog", "rba-watch.com", "Rba Foo", "APRA Tracker Blog", "NIST Unofficial"):
        assert we.publisher_family(n, "x") not in _ORGS, n
    assert we.publisher_family("CISA-Watch Blog", "x") != we.publisher_family("CISA Alerts", "x")
    assert we.publisher_family("RBA Media Releases", "x") == "rba"  # negative control


_ORGS = {"apra", "asic", "cisa", "acsc", "aemo", "nist", "rba"}


def test_unknown_suffix_does_not_hide_second_source():
    es = be.build_evidence([_ev(1, T1, "CISA Alerts", SUM), _ev(2, T2, "CISA-Watch Blog", SUM)], now=NOW, window_hours=72)
    assert any(i.independent_publishers == 2 for i in es.incidents)


def test_sub_brands_and_full_names_merge():
    fam = we.publisher_family
    assert fam("Guardian US", "x") == fam("The Guardian", "x") == "guardian australia"
    assert {fam(n, "x") for n in ("BBC Sport", "BBC World Service", "BBC Culture", "BBC News")} == {"bbc news"}
    assert {fam(n, "x") for n in ("ABC Radio National", "ABC Science", "ABC News")} == {"abc news"}
    assert fam("AFR Weekend", "x") == fam("AFR", "x") == "afr"
    assert fam("Reserve Bank of Australia", "x") == fam("RBA", "x") == "rba"
    assert fam("Google News - BBC Sport", "x - BBC Sport") == "bbc news"


def test_sub_brand_negative_controls():
    fam = we.publisher_family
    assert fam("ABC7 Chicago", "x") != "abc news"
    assert fam("ABC Foo Gazette", "x") != "abc news"
    assert fam("BBC Watch Blog", "x") != "bbc news"
    assert fam("Guardian Angel Security", "x") != "guardian australia"
    assert fam("Reuters", "x") not in ("rba", "bbc news")
