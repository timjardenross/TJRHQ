"""Australian institutions with no Australian marker word in the headline must classify as geography AU (NAB, Coles, Woolworths, Qantas,
TPG, Commonwealth Bank ...). Before: GLOBAL, which carries the lowest geography weight in the ranker."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO)]

from intelligence.classification.classifier import classify
from intelligence.models import IntelligenceItem


def _geo(title: str) -> str:
    item = IntelligenceItem(source_id="s", source_name="ABC News", source_priority=2, source_confidence_weight=0.8, source_category="media",
                            raw_title=title, collected_at=datetime(2026, 11, 24, tzinfo=timezone.utc), raw_summary="")
    return classify(item).geography


@pytest.mark.parametrize("title", [
    "Breaking: NAB customers experiencing phone and internet banking outages",
    "Coles Group investigating a cyber incident",
    "Woolworths apologises after customers report drained gift card balances",
    "Qantas taps Accenture for major IT and data modernisation",
    "TPG Telecom wants customer-triggered AI agents",
    "Commonwealth Bank allegedly overcharged business customers",
    "ANZ uses AI to move 1.7PB data platform to AWS",
    "Origin Energy (ASX:ORG) Faces the East Coast Gas Reservation Shift",
    "Vocus hit by Singapore cable break",
    "Services Australia myGov outage leaves millions unable to log in",
])
def test_australian_institutions_are_au(title):
    assert _geo(title) == "AU"


@pytest.mark.parametrize("title", [
    "Police nab two suspects after chase",
    "South Africa’s Woolworths, Momentum Face Investor Pay Challenges",
    "Cloudflare outage disrupts websites worldwide",
    "Microsoft Outlook outage hits users globally",
    "Paper mill tackles ethanol shortage in Brazil",
])
def test_non_australian_items_are_not_tagged_au(title):
    assert _geo(title) != "AU"


def test_existing_markers_still_work():
    assert _geo("Victoria power outage hits 20,000 homes") == "AU"
    assert _geo("Singapore data centre fire") == "APAC"
