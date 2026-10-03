"""Tests for intelligence.scheduler._resilience_change_scan_job and the
intelligence_store query it uses (Operational Resilience Advisor change flags).

The store is patched at its own module (the job imports it inside its body,
matching the scheduler's existing job style); no Supabase or network access.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "platform-runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intelligence import scheduler
from intelligence.persistence import intelligence_store as store


def _events():
    return [
        {"event_id": "e1", "source_name": "APRA Media Releases", "raw_title": "APRA finalises CPS 230 FAQ",
         "raw_summary": "", "canonical_url": "https://example.test/a", "published_at": "2026-10-01T00:00:00+00:00"},
        {"event_id": "e2", "source_name": "BIS Press Releases", "raw_title": "Basel Committee consults on operational resilience",
         "raw_summary": "", "canonical_url": "https://example.test/b", "published_at": "2026-10-01T00:00:00+00:00"},
        {"event_id": "e3", "source_name": "APRA Media Releases", "raw_title": "APRA publishes quarterly statistics",
         "raw_summary": "", "canonical_url": "https://example.test/c", "published_at": "2026-10-01T00:00:00+00:00"},
    ]


def test_job_flags_matching_events_and_records_heartbeat(monkeypatch, tmp_path):
    flags = tmp_path / "flags.jsonl"
    monkeypatch.setenv("RESILIENCE_CHANGE_FLAGS", str(flags))
    seen = {}

    def fake_load(prefixes, since_iso, limit=500):
        seen["prefixes"] = prefixes
        return _events()

    beats = []
    monkeypatch.setattr(store, "load_events_by_source_prefixes", fake_load)
    monkeypatch.setattr(scheduler, "_record_heartbeat", lambda *a, **k: beats.append((a, k)))

    scheduler._resilience_change_scan_job()

    assert seen["prefixes"] == ["APRA", "BIS"]
    records = [json.loads(line) for line in flags.read_text().splitlines()]
    flagged = {(r["framework_id"], r["event_id"]) for r in records}
    assert ("APRA-CPS-230", "e1") in flagged
    assert ("BCBS-d516", "e2") in flagged
    assert not any(eid == "e3" for _, eid in flagged)
    assert beats[0][0][:2] == ("resilience_change_scan", "ok")


def test_job_failure_is_contained_and_heartbeated(monkeypatch, tmp_path):
    monkeypatch.setenv("RESILIENCE_CHANGE_FLAGS", str(tmp_path / "flags.jsonl"))

    def boom(*a, **k):
        raise RuntimeError("Supabase not configured")

    beats = []
    monkeypatch.setattr(store, "load_events_by_source_prefixes", boom)
    monkeypatch.setattr(scheduler, "_record_heartbeat", lambda *a, **k: beats.append((a, k)))

    scheduler._resilience_change_scan_job()  # must not raise

    assert beats[0][0][:2] == ("resilience_change_scan", "failed")


def test_store_query_builds_prefix_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(store, "_get_strict", lambda path, timeout=10: captured.setdefault("path", path) and [])
    store.load_events_by_source_prefixes(["APRA", "BIS; drop"], "2026-10-01T00:00:00+00:00")
    path = captured["path"]
    assert "or=(source_name.ilike.APRA*,source_name.ilike.BIS%20drop*)" in path
    assert "collected_at=gte.2026-10-01T00%3A00%3A00%2B00%3A00" in path
    assert "suppressed" not in path


def test_store_query_empty_prefixes_skips_request(monkeypatch):
    monkeypatch.setattr(store, "_get_strict", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert store.load_events_by_source_prefixes([], "2026-10-01") == []
