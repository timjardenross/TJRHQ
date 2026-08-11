"""Tests for MSN-0098 personal/strategic intelligence modules:
data_quality, wellness, operating_picture, strategic, forecast, daily_brief.

Isolated via conftest (ADVISORY_DATA_ROOT → temp). Runs offline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
if str(_ADVISORY) not in sys.path:
    sys.path.insert(0, str(_ADVISORY))

from _local_import_advisory import import_sibling, reload_sibling  # noqa: E402

# Fleet Engineering Review 2026-08-11: operating_picture, forecast,
# daily_brief, learning, opportunities, outcomes, service collide with
# same-named files elsewhere in the repo — see core/advisory/
# _local_import_advisory.py's own docstring. Routed through
# reload_sibling()/import_sibling() so this file's own module-level
# reloads can't be poisoned by (or poison) an unrelated same-named file
# loaded elsewhere in the same pytest session.
_COLLIDING_RELOAD_NAMES = {
    "outcomes", "learning", "opportunities", "operating_picture",
    "forecast", "daily_brief", "service",
}


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    for m in ("outcomes", "timeline", "learning", "calibration", "metrics",
              "patterns", "signals", "advisory_health", "opportunities",
              "data_quality", "wellness", "operating_picture", "strategic",
              "forecast", "daily_brief", "service"):
        if m in _COLLIDING_RELOAD_NAMES:
            reload_sibling(m)
        else:
            importlib.reload(importlib.import_module(m))
    service = import_sibling("service")
    outcomes = import_sibling("outcomes")
    for i in range(6):
        r = service.request_advice(f"Decision {i} about rollout sequencing and capacity?")
        outcomes.record_outcome(r.advisory_id, outcome="success" if i % 3 else "failure")
    return tmp_path


# --- WP1 + WP8 data quality / trust ---------------------------------------

def test_capture_gaps(seeded):
    import data_quality
    importlib.reload(data_quality)
    g = data_quality.capture_gaps()
    assert "gaps" in g and isinstance(g["gaps"], list)
    assert "narrative" in g


def test_trust_metrics_recognises_uncertainty(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    import data_quality
    importlib.reload(data_quality)
    t = data_quality.trust_metrics()
    # empty dataset: must flag insufficient data, not overclaim
    assert t["sufficient_data"] is False
    assert t["recognises_uncertainty"] is True


# --- WP3 wellness ----------------------------------------------------------

def test_wellness_available_and_advisory():
    import wellness
    importlib.reload(wellness)
    w = wellness.wellness_intelligence()
    assert "narrative" in w
    # health summary exists in the repo, so it should parse
    assert w.get("available") in (True, False)
    assert "clinical" in w["narrative"].lower() or not w.get("available")


# --- WP2 operating picture -------------------------------------------------

def test_operating_picture(seeded):
    operating_picture = reload_sibling("operating_picture")
    p = operating_picture.captain_operating_picture()
    assert "workload" in p and "headline" in p
    # missions load from the canonical index regardless of cwd
    assert p["workload"]["missions_on_record"] >= 1
    assert "advisory only" in p["note"].lower()


# --- WP4 + WP6 strategic / opportunity -------------------------------------

def test_strategic_intelligence(seeded):
    import strategic
    importlib.reload(strategic)
    s = strategic.strategic_intelligence()
    for key in ("should_concern", "what_is_changing", "portfolio_health",
                "opportunities", "headline"):
        assert key in s


def test_opportunity_intelligence(seeded):
    import strategic
    importlib.reload(strategic)
    o = strategic.opportunity_intelligence()
    assert "opportunities" in o and "count" in o


# --- WP5 forecasting (evidence before prediction) --------------------------

def test_forecasts_are_evidence_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    forecast = reload_sibling("forecast")
    data = forecast.all_forecasts()
    # with no data, every forecast must report insufficient evidence (no guessing)
    assert all(f["direction"] == "insufficient_evidence" for f in data["forecasts"])
    assert data["supported_count"] == 0


def test_forecasts_supported_with_data(seeded):
    forecast = reload_sibling("forecast")
    data = forecast.all_forecasts()
    assert data["supported_count"] >= 1
    # confidence never overclaims
    for f in data["forecasts"]:
        assert f["confidence"] in ("low", "moderate")


# --- WP7 daily briefing ----------------------------------------------------

def test_daily_brief_composes(seeded):
    daily_brief = reload_sibling("daily_brief")
    b = daily_brief.daily_intelligence_brief()
    for key in ("what_changed_overnight", "what_matters_today", "operating_picture",
                "wellness", "strategic", "headline", "note"):
        assert key in b
    assert "actioned" in b["note"].lower() or "advisory only" in b["note"].lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
