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


# ── Egress controls (windowing, single corroboration read, batched escalation, I/O stats) ──

import json
from datetime import datetime, timedelta, timezone


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Just enough of the PostgREST builder for this script: select/eq/gt/gte/in_/order/range/
    insert/update, resolved against in-memory rows. Every execute() is logged on the db."""

    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.cols, self.filters, self.order_by, self.rng, self.payload = "select", None, [], None, None, None

    def select(self, cols):
        self.cols = cols
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def gt(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r[col] > val)
        self.cutoff = val
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r[col] >= val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in set(vals))
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def execute(self):
        self.db.log.append({"table": self.table, "op": self.op, "cols": self.cols, "query": self})
        if self.op == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            self.db.tables.setdefault(self.table, []).extend(rows)
            return _Resp(rows)
        if self.op == "update":
            return _Resp([])
        rows = [r for r in self.db.tables.get(self.table, []) if all(f(r) for f in self.filters)]
        if self.order_by:
            rows.sort(key=lambda r: r[self.order_by[0]], reverse=self.order_by[1])
        if self.rng:
            rows = rows[self.rng[0]:self.rng[1] + 1]
        return _Resp(rows)


class _FakeDB:
    def __init__(self, **tables):
        self.tables, self.log = tables, []

    def table(self, name):
        return _FakeQuery(self, name)

    def rpc(self, name, payload):
        q = _FakeQuery(self, f"rpc:{name}")
        q.op, q.payload = "rpc", payload
        q.execute = lambda: (self.log.append({"table": q.table, "op": "rpc", "cols": None, "query": q}), _Resp(None))[1]
        return q

    def reads(self, table):
        return [c for c in self.log if c["table"] == table and c["op"] == "select"]


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _ev(i, days_ago, title=None, rank_score=None, **extra):
    row = {
        "event_id": f"00000000-0000-0000-0000-{i:012d}", "source_id": f"src{i % 3}", "sector": "tech",
        "raw_title": title or f"alpha{i} bravo{i} charlie", "suppressed": False,
        "published_at": _iso(days_ago), "collected_at": _iso(days_ago), "dedup_hash": f"h{i}",
        "operational_relevance": 0.5, "risk_rating": "HIGH", "banking_relevance": "high",
        "cps230_relevance": True, "rank_score": rank_score, "osint_confidence_level": "LOW",
        "criticality_score": None, "intelligence_source_registry": {"reliability_tier": "TIER_2"},
    }
    row.update(extra)
    return row


def _recomputer_on(db, **attrs):
    r = rss.SignalScoreRecomputer.__new__(rss.SignalScoreRecomputer)
    r.dry_run, r.backfill, r.limit, r.supabase = False, False, None, db
    r.window_days = rss.WINDOW_DAYS
    r._call_counts, r._response_bytes = {}, {}
    r.stats = {"signals_confidence_recomputed": 0, "signals_rank_recomputed": 0, "corroboration_pairs_inserted": 0,
               "snapshots_inserted": 0, "escalations_logged": 0, "errors": 0}
    for k, v in attrs.items():
        setattr(r, k, v)
    return r


def _db_with_old_and_new_events():
    return _FakeDB(intelligence_events=[_ev(1, 2), _ev(2, 10), _ev(3, 30), _ev(4, 90)],
                   signal_corroboration=[], signal_escalation_history=[],
                   intelligence_source_registry=[], validation_job_runs=[])


def _selects(db, table="intelligence_events"):
    return [c["cols"] for c in db.reads(table)]


def _cutoff_age_days(query):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(query.cutoff)).total_seconds() / 86400


def test_rank_pass_does_not_select_raw_summary_and_still_scores():
    db = _db_with_old_and_new_events()
    r = _recomputer_on(db)
    with patch("intelligence.ranking.ranker._load_srs_scores"):
        r.recompute_rank_scores()
    cols = _selects(db)[0]
    assert "raw_summary" not in cols
    assert "raw_title" in cols and "dedup_hash" in cols and "intelligence_source_registry(" in cols
    assert r.stats["signals_rank_recomputed"] == 2  # only the two in-window events
    assert [c["table"] for c in db.log if c["op"] == "rpc"] == ["rpc:bulk_update_signal_scores"]


def test_confidence_and_rank_passes_apply_the_window_cutoff():
    db = _db_with_old_and_new_events()
    r = _recomputer_on(db)
    with patch("intelligence.ranking.ranker._load_srs_scores"):
        r.recompute_confidence_and_criticality()
        r.recompute_rank_scores()
    queries = [c["query"] for c in db.reads("intelligence_events")]
    assert len(queries) == 2
    for q in queries:
        assert abs(_cutoff_age_days(q) - rss.WINDOW_DAYS) < 0.01
    assert r.stats["signals_confidence_recomputed"] == 2  # 2 in-window events changed; 30d/90d untouched


def test_window_days_is_configurable():
    db = _db_with_old_and_new_events()
    r = _recomputer_on(db, window_days=5)
    with patch("intelligence.ranking.ranker._load_srs_scores"):
        r.recompute_rank_scores()
    assert abs(_cutoff_age_days(db.reads("intelligence_events")[0]["query"]) - 5) < 0.01
    assert r.stats["signals_rank_recomputed"] == 1


def test_full_sweep_applies_no_window_via_flag_backfill_or_sunday():
    cases = {
        "--full": {"full": True},
        "--backfill": {"backfill": True},
    }
    for label, kw in cases.items():
        with patch.object(rss, "create_client", return_value=MagicMock()), patch.object(rss, "_is_full_sweep_day", return_value=False):
            r = rss.SignalScoreRecomputer(**kw)
        assert r.window_days is None, label
        assert r.full_reason == label
    with patch.object(rss, "create_client", return_value=MagicMock()), patch.object(rss, "_is_full_sweep_day", return_value=True):
        r = rss.SignalScoreRecomputer()
    assert r.window_days is None and r.full_reason == "sunday-utc"
    with patch.object(rss, "create_client", return_value=MagicMock()), patch.object(rss, "_is_full_sweep_day", return_value=False):
        r = rss.SignalScoreRecomputer()
    assert r.window_days == rss.WINDOW_DAYS and r.full_reason is None

    # and an unwindowed instance really reads everything, with no collected_at filter
    db = _db_with_old_and_new_events()
    full = _recomputer_on(db, window_days=None)
    with patch("intelligence.ranking.ranker._load_srs_scores"):
        full.recompute_rank_scores()
    assert not hasattr(db.reads("intelligence_events")[0]["query"], "cutoff")
    assert full.stats["signals_rank_recomputed"] == 4


def test_sunday_utc_is_the_weekly_full_sweep_day():
    with patch.object(rss, "datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)  # a Sunday
        assert rss._is_full_sweep_day()
        dt.now.return_value = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)  # Monday
        assert not rss._is_full_sweep_day()


def test_signal_corroboration_is_read_once_and_new_pairs_reach_the_confidence_counts():
    # two same-sector events sharing >= 2 title words become a new corroboration pair this run
    events = [_ev(1, 1, title="outage northern region telecom"), _ev(2, 1, title="telecom outage region report")]
    db = _FakeDB(intelligence_events=events, signal_corroboration=[], signal_escalation_history=[],
                 intelligence_source_registry=[], validation_job_runs=[{"run_id": "r"}])
    r = _recomputer_on(db)
    r.compute_corroboration()
    with patch.object(r, "_bulk_update_scores") as upd:
        r.recompute_confidence_and_criticality()

    assert len(db.reads("signal_corroboration")) == 1, "signal_corroboration must be fetched exactly once"
    assert r.stats["corroboration_pairs_inserted"] == 1
    # TIER_2 with only 1 corroborating row stays MEDIUM; the point is the count saw this run's inserted pair
    assert r._corroboration_counts([])[events[0]["event_id"]] == 1
    assert upd.call_args.args[0][0]["osint_confidence_level"] == "MEDIUM"


def _escalating_events(n):
    return [_ev(i, 1, rank_score=90, osint_confidence_level="HIGH", criticality_score=0.9) for i in range(1, n + 1)]


def _old_decision_per_signal(history, signal_id):
    """The pre-change lookup: newest escalation_decision for one signal (order desc, limit 1)."""
    rows = sorted((h for h in history if h["signal_id"] == signal_id), key=lambda h: h["escalated_at"], reverse=True)
    return rows[0]["escalation_decision"] if rows else None


def test_escalation_lookups_are_batched_and_decisions_match_the_per_signal_version():
    events = _escalating_events(450)
    # history: every 3rd signal already logged ESCALATE (-> unchanged, skip), every 5th has an
    # older MONITOR then a newer WATCH (-> latest is WATCH, differs from ESCALATE, so it is logged)
    history = []
    for i, e in enumerate(events, 1):
        if i % 3 == 0:
            history.append({"signal_id": e["event_id"], "escalation_decision": "ESCALATE", "escalated_at": "2026-10-01T00:00:00"})
        if i % 5 == 0:
            history.append({"signal_id": e["event_id"], "escalation_decision": "ESCALATE", "escalated_at": "2026-09-01T00:00:00"})
            history.append({"signal_id": e["event_id"], "escalation_decision": "WATCH", "escalated_at": "2026-10-02T00:00:00"})

    db = _FakeDB(intelligence_events=events, signal_escalation_history=list(history))
    r = _recomputer_on(db)
    r.log_escalation_changes()

    expected_logged = {
        e["event_id"] for e in events
        if _old_decision_per_signal(history, e["event_id"]) != "ESCALATE"  # decision for these events is ESCALATE
    }
    inserted = {c["query"].payload["signal_id"] for c in db.log if c["table"] == "signal_escalation_history" and c["op"] == "insert"}
    assert inserted == expected_logged
    assert r.stats["escalations_logged"] == len(expected_logged)
    history_reads = db.reads("signal_escalation_history")
    assert len(history_reads) == 3  # 450 ids / 200 per chunk, not 450 per-signal queries
    assert all(c["cols"] == "signal_id, escalation_decision" for c in history_reads)


def test_escalation_batching_ignores_the_events_limit_flag():
    events = _escalating_events(3)
    history = [{"signal_id": events[2]["event_id"], "escalation_decision": "ESCALATE", "escalated_at": "2026-10-01T00:00:00"}]
    r = _recomputer_on(_FakeDB(intelligence_events=events, signal_escalation_history=history), limit=2)
    # --limit caps the events pass, not the history lookup, so signal 3's history is still seen
    assert r._latest_escalation_decisions([e["event_id"] for e in events]) == {events[2]["event_id"]: "ESCALATE"}


def test_run_reports_calls_and_response_bytes_per_phase_in_the_final_stats():
    db = _db_with_old_and_new_events()
    r = _recomputer_on(db, dry_run=True)
    with patch("intelligence.ranking.ranker._load_srs_scores"), patch.object(rss.logger, "info") as info:
        r.run()

    complete = [c for c in info.call_args_list if c.args and c.args[0] == "Recompute complete: %s"]
    assert len(complete) == 1
    stats = complete[0].args[1]
    assert stats["calls_total"] == sum(p["calls"] for p in stats["by_phase"].values()) > 0
    assert set(stats["by_phase"]) >= {"corroboration", "confidence", "rank", "snapshots", "escalation"}
    rank_bytes = stats["by_phase"]["rank"]["response_bytes"]
    expected = len(json.dumps([e for e in db.tables["intelligence_events"]
                               if e["collected_at"] > _iso(rss.WINDOW_DAYS)], separators=(",", ":"), default=str))
    assert rank_bytes == expected  # byte count is len() of the compact JSON the pass actually received
    assert stats["response_bytes_total"] == sum(p["response_bytes"] for p in stats["by_phase"].values())
