"""recompute_signal_scores writes score changes in bulk (migration 0225),
not one PATCH per row — the per-row version was ~31k requests a night."""

import sys
import types
from unittest.mock import MagicMock, patch

sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: MagicMock()))

from tools.intelligence import recompute_signal_scores as rss


def _recomputer():
    r = rss.SignalScoreRecomputer.__new__(rss.SignalScoreRecomputer)
    r.dry_run = False
    r.backfill = False
    r.limit = None
    r.supabase = MagicMock()
    r.stats = {"signals_confidence_recomputed": 0, "signals_rank_recomputed": 0, "errors": 0}
    return r


def _event(i, tier="TIER_1", level="HIGH", crit=None):
    return {
        "event_id": f"00000000-0000-0000-0000-{i:012d}", "source_id": "s", "risk_rating": "HIGH",
        "operational_relevance": 0.9, "banking_relevance": "high", "cps230_relevance": True,
        "osint_confidence_level": level, "criticality_score": crit,
        "intelligence_source_registry": {"reliability_tier": tier},
    }


def test_confidence_pass_skips_unchanged_and_batches_the_rest():
    crit = rss.compute_criticality("HIGH", 0.9, "high", True)
    unchanged = [_event(i, crit=crit) for i in range(3)]
    changed = [_event(100 + i, level="LOW", crit=crit) for i in range(1200)]
    r = _recomputer()
    with patch.object(r, "_fetch_all", return_value=unchanged + changed), \
         patch.object(r, "_corroboration_counts", return_value={}):
        r.recompute_confidence_and_criticality()

    assert r.stats["signals_confidence_recomputed"] == 1200
    r.supabase.table.return_value.update.assert_not_called()
    calls = r.supabase.rpc.call_args_list
    assert [c.args[0] for c in calls] == ["bulk_update_signal_scores"] * 3  # 500 + 500 + 200
    assert sum(len(c.args[1]["p_rows"]) for c in calls) == 1200
    assert calls[0].args[1]["p_rows"][0]["osint_confidence_level"] == "HIGH"


def test_same_score_tolerates_numeric_string_and_float_noise():
    assert rss._same_score("42.5", 42.5000000001)
    assert rss._same_score(None, None)
    assert not rss._same_score(None, 1.0)
    assert not rss._same_score(41.0, 42.0)


def test_bulk_update_chunk_failure_is_counted_not_raised():
    r = _recomputer()
    r.supabase.rpc.return_value.execute.side_effect = RuntimeError("boom")
    r._bulk_update_scores([{"event_id": "x", "rank_score": 1.0}] * 3, "rank_score", chunk_size=2)
    assert r.stats["errors"] == 2


def _rank_row(i, collected_at="2026-10-05T00:00:00+00:00"):
    return {
        "event_id": f"00000000-0000-0000-0000-{i:012d}", "source_id": "s", "raw_title": f"t{i}",
        "published_at": collected_at, "collected_at": collected_at, "dedup_hash": f"h{i}",
        "operational_relevance": 0.5, "rank_score": 1.0, "intelligence_source_registry": {},
    }


def _run_rank_pass(r, rows=()):
    """Run recompute_rank_scores with a stubbed ranker, returning the query builder mock
    that _fetch_all was handed and the (event_id, score) pairs ranker saw."""
    seen = {}

    def fake_fetch_all(build_query):
        seen["q"] = build_query()
        return list(rows)

    def fake_rank(events):
        seen["event_ids"] = [e.event_id for e in events]
        return [types.SimpleNamespace(event_id=e.event_id, rank_score=2.0) for e in events]

    with patch.object(r, "_fetch_all", side_effect=fake_fetch_all), \
         patch("intelligence.ranking.ranker.rank", side_effect=fake_rank):
        r.recompute_rank_scores()
    return seen


def test_rank_pass_does_not_select_raw_summary_and_is_windowed_by_default():
    r = _recomputer()
    table = r.supabase.table.return_value
    table.select.return_value.eq.return_value = table  # chain: select().eq() -> same mock
    table.gte.return_value = table
    _run_rank_pass(r, [_rank_row(1)])

    selected = table.select.call_args.args[0]
    assert "raw_summary" not in selected
    assert "raw_title" in selected  # rank() needs the title for its cross-source bonus
    (col, cutoff), _ = table.gte.call_args
    assert col == "collected_at"
    age = rss.datetime.now(rss.timezone.utc) - rss.datetime.fromisoformat(cutoff)
    assert rss.timedelta(days=rss.RANK_WINDOW_DAYS) - rss.timedelta(minutes=1) < age < rss.timedelta(days=rss.RANK_WINDOW_DAYS, minutes=1)


def test_rank_pass_backfill_reads_full_history():
    r = _recomputer()
    r.backfill = True
    table = r.supabase.table.return_value
    table.select.return_value.eq.return_value = table
    _run_rank_pass(r, [_rank_row(1)])

    table.gte.assert_not_called()
    assert "raw_summary" not in table.select.call_args.args[0]


def test_rank_pass_still_writes_changed_scores_in_bulk():
    r = _recomputer()
    table = r.supabase.table.return_value
    table.select.return_value.eq.return_value = table
    table.gte.return_value = table
    seen = _run_rank_pass(r, [_rank_row(i) for i in range(3)])

    assert len(seen["event_ids"]) == 3
    assert r.stats["signals_rank_recomputed"] == 3
    (name, payload), _ = r.supabase.rpc.call_args
    assert name == "bulk_update_signal_scores"
    assert len(payload["p_rows"]) == 3 and payload["p_rows"][0]["rank_score"] == 2.0
