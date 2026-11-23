"""P0: whole-word source_kind, content kinds for wellness/thought-leadership feeds, and wire/aggregator copies not counting as
independent publishers."""
import pytest

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we
from tools.intelligence.seed_source_registry import SOURCES

P, M, S, A, C, U = we.PRIMARY, we.MAINSTREAM, we.SPECIALIST, we.AGGREGATOR, we.CONTENT, we.UNKNOWN

_PRIMARY = {"Google Cloud Security Bulletins", "AEMO NEMweb Market Notices", "AEMO Market Notices", "Cisco Security Advisories",
            "NVD / NIST CVE Database", "ACSC Advisories", "ACSC Alerts & Advisories", "APRA Consultations", "APRA Media Releases",
            "APRA Publications", "ASIC Enforcement Activity", "ASIC News Centre", "CISA Alerts", "CISA Known Exploited Vulnerabilities",
            "APRA — Speeches and Publications", "APRA (changedetection.io watchlist)", "ASIC (changedetection.io watchlist)"}
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


def test_three_outlets_one_reuters_dateline_is_one_family():
    c = [_cand(i, WORDINGS[i], src, summary="MELBOURNE (Reuters) - " + WORDINGS[i]) for i, src in enumerate(["The Age", "Financial Review", "Guardian Australia"])]
    g = _group(c)
    assert len({m.family for m in g.members}) == 1
    assert g.independent_publishers == 1
    assert ed.evidence_status(g)[0] != "corroborated"


@pytest.mark.parametrize("dl", ["(Reuters) -", "AAP -", "AFP -", "(AP) —"])
def test_wire_datelines_in_title(dl):
    assert we.publisher_family("The Age", f"{dl} {TITLE}") == we.publisher_family("ABC News", f"{dl} {TITLE}")


def test_independent_originals_corroborate():
    g = _group([_cand(1, WORDINGS[0], "ABC News"), _cand(2, WORDINGS[1], "Bloomberg")])
    assert g.independent_publishers == 2
    assert ed.evidence_status(g)[0] == "corroborated"


def test_same_publisher_repeated_counts_once():
    g = _group([_cand(1, WORDINGS[0], "ABC News"), _cand(2, WORDINGS[1], "ABC News Business")])
    assert g.independent_publishers == 1
