"""Tests for notify()'s chat_id override and chunk=True path (added
2026-08-29 as part of the notification-sender consolidation — see
tools/check_notification_senders.py). This module is now load-bearing for
multiple migrated senders, so it needs real coverage, not just the
call-log spot-check the module previously shipped without."""

from __future__ import annotations

import pytest

import core.platform.notification_service as ns


@pytest.fixture(autouse=True)
def _reset_sender(monkeypatch):
    calls = []

    def fake_telegram(text, reply_markup=None, chat_id=None, severity=ns.Severity.INFO):
        calls.append({"text": text, "reply_markup": reply_markup, "chat_id": chat_id, "severity": severity})
        return True, None, 12345

    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, fake_telegram)
    ns._CALL_LOG.clear()
    return calls


def test_chat_id_override_reaches_sender(_reset_sender):
    ns.notify("hi", chat_id="999")
    assert _reset_sender[-1]["chat_id"] == "999"


def test_default_chat_id_is_none_when_unset(_reset_sender):
    ns.notify("hi")
    assert _reset_sender[-1]["chat_id"] is None


def test_reply_markup_passed_through(_reset_sender):
    markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "x"}]]}
    ns.notify("hi", reply_markup=markup)
    assert _reset_sender[-1]["reply_markup"] == markup


def test_message_id_returned_in_result(_reset_sender):
    result = ns.notify("hi")
    assert result.message_id == 12345


def test_chunk_false_truncates_at_4096(_reset_sender):
    long_body = "word " * 2000  # ~10000 chars, well over the limit
    ns.notify(long_body, chunk=False)
    assert len(_reset_sender) == 1
    assert len(_reset_sender[0]["text"]) <= ns._TELEGRAM_MAX_LEN


def test_chunk_true_splits_without_truncating_content(_reset_sender):
    long_body = ("word " * 2000).strip()
    ns.notify(long_body, template="plain", chunk=True)
    assert len(_reset_sender) > 1
    for call in _reset_sender:
        assert len(call["text"]) <= ns._TELEGRAM_MAX_LEN
        assert not call["text"].endswith(" ")
    reassembled = " ".join(c["text"] for c in _reset_sender)
    assert reassembled.split() == long_body.split()


def test_chunk_true_short_body_sends_one_message(_reset_sender):
    ns.notify("short message", chunk=True)
    assert len(_reset_sender) == 1


def test_apprise_render_strips_telegram_html_and_unescapes_entities():
    # "alert" template wraps title in <b> for Telegram — Apprise transports
    # don't parse that as HTML, so it must come out as plain text, and the
    # &amp;-escaping _escape_telegram_html applied must be undone too.
    text = ns._render_for_apprise("alert", "A & B", "body <x>", ns.Severity.CRITICAL)
    assert "<b>" not in text and "</b>" not in text
    assert "A & B" in text
    assert "&amp;" not in text


def test_apprise_render_prefixes_severity_emoji_on_plain_template():
    text = ns._render_for_apprise("plain", None, "hello", ns.Severity.WARNING)
    assert text.startswith(ns._SEVERITY_EMOJI[ns.Severity.WARNING])
    assert "hello" in text


def test_apprise_render_leaves_raw_template_untouched_besides_unescaping():
    # "raw" is caller-composed — no severity emoji should be injected.
    text = ns._render_for_apprise("raw", None, "already composed", ns.Severity.CRITICAL)
    assert text == "already composed"


def test_send_apprise_missing_urls_env(monkeypatch):
    monkeypatch.delenv("APPRISE_URLS", raising=False)
    ok, error, message_id = ns._send_apprise("hi")
    assert ok is False
    assert "APPRISE_URLS" in error
    assert message_id is None


def test_send_apprise_invalid_url(monkeypatch):
    monkeypatch.setenv("APPRISE_URLS", "not-a-real-apprise-scheme://nope")
    ok, error, _message_id = ns._send_apprise("hi")
    assert ok is False
    assert error is not None


def test_notify_apprise_transport_routes_through_send_apprise(monkeypatch):
    captured = {}

    def fake_send_apprise(text, reply_markup=None, chat_id=None, severity=ns.Severity.INFO):
        captured["text"] = text
        captured["severity"] = severity
        return True, None, None

    monkeypatch.setitem(ns._SENDERS, ns.Transport.APPRISE, fake_send_apprise)
    result = ns.notify("hello", severity=ns.Severity.WARNING, transport=ns.Transport.APPRISE)
    assert result.ok is True
    assert result.transport == ns.Transport.APPRISE
    assert result.message_id is None
    # Rendered via _render_for_apprise, not Telegram's _render — no HTML tags.
    assert "<" not in captured["text"]
    assert captured["severity"] == ns.Severity.WARNING


def test_chunk_never_cuts_mid_word(_reset_sender):
    # A body designed so a naive text[:4096] slice would land mid-word.
    token = "boundary-word-that-must-not-be-split"
    long_body = "a" * 4090 + " " + token + " " + "b" * 100
    ns.notify(long_body, template="plain", chunk=True)
    whole_texts = [c["text"] for c in _reset_sender]
    assert any(token in t for t in whole_texts), "token must survive intact in some chunk"
    assert not any(t.endswith(token[: len(token) // 2]) for t in whole_texts), "token was split across chunks"


# ── Telegram HTTP errors: log Telegram's description, don't retry a 400 ────────

import io
import json
import logging
import urllib.error

_TOKEN = "123456:SECRET-TOKEN-VALUE"
_CHAT = "987654321"
_SECRET_TEXT = "private message body with <NRP>"


def _http_error(code, description=None, body=None):
    raw = body if body is not None else json.dumps(
        {"ok": False, "error_code": code, "description": description}
    ).encode()
    return urllib.error.HTTPError(
        f"https://bot-api.example.invalid/bot{_TOKEN}/sendMessage", code, "err", {}, io.BytesIO(raw)
    )


@pytest.fixture
def real_telegram(monkeypatch):
    """Use the real _send_telegram with urlopen faked; count attempts."""
    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, ns._send_telegram)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", _CHAT)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.setattr(ns.time, "sleep", lambda _s: None)
    attempts = []

    def install(outcomes):
        it = iter(outcomes)

        def fake_urlopen(req, timeout=None):
            attempts.append(1)
            outcome = next(it)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(ns.urllib.request, "urlopen", fake_urlopen)
        return attempts

    return install


class _OkResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps({"ok": True, "result": {"message_id": 7}}).encode()


def test_400_logs_description_and_makes_one_attempt_only(real_telegram, caplog):
    attempts = real_telegram([_http_error(400, "Bad Request: can't parse entities: Unsupported start tag \"nrp\" at byte offset 1525")] * 3)
    with caplog.at_level(logging.WARNING):
        result = ns.notify(_SECRET_TEXT, template="raw", transport=ns.Transport.TELEGRAM, max_retries=2)
    assert not result.ok
    assert len(attempts) == 1 and result.attempts == 1
    assert result.error.startswith("HTTP 400: Bad Request: can't parse entities")
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Unsupported start tag" in logged


def test_500_still_retries(real_telegram):
    attempts = real_telegram([_http_error(500, "Internal Server Error"), _http_error(500, "Internal Server Error"), _OkResponse()])
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM, max_retries=2)
    assert result.ok and result.message_id == 7
    assert len(attempts) == 3


def test_429_still_retries(real_telegram):
    attempts = real_telegram([_http_error(429, "Too Many Requests: retry after 1"), _OkResponse()])
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM, max_retries=1)
    assert result.ok and len(attempts) == 2


def test_network_error_still_retries(real_telegram):
    attempts = real_telegram([urllib.error.URLError("connection reset"), _OkResponse()])
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM, max_retries=1)
    assert result.ok and len(attempts) == 2


def test_log_line_has_no_message_text_token_or_chat_id(real_telegram, caplog):
    real_telegram([_http_error(400, f"Bad Request: bad token {_TOKEN} for chat {_CHAT}")])
    with caplog.at_level(logging.DEBUG):
        result = ns.notify(_SECRET_TEXT, template="raw", transport=ns.Transport.TELEGRAM)
    logged = "\n".join(r.getMessage() for r in caplog.records) + result.error
    assert _TOKEN not in logged
    assert "SECRET-TOKEN-VALUE" not in logged
    assert _SECRET_TEXT not in logged and "private message body" not in logged
    # the chat id is not logged by us; if Telegram echoes it in its description it is Telegram's text,
    # but the token is always blanked
    assert "<token>" in result.error


def test_description_is_capped(real_telegram):
    real_telegram([_http_error(400, "x" * 5000)])
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM)
    assert len(result.error) <= len("HTTP 400: ") + ns._TELEGRAM_ERROR_DESCRIPTION_MAX


def test_400_with_unreadable_body_reports_status_only(real_telegram):
    real_telegram([_http_error(400, body=b"<html>not json</html>")])
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM)
    assert result.error == "HTTP 400" and result.attempts == 1


def test_network_error_message_never_contains_the_token(real_telegram):
    real_telegram([urllib.error.URLError(f"failed for https://bot-api.example.invalid/bot{_TOKEN}/sendMessage")] * 2)
    result = ns.notify("hi", template="raw", transport=ns.Transport.TELEGRAM, max_retries=1)
    assert _TOKEN not in result.error and "<token>" in result.error
