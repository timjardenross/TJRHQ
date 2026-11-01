"""Telegram bot token redaction in logging (telegram-bots/log_redaction.py).

All tokens here are synthetic.
"""

import io
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "telegram-bots"))

import log_redaction

SECRET = "AAFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0"  # pragma: allowlist secret
TOKEN = f"123456789:{SECRET}"
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"


class HttpxStyleError(Exception):
    """Mimics httpx.ConnectError: str() embeds the request URL."""


@pytest.fixture
def stream():
    """Root logger with a plain handler + real Formatter, redaction installed."""
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    old_factory = logging.getLogRecordFactory()
    old_installed = log_redaction._installed
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root.handlers = [h]
    root.setLevel(logging.DEBUG)
    log_redaction._installed = False
    log_redaction.install_token_redaction()
    yield buf
    root.handlers = old_handlers
    root.setLevel(old_level)
    logging.setLogRecordFactory(old_factory)
    log_redaction._installed = old_installed


def _assert_clean(out: str):
    assert SECRET not in out
    assert "123456789" not in out
    assert "bot<REDACTED>" in out


def test_plain_url(stream):
    logging.getLogger("httpx").info(f"HTTP Request: POST {URL} 200")
    _assert_clean(stream.getvalue())
    assert "https://api.telegram.org/bot<REDACTED>/getUpdates" in stream.getvalue()


def test_file_url(stream):
    logging.getLogger("telegram").warning(f"https://api.telegram.org/file/bot{TOKEN}/voice/f.ogg")
    _assert_clean(stream.getvalue())
    assert "/file/bot<REDACTED>/voice/f.ogg" in stream.getvalue()


def test_args_tuple(stream):
    logging.getLogger("httpx").info("HTTP Request: %s %s", "POST", URL)
    _assert_clean(stream.getvalue())


def test_args_dict(stream):
    logging.getLogger("httpcore").info("req %(url)s method=%(m)s", {"url": URL, "m": "GET"})
    out = stream.getvalue()
    _assert_clean(out)
    assert "method=GET" in out


def test_non_string_arg_with_token(stream):
    logging.getLogger("x").info("failed: %s count=%d", HttpxStyleError(URL), 3)
    out = stream.getvalue()
    _assert_clean(out)
    assert "count=3" in out


def test_percent_encoded(stream):
    logging.getLogger("x").info("https://api.telegram.org/bot123456789%3A" + SECRET + "/getMe")
    out = stream.getvalue()
    assert SECRET not in out
    assert "bot<REDACTED>/getMe" in out


def test_exception_str_contains_url(stream):
    try:
        raise HttpxStyleError(f"All connection attempts failed for url '{URL}'")
    except HttpxStyleError as e:
        logging.getLogger("telegram.ext").error("Update failed: %s", e)
    _assert_clean(stream.getvalue())


def test_logger_exception_traceback(stream):
    try:
        raise HttpxStyleError(f"boom {URL}")
    except HttpxStyleError:
        logging.getLogger("telegram.ext").exception("polling error")
    out = stream.getvalue()
    _assert_clean(out)
    assert "Traceback (most recent call last)" in out
    assert "HttpxStyleError" in out


def test_exc_info_true(stream):
    try:
        raise HttpxStyleError(f"boom {URL}")
    except HttpxStyleError:
        logging.getLogger("x").warning("oops", exc_info=True)
    out = stream.getvalue()
    _assert_clean(out)
    assert "Traceback" in out


def test_exc_info_cleared_on_record_handler_filter_only():
    """Filter used standalone (no record factory): exc_info is cleared so a
    Formatter cannot re-render the raw traceback."""
    try:
        raise HttpxStyleError(f"boom {URL}")
    except HttpxStyleError:
        import sys as _s

        rec = logging.LogRecord("n", logging.ERROR, __file__, 1, "m", (), _s.exc_info())
    log_redaction.RedactTelegramToken().filter(rec)
    assert rec.exc_info is None
    out = logging.Formatter("%(message)s").format(rec)
    assert SECRET not in out
    assert "Traceback" in out


def test_exc_text_prepopulated():
    rec = logging.LogRecord("n", logging.ERROR, __file__, 1, "m", (), None)
    rec.exc_text = f"Traceback...\nHttpxStyleError: {URL}"
    log_redaction.RedactTelegramToken().filter(rec)
    out = logging.Formatter("%(message)s").format(rec)
    assert SECRET not in out
    assert "bot<REDACTED>" in out


def test_stack_info():
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", (), None)
    rec.stack_info = f"Stack (most recent call last):\n  fetch('{URL}')"
    log_redaction.RedactTelegramToken().filter(rec)
    assert SECRET not in logging.Formatter("%(message)s").format(rec)


def test_later_added_handler_and_propagation(stream):
    """A handler attached AFTER install (and on a child logger) is still covered."""
    buf2 = io.StringIO()
    late = logging.StreamHandler(buf2)
    late.setFormatter(logging.Formatter("%(message)s"))
    child = logging.getLogger("httpx.child")
    child.addHandler(late)
    try:
        child.info("GET %s", URL)
    finally:
        child.removeHandler(late)
    _assert_clean(buf2.getvalue())
    _assert_clean(stream.getvalue())  # propagated to root too


def test_install_is_idempotent(stream):
    log_redaction.install_token_redaction()
    log_redaction.install_token_redaction()
    root = logging.getLogger()
    assert sum(isinstance(f, log_redaction.RedactTelegramToken) for f in root.handlers[0].filters) == 1


def test_non_token_text_unchanged(stream):
    logging.getLogger("x").info("robot12345 said hi; bot is up: %s %d", "https://example.com/bot/x", 42)
    try:
        raise ValueError("plain error")
    except ValueError:
        logging.getLogger("x").exception("kept")
    out = stream.getvalue()
    assert "robot12345 said hi; bot is up: https://example.com/bot/x 42" in out
    assert "ValueError: plain error" in out
    assert "REDACTED" not in out
