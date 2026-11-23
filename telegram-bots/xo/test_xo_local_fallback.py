"""End-to-end: the XO chat handler delivers the visible fallback when local processing fails (#661).

The handler runs for real (asyncio.run, no pytest-asyncio needed). Only the database/lookup helpers are stubbed; the LLM path is the
real telegram_bots.llm code with urlopen replaced, and every requested host is recorded, so the test also proves nothing left the
machine."""
from __future__ import annotations

import asyncio
import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

pytest.importorskip("telegram")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram_bots import llm
from telegram_bots.xo import app

EXPECTED = "The local AI assistant is unavailable right now. You can still use /brief or /priorities."


def _update(text):
    u = MagicMock()
    u.message.text = text
    u.message.reply_to_message = None
    u.message.message_id = 7
    u.message.reply_text = AsyncMock()
    u.message.chat.send_action = AsyncMock()
    u.effective_chat.id = 12345
    return u


def _run_handler(text, urlopen):
    update = _update(text)
    ctx = MagicMock()
    with patch.object(app, "_get_supabase", return_value=None), \
         patch.object(app, "get_recovery_status", return_value={}), \
         patch.object(app, "get_wellness_snapshot", return_value=None), \
         patch.object(app, "_get_open_missions", return_value=[]), \
         patch.object(app, "_get_recent_turns", return_value=[]), \
         patch.object(app, "_log_conversation_turn"), \
         patch.object(app, "_xo_system_prompt", return_value="system"), \
         patch.object(app.meds, "is_outstanding", return_value=False), \
         patch.dict(os.environ, {"OLLAMA_API_KEY": "dummy-key"}, clear=False), \
         patch.object(llm.urllib.request, "urlopen", urlopen):
        os.environ.pop("HEALTH_LLM_EXTERNAL_ALLOWED", None)
        asyncio.run(app.cmd_message(update, ctx))
    return update


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), urllib.error.URLError(ConnectionRefusedError(111, "refused"))])
def test_local_failure_shows_friendly_fallback_and_never_reaches_the_cloud(failure):
    hosts = []

    def urlopen(req, timeout=None):
        hosts.append(urlparse(req.full_url).hostname)
        if hosts[-1] not in {"127.0.0.1", "localhost"}:
            raise AssertionError(f"off-box request to {hosts[-1]}")
        raise failure

    update = _run_handler("I slept badly and my pain is higher today, what should I do?", urlopen)
    sent = update.message.reply_text.call_args
    assert sent is not None, "the Captain got no reply at all"
    assert sent.args[0] == app._escape(EXPECTED)
    assert "LLM unreachable" not in sent.args[0]
    assert hosts and set(hosts) <= {"127.0.0.1", "localhost"}


def test_fallback_wording_is_exactly_the_approved_text():
    assert app.XO_LOCAL_AI_UNAVAILABLE == EXPECTED
