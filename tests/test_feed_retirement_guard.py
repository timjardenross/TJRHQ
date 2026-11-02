"""A retired feed that still answers with a retirement notice fails the heartbeat."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import pytest

import intelligence.emergency_alerts as ea


def _alert(headline):
    return SimpleNamespace(headline=headline, severity="unknown")


@pytest.mark.parametrize("headline", [
    "Feed Retirement Notice",
    "This feed has been retired",
    "API no longer available",
    "Decommission notice",
])
def test_retirement_headlines_are_caught(headline):
    assert ea.feed_retirement_notice([_alert(headline)]) == headline


@pytest.mark.parametrize("headline", [
    "Bus service discontinued during bushfire",
    "Moderate Flood Warning for the Barcoo River",
    "Retire to a safe place now",
    "",
])
def test_ordinary_alerts_are_not(headline):
    assert ea.feed_retirement_notice([_alert(headline)]) is None


def test_run_source_fails_the_heartbeat_and_does_not_upsert():
    fake = SimpleNamespace(fetch=lambda: [_alert("Feed Retirement Notice")])
    beats = []
    with patch.dict(ea._ADAPTERS, {"x_src": (fake, "emergency_alert_x")}), patch.object(ea, "_upsert_batch") as upsert:
        out = ea.run_source("x_src", run_started_at="2026-11-02T00:00:00+00:00", heartbeats=beats)
    assert "retired" in out["error"] and not upsert.called
    assert beats[0]["status"] == "failed" and "retired" in beats[0]["error_message"]
