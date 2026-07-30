#!/usr/bin/env python3
"""
Unit tests for the Signal -> Opportunity Converter (Phase 1C Communications).

Pure tests: _get / _post_batch / _log_batch_operation are monkeypatched so no
network or Supabase credentials are required.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.content import signal_opportunity_converter as conv


def _signal(
    event_id_text="evt-1",
    raw_title="Team wellness initiative reduced absenteeism 15%",
    pillar_key="wellness_sustainable_performance",
    rank_score=0.85,
    domain="health",
    suggested_angle="A 15% drop in absenteeism worth writing about",
):
    return {
        "id": f"signal-{event_id_text}",
        "event_id_text": event_id_text,
        "raw_title": raw_title,
        "pillar_key": pillar_key,
        "rank_score": rank_score,
        "domain": domain,
        "suggested_angle": suggested_angle,
        "suppressed": False,
    }


def setup_function(_fn):
    # Neutralise the audit log write for every test unless a test overrides it.
    conv._log_batch_operation = lambda result: None


def test_no_signals_returns_no_signals_status(monkeypatch):
    monkeypatch.setattr(conv, "_get", lambda path: [])
    result = conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="health")
    assert result["status"] == "no_signals"
    assert result["created"] == 0


def test_successful_batch_creates_all_opportunities(monkeypatch):
    signals = [_signal(event_id_text=f"evt-{i}") for i in range(3)]
    monkeypatch.setattr(conv, "_get", lambda path: signals)

    created = [{"id": f"opp-{i}"} for i in range(3)]
    monkeypatch.setattr(conv, "_post_batch", lambda table, rows: created)

    result = conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="health")

    assert result["status"] == "completed"
    assert result["requested"] == 3
    assert result["created"] == 3
    assert result["opportunity_ids"] == ["opp-0", "opp-1", "opp-2"]
    assert result["signal_ids"] == ["evt-0", "evt-1", "evt-2"]


def test_batch_insert_failure_creates_nothing(monkeypatch):
    """If the atomic insert call fails, zero opportunities are created — no partial commit."""
    signals = [_signal(event_id_text=f"evt-{i}") for i in range(5)]
    monkeypatch.setattr(conv, "_get", lambda path: signals)
    monkeypatch.setattr(conv, "_post_batch", lambda table, rows: None)

    result = conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="health")

    assert result["status"] == "failed"
    assert result["created"] == 0
    assert result["opportunity_ids"] == []
    assert "rolled back" in result["error"]


def test_invalid_signal_aborts_entire_batch_before_insert(monkeypatch):
    """One malformed signal in a batch of 5 rolls back all 5 — none created."""
    good = [_signal(event_id_text=f"evt-{i}") for i in range(4)]
    bad = _signal(event_id_text=None)  # missing event_id_text -> invalid
    signals = good + [bad]
    monkeypatch.setattr(conv, "_get", lambda path: signals)

    insert_calls = []
    monkeypatch.setattr(
        conv, "_post_batch", lambda table, rows: insert_calls.append(rows) or [{"id": "x"}]
    )

    result = conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="health")

    assert result["status"] == "failed"
    assert result["created"] == 0
    assert insert_calls == []  # batch insert must never be attempted


def test_domain_filter_is_applied_to_query(monkeypatch):
    captured_paths = []

    def fake_get(path):
        captured_paths.append(path)
        return []

    monkeypatch.setattr(conv, "_get", fake_get)
    conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="operational")

    assert "domain=eq.operational" in captured_paths[0]


def test_both_domains_omits_domain_filter(monkeypatch):
    captured_paths = []

    def fake_get(path):
        captured_paths.append(path)
        return []

    monkeypatch.setattr(conv, "_get", fake_get)
    conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain=None)

    assert "domain=eq." not in captured_paths[0]


def test_default_format_per_domain(monkeypatch):
    monkeypatch.setattr(conv, "_get", lambda path: [_signal(domain="health")])

    captured_rows = []
    monkeypatch.setattr(
        conv,
        "_post_batch",
        lambda table, rows: captured_rows.extend(rows) or [{"id": "opp-1"}],
    )

    conv.create_opportunities_from_signals(limit=5, min_rank_score=0.7, domain="health")

    assert captured_rows[0]["format"] == "case_study"


def test_limit_must_be_positive():
    import pytest

    with pytest.raises(ValueError):
        conv.create_opportunities_from_signals(limit=0)
