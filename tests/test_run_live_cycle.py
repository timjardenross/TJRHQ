"""Offline tests for tools/ops/run_live_cycle.py: guards, collection recorder, products step, verification inputs, missed-brief drill."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence import brief_reliability as br
from tools.intelligence import verify_operational as vo
from tools.ops import live_cycle_queries as lq
from tools.ops import run_live_cycle as rlc

NOW = datetime(2026, 11, 24, 8, 30, tzinfo=timezone.utc)
DEPLOYED = datetime(2026, 11, 24, 6, 26, 32, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "verify_operational" / "production_2026-11-24.json"

BRIEFS = [
    {"brief_type": "eod", "brief_date": "2026-11-24", "generated_at": "2026-11-24 07:00:03+00"},
    {"brief_type": "morning", "brief_date": "2026-11-24", "generated_at": "2026-11-23 20:01:09+00"},
    {"brief_type": "morning", "brief_date": "2026-11-23", "generated_at": "2026-11-22 20:01:04+00"},
]


def briefs_get(rows):
    def get(table, query):
        assert table == "captains_daily_briefs", table
        return rlc._fixture_get(rows, query)
    return get


# ── delivery guard ─────────────────────────────────────────────────────────────────────────────────────────────
def test_guard_removes_env_blocks_delivery_hosts_and_restores(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("INTEL_PRODUCTS_WEEKLY_TELEGRAM", "1")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "y")
    real = urllib.request.urlopen
    with rlc.DeliveryGuard() as g:
        assert "TELEGRAM_BOT_TOKEN" not in os.environ and "INTEL_PRODUCTS_WEEKLY_TELEGRAM" not in os.environ
        assert set(g.env_removed) == {"TELEGRAM_BOT_TOKEN", "INTEL_PRODUCTS_WEEKLY_TELEGRAM", "SLACK_BOT_TOKEN"}
        with pytest.raises(ConnectionRefusedError):
            urllib.request.urlopen("https://api.telegram.org/bot1/sendMessage")
        assert g.attempts == [{"kind": "http", "host": "api.telegram.org"}] and not g.clean
    assert urllib.request.urlopen is real


def test_guard_stubs_are_record_only_and_restored():
    from core.platform import notification_service as ns
    from intelligence.persistence import intelligence_store as store
    orig = (ns.notify, store._maybe_push_outage_alert, store._publish_core_event)
    with rlc.DeliveryGuard() as g:
        assert ns.notify("hello").ok is False
        assert store._maybe_push_outage_alert(object(), "1") is None
        store._publish_core_event("intelligence.signal.ranked")
        assert {s["kind"] for s in g.suppressed} >= {"notify", "outage_alert_push", "core_events"}
        assert g.clean
    assert (ns.notify, store._maybe_push_outage_alert, store._publish_core_event) == orig


# ── collection recorder / budget / locks ───────────────────────────────────────────────────────────────────────
def test_collection_recorder_reports_per_source_and_drops_firecrawl_when_budget_short():
    srcs = [SimpleNamespace(source_name="ASIC News Centre"), SimpleNamespace(source_name="iTnews")]

    def real(sources, max_workers=8):
        health = [SimpleNamespace(source_name=s.source_name, status="ok" if s.source_name == "iTnews" else "failed", items_retrieved=2,
                                  content_valid=True, error_message=None if s.source_name == "iTnews" else "boom") for s in sources]
        return [SimpleNamespace(source_name=s.source_name) for s in sources for _ in range(2)], health
    rec = rlc.CollectionRecorder(real, {"ASIC News Centre"}, exclude_firecrawl=True, load_registry=lambda: srcs)
    _items, health = rec()
    assert [h.source_name for h in health] == ["iTnews"] and rec.skipped_firecrawl == ["ASIC News Centre"]
    assert rec.sources["iTnews"]["items_collected"] == 2 and rec.sources["iTnews"]["firecrawl_path"] is False
    rec2 = rlc.CollectionRecorder(real, {"ASIC News Centre"}, exclude_firecrawl=False, load_registry=lambda: srcs)
    rec2()
    assert rec2.sources["ASIC News Centre"]["status"] == "failed" and rec2.sources["ASIC News Centre"]["error"] == "boom"


def test_firecrawl_headroom_reads_both_accounts_and_fails_closed():
    ok = rlc.firecrawl_headroom(lambda p: {"call_count": 100, "ceiling": 1700, "headroom": 1600})
    assert ok["firecrawl"]["headroom"] == 1600 and "firecrawl_2" in ok

    def boom(p):
        raise RuntimeError("unreadable")
    assert "error" in rlc.firecrawl_headroom(boom)


def test_previous_run_guard_and_lock(tmp_path):
    assert rlc.previous_run_guard(120, tmp_path) is None
    (tmp_path / "last-collection-1.json").write_text(json.dumps({"finished_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()}))
    assert rlc.previous_run_guard(120, tmp_path)["file"] == "last-collection-1.json"
    assert rlc.previous_run_guard(10, tmp_path) is None
    with rlc.run_lock(tmp_path), pytest.raises(rlc.Refused), rlc.run_lock(tmp_path):
        pass
    with rlc.run_lock(tmp_path):    # released afterwards
        pass


# ── products (idempotent, no Telegram) ─────────────────────────────────────────────────────────────────────────
def test_products_upsert_three_rows_twice_without_telegram(monkeypatch):
    from intelligence import intel_products_job as job
    monkeypatch.setenv("INTEL_PRODUCTS_WEEKLY_TELEGRAM", "1")
    monkeypatch.setattr(job, "send_weekly", lambda *a, **k: pytest.fail("send_weekly must never be called"))
    written = []

    def getter(table, query):
        return []
    args = SimpleNamespace()
    with rlc.DeliveryGuard():
        s1 = rlc.run_products(args, getter=getter, writer=written.append, now=NOW)
        s2 = rlc.run_products(args, getter=getter, writer=written.append, now=NOW)
    assert s1.status == s2.status == rlc.PASS
    assert [w["product_key"] for w in written] == ["recurring_provider", "systemic_risk", "forward_watch"] * 2
    assert {w["generated_for"] for w in written} == {"2026-11-24"}      # same upsert key on a rerun: no duplicate rows


def test_products_fail_when_table_unreadable():
    def getter(table, query):
        raise RuntimeError("relation does not exist")
    s = rlc.run_products(SimpleNamespace(), getter=getter, writer=lambda r: None, now=NOW)
    assert s.status == rlc.FAIL and "0261" in s.detail


# ── verification inputs from GET-only reads ────────────────────────────────────────────────────────────────────
class FakeSB:
    def __init__(self):
        self.calls = []
        t = lambda m: (NOW - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        self.tables = {
            "intelligence_source_registry": [{"source_id": "s1", "source_name": "Optus National Outage Register", "source_type": "scrape", "category": "critical_infrastructure", "active": True, "updated_at": t(900)},
                                             {"source_id": "s2", "source_name": "iTnews", "source_type": "rss", "category": "media", "active": True, "updated_at": t(900)}],
            "intelligence_source_health": [{"source_id": "s1", "status": "ok", "checked_at": t(20), "items_retrieved": 3, "content_valid": True, "error_message": None},
                                           {"source_id": "s2", "status": "ok", "checked_at": t(10), "items_retrieved": 30, "content_valid": True, "error_message": None}]
                                          + [{"source_id": "s2", "status": "ok", "checked_at": t(600 + i), "items_retrieved": 10, "content_valid": True, "error_message": None} for i in range(80)],
            "domain_heartbeats": [{"checked_at": t(15), "status": "ok", "detail": "sources=2", "error_message": None}],
            "intelligence_events": [{"event_id": "e1", "source_id": "s1", "collected_at": t(20), "published_at": None, "dedup_hash": "h1", "canonical_url": "u1",
                                     "raw_title": "Optus outage Melbourne", "raw_summary": "register entry", "geography": "AU", "suppressed": False, "signal_status": "NEW",
                                     "publisher_domain": None, "publisher_family": None, "published_at_basis": "unknown", "published_at_precision": "unknown",
                                     "published_at_confidence": "unknown", "published_at_label": None},
                                    {"event_id": "e2", "source_id": "s2", "collected_at": t(30), "published_at": t(40), "dedup_hash": "h2", "canonical_url": "u2",
                                     "raw_title": "iTnews item", "raw_summary": "x", "geography": "AU", "suppressed": False, "signal_status": "NEW",
                                     "publisher_domain": "itnews.com.au", "publisher_family": "itnews", "published_at_basis": "feed", "published_at_precision": "second",
                                     "published_at_confidence": "feed", "published_at_label": "publication"}],
            "captains_daily_briefs": [{**b, "evidence_window_hours": 24, "collection_caveat": None, "signals_count": 3, "brief_text": "Based on reports from the last 24 hours"} for b in BRIEFS],
            "external_fetch_usage": [{"provider": "firecrawl", "billing_cycle_start": "2026-11-09", "billing_cycle_end": "2026-12-09", "call_count": 400, "updated_at": t(5)}],
            "intelligence_products": [{"product_key": k, "generated_for": "2026-11-24", "as_of": t(3), "title": k, "summary": "s", "sections": [], "exceptions": {}, "body_md": "# x"}
                                      for k in vo.PRODUCT_KEYS],
        }

    def __call__(self, table, query):
        self.calls.append((table, query))
        rows = self.tables[table]
        off = int(dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("offset", 0))
        lim = int(dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("limit", 1000))
        return rows[off:off + lim]


def test_collect_results_shape_and_verify_runs_with_evidence():
    sb = FakeSB()
    results = lq.collect_results(sb, NOW, sweep_hour=19, deployed_at=DEPLOYED)
    assert all(table in sb.tables for table, _ in sb.calls)
    assert all("limit=" in q for _, q in sb.calls)                                    # every read is bounded
    for name in ("sweep_days", "sweep_items", "sources", "heartbeats", "briefs", "latest_morning_brief", "window_events", "live_window_events",
                 "provenance_days", "provenance_labels", "products_today", "health_split", "external_fetch_usage", "nvd_runs", "nvd_totals"):
        assert name in results, name
    assert results["products_today"][0]["sections_type"] == "array" and results["products_today"][0]["exceptions_type"] == "object"
    assert results["briefs"][0]["text_len"] > 0 and "brief_text" not in results["briefs"][0]
    res = {r.name: r for r in vo.evaluate(results, now=NOW, deployed_at=DEPLOYED)}
    live = next(r for n, r in res.items() if n.startswith("Live-cycle"))
    by = {c.id: c for c in live.checks}
    assert by["products"].verdict == vo.PASS and by["products"].evidence
    assert by["prov_labels"].verdict == vo.PASS
    assert by["health_spike"].verdict == vo.PASS
    assert by["brief_evidence"].verdict == vo.PASS and by["brief_evidence"].evidence[0]["register_rows"] == 1
    for r in res.values():
        for c in r.checks:
            assert c.verdict != vo.PASS or c.evidence


# ── new verification checks ────────────────────────────────────────────────────────────────────────────────────
def ctx(**results):
    return vo.Ctx({k: v for k, v in results.items()}, NOW, DEPLOYED, 19)


def test_provenance_label_rules():
    good = {"event_id": "1", "source_name": "x", "published_at": "2026-11-24T01:00:00Z", "published_at_basis": "feed", "published_at_precision": "second",
            "published_at_confidence": "verified", "published_at_label": "publication"}
    assert vo.check_provenance_labels(ctx(provenance_labels=[good])).verdict == vo.PASS
    assert vo.check_provenance_labels(ctx(provenance_labels=[])).verdict == vo.NYO
    assert vo.check_provenance_labels(ctx()).verdict == vo.NYO
    no_date = {**good, "published_at": None}
    c = vo.check_provenance_labels(ctx(provenance_labels=[good, no_date]))
    assert c.verdict == vo.FAIL and "verified" in c.evidence[0]["reasons"][0]
    assert vo.check_provenance_labels(ctx(provenance_labels=[{**good, "published_at_basis": "unknown"}])).verdict == vo.FAIL
    assert vo.check_provenance_labels(ctx(provenance_labels=[{**good, "published_at_label": "made_up"}])).verdict == vo.FAIL


def test_products_check_verdicts():
    row = lambda k, **kw: {"product_key": k, "generated_for": "2026-11-24", "as_of": "x", "title": "t", "summary": "s", "sections_type": "array",
                           "exceptions_type": "array", "body_len": 10, **kw}
    allp = [row(k) for k in vo.PRODUCT_KEYS]
    assert vo.check_products(ctx(products_today=allp)).verdict == vo.PASS
    assert vo.check_products(ctx(products_today=[])).verdict == vo.NYO
    assert vo.check_products(ctx(products_today=[row(k, generated_for="2026-11-20") for k in vo.PRODUCT_KEYS])).verdict == vo.NYO
    assert vo.check_products(ctx(products_today=allp[:2])).verdict == vo.FAIL
    assert vo.check_products(ctx(products_today=[row("recurring_provider", body_len=0)] + allp[1:])).verdict == vo.FAIL


def test_health_spike_and_brief_evidence_gaps():
    assert vo.check_health_spike(ctx(health_split=[{"w": "recent", "checks": 100, "not_ok": 5}, {"w": "baseline", "checks": 1000, "not_ok": 50}])).verdict == vo.PASS
    assert vo.check_health_spike(ctx(health_split=[{"w": "recent", "checks": 100, "not_ok": 40}, {"w": "baseline", "checks": 1000, "not_ok": 50}])).verdict == vo.FAIL
    assert vo.check_health_spike(ctx(health_split=[{"w": "recent", "checks": 0, "not_ok": 0}, {"w": "baseline", "checks": 1000, "not_ok": 50}])).verdict == vo.NYO
    assert vo.check_brief_evidence_unaffected(ctx(live_window_events=[])).verdict == vo.NYO
    truncated = ctx(live_window_events=[], _meta={"live_window_events_complete": False})
    assert vo.check_brief_evidence_unaffected(truncated).verdict == vo.NYO


# ── missed-brief drill ─────────────────────────────────────────────────────────────────────────────────────────
def test_drill_passes_and_leaves_real_state_and_module_memory_untouched():
    mem = (set(br._alerted), dict(br._delivery), set(br._caught_up))
    before = json.dumps(BRIEFS)
    with rlc.DeliveryGuard() as g:
        steps = rlc.run_drill(briefs_get(BRIEFS), source="test")
    assert [s.status for s in steps] == [rlc.PASS] * len(steps), [(s.name, s.detail) for s in steps if s.status != rlc.PASS]
    names = [s.name for s in steps]
    assert "drill:detects the miss" in names and "drill:delivery-memory caveat shown" in names and "drill:real state unchanged" in names
    assert json.dumps(BRIEFS) == before and g.clean
    assert (set(br._alerted), dict(br._delivery), set(br._caught_up)) == mem


def test_drill_refuses_without_delivery_guard():
    with pytest.raises(rlc.Refused):
        rlc.run_drill(briefs_get(BRIEFS), source="test")


def test_drill_refuses_when_a_telegram_token_is_present(monkeypatch):
    with rlc.DeliveryGuard():
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "late")
        with pytest.raises(rlc.Refused):
            rlc.run_drill(briefs_get(BRIEFS), source="test")


def test_drill_fails_when_the_hypothetical_date_already_has_a_row():
    clash = BRIEFS + [{"brief_type": "morning", "brief_date": "2026-11-26", "generated_at": "2026-11-25 20:01:00+00"}]

    def get(table, query):
        out = rlc._fixture_get(BRIEFS, query)
        if "brief_date=eq.2026-11-26" in query:
            return [clash[-1]]
        return out
    with rlc.DeliveryGuard():
        first = rlc.run_drill(get, source="test")[0]
    assert first.status == rlc.FAIL and "1 row" in first.detail


def test_drill_flags_state_change_between_snapshots():
    snaps = {"n": 0}

    def get(table, query):
        rows = rlc._fixture_get(BRIEFS, query)
        if "limit=8" in query:
            snaps["n"] += 1
        if snaps["n"] >= 2 and "limit=8" in query:        # the 'after' snapshot sees a new row appear
            return rows + [{"brief_type": "eod", "brief_date": "2026-11-26", "generated_at": "2026-11-26 07:00:00+00"}]
        return rows
    with rlc.DeliveryGuard():
        steps = rlc.run_drill(get, source="test")
    assert steps[-1].name == "drill:real state unchanged" and steps[-1].status == rlc.FAIL


def test_drill_rejects_reads_of_other_tables():
    def get(table, query):
        return []
    with rlc.DeliveryGuard():
        steps = rlc.run_drill(get, source="test")
    assert steps[0].status == rlc.FAIL      # no morning brief to anchor on: reported, never invented


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_cli_dry_run_skips_writes_and_writes_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rlc, "STATE_DIR", tmp_path)
    report = tmp_path / "r.json"
    rc = rlc.main(["--dry-run", "--verify-results", str(FIXTURE), "--report", str(report)])
    out = capsys.readouterr().out
    assert "[SKIPPED] collect" in out and "[SKIPPED] products" in out and "[PASS   ] delivery guard" in out
    doc = json.loads(report.read_text())
    assert doc["mode"] == "dry-run" and {s["name"]: s["status"] for s in doc["steps"]}["collect"] == "SKIPPED"
    assert doc["verification"]["capabilities"] and rc in (0, 1)


def test_cli_refuses_without_supabase_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(rlc, "STATE_DIR", tmp_path)
    for k in rlc.REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(rlc, "firecrawl_headroom", lambda *a, **k: {})
    assert rlc.main(["--dry-run", "--report", str(tmp_path / "r.json")]) == 3
    assert json.loads((tmp_path / "r.json").read_text())["overall"] == "FAIL"


def test_cli_drill_with_fixture_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(rlc, "STATE_DIR", tmp_path)
    fx = tmp_path / "b.json"
    fx.write_text(json.dumps(BRIEFS))
    assert rlc.main(["--drill-missed-brief", "--drill-fixture-rows", str(fx), "--report", str(tmp_path / "r.json")]) == 0
    doc = json.loads((tmp_path / "r.json").read_text())
    assert doc["overall"] == "PASS" and any(s["name"] == "drill:delivery-memory caveat shown" for s in doc["steps"])


def test_module_never_calls_weekly_telegram_or_brief_send_paths():
    src = Path(rlc.__file__).read_text()
    assert "job_weekly(" not in src and ".send_weekly(" not in src
    assert "cb.send_brief(" not in src and "_send_telegram(" not in src


def test_run_collection_calls_the_three_scheduler_jobs_once_each(monkeypatch):
    from intelligence.ingestion import collection_engine as ce
    from intelligence.persistence import intelligence_store as store
    srcs = [SimpleNamespace(source_id="1", source_name="iTnews", category="media", source_type="rss"),
            SimpleNamespace(source_id="2", source_name="ASIC News Centre", category="critical_infrastructure", source_type="scrape"),
            SimpleNamespace(source_id="3", source_name="AWS Status", category="cloud_technology", source_type="rss")]
    seen = []

    def fake_collect(sources=None, max_workers=8):
        seen.append([s.source_name for s in sources])
        return [], [SimpleNamespace(source_name=s.source_name, status="ok", items_retrieved=0, content_valid=True, error_message=None) for s in sources]
    monkeypatch.setattr(ce, "collect_all", fake_collect)
    monkeypatch.setattr(store, "load_source_registry", lambda: srcs)
    monkeypatch.setattr(store, "filter_unpersisted_events", lambda ev: ev)
    args = SimpleNamespace(max_firecrawl_credits=30, deadline=1e18)
    budget = {"firecrawl": {"call_count": 10, "ceiling": 1700, "headroom": 1690}}
    with rlc.DeliveryGuard() as g:
        steps = rlc.run_collection(args, g, budget)
    assert [s.name for s in steps] == ["collect:daily_sweep", "collect:intraday_status", "collect:intraday_media"]
    assert [s.status for s in steps] == [rlc.PASS] * 3, [(s.name, s.detail) for s in steps]
    assert seen[0] == ["iTnews", "ASIC News Centre", "AWS Status"]          # daily sweep includes the Firecrawl-path source
    assert seen[1] == ["AWS Status"]                   # the scheduler's own intraday exclusion still applies
    assert seen[2] == ["iTnews"]
    assert ce.collect_all is fake_collect                      # patches restored
    # with no Firecrawl headroom the daily sweep drops those sources
    seen.clear()
    with rlc.DeliveryGuard() as g:
        s2 = rlc.run_collection(args, g, {"firecrawl": {"call_count": 1690, "ceiling": 1700, "headroom": 10}})
    assert seen[0] == ["iTnews", "AWS Status"] and s2[0].data["firecrawl_sources_skipped_for_budget"] == ["ASIC News Centre"]


def test_adopt_service_flags_copies_only_flag_names_and_never_overrides():
    from tools.ops import run_live_cycle as rlc

    env = {"INTEL_PRODUCTS_ENABLED": "0"}
    raw = "INTEL_PROVENANCE_COLUMNS=1 INTEL_PRODUCTS_ENABLED=1 DELIVERY_TIERS_V1=1 SUPABASE_SERVICE_ROLE_KEY=secret PATH=/bin INTEL_PRODUCTS_WEEKLY_TELEGRAM=1"
    got = rlc.adopt_service_flags(show=lambda: raw, environ=env)
    assert got == {"INTEL_PROVENANCE_COLUMNS": "1", "DELIVERY_TIERS_V1": "1"}
    assert env["INTEL_PRODUCTS_ENABLED"] == "0"          # existing value is never overridden
    assert "SUPABASE_SERVICE_ROLE_KEY" not in env and "PATH" not in env
    assert "INTEL_PRODUCTS_WEEKLY_TELEGRAM" not in env   # the always-off flag is never adopted


def test_adopt_service_flags_is_best_effort():
    from tools.ops import run_live_cycle as rlc

    def boom():
        raise OSError("no systemctl")

    assert rlc.adopt_service_flags(show=boom, environ={}) == {}
