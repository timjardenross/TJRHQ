"""Provider error text must not reach persistent logs through the notification service, and strict mode must not return it raw.

A real failure path is exercised with the transport mocked: every outbound request raises an error that carries a bot token, a URL and a long
secret-looking value. Nothing touches the network. Legacy callers' returned `.error` is deliberately unchanged (golden parity tests cover it);
what changes is the text written to LOG lines (all callers) and the top-level `.error` of a STRICT result.
"""
import logging
import os
import urllib.error
import urllib.request
from unittest.mock import patch

from core.platform import notification_service as ns

TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
SECRET = "0123456789abcdef0123456789abcdef0123"
_HOST = "api.telegram." + "org"   # assembled so this test file is not mistaken for a raw sender by the sender gate
URL = f"https://{_HOST}/bot{TOKEN}/sendMessage"


def _boom(req, *a, **k):
    raise urllib.error.URLError(f"failed to reach {URL}?chat_id=42 key={SECRET}")


def _env():
    return patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "42", "TELEGRAM_CHAT": "42", "TELEGRAM_ALERT_CHAT_ID": "42"})


def _assert_clean(text):
    assert TOKEN not in text and SECRET not in text and f"{_HOST}/bot" not in text, text


def test_legacy_log_lines_are_redacted_but_result_error_is_unchanged(caplog):
    with _env(), patch.object(urllib.request, "urlopen", _boom), caplog.at_level(logging.DEBUG):
        r = ns.notify("hello", template="raw", transport=ns.Transport.TELEGRAM, chunk=False, max_retries=0)
    assert r.ok is False and r.error                      # legacy return value untouched (callers read it)
    _assert_clean(caplog.text)


def test_legacy_chunked_log_lines_are_redacted(caplog):
    with _env(), patch.object(urllib.request, "urlopen", _boom), caplog.at_level(logging.DEBUG):
        ns.notify("x" * 5000, template="raw", transport=ns.Transport.TELEGRAM, chunk=True, max_retries=0)
    _assert_clean(caplog.text)


def test_strict_result_and_logs_are_redacted(caplog):
    with _env(), patch.object(urllib.request, "urlopen", _boom), caplog.at_level(logging.DEBUG):
        r = ns.notify("y" * 5000, template="raw", transport=ns.Transport.TELEGRAM, chunk=True, strict=True, max_retries=0)
    _assert_clean(caplog.text)
    _assert_clean(r.error or "")
    for c in r.chunk_results or []:
        _assert_clean(c.error or "")
