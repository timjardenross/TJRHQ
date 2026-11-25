"""notify(..., strict=True): per-chunk results, aggregate outcome, no retry of ambiguous acceptance, stop on first
non-confirmed chunk. Transports are scripted; nothing is sent."""
from __future__ import annotations

import time
import urllib.request

import pytest

import core.platform.notification_service as ns
from tests.ns_support import LONG_PLAIN, LONG_RAW, ScriptedTelegram


@pytest.fixture
def wire(monkeypatch):
    holder = {}
    sleeps: list[float] = []

    def arm(*script):
        holder["f"] = ScriptedTelegram(*script)
        monkeypatch.setattr(urllib.request, "urlopen", holder["f"])
        return holder["f"]

    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
    ns._CALL_LOG.clear()
    arm.sleeps = sleeps
    return arm


def states(r):
    return [c.state for c in r.chunk_results]


def test_all_confirmed(wire):
    w = wire("ok", "ok", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    assert states(r) == ["CONFIRMED"] * 3 and r.delivery_outcome == "CONFIRMED" and r.ok
    assert [c.message_id for c in r.chunk_results] == [1001, 1002, 1003]
    assert [(c.index, c.total) for c in r.chunk_results] == [(0, 3), (1, 3), (2, 3)]
    assert len(w.wire) == 3 and len(ns._CALL_LOG) == 3


def test_partial_stops_at_first_definite_failure(wire):
    w = wire("ok", "h400", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    assert states(r) == ["CONFIRMED", "FAILED", "NOT_ATTEMPTED"]
    assert r.delivery_outcome == "PARTIAL"
    assert not r.ok                      # last chunk ATTEMPTED failed: legacy rule, not "all delivered"
    assert len(w.wire) == 2 and len(ns._CALL_LOG) == 2
    assert r.chunk_results[1].error.startswith("HTTP 400") and r.chunk_results[1].attempts == 1


def test_early_chunk_failure_is_visible_and_later_chunks_not_sent(wire):
    w = wire("h400", "ok", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    assert states(r) == ["FAILED", "NOT_ATTEMPTED", "NOT_ATTEMPTED"] and r.delivery_outcome == "FAILED"
    assert len(w.wire) == 1 and r.ok is False


def test_early_chunk_failure_without_stop_matches_legacy_ok_but_reports_partial(wire):
    wire("h400", "ok", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True, chunk_stop_on_failure=False)
    assert states(r) == ["FAILED", "CONFIRMED", "CONFIRMED"]
    assert r.ok is True                  # legacy quirk preserved: last chunk ok
    assert r.delivery_outcome == "PARTIAL"   # the new field tells the truth


def test_all_failed(wire):
    wire("h400", "h400", "h400")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True, chunk_stop_on_failure=False)
    assert states(r) == ["FAILED"] * 3 and r.delivery_outcome == "FAILED" and not r.ok


def test_timeout_after_accept_is_unknown_and_not_retried(wire):
    w = wire("timeout", "ok")
    r = ns.notify("hello", strict=True)            # default max_retries=1 would retry in legacy mode
    assert states(r) == ["UNKNOWN"] and r.delivery_outcome == "UNKNOWN"
    assert len(w.wire) == 1 and r.attempts == 1 and r.chunk_results[0].message_id is None
    assert not wire.sleeps


@pytest.mark.parametrize("tok", ["timeout", "reset", "h500", "badjson"])
def test_ambiguous_signals_never_retried(wire, tok):
    w = wire(tok, "ok", "ok")
    r = ns.notify("hello", strict=True, max_retries=3)
    assert states(r) == ["UNKNOWN"] and len(w.wire) == 1


def test_timeout_mid_brief_unknown_chunk_stops_the_rest(wire):
    w = wire("ok", "timeout", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    assert states(r) == ["CONFIRMED", "UNKNOWN", "NOT_ATTEMPTED"] and r.delivery_outcome == "PARTIAL"
    assert len(w.wire) == 2


def test_only_unknown_when_nothing_confirmed(wire):
    wire("timeout")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    assert r.delivery_outcome == "UNKNOWN"


def test_definite_failures_retry_when_safe(wire):
    w = wire("h429", "ok")
    r = ns.notify("hello", strict=True)
    assert states(r) == ["CONFIRMED"] and r.attempts == 2 and len(w.wire) == 2 and wire.sleeps == [2.0]
    w = wire("refused", "ok")
    r = ns.notify("hello", strict=True)
    assert states(r) == ["CONFIRMED"] and len(w.wire) == 2


def test_definite_rejection_not_retried(wire):
    w = wire("h400", "ok")
    r = ns.notify("hello", strict=True)
    assert states(r) == ["FAILED"] and len(w.wire) == 1


def test_retry_budget_respected(wire):
    w = wire("h429", "h429", "h429")
    r = ns.notify("hello", strict=True, max_retries=1)
    assert states(r) == ["FAILED"] and len(w.wire) == 2 and r.attempts == 2


def test_missing_credentials_is_definite_and_not_retried(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = ns.notify("hello", strict=True)
    assert states(r) == ["FAILED"] and r.attempts == 1


def test_sender_raising_is_ambiguous(monkeypatch):
    calls = []

    def boom(text, reply_markup=None, chat_id=None, severity=ns.Severity.INFO):
        calls.append(text)
        raise ConnectionError("lost")

    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, boom)
    r = ns.notify("hello", strict=True, max_retries=2)
    assert states(r) == ["UNKNOWN"] and len(calls) == 1 and r.chunk_results[0].error == "ConnectionError"


def test_ok_without_message_id_is_unknown_not_confirmed(wire):
    """Round 3 (N11): acceptance without a provider message id is UNKNOWN in strict mode, consistent with the delivery adapter. The legacy ``.ok``
    meaning is unchanged (True: the request was accepted) and the chunk is never retried."""
    wire("okNoId")
    r = ns.notify("hello", strict=True)
    c = r.chunk_results[0]
    assert c.state == "UNKNOWN" and c.message_id is None and c.error == "accepted_without_message_id" and c.attempts == 1
    assert r.delivery_outcome == "UNKNOWN" and r.ok is True


def test_error_text_is_capped_and_has_no_token(wire):
    wire("h400")
    r = ns.notify("hello", strict=True)
    assert len(r.chunk_results[0].error) <= 200 and "TESTTOKEN" not in r.chunk_results[0].error


def test_raw_html_chunks_balanced_and_numbered(wire):
    w = wire("ok", "ok", "ok")
    r = ns.notify(LONG_RAW, template="raw", chunk=True, strict=True)
    assert r.delivery_outcome == "CONFIRMED" and all(t.count("<b>") == t.count("</b>") for t in w.wire)


def test_short_body_single_chunk_result(wire):
    wire("ok")
    r = ns.notify("hello", chunk=True, strict=True)
    assert len(r.chunk_results) == 1 and r.chunk_results[0].total == 1 and r.delivery_outcome == "CONFIRMED"


def test_unknown_transport_strict():
    r = ns.notify("hi", strict=True, transport="nope")  # type: ignore[arg-type]
    assert r.delivery_outcome == "FAILED" and r.chunk_results[0].state == "FAILED" and r.attempts == 0


def test_classifier_table():
    c = ns.classify_send_error
    assert c("HTTP 400: x") == ("FAILED", False) and c("HTTP 429") == ("FAILED", True)
    assert c("HTTP 502") == ("UNKNOWN", False) and c("TimeoutError: timed out") == ("UNKNOWN", False)
    assert c("URLError: <urlopen error [Errno 111] Connection refused>") == ("FAILED", True)
    assert c("missing TELEGRAM_BOT_TOKEN or chat id") == ("FAILED", False)
    assert c("") == ("UNKNOWN", False) and c(None) == ("UNKNOWN", False)


def test_adapter_and_platform_classifiers_agree():
    from intelligence import delivery_adapter as da
    for err in ["HTTP 400: x", "HTTP 429", "HTTP 500", "TimeoutError: t", "Connection refused", "missing TELEGRAM_BOT_TOKEN or chat id",
                "Name or service not known", "ConnectionResetError: x", "", None]:
        assert da.classify_notify_result(False, None, err) == ns.classify_send_error(err)


def test_chunks_from_notification_maps_to_delivery_record(wire):
    from intelligence import delivery_adapter as da
    from intelligence import delivery_record as dr
    wire("ok", "timeout", "ok")
    r = ns.notify(LONG_PLAIN, chunk=True, strict=True)
    mapped = da.chunks_from_notification(r)
    assert [m.state for m in mapped] == ["CONFIRMED", "UNKNOWN", "NOT_ATTEMPTED"]
    assert dr.outcome_from_chunks(mapped, 3).value == r.delivery_outcome == "PARTIAL"
    legacy = ns.NotificationResult(True, ns.Transport.TELEGRAM, 1)
    with pytest.raises(ValueError):
        da.chunks_from_notification(legacy)


def test_aggregate_matches_delivery_record_for_all_state_combinations():
    import itertools

    from intelligence import delivery_record as dr
    for combo in itertools.product(["CONFIRMED", "FAILED", "UNKNOWN", "NOT_ATTEMPTED"], repeat=3):
        cr = [ns.ChunkResult(i, 3, s) for i, s in enumerate(combo)]
        d = [dr.ChunkResult(i, s) for i, s in enumerate(combo)]
        assert ns._aggregate_outcome(cr) == dr.outcome_from_chunks(d, 3).value, combo
