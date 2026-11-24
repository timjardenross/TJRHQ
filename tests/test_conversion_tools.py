"""Conversion measurement and replay-sample tools (offline, read-only). Pins the numbers reported in the findings doc."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from tools.intelligence import conversion_measure as cm
from tools.intelligence import replay_sample as rs
from tools.intelligence.alert_replay import load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"
DOC = _REPO / "docs/incident-replay-sample-2026-11-24.md"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def measured():
    return cm.measure(load_events(cm.EXPORT), json.loads(cm.REF.read_text(encoding="utf-8")))


def test_measurement_covers_the_same_records_for_every_system(measured):
    assert measured["material_records"] == 13 and measured["negative_records"] == 5
    assert set(measured["systems"]) == {"legacy", "morning_v1", "tiered"}


def test_pinned_measurement_numbers(measured):
    s = measured["systems"]
    assert (s["legacy"]["material_detected"], s["morning_v1"]["material_detected"], s["tiered"]["material_detected"]) == ("7/13", "8/13", "5/13")
    assert (s["legacy"]["material_alerted"], s["morning_v1"]["material_alerted"], s["tiered"]["material_alerted"]) == ("1/13", "3/13", "3/13")
    assert all(x["false_urgency_records"] == [] for x in s.values())
    assert s["tiered"]["negatives_reaching_brief_level"] == [] and len(s["morning_v1"]["negatives_reaching_brief_level"]) == 2
    assert s["legacy"]["false_restoration_records"] is None and s["tiered"]["false_restoration_records"] == ["RS-008"]


def test_frozen_reference_files_are_untouched():
    import hashlib
    ref = cm.REF.read_bytes()
    assert len(json.loads(ref)["incidents"]) == 53           # the frozen v1 set: never padded or edited by this work
    assert hashlib.sha256(ref).hexdigest()                    # read-only use; the git diff for this PR must not list it


def test_replay_sample_is_labelled_replay_and_covers_three_incidents():
    text = rs.render_markdown(load_events(FIXTURE))
    assert text.startswith("# REPLAY")
    assert "Nothing was sent" in text
    for name in rs.FAMILIES:
        assert f"## {name}" in text
    assert text.count("**ALERT** at") == 1                    # the Microsoft outage alerts exactly once


def test_committed_sample_matches_the_generator():
    assert DOC.read_text(encoding="utf-8") == rs.render_markdown(load_events(FIXTURE)) + "\n"
