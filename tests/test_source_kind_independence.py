"""P0: whole-word source_kind, content kinds for wellness/thought-leadership feeds, and aggregator copies not counting as
independent publishers. Wire-copy (dateline) detection is deliberately NOT implemented: 0 wire datelines in 2,908 real reports, and
name-based wire matching collided with real sources (AWS Sydney (ap-southeast-2) -> AP, Thomson Reuters Institute -> Reuters)."""
import pytest

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we
from tools.intelligence.seed_source_registry import SOURCES

P, M, S, A, C, U = we.PRIMARY, we.MAINSTREAM, we.SPECIALIST, we.AGGREGATOR, we.CONTENT, we.UNKNOWN

_PRIMARY = {"Google Cloud Security Bulletins", "AEMO NEMweb Market Notices", "AEMO Market Notices", "Cisco Security Advisories",
            "NVD / NIST CVE Database", "ACSC Advisories", "ACSC Alerts & Advisories", "APRA Consultations", "APRA Media Releases",
            "APRA Publications", "ASIC Enforcement Activity", "ASIC News Centre", "ASIC Consultations", "CISA Alerts", "CISA Known Exploited Vulnerabilities",
            "APRA — Speeches and Publications", "APRA (changedetection.io watchlist)", "ASIC (changedetection.io watchlist)",
            "RBA Media Releases", "ATO Online Services for Agents Status", "ATO Online Services for Business Status", "ATO Practitioner Lodgment Service Status",
            "ATO Online Services for Agents Scheduled Maintenance", "ATO Online Services for Business Scheduled Maintenance",
            "ATO Practitioner Lodgment Service Scheduled Maintenance", "ATO System Maintenance",
            "ATO ABR Scheduled Site Maintenance", "DVS Status Scheduled Outages"}
_MAINSTREAM = {"ABC News", "ABC News Business", "BBC News", "Bloomberg", "Financial Times", "Guardian Australia"}
_SPECIALIST = {"SANS Internet Storm Center", "Financial Newswire"}
# every wellness / thought_leadership seed source is CONTENT except technology journalism
_CONTENT = {s["source_name"] for s in SOURCES if s["category"] in ("wellness", "thought_leadership")} - {"MIT Technology Review"}


def _expected(name):
    for kind, names in ((P, _PRIMARY), (M, _MAINSTREAM), (S, _SPECIALIST), (C, _CONTENT)):
        if name in names:
            return kind
    return U


@pytest.mark.parametrize("name", [s["source_name"] for s in SOURCES])
def test_every_seed_source_kind(name):
    assert we.source_kind(name) == _expected(name)


def test_whole_word_negatives():
    assert we.source_kind("Weatherzone Warnings") != S
    assert we.source_kind("CFA Warnings & Incidents") != S
    assert we.source_kind("Learning Network") != S
    assert we.source_kind("ARN Media") == S
    assert we.source_kind("MIT Technology Review") == U


def _cand(i, title, source, summary=""):
    return ed.detect_candidate({"id": f"e{i}", "title": title, "summary": summary, "source": source, "geography": "AU",
                                "collected_at": f"2026-11-22T10:{i:02d}:00+00:00"})


TITLE = "Eyre Peninsula blackout: 20,000 customers without power after transmission towers crushed"
# Distinct wordings of one story, so the near-duplicate (syndication) rule does not hide the family logic under test.
WORDINGS = [
    "Eyre Peninsula blackout: 20,000 customers without power after transmission towers crushed",
    "Eyre Peninsula blackout leaves 20,000 customers without power as storm crushed transmission towers, crews assess damage",
    "Eyre Peninsula blackout: storm crushed transmission towers, 20,000 customers without power, SA Power Networks says",
    "Eyre Peninsula blackout hits 20,000 customers without power after storm crushed transmission towers, repairs under way",
    "Eyre Peninsula blackout: transmission towers crushed, 20,000 customers without power, restoration days away",
    "Eyre Peninsula blackout: 20,000 customers without power after storm crushed towers on key transmission line",
]


def _group(cands):
    groups = ed.correlate(cands)
    assert len(groups) == 1
    return groups[0]


def test_five_google_news_plus_one_abc_is_one_publisher():
    c = [_cand(0, WORDINGS[0], "ABC News")] + [_cand(i, f"{WORDINGS[i]} - Outlet{i}", "Google News - Power") for i in range(1, 6)]
    g = _group(c)
    assert g.independent_publishers == 1
    assert ed.evidence_status(g)[0] != "corroborated"


def test_independent_originals_corroborate():
    g = _group([_cand(1, WORDINGS[0], "ABC News"), _cand(2, WORDINGS[1], "Bloomberg")])
    assert g.independent_publishers == 2
    assert ed.evidence_status(g)[0] == "corroborated"


def test_same_publisher_repeated_counts_once():
    g = _group([_cand(1, WORDINGS[0], "ABC News"), _cand(2, WORDINGS[1], "ABC News Business")])
    assert g.independent_publishers == 1


# ── no wire inference: every source keeps its OWN publisher family and kind ─────────────────────────────────────────
@pytest.mark.parametrize("source,title,family,kind", [
    ("AWS Sydney (ap-southeast-2)", "Increased API error rates in ap-southeast-2", "aws sydney ap southeast 2", U),
    ("AWS Service Health", "Service disruption: Amazon EC2 (Sydney)", "aws service health", U),
    ("Australian Associated Press", "Storms forecast for Victoria", "australian associated press", M),
    ("Thomson Reuters Institute", "Future of professionals report", "thomson reuters institute", M),
    ("Australian Federal Police (AFP)", "AFP charges man over cyber attack on telco", "australian federal police afp", U),
    ("ABC News", "AFP - Talks resume after outage", "abc news", M),
    ("ABC News", "SYDNEY (Reuters) - Power restored across Sydney after outage", "abc news", M),
    ("Bloomberg", "Fed holds rates - Reuters poll shows", "bloomberg", M),
    ("The Age", "Reuters poll: economists expect RBA to hold", "the age", M),
])
def test_family_comes_from_the_source_not_the_headline(source, title, family, kind):
    assert we.publisher_family(source, title) == family
    assert we.source_kind(source) == kind
    assert not hasattr(we, "wire_of")


def test_three_outlets_carrying_one_story_stay_three_publishers_without_wire_inference():
    c = [_cand(i, WORDINGS[i], src, summary="MELBOURNE (Reuters) - " + WORDINGS[i]) for i, src in enumerate(["The Age", "Financial Review", "Guardian Australia"])]
    assert len({m.family for m in c}) == 3


# ── weekly_evidence applies the same corroboration principle ─────────────────────────────────────────────────────
def _wk(i, title, source):
    return {"id": f"w{i}", "title": title, "source": source, "geography": "AU", "collected_at": f"2026-11-22T10:{i:02d}:00+00:00"}


def test_weekly_google_news_items_never_count_as_independent_publishers():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
    gn = [_wk(i, f"{WORDINGS[i]} - Outlet{i}", "Google News - Power") for i in range(1, 6)]
    incs = we.correlate_incidents([_wk(0, WORDINGS[0], "ABC News")] + gn, now=now)
    assert len(incs) == 1 and incs[0].independent_publishers == 1
    only_gn = we.correlate_incidents(gn, now=now)
    assert len(only_gn) == 1 and only_gn[0].independent_publishers == 0


def test_weekly_same_publisher_repeated_counts_once_and_independents_count_twice():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
    same = we.correlate_incidents([_wk(0, WORDINGS[0], "ABC News"), _wk(1, WORDINGS[1], "ABC News Business")], now=now)
    assert [i.independent_publishers for i in same] == [1]
    two = we.correlate_incidents([_wk(0, WORDINGS[0], "ABC News"), _wk(1, WORDINGS[1], "Bloomberg")], now=now)
    assert [i.independent_publishers for i in two] == [2]


def test_causal_claim_cannot_be_corroborated_by_aggregator_copies():
    ev = {"a": {"source": "Google News - X", "title": "Storm caused blackout across Eyre Peninsula - ABC News", "summary": ""},
          "b": {"source": "Google News - Y", "title": "Storm caused blackout across Eyre Peninsula - Guardian", "summary": ""}}
    res = we.validate_claims([we.Claim("Storm caused blackout across Eyre Peninsula", ["a", "b"])], ev)
    assert any("causal claim" in f for f in res.failures)
