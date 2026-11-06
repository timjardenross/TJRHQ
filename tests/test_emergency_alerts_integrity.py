"""Ingestion integrity rules in run_source(): "no alerts" must mean quiet, never broken.

Uses a fake adapter exposing fetch_with_ledger(); fully offline."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters.base import (
    CanonicalAlert,
    DropLedger,
)


def _alert(n=1, **kw):
    return CanonicalAlert(source_key="x_src", jurisdiction="NSW", headline=f"h{n}", event_key=f"e{n}", **kw)


def _ledger(seen=0, excluded=None, invalid=None, unmapped=None):
    ledger = DropLedger()
    ledger.seen(seen)
    for reason, n in (excluded or {}).items():
        for _ in range(n):
            ledger.exclude(reason)
    for reason, n in (invalid or {}).items():
        for _ in range(n):
            ledger.invalid(reason)
    for label, n in (unmapped or {}).items():
        for _ in range(n):
            ledger.unmapped(label)
    return ledger


def _adapter(alerts, ledger):
    return SimpleNamespace(fetch_with_ledger=lambda: (alerts, ledger), fetch=lambda: (_ for _ in ()).throw(AssertionError("fetch() must not be used when fetch_with_ledger exists")))


class _Run:
    pass


def _standalone(alerts, ledger):
    r = _Run()
    with patch.dict(ea._ADAPTERS, {"x_src": (_adapter(alerts, ledger), "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_upsert_batch") as r.upsert, \
         patch.object(ea, "_expire_stale", return_value=0) as r.expire, \
         patch.object(ea, "_coerce_rows", wraps=ea._coerce_rows) as r.coerce, \
         patch.object(ea, "_record_heartbeat") as r.heartbeat:
        r.result = ea.run_source("x_src", run_started_at="2026-11-06T12:00:00+00:00")
    r.kwargs = r.heartbeat.call_args.kwargs
    return r


def _batched(alerts, ledger, stale_rows=()):
    r = _Run()
    with patch.object(ea, "_ADAPTERS", {"x_src": (_adapter(alerts, ledger), "emergency_alert_x")}), \
         patch.object(ea, "_upsert_batch") as r.upsert, \
         patch.object(ea, "supabase_get", return_value=list(stale_rows)) as r.get, \
         patch.object(ea, "_supabase_request") as r.request, \
         patch.object(ea, "_send_follow_up_emails", return_value={"updates": 0, "lifted": 0}), \
         patch.object(ea, "_send_feed_emails", return_value={"down": 0, "reminders": 0, "recovered": 0}), \
         patch.object(ea, "record_heartbeats") as r.beats:
        r.results = ea.run_all()
    r.beat = r.beats.call_args.args[0][0]
    return r


# ---- rule 1: items seen, none accepted, some invalid -> failed, no upsert, no expiry ----

def test_all_invalid_fails_the_source_before_upsert_and_expiry():
    r = _standalone([], _ledger(seen=5, invalid={"missing_id": 3, "unparseable_item": 2}))
    assert r.kwargs["status"] == "failed"
    assert r.kwargs["error_message"] == "all 5 items failed structural parsing: missing_id 3, unparseable_item 2"
    r.upsert.assert_not_called()
    r.expire.assert_not_called()  # an existing live alert must not be expired (-> false "lifted")
    assert r.result["error"].startswith("all 5 items failed structural parsing")
    assert r.result["count"] == 0


def test_all_invalid_returns_before_coercion():
    r = _standalone([], _ledger(seen=2, invalid={"missing_id": 2}))
    r.coerce.assert_not_called()


def test_all_invalid_in_run_all_schedules_no_expiry_for_that_source():
    r = _batched([], _ledger(seen=4, invalid={"missing_headline": 4}), stale_rows=[{"id": "a1", "source_key": "x_src"}])
    assert r.beat["status"] == "failed" and "failed structural parsing" in r.beat["error_message"]
    r.upsert.assert_not_called()
    r.get.assert_not_called()  # no expiry read at all
    # and so no PATCH that could expire a live alert: the only write is the integrity row
    assert [c.args[:2] for c in r.request.call_args_list] == [("POST", "emergency_alert_source_integrity?on_conflict=source_key")]
    assert "pending_expiry" not in r.results["x_src"]


def test_invalid_mixed_with_exclusions_and_nothing_accepted_still_fails_with_an_accurate_message():
    r = _standalone([], _ledger(seen=30, excluded={"hazard_reduction": 17}, invalid={"missing_id": 13}))
    assert r.kwargs["status"] == "failed"
    assert r.kwargs["error_message"] == "no items accepted - 13 of 30 failed structural parsing: missing_id 13 (17 deliberately excluded)"
    r.upsert.assert_not_called()
    r.expire.assert_not_called()


def test_error_message_lists_only_the_top_three_reasons():
    ledger = _ledger(seen=10, invalid={"a": 4, "b": 3, "c": 2, "d": 1})
    r = _standalone([], ledger)
    assert r.kwargs["error_message"] == "all 10 items failed structural parsing: a 4, b 3, c 2"


# ---- rule 2: everything deliberately excluded -> ok (legitimately quiet) ----

def test_all_excluded_is_ok_and_still_follows_the_normal_expiry_path():
    r = _standalone([], _ledger(seen=17, excluded={"ambulance_mva": 17}))
    assert r.kwargs["status"] == "ok"
    assert "17 alert" not in r.kwargs["detail"] and r.kwargs["detail"].startswith("0 alert(s), 0 unknown severity, 0 expired")
    assert "seen 17, excluded 17 (ambulance_mva 17)" in r.kwargs["detail"]
    r.expire.assert_called_once()  # a genuinely quiet feed expires, via the existing 2h empty-feed grace
    assert r.expire.call_args.args[1] == "2026-11-06T10:00:00+00:00"


def test_all_excluded_in_run_all_is_ok_with_grace_expiry():
    r = _batched([], _ledger(seen=3, excluded={"information": 3}))
    assert r.beat["status"] == "ok"
    assert "seen 3, excluded 3 (information 3)" in r.beat["detail"]
    assert "empty feed" in r.beat["detail"]


def test_nothing_seen_is_not_a_failure():
    assert _standalone([], _ledger()).kwargs["status"] == "ok"


# ---- rule 3: > 20% invalid with some accepted -> ok + warning ----

def test_over_twenty_percent_invalid_is_ok_with_a_warning():
    r = _standalone([_alert(1), _alert(2)], _ledger(seen=10, invalid={"missing_id": 3}, excluded={"x": 5}))
    assert r.kwargs["status"] == "ok"
    assert "| WARNING: 30% invalid (3 of 10 items) |" in r.kwargs["detail"]
    r.upsert.assert_called_once()


def test_exactly_twenty_percent_invalid_does_not_warn():
    r = _standalone([_alert(1)], _ledger(seen=10, invalid={"missing_id": 2}, excluded={"x": 7}))
    assert "WARNING" not in r.kwargs["detail"]


def test_warning_reaches_the_batched_heartbeat_too():
    r = _batched([_alert(1)], _ledger(seen=4, invalid={"unparseable_item": 2}, excluded={"x": 1}))
    assert r.beat["status"] == "ok"
    assert "WARNING: 50% invalid (2 of 4 items)" in r.beat["detail"]


# ---- detail text ----

def test_detail_format_matches_the_spec_example():
    alerts = [_alert(i, severity="advice") for i in range(11)] + [_alert(99)]
    ledger = _ledger(seen=30, excluded={"hazard_reduction": 15, "not_applicable": 2}, invalid={"missing_id": 1})
    r = _standalone(alerts, ledger)
    assert r.kwargs["detail"] == "12 alert(s), 1 unknown severity, 0 expired | seen 30, excluded 17 (hazard_reduction 15, not_applicable 2), invalid 1 (missing_id 1)"


def test_unmapped_labels_surface_first_three_only():
    ledger = _ledger(seen=7, unmapped={"alpha": 1, "bravo": 2, "charlie": 3, "delta": 1})
    detail = _standalone([_alert(i) for i in range(7)], ledger).kwargs["detail"]
    assert detail.endswith("unmapped charlie 3, bravo 2, alpha 1")
    assert "delta" not in detail


def test_detail_is_bounded_and_keeps_the_headline_counts():
    ledger = _ledger(seen=500, excluded={f"reason_{i}": 1 for i in range(80)})
    detail = _standalone([_alert(1)], ledger).kwargs["detail"]
    assert len(detail) <= ea._DETAIL_MAX_CHARS
    assert detail.startswith("1 alert(s), 1 unknown severity, 0 expired | seen 500, excluded 80")


def test_adapters_without_a_ledger_behave_exactly_as_before():
    adapter = SimpleNamespace(fetch=lambda: [_alert(1)])
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_upsert_batch"), patch.object(ea, "_expire_stale", return_value=0), \
         patch.object(ea, "_record_heartbeat") as hb:
        result = ea.run_source("x_src")
    assert hb.call_args.kwargs["detail"] == "1 alert(s), 1 unknown severity, 0 expired"
    assert "drops" not in result


def test_result_carries_the_drop_counts():
    r = _standalone([_alert(1)], _ledger(seen=3, excluded={"x": 2}))
    assert r.result["drops"] == {"items_seen": 3, "excluded_x": 2}


# ---- ordering: ledger rules run before coercion (WS3) and upsert ----

def test_coercion_runs_after_the_ledger_gate_and_before_upsert():
    order = []
    adapter = _adapter([_alert(1, alert_type="volcano")], _ledger(seen=1))
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_ledger_verdict", side_effect=lambda *a, **k: (order.append("ledger"), (None, None))[1]), \
         patch.object(ea, "_coerce_rows", side_effect=lambda *a, **k: (order.append("coerce"), (0, 0))[1]), \
         patch.object(ea, "_upsert_batch", side_effect=lambda rows: order.append("upsert")), \
         patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat"):
        ea.run_source("x_src")
    assert order == ["ledger", "coerce", "upsert"]


def test_a_retirement_notice_alert_still_fails_the_source():
    """The existing feed_retirement_notice guard is unaffected by the ledger path."""
    notice = CanonicalAlert(source_key="x_src", jurisdiction="SA", headline="Feed Retirement Notice", event_key="r")
    r = _standalone([notice], _ledger(seen=1))
    assert r.kwargs["status"] == "failed" and "retired" in r.kwargs["error_message"]
    r.upsert.assert_not_called()
