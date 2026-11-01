"""Repeated healthy heartbeats are written at most every
HEARTBEAT_OK_MIN_INTERVAL_SECONDS per domain; failures, status changes and
exempt domains always go through (Supabase usage review 2026-09-27)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import heartbeat as hb


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, "_URL", "https://example.supabase.co")
    monkeypatch.setattr(hb, "_KEY", "key")
    monkeypatch.setattr(hb, "_THROTTLE_STATE_PATH", tmp_path / "throttle.json")
    monkeypatch.setattr(hb, "_OK_MIN_INTERVAL_SECONDS", 1200)
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(hb.time, "time", lambda: clock["now"])
    posts = []

    def fake_urlopen(req, timeout=None):
        posts.append(json.loads(req.data))
        return MagicMock(__enter__=lambda s: s, __exit__=lambda s, *a: False)

    monkeypatch.setattr(hb.urllib.request, "urlopen", fake_urlopen)
    return clock, posts


def test_repeated_ok_is_throttled_until_interval(env):
    clock, posts = env
    assert hb.record_heartbeat("pending_research_sweep")
    clock["now"] += 300
    assert hb.record_heartbeat("pending_research_sweep")  # skipped, still reports success
    assert len(posts) == 1
    clock["now"] += 1200
    hb.record_heartbeat("pending_research_sweep")
    assert len(posts) == 2


def test_failures_and_recovery_always_written(env):
    clock, posts = env
    hb.record_heartbeat("d")
    clock["now"] += 60
    hb.record_heartbeat("d", status="failed", error_message="x")
    clock["now"] += 60
    hb.record_heartbeat("d", status="failed", error_message="x")
    clock["now"] += 60
    hb.record_heartbeat("d")  # failed -> ok transition
    assert [p["status"] for p in posts] == ["ok", "failed", "failed", "ok"]


def test_exempt_domains_never_throttled(env):
    clock, posts = env
    for _ in range(3):
        hb.record_heartbeat("verification_engine")
        hb.record_heartbeat("intelligence_collection")
        clock["now"] += 60
    assert len(posts) == 6


def test_failed_write_is_not_remembered(env, monkeypatch):
    monkeypatch.setattr(hb.urllib.request, "urlopen", MagicMock(side_effect=OSError("down")))
    assert hb.record_heartbeat("d") is False
    assert not hb._THROTTLE_STATE_PATH.exists()


def test_batch_filters_throttled_rows(env):
    clock, posts = env
    hb.record_heartbeats([{"domain_key": "a", "status": "ok"}, {"domain_key": "b", "status": "ok"}])
    clock["now"] += 60
    hb.record_heartbeats([{"domain_key": "a", "status": "ok"}, {"domain_key": "b", "status": "failed"}])
    assert [[r["domain_key"] for r in p] for p in posts] == [["a", "b"], ["b"]]


def test_zero_interval_disables_throttle(env, monkeypatch):
    _clock, posts = env
    monkeypatch.setattr(hb, "_OK_MIN_INTERVAL_SECONDS", 0)
    hb.record_heartbeat("d")
    hb.record_heartbeat("d")
    assert len(posts) == 2


def test_unreadable_state_fails_open(env):
    _clock, posts = env
    hb._THROTTLE_STATE_PATH.write_text("not json")
    hb.record_heartbeat("d")
    assert len(posts) == 1
    with patch.object(hb, "_read_throttle_state", return_value={}):
        hb.record_heartbeat("d")
    assert len(posts) == 2
