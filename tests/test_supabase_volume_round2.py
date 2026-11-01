"""Round-2 Supabase request-volume reductions (usage review 2026-09-27):
each test fails against the pre-change per-item / per-cycle behaviour."""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: MagicMock()))
for sub in ("core/coordination", "tools/health"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

import collect_health_signals as chs
import number_one_exporter as noe
import validate_health_source_accuracy as vhsa

import core.coordination.number_one_memory_adapter as noma
from intelligence import proactive_cadences
from intelligence.persistence import intelligence_store as store

# ── Number One exporter: intelligence reports at most hourly ────────────────

def test_exporter_skips_reports_while_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(noe, "_REPO_ROOT", tmp_path)
    (tmp_path / "outputs").mkdir()
    exporter = noe.NumberOneExporter.__new__(noe.NumberOneExporter)
    with patch.object(noe, "_run_intelligence_reports") as run_reports, \
         patch.object(noe, "_persist_readiness_snapshot_if_available") as persist:
        exporter.export_intelligence()  # no report files yet -> runs
        assert run_reports.call_count == 1
        for name in noe._INTELLIGENCE_REPORTS:
            (tmp_path / "outputs" / f"{name}.json").write_text("{}")
        exporter.export_intelligence()  # all fresh -> readiness only
        assert run_reports.call_count == 1
        persist.assert_called_once()


def test_exporter_reruns_when_any_report_is_stale(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(noe, "_REPO_ROOT", tmp_path)
    (tmp_path / "outputs").mkdir()
    for name in noe._INTELLIGENCE_REPORTS:
        (tmp_path / "outputs" / f"{name}.json").write_text("{}")
    old = next(iter(noe._INTELLIGENCE_REPORTS))
    stale = datetime.now(timezone.utc).timestamp() - noe._INTELLIGENCE_REPORT_INTERVAL_SECONDS - 5
    os.utime(tmp_path / "outputs" / f"{old}.json", (stale, stale))
    assert noe._intelligence_reports_fresh() is False


# ── Number One memory adapter: unfiltered table reads cached ────────────────

def test_memory_adapter_caches_table_reads(monkeypatch):
    monkeypatch.setattr(noma, "_table_cache", {})
    adapter = noma.NumberOneMemoryAdapter.__new__(noma.NumberOneMemoryAdapter)
    adapter.supabase = MagicMock()
    raw = adapter.supabase.raw_client
    raw.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "c1", "name": "cap"}])
    first = adapter._retrieve_from_supabase("capabilities", "query one")
    second = adapter._retrieve_from_supabase("capabilities", "a different query")
    assert first == second
    assert raw.table.call_count == 1


def test_memory_adapter_failure_falls_back_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(noma, "_table_cache", {})
    adapter = noma.NumberOneMemoryAdapter.__new__(noma.NumberOneMemoryAdapter)
    adapter.repo_root = ROOT
    adapter.supabase = MagicMock()
    adapter.supabase.raw_client.table.side_effect = RuntimeError("down")
    with patch.object(adapter, "_retrieve_from_files", return_value=["file"]) as files:
        assert adapter._retrieve_from_supabase("adr", "q") == ["file"]
    files.assert_called_once()
    assert "adr" not in noma._table_cache


# ── Pending research sweep: one read for both passes ────────────────────────

def _sweep(rows):
    db = MagicMock()
    db.enabled.return_value = True
    query = db._client.table.return_value.select.return_value.or_.return_value.order.return_value.limit.return_value
    query.execute.return_value = MagicMock(data=rows)
    fake = types.SimpleNamespace(_db=db, _run_research=MagicMock(), process_captured_item=MagicMock())
    with patch.dict(sys.modules, {"core.inbox.orchestrator": fake}), \
         patch.object(proactive_cadences, "_shakedown_log"):
        proactive_cadences.job_pending_research_sweep()
    return db, fake


def test_sweep_uses_one_query_for_both_passes():
    rows = [
        {"id": 1, "title": "a", "processing_status": "pending", "research_status": "pending"},
        {"id": 2, "title": "b", "processing_status": "done", "research_status": "pending"},
    ]
    db, fake = _sweep(rows)
    assert db._client.table.call_count == 1
    fake.process_captured_item.assert_called_once_with(1)
    fake._run_research.assert_called_once_with(2, rows[1])  # item 1 excluded: handled in pass 1


def test_sweep_requeries_research_when_first_read_is_full():
    rows = [{"id": i, "title": "x", "processing_status": "pending", "research_status": None} for i in range(50)]
    db, _ = _sweep(rows)
    assert db._client.table.call_count == 2


# ── Health source validator: prefetch instead of 4-5 queries per source ─────

def test_validator_prefetch_answers_per_source_reads():
    v = vhsa.HealthSourceValidator.__new__(vhsa.HealthSourceValidator)
    v.dry_run = True
    v.validated_count = v.errors = 0
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    v._bulk = {
        "days": 30,
        "validations": [
            {"signal_id": "s1", "source_id": "A", "is_accurate": True, "validated_at": recent},
            {"signal_id": "s9", "source_id": "A", "is_accurate": True, "validated_at": old},
            {"signal_id": "s5", "source_id": "B", "is_accurate": False, "validated_at": recent},
        ],
        "recent_signals": [
            {"signal_id": "s1", "source_id": "A", "study_design": "rct"},
            {"signal_id": "s2", "source_id": "A", "study_design": "rct"},
        ],
        "scored_signals": [{"source_id": "A", "methodology_quality_score": q} for q in (0.4, 0.6, 0.8)],
    }
    v.supabase = MagicMock()
    assert v.get_unvalidated_signals_for_source("A") == [{"signal_id": "s2", "study_design": "rct"}]
    assert v.recompute_avg_methodology_quality("A") == (0.6, 3)
    v.save_validation("s2", "A", True, "automated", "x")  # dry run still updates the prefetched view
    assert sum(1 for r in v._bulk["validations"] if r["source_id"] == "A" and r["is_accurate"]) == 3
    v.supabase.table.assert_not_called()


# ── Health signal collector: batched dedup + cached lookups ─────────────────

def test_collector_dedups_in_batches_and_caches_tiers():
    c = chs.HealthCollector.__new__(chs.HealthCollector)
    c.dry_run = False
    c.supabase = MagicMock()
    c._source_cache, c._rss_source_cache, c._tier_cache = {}, {}, {}
    c.stats = {"saved": 0, "duplicates": 0, "errors": 0, "sources_auto_registered": 0}
    items = [{"source": "ctgov", "nct_id": f"NCT{i}", "title": "t", "health_domain": "d",
              "study_design": "rct", "canonical_url": f"u{i}"} for i in range(250)]
    known = chs._dedup_hash(items[0])
    c.supabase.table.return_value.select.return_value.in_.return_value.execute.side_effect = [
        MagicMock(data=[{"dedup_hash": known}]), MagicMock(data=[]), MagicMock(data=[])]
    c._known_hashes = c._existing_hashes([chs._dedup_hash(i) for i in items])
    assert c.supabase.table.return_value.select.return_value.in_.call_count == 3  # 100 + 100 + 50
    assert c._known_hashes == {known}

    with patch.object(c, "_get_or_create_source", return_value="SRC"), \
         patch.object(c, "_methodology_quality", return_value=0.5), \
         patch.object(c, "_confidence_level", return_value="MEDIUM"), \
         patch.object(c, "_signal_type_from_title", return_value="study_result"):
        c.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"reliability_tier": "TIER_2"}])
        for item in items[:5]:
            c.save_item(item)
    assert c.stats["duplicates"] == 1 and c.stats["saved"] == 4
    # one tier lookup for the shared source, no per-item dedup GETs
    assert c.supabase.table.return_value.select.return_value.eq.return_value.limit.call_count == 1


# ── Intelligence source health: one array insert per collection run ─────────

def test_source_health_batch_single_post_and_failure_events(monkeypatch):
    monkeypatch.setattr(store, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(store, "SUPABASE_KEY", "key")
    posts = []

    def fake_urlopen(req, timeout=None):
        posts.append((json.loads(req.data), req.headers.get("Prefer")))
        return MagicMock(__enter__=lambda s: s, __exit__=lambda s, *a: False)

    now = datetime.now(timezone.utc)
    healths = [
        types.SimpleNamespace(source_id=f"s{i}", checked_at=now, status="failed" if i == 1 else "ok",
                              items_retrieved=1, latency_ms=10, error_message="boom" if i == 1 else None,
                              http_status=200, content_valid=True, content_validity_reason=None)
        for i in range(3)
    ]
    with patch.object(store.urllib.request, "urlopen", fake_urlopen), \
         patch.object(store, "_publish_core_event") as publish:
        store.save_source_health_batch(healths)
    assert len(posts) == 1
    assert [r["source_id"] for r in posts[0][0]] == ["s0", "s1", "s2"]
    assert posts[0][1] == "return=minimal"
    publish.assert_called_once()
