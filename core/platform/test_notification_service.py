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

    def fake_telegram(text, reply_markup=None, chat_id=None):
        calls.append({"text": text, "reply_markup": reply_markup, "chat_id": chat_id})
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


def test_chunk_never_cuts_mid_word(_reset_sender):
    # A body designed so a naive text[:4096] slice would land mid-word.
    token = "boundary-word-that-must-not-be-split"
    long_body = "a" * 4090 + " " + token + " " + "b" * 100
    ns.notify(long_body, template="plain", chunk=True)
    whole_texts = [c["text"] for c in _reset_sender]
    assert any(token in t for t in whole_texts), "token must survive intact in some chunk"
    assert not any(t.endswith(token[: len(token) // 2]) for t in whole_texts), "token was split across chunks"
