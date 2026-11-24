"""Tiered/clustered brief wiring (DELIVERY_TIERS_V1) and opt-in event recording (CAPTAINS_BRIEF_RECORD_EVENTS). No network, no sends.

The central guarantee: with the flags OFF the morning evidence block is byte-for-byte what it was before this change
(tests/fixtures/conversion_integration/morning_view_flags_off_golden.txt was generated from the unchanged ``brief_evidence.morning_view``)."""
from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import brief_event_links as bel
from intelligence import brief_evidence as be
from intelligence import captains_brief as cb
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb
from tools.intelligence.alert_replay import load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"
GOLDEN = _REPO / "tests/fixtures/conversion_integration/morning_view_flags_off_golden.txt"
NOW = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
_REAL_BUILD = be.build_evidence


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in ("DELIVERY_TIERS_V1", "INCIDENT_CLUSTERING_V2", bel.FLAG, "BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING"):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def events():
    evs = load_events(FIXTURE)
    return [e for e in evs if e["collected_at"] <= "2026-11-13T21:00:00+00:00"]


def _stub_evidence(monkeypatch, events):
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    monkeypatch.setattr(be, "load_events", lambda sb_get, **kw: events)
    monkeypatch.setattr(be, "build_evidence", lambda evs, **kw: _REAL_BUILD(evs, now=NOW, **kw))


def test_flags_off_renders_identical_text_to_the_unchanged_view(monkeypatch, events):
    _stub_evidence(monkeypatch, events)
    lines = cb._evidence_lines("morning", 72)
    expected = [cb._esc(x) for x in be.morning_view(_REAL_BUILD(events, now=NOW, window_hours=72))] + [""]
    assert lines == expected
    assert "\n".join(lines) == GOLDEN.read_text(encoding="utf-8")
    assert "TIERED INCIDENT PICTURE" not in "\n".join(lines)


def test_recording_flag_alone_does_not_change_the_text(monkeypatch, events):
    _stub_evidence(monkeypatch, events)
    baseline = cb._evidence_lines("morning", 72)
    monkeypatch.setenv(bel.FLAG, "1")
    bel.begin()
    assert cb._evidence_lines("morning", 72) == baseline
    assert bel.drain("morning")                       # ids were noted, text untouched


def test_tiered_flag_replaces_the_view_with_incident_level_entries(monkeypatch, events):
    _stub_evidence(monkeypatch, events)
    monkeypatch.setenv("DELIVERY_TIERS_V1", "1")
    text = "\n".join(cb._evidence_lines("morning", 72))
    assert "TIERED INCIDENT PICTURE" in text
    assert "NEW " in text and "SUBSEQUENT x" in text and "RESTORATION" in text and "RELATED x" in text


def test_one_incident_one_entry_for_the_microsoft_outage(events):
    lines, shown = tb.render(events, now=NOW)
    entries = [ln for ln in lines if ln.startswith("- ") and "Microsoft" in ln]
    assert len(entries) == 1                          # clustered: one disruption, one entry
    assert len(shown) >= 20 and len(set(shown)) == len(shown)


def test_lifecycle_labels_follow_the_clustering_roles(events):
    inc = max(ic.cluster_incidents(events, now=NOW, force=True), key=lambda i: i.n_reports)
    life = "\n".join(tb.lifecycle_lines(inc))
    assert life.count("    NEW ") == 1
    assert "RESTORATION (full)" in life or "RESTORATION (partial)" in life


def test_tier_sections_hide_context_and_reference_as_counts_only(events):
    lines, _ = tb.render(events, now=NOW)
    text = "\n".join(lines)
    assert "Context only" in text and "Reference retained" in text
    assert not any(ln.startswith("- ") and "APRA calls Microsoft outage" in ln for ln in lines)     # a CONTEXT incident gets no entry of its own


def test_empty_window_is_not_an_all_clear():
    lines, shown = tb.render([], now=NOW)
    assert shown == []
    assert any("not an all-clear" in ln for ln in lines)


# ── event recording ───────────────────────────────────────────────────────────────────────────────────────
def test_recording_is_a_noop_when_the_flag_is_off():
    store = bel.InMemoryLinkStore()
    bel.begin()
    bel.note("morning", ["a", "b"])
    assert bel.flush("morning", brief_ref="x", store=store) == 0 and store.rows == []


def test_recording_writes_ids_with_the_brief_reference_when_on(monkeypatch):
    monkeypatch.setenv(bel.FLAG, "1")
    store = bel.InMemoryLinkStore()
    bel.begin()
    bel.note("morning", ["e2", "e1"])
    bel.note("morning", ["e1"])
    assert bel.flush("morning", brief_ref="brief-1", store=store) == 2
    assert [r["event_id"] for r in store.rows] == ["e1", "e2"] and store.rows[0]["brief_id"] == "brief-1"
    assert bel.flush("morning", brief_ref="brief-1", store=store) == 0         # drained: never recorded twice


def test_recording_failure_never_raises(monkeypatch):
    monkeypatch.setenv(bel.FLAG, "1")

    class Boom:
        def record(self, *a):
            raise RuntimeError("table missing")
    bel.begin()
    bel.note("morning", ["e1"])
    assert bel.flush("morning", store=Boom()) == 0


def test_record_hook_in_send_path_does_nothing_when_off(monkeypatch):
    calls = []
    monkeypatch.setattr(cb, "_sb_get", lambda *a, **k: calls.append(a) or [])
    cb._record_brief_events("morning")
    assert calls == []                                 # no query at all with the flag off
