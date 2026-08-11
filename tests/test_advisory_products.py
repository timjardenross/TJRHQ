"""Tests for MSN-0099 intelligence products + presentation layer.

Key invariants:
 - products show MEANING, not machinery (no scores/rankings/confidence numbers);
 - the Daily Awareness Brief is curated (caps + suppression);
 - interruption is exceptional (escalation only);
 - confidence is shown as words, never numbers.

Isolated via conftest. Runs offline.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
if str(_ADVISORY) not in sys.path:
    sys.path.insert(0, str(_ADVISORY))

import presentation as P  # noqa: E402
from _local_import_advisory import import_sibling, reload_sibling  # noqa: E402

# Fleet Engineering Review 2026-08-11: 7 of the 17 names below (outcomes,
# learning, patterns, opportunities, forecast, operating_picture, service)
# collide with same-named files elsewhere in the repo (see
# core/advisory/_local_import_advisory.py's own docstring). A plain bare
# `importlib.reload(importlib.import_module(m))` for those 7 could reload
# — or, worse, wrongly cache — the WRONG file if something else in the
# same pytest session already claimed that bare name; confirmed as the
# real cause of AttributeErrors against operating_picture/daily_brief in
# full multi-file test runs. Routed through reload_sibling() instead,
# which stays collision-proof and still mutates the same cached module
# object in place (matching real importlib.reload() semantics) so
# cross-references from other core/advisory modules see the refresh.
_COLLIDING_RELOAD_NAMES = {
    "outcomes", "learning", "patterns", "opportunities", "forecast",
    "operating_picture", "service",
}
# Original reload order preserved exactly (only the per-name mechanism
# changed) in case reload order itself matters to any of these modules.
_RELOAD_ORDER = (
    "outcomes", "timeline", "learning", "calibration", "metrics",
    "patterns", "signals", "opportunities", "strategic", "forecast",
    "operating_picture", "wellness", "temporal", "triggers",
    "presentation", "products", "service",
)


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    for m in _RELOAD_ORDER:
        if m in _COLLIDING_RELOAD_NAMES:
            reload_sibling(m)
        else:
            importlib.reload(importlib.import_module(m))
    service = import_sibling("service")
    outcomes = import_sibling("outcomes")
    for i in range(6):
        r = service.request_advice(f"Rollout decision {i} about sequencing?")
        outcomes.record_outcome(r.advisory_id, outcome="success" if i % 2 else "failure")
    return tmp_path


# --- Presentation primitives (WP6/WP7) ------------------------------------

def test_humanize_confidence_is_words():
    assert P.humanize_confidence(0.9) == "well-supported"
    assert P.humanize_confidence(0.6) == "reasonably supported"
    assert P.humanize_confidence(0.2) == "unproven"
    assert P.humanize_confidence(band="High") == "well-supported"
    # never a number
    for v in (0.0, 0.5, 1.0):
        assert not any(ch.isdigit() for ch in P.humanize_confidence(v))


def test_curate_caps_and_suppresses():
    c = P.curate([1, 2, 3, 4, 5], 2)
    assert c["shown"] == [1, 2] and c["suppressed"] == 3


def test_interruption_is_exceptional():
    assert P.interruption_class("escalation") == "interrupt"
    assert P.interruption_class("concern") == "brief"
    assert P.interruption_class("warning") == "brief"
    assert P.interruption_class("observation") == "silent"
    assert P.deserves_interruption("concern") is False
    assert P.deserves_interruption("escalation") is True


def test_strip_machinery_removes_hidden_keys():
    raw = {"message": "x", "score": 0.9, "confidence_value": 0.8,
           "officer_ranking": [1], "nested": {"rank_score": 5, "keep": "y"}}
    clean = P.strip_machinery(raw)
    assert "message" in clean and clean["nested"]["keep"] == "y"
    assert "score" not in clean and "confidence_value" not in clean
    assert "officer_ranking" not in clean and "rank_score" not in clean["nested"]


# --- Products: meaning, not machinery -------------------------------------

_MACHINERY = ["rank_score", "confidence_value", "officer_ranking", "outcome_score",
              "success_rate", "sample_size", "accuracy", "confidence_distribution",
              "advisor_utilisation", "confidence_adjustment"]


def _no_machinery(prod: dict) -> bool:
    blob = json.dumps(prod)
    return not any(k in blob for k in _MACHINERY)


def test_daily_awareness_brief_shape(seeded):
    import products
    importlib.reload(products)
    b = products.daily_awareness_brief()
    headings = [s["heading"] for s in b["sections"]]
    assert "What Changed" in headings
    assert "What Requires Attention" in headings
    assert b["bottom_line"]
    assert _no_machinery(b), "awareness brief must not leak machinery"


def test_all_products_hide_machinery(seeded):
    import products
    importlib.reload(products)
    for builder in (products.daily_awareness_brief, products.captains_operating_picture,
                    products.wellness_insights, products.strategic_outlook,
                    products.opportunity_review, products.operational_resilience_watch):
        prod = builder()
        assert "product" in prod and "sections" in prod
        assert _no_machinery(prod), f"{prod.get('product')} leaked machinery"


def test_catalogue_is_small_and_described(seeded):
    import products
    importlib.reload(products)
    c = products.catalogue()
    assert 3 <= c["count"] <= 8  # a SMALL number of high-value products
    for p in c["products"]:
        assert "cadence" in p and "interruption" in p


def test_wellness_product_non_clinical(seeded):
    import products
    importlib.reload(products)
    w = products.wellness_insights()
    assert "non-clinical" in w["note"].lower()


def test_resilience_watch_degrades_gracefully(seeded):
    import products
    importlib.reload(products)
    r = products.operational_resilience_watch()
    # offline there is no source data; must still return a valid product
    assert r["product"] == "Operational Resilience Watch"
    assert r["sections"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
