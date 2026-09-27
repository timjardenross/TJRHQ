"""recompute_signal_scores writes score changes in bulk (migration 0224),
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
