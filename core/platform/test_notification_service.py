"""Tests for notify()'s chat_id override and chunk=True path (added
2026-08-29 as part of the notification-sender consolidation — see
tools/check_notification_senders.py). This module is now load-bearing for
multiple migrated senders, so it needs real coverage, not just the
call-log spot-check the module previously shipped without."""

from __future__ import annotations

import core.platform.notification_service as ns
import pytest


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
    ok, error, message_id = ns._send_apprise("hi")
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
