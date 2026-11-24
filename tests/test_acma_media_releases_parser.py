"""Offline tests for the ACMA media-releases listing parser (real markup captured 2026-11-24)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO)]

pytest.importorskip("bs4")

from intelligence.ingestion.acma_media_releases import (
    AcmaRelease,
    is_outage_relevant,
    parse_listing,
)

FIXTURE = Path(__file__).parent / "fixtures" / "acma_media_releases_listing.html"


@pytest.fixture(scope="module")
def releases():
    return parse_listing(FIXTURE.read_text(encoding="utf-8"))


def test_parses_all_cards_in_order(releases):
    assert len(releases) == 4
    assert releases[0].title == "ACMA finalises review into alcohol advertising"
    assert releases[0].url == "https://www.acma.gov.au/articles/2026-11/acma-finalises-review-alcohol-advertising"
    assert releases[0].published == date(2026, 11, 12)
    assert releases[1].published == date(2026, 11, 4)


def test_summary_and_whitespace_normalised(releases):
    assert "\n" not in releases[1].title
    assert releases[1].summary.startswith("Australian telco SpinTel")


def test_fixture_items_are_not_outage_relevant(releases):
    assert not any(is_outage_relevant(r) for r in releases)


def test_outage_relevance_detects_triple_zero():
    r = AcmaRelease("ACMA takes Optus Mobile to court over September 2025 Triple Zero outage", "u", "", None)
    assert is_outage_relevant(r)


def test_empty_and_malformed_input():
    assert parse_listing("") == []
    assert parse_listing("<article class='card'><h3 class='card-title'>x</h3></article>") == []


def test_bad_date_and_duplicates():
    html = ('<article class="card"><a class="card-link" href="https://x/a"><h3 class="card-title">T</h3></a>'
            '<time datetime="nope"></time></article>'
            '<article class="card"><a class="card-link" href="https://x/a"><h3 class="card-title">T</h3></a></article>')
    got = parse_listing(html)
    assert len(got) == 1 and got[0].published is None


def test_numbers_ending_in_000_are_not_triple_zero():
    assert not is_outage_relevant(AcmaRelease("Fine", "u", "sent more than 32,000 emails", None))
    assert is_outage_relevant(AcmaRelease("Call Triple Zero (000) failed", "u", "", None))
