"""WP2: structured notify adapter, platform characterisation, captains_brief wiring, render wording. No real sends."""
import urllib.request
from types import SimpleNamespace
from unittest import mock

import pytest

import intelligence.captains_brief as cb
from intelligence import delivery_adapter as da
from intelligence import delivery_record as dr
from intelligence.delivery_record import DeliveryOutcome as O, InMemoryAttemptStore


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call attempted in test")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    for f in (dr.FLAG, dr.AUTO_RESEND_FLAG, "BRIEF_STATUS_V1"):
        monkeypatch.delenv(f, raising=False)


def R(ok, mid=None, err=None):
    return SimpleNamespace(ok=ok, message_id=mid, error=err)


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("ok,mid,err,state", [
    (True, 5, None, "CONFIRMED"), (True, None, None, "UNKNOWN"),
    (False, None, "HTTP 400: Bad Request: can't parse entities", "FAILED"), (False, None, "HTTP 403: Forbidden", "FAILED"),
    (False, None, "HTTP 429: Too Many Requests", "FAILED"), (False, None, "missing TELEGRAM_BOT_TOKEN or chat id", "FAILED"),
    (False, None, "URLError: <urlopen error [Errno 111] Connection refused>", "FAILED"),
    (False, None, "URLError: <urlopen error [Errno -2] Name or service not known>", "FAILED"),
    (False, None, "TimeoutError: timed out", "UNKNOWN"), (False, None, "URLError: <urlopen error timed out>", "UNKNOWN"),
    (False, None, "RemoteDisconnected: Remote end closed connection without response", "UNKNOWN"),
    (False, None, "HTTP 502: Bad Gateway", "UNKNOWN"), (False, None, "HTTP 500", "UNKNOWN"),
    (False, None, None, "UNKNOWN"), (False, None, "", "UNKNOWN"), (False, None, "weird", "UNKNOWN"),
])
def test_classification(ok, mid, err, state):
    assert da.classify_notify_result(ok, mid, err)[0] == state


def test_timeout_is_never_retried_but_429_is_retried_once():
    calls = []
    send = da.make_telegram_sender(notify_fn=lambda p: calls.append(p) or R(False, None, "TimeoutError: timed out"), sleep=lambda s: None)
    assert send("x").state == "UNKNOWN" and len(calls) == 1
    seq = [R(False, None, "HTTP 429: slow down"), R(True, 9)]
    send = da.make_telegram_sender(notify_fn=lambda p: seq.pop(0), sleep=lambda s: None)
    res = send("x")
    assert res.state == "CONFIRMED" and res.attempts == 2 and res.message_id == 9


def test_raising_notify_is_ambiguous():
    def fn(p):
        raise OSError("socket died")
    assert da.make_telegram_sender(notify_fn=fn)("x").state == "UNKNOWN"


def test_error_text_is_capped_and_message_id_only_on_success():
    send = da.make_telegram_sender(notify_fn=lambda p: R(False, 7, "HTTP 400: " + "z" * 900), sleep=lambda s: None)
    res = send("x")
    assert len(res.error) <= 200 and res.message_id is None


# ---------------------------------------------------------------- platform characterisation (why the adapter exists)
def _ns():
    from core.platform import notification_service as ns
    return ns


def test_platform_chunk_mode_reports_ok_when_an_early_chunk_failed(monkeypatch):
    ns = _ns()
    seq = iter([(False, "HTTP 400: bad", None), (True, None, 12)])
    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, lambda *a, **k: next(seq))
    monkeypatch.setattr(ns.time, "sleep", lambda s: None)
    body = ("word " * 1500).strip()                     # > 4096 chars: two chunks
    res = ns.notify(body, template="raw", transport=ns.Transport.TELEGRAM, chunk=True)
    assert res.ok is True                               # LIMITATION: chunk 1 failed, the single result says ok


def test_platform_default_retry_resends_after_a_timeout(monkeypatch):
    ns = _ns(); sent = []
    seq = iter([(False, "TimeoutError: timed out", None), (True, None, 3)])
    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, lambda text, *a, **k: sent.append(text) or next(seq))
    monkeypatch.setattr(ns.time, "sleep", lambda s: None)
    ns.notify("hello", template="raw", transport=ns.Transport.TELEGRAM)
    assert len(sent) == 2                               # LIMITATION: a possibly-delivered message is blindly re-sent


def test_adapter_over_real_notify_per_piece_no_blind_retry(monkeypatch):
    ns = _ns(); sent = []
    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, lambda text, *a, **k: sent.append(text) or (False, "TimeoutError: timed out", None))
    monkeypatch.setattr(ns.time, "sleep", lambda s: None)
    res = da.make_telegram_sender()("hello")
    assert res.state == "UNKNOWN" and len(sent) == 1


def test_splitter_matches_platform_and_bounds_length():
    body = "\n".join("<b>line</b> " + "w" * 50 for _ in range(200))
    pieces = da.split_for_telegram(body)
    assert len(pieces) > 1 and all(len(p) <= 4096 for p in pieces)
    assert da.split_for_telegram("short") == ["short"]


# ---------------------------------------------------------------- captains_brief wiring
def _stub_morning(monkeypatch, sends):
    monkeypatch.setattr(cb, "generate_knowledge_ops_brief", lambda: "K" * 80)
    monkeypatch.setattr(cb, "_persist_brief", lambda *a, **k: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cb, "_record_brief_events", lambda *a, **k: None)
    monkeypatch.setattr(cb, "_send_telegram", lambda text: sends.append(text) or True)


def test_flags_off_is_the_legacy_path_exactly(monkeypatch):
    sends = []
    _stub_morning(monkeypatch, sends)
    with mock.patch.object(dr, "deliver", side_effect=AssertionError("must not run")), \
         mock.patch.object(cb, "_patch_brief_row", side_effect=AssertionError("must not run")):
        assert cb.send_brief("knowledge_ops") is True
    assert sends == ["K" * 80]


def test_persist_asks_for_row_id_only_when_a_flag_is_on(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def read(s): return b'[{"id": "abc"}]'

    def fake(req, timeout=0):
        seen["prefer"] = req.headers.get("Prefer"); return Resp()
    monkeypatch.setattr(cb, "_SUPABASE_URL", "https://example.test"); monkeypatch.setattr(cb, "_SUPABASE_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cb._persist_brief("morning", "t") is None and seen["prefer"] == "return=minimal"
    monkeypatch.setenv("BRIEF_STATUS_V1", "1")
    assert cb._persist_brief("morning", "t") == "abc" and seen["prefer"] == "return=representation"


def test_recorded_delivery_confirmed_returns_true_and_patches_rollup(monkeypatch):
    patches = []
    monkeypatch.setattr(cb, "_patch_brief_row", lambda bid, f: patches.append((bid, f)) or True)
    store = InMemoryAttemptStore()
    ok = cb._deliver_recorded("morning", "hello brief", "id-1", store=store,
                              send_chunk=lambda p: dr.ChunkResult(0, "CONFIRMED", message_id=1, attempts=1))
    assert ok is True and patches[0][1]["telegram_status"] == "CONFIRMED"
    # same brief again: refused, nothing re-sent, still reported from the record
    sent = []
    ok2 = cb._deliver_recorded("morning", "hello brief", "id-1", store=store, send_chunk=lambda p: sent.append(p))
    assert ok2 is True and sent == []


def test_recorded_delivery_ambiguous_no_auto_resend_by_default(monkeypatch):
    monkeypatch.setenv(dr.FLAG, "1")
    patches, wire = [], []
    monkeypatch.setattr(cb, "_patch_brief_row", lambda bid, f: patches.append(f) or True)

    def send(p):
        wire.append(p); return dr.ChunkResult(0, "UNKNOWN", error="TimeoutError", attempts=1)
    assert cb._deliver_recorded("morning", "hello brief", "id-2", store=InMemoryAttemptStore(), send_chunk=send) is False
    assert patches[0]["telegram_status"] == "UNKNOWN" and wire == ["hello brief"]


def test_recorded_delivery_auto_resend_only_with_second_flag_and_is_disclosed(monkeypatch):
    monkeypatch.setenv(dr.FLAG, "1"); monkeypatch.setenv(dr.AUTO_RESEND_FLAG, "1")
    patches, wire = [], []
    monkeypatch.setattr(cb, "_patch_brief_row", lambda bid, f: patches.append(f) or True)
    seq = iter(["UNK", "OK", "OK"])

    def send(p):
        wire.append(p)
        return dr.ChunkResult(0, "UNKNOWN" if next(seq) == "UNK" else "CONFIRMED", message_id=2, attempts=1)
    store = InMemoryAttemptStore()
    assert cb._deliver_recorded("morning", "hello brief", "id-3", store=store, send_chunk=send) is True
    assert wire == ["hello brief", dr.RECOVERY_MARKER + "\n\nhello brief"]     # marker merged into the first resent chunk (fix-logic)
    assert "may have been delivered twice" in patches[-1]["delivery_disclosure"]
    rep = dr.duplicate_report(store.load("captains_daily_briefs", "id-3", "telegram"))
    assert rep["preventable_duplicates"] == 0 and rep["authorised_recovery_resends"] == 1


def test_status_and_delivery_independent_in_send_brief(monkeypatch):
    """Break delivery -> status unchanged; break content -> delivery unchanged."""
    monkeypatch.setenv("BRIEF_STATUS_V1", "1"); monkeypatch.setenv(dr.FLAG, "1")
    monkeypatch.setattr(cb, "_TELEGRAM_TOKEN", "t"); monkeypatch.setattr(cb, "_TELEGRAM_CHAT", "c")

    def run(text, chunk_state):
        rows = []
        monkeypatch.setattr(cb, "_patch_brief_row", lambda bid, f: rows.append(f) or True)
        monkeypatch.setattr(cb, "generate_knowledge_ops_brief", lambda: text)
        monkeypatch.setattr(cb, "_persist_brief", lambda *a, **k: "rid-" + chunk_state + str(len(text)))
        monkeypatch.setattr(cb, "_record_brief_events", lambda *a, **k: None)
        monkeypatch.setattr(cb, "_delivery_store", lambda: InMemoryAttemptStore())
        monkeypatch.setattr(da, "make_telegram_sender",
                            lambda: (lambda p: dr.ChunkResult(0, chunk_state, message_id=1 if chunk_state == "CONFIRMED" else None, attempts=1)))
        cb.send_brief("knowledge_ops")
        merged = {}
        for r in rows:
            merged.update(r)
        return merged

    good = "A genuinely substantive brief with enough real content to count as a narrative of record."
    a = run(good, "CONFIRMED"); b = run(good, "FAILED")
    assert a["production_status"] == b["production_status"] == "NORMAL"
    assert a["telegram_status"] == "CONFIRMED" and b["telegram_status"] == "FAILED"
    c = run("N/A", "CONFIRMED")
    assert c["production_status"] != "NORMAL" and c["telegram_status"] == "CONFIRMED"


def test_telegram_unconfigured_keeps_legacy_behaviour_with_flags_on(monkeypatch):
    monkeypatch.setenv(dr.FLAG, "1")
    monkeypatch.setattr(cb, "_TELEGRAM_TOKEN", ""); monkeypatch.setattr(cb, "_TELEGRAM_CHAT", "")
    with mock.patch.object(cb, "_deliver_recorded", side_effect=AssertionError("no attempt when unconfigured")):
        assert cb._send_brief_v1("x", "text", None, None) is False


# ---------------------------------------------------------------- render wording
from intelligence.brief.render import render_telegram_morning_text

LEGACY = "Nothing currently requires immediate action."


@pytest.mark.parametrize("brief", [
    {"brief_id": "b", "overall_risk": "GREEN", "top_events": [], "coverage": {}},
    {"brief_id": "b", "overall_risk": "UNKNOWN", "top_events": [], "coverage": {"degraded": True, "missing_sources": ["A"]}},
])
def test_render_flag_off_is_legacy_flag_on_is_not_reassuring(monkeypatch, brief):
    assert LEGACY in render_telegram_morning_text(brief)
    monkeypatch.setenv("BRIEF_STATUS_V1", "1")
    out = render_telegram_morning_text(brief)
    assert LEGACY not in out
    if brief["coverage"].get("degraded") or brief["overall_risk"] == "UNKNOWN":
        assert "not an all-clear" in out
    else:
        assert "assessed as requiring immediate action" in out


def test_render_with_content_unchanged_by_flag(monkeypatch):
    brief = {"brief_id": "b", "overall_risk": "AMBER", "top_events": [{"title": "T", "so_what": "S"}], "coverage": {}}
    off = render_telegram_morning_text(brief)
    monkeypatch.setenv("BRIEF_STATUS_V1", "1")
    assert render_telegram_morning_text(brief) == off
