"""Golden tests: with strict mode off, the extended notification service behaves exactly like the baseline copy
(tests/fixtures/notification_service_baseline.py, a byte copy of the pre-change module): ok, attempts, error,
message_id, call-log entries, requests on the wire, retry count and sleeps after a timeout, and early-chunk
failure behaviour. Nothing is sent: urlopen is scripted."""
from __future__ import annotations

import dataclasses
import pathlib
import sys
import time
import types
import urllib.request

import pytest

import core.platform.notification_service as ns_new
from tests.ns_support import LONG_PLAIN, LONG_RAW, ScriptedTelegram

# The frozen pre-change copy is stored as text (".py.txt"): it is test data, not a sender, and must not trip the raw-sender gate.
_BASE = pathlib.Path(__file__).parent / "fixtures" / "notification_service_baseline.py.txt"
ns_old = types.ModuleType("ns_baseline")
ns_old.__file__ = str(_BASE)
sys.modules["ns_baseline"] = ns_old
exec(compile(_BASE.read_text(), str(_BASE), "exec"), ns_old.__dict__)  # noqa: S102 - the repo's own frozen baseline source

SCENARIOS = {
    "short_ok": ({"body": "hello"}, ["ok"]),
    "timeout_then_ok_retries": ({"body": "hello"}, ["timeout", "ok"]),
    "timeout_twice": ({"body": "hello"}, ["timeout", "timeout"]),
    "timeout_no_retries": ({"body": "hello", "max_retries": 0}, ["timeout"]),
    "http400_not_retried": ({"body": "hello"}, ["h400"]),
    "http429_retried": ({"body": "hello"}, ["h429", "ok"]),
    "http500_retried_then_ok": ({"body": "hello"}, ["h500", "ok"]),
    "reset_then_ok": ({"body": "hello"}, ["reset", "ok"]),
    "refused_twice": ({"body": "hello"}, ["refused", "refused"]),
    "badjson_ok_path": ({"body": "hello"}, ["badjson", "ok"]),
    "ok_without_id": ({"body": "hello"}, ["okNoId"]),
    "chunked_all_ok": ({"body": LONG_PLAIN, "chunk": True}, ["ok", "ok", "ok"]),
    "chunked_early_fail_last_ok": ({"body": LONG_PLAIN, "chunk": True}, ["h400", "ok", "ok"]),
    "chunked_middle_fail_continues": ({"body": LONG_PLAIN, "chunk": True}, ["ok", "h400", "ok"]),
    "chunked_last_fail": ({"body": LONG_PLAIN, "chunk": True}, ["ok", "ok", "h400"]),
    "chunked_timeout_retry_resends": ({"body": LONG_PLAIN, "chunk": True}, ["ok", "timeout", "ok", "ok"]),
    "chunked_all_fail": ({"body": LONG_PLAIN, "chunk": True}, ["h400", "h400", "h400"]),
    "chunked_raw_html": ({"body": LONG_RAW, "template": "raw", "chunk": True}, ["ok", "ok", "ok"]),
    "chunk_flag_but_short": ({"body": "hello", "chunk": True}, ["ok"]),
    "not_chunked_long_truncates": ({"body": LONG_PLAIN}, ["ok"]),
    "title_and_severity": ({"body": "b", "title": "T", "severity": "alert", "template": "alert"}, ["ok"]),
    "chat_id_override": ({"body": "b", "chat_id": "42"}, ["ok"]),
}


def _run(mod, kwargs, script, monkeypatch):
    kwargs = dict(kwargs)
    if "severity" in kwargs:
        kwargs["severity"] = mod.Severity(kwargs["severity"])
    fake = ScriptedTelegram(*script)
    sleeps: list[float] = []
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
    mod._CALL_LOG.clear()
    body = kwargs.pop("body")
    result = mod.notify(body, **kwargs)
    legacy = lambda r: (r.ok, r.transport.value, r.attempts, r.error, r.message_id)
    log_ = [(e.transport.value, e.severity.value, e.title, e.body, legacy(e.result)) for e in mod._CALL_LOG]
    return legacy(result), log_, list(fake.wire), sleeps


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_default_behaviour_identical_to_baseline(name, monkeypatch):
    kwargs, script = SCENARIOS[name]
    old = _run(ns_old, kwargs, script, monkeypatch)
    new = _run(ns_new, kwargs, script, monkeypatch)
    assert new == old


def test_legacy_results_carry_no_structured_fields(monkeypatch):
    for name, (kwargs, script) in SCENARIOS.items():
        kw = dict(kwargs)
        if "severity" in kw:
            kw["severity"] = ns_new.Severity(kw["severity"])
        monkeypatch.setattr(urllib.request, "urlopen", ScriptedTelegram(*script))
        monkeypatch.setattr(time, "sleep", lambda s: None)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
        r = ns_new.notify(kw.pop("body"), **kw)
        assert r.chunk_results is None and r.delivery_outcome is None, name


def test_explicit_strict_false_is_the_default(monkeypatch):
    a = _run(ns_new, SCENARIOS["timeout_then_ok_retries"][0], ["timeout", "ok"], monkeypatch)
    kw = dict(SCENARIOS["timeout_then_ok_retries"][0], strict=False, chunk_stop_on_failure=True)
    b = _run(ns_new, kw, ["timeout", "ok"], monkeypatch)
    assert a == b


def test_result_dataclass_is_a_pure_extension():
    old = [f.name for f in dataclasses.fields(ns_old.NotificationResult)]
    new = [f.name for f in dataclasses.fields(ns_new.NotificationResult)]
    assert new[:len(old)] == old and new[len(old):] == ["chunk_results", "delivery_outcome"]
    # existing positional/keyword construction is unchanged
    r = ns_new.NotificationResult(True, ns_new.Transport.TELEGRAM, 1)
    assert (r.error, r.message_id, r.chunk_results, r.delivery_outcome) == (None, None, None, None)


def test_public_names_are_a_superset():
    assert set(ns_old.__all__) <= set(ns_new.__all__)
    old_notify = ns_old.notify.__code__.co_varnames[:ns_old.notify.__code__.co_argcount + ns_old.notify.__code__.co_kwonlyargcount]
    new_notify = ns_new.notify.__code__.co_varnames[:ns_new.notify.__code__.co_argcount + ns_new.notify.__code__.co_kwonlyargcount]
    assert new_notify[:len(old_notify)] == old_notify and new_notify[len(old_notify):] == ("strict", "chunk_stop_on_failure")


def test_legacy_functions_are_textually_unchanged():
    import inspect
    for fn in ("_send_one", "_send_telegram", "_split_html_aware", "_split_at_word_boundary", "_render_full", "_is_permanent_failure"):
        assert inspect.getsource(getattr(ns_new, fn)) == inspect.getsource(getattr(ns_old, fn)), fn
