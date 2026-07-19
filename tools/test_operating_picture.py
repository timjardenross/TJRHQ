"""MSN-0179 — Tests for /operating_picture Telegram command.

Five tests covering:
  1. Successful response — all fields rendered
  2. Degraded response — "error" key in payload → warning shown
  3. Missing LCARS_PORTAL_URL — error without HTTP call
  4. Telegram MarkdownV2 escaping (hyphens escaped, etc.)
  5. No direct Supabase calls from Telegram
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Dependency stubs ──────────────────────────────────────────────────────────

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-0179")
os.environ.setdefault("TELEGRAM_CHAT_ID",   "123456")
os.environ.setdefault("SUPABASE_URL",        "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY",        "test-key")
os.environ.setdefault("LCARS_PORTAL_URL",    "https://lcars.example.com")

def _build_telegram_stub():
    mod = types.ModuleType("telegram")
    for name in [
        "Update", "InlineKeyboardButton", "InlineKeyboardMarkup",
        "BotCommand", "ReplyKeyboardMarkup", "KeyboardButton",
    ]:
        setattr(mod, name, MagicMock)
    mod.constants = types.SimpleNamespace(ParseMode=types.SimpleNamespace(MARKDOWN_V2="MarkdownV2"))
    return mod

def _build_ext_stub():
    ext = types.ModuleType("telegram.ext")
    for name in [
        "Application", "CommandHandler", "MessageHandler", "CallbackQueryHandler",
        "ContextTypes", "filters", "JobQueue",
    ]:
        setattr(ext, name, MagicMock)
    ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=MagicMock)
    return ext

sys.modules.setdefault("telegram",     _build_telegram_stub())
sys.modules.setdefault("telegram.ext", _build_ext_stub())

for _name, _attrs in [
    ("apscheduler",                    {}),
    ("apscheduler.schedulers",         {}),
    ("apscheduler.schedulers.asyncio", {"AsyncIOScheduler": MagicMock}),
    ("apscheduler.triggers",           {}),
    ("apscheduler.triggers.cron",      {"CronTrigger": MagicMock}),
]:
    _m = types.ModuleType(_name)
    for k, v in _attrs.items():
        setattr(_m, k, v)
    sys.modules.setdefault(_name, _m)

_httpx = types.ModuleType("httpx")
_httpx.AsyncClient = MagicMock
sys.modules.setdefault("httpx", _httpx)

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)

_sb = types.ModuleType("supabase")
_sb.create_client = MagicMock(return_value=MagicMock())
sys.modules.setdefault("supabase", _sb)

for _name, _attrs in [
    ("telegram_bots",                  {}),
    ("telegram_bots.recovery_officer", {}),
    ("telegram_bots.recovery_officer.engagement_dispatcher", {
        "RecoveryStatus":     MagicMock,
        "build_daily_summary": MagicMock(return_value=""),
        "get_recovery_status": MagicMock(return_value=MagicMock()),
        "run_dispatch_check":  MagicMock(),
    }),
    ("telegram_bots.llm", {
        "generate_async": AsyncMock(return_value=""),
    }),
    ("telegram_bots.wellness_officer", {}),
    ("telegram_bots.wellness_officer.intelligence", {
        "get_wellness_snapshot": MagicMock(return_value=MagicMock()),
    }),
    ("telegram_bots.wellness_officer.brief", {
        "generate_wellness_brief_async": AsyncMock(return_value=""),
    }),
]:
    _m = types.ModuleType(_name)
    for k, v in _attrs.items():
        setattr(_m, k, v)
    sys.modules.setdefault(_name, _m)

# ── Load bot module ───────────────────────────────────────────────────────────

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "xo_app_0179",
    os.path.join(os.path.dirname(__file__), "..", "telegram-bots", "xo", "app.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

cmd_operating_picture = _mod.cmd_operating_picture


# ── Helpers ───────────────────────────────────────────────────────────────────

_FULL_PAYLOAD = {
    "generated_at": "2026-06-27T00:00:00Z",
    "missions": {
        "active_count":           5,
        "awaiting_approval_count": 2,
        "blocked_count":          1,
        "approved_count":         3,
        "active":                 [],
        "awaiting_approval":      [],
        "blocked":                [],
        "approved":               [],
    },
    "decisions": {"open_count": 4, "items": []},
    "counters":  {"MSN": 180, "next_MSN": "USS-TJR-MSN-0181"},
    "next_actions": [
        "Captain approval needed for 2 missions",
        "1 mission blocked — investigate",
    ],
    "recent_transitions": [
        {"mission_id": "USS-TJR-MSN-0178", "to_state": "Awaiting Captain Approval"},
        {"mission_id": "USS-TJR-MSN-0177", "to_state": "Approved"},
    ],
}

def _make_update():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    return update

def _make_resp(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.text = str(body)
    return r

def _make_client(resp):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__  = AsyncMock(return_value=False)
    cm.get = AsyncMock(return_value=resp)
    return cm


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestOperatingPicture(unittest.IsolatedAsyncioTestCase):

    async def test_successful_response(self):
        """All fields from full payload are rendered in reply."""
        resp = _make_resp(200, _FULL_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_operating_picture(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "5" in text        # active count
        assert "2" in text        # awaiting_approval
        assert "4" in text        # open decisions
        assert "0181" in text     # next_MSN (hyphens escaped but digit tail present)
        assert "Operating Picture" in text

    async def test_degraded_response(self):
        """Payload with 'error' key triggers partial-data warning."""
        degraded = dict(_FULL_PAYLOAD)
        degraded["error"] = "decisions table unavailable"
        resp = _make_resp(200, degraded)
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_operating_picture(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "Partial" in text or "partial" in text or "unavailable" in text.lower()

    async def test_missing_lcars_url(self):
        """No LCARS_PORTAL_URL → error without HTTP call."""
        orig = _mod.LCARS_PORTAL_URL
        _mod.LCARS_PORTAL_URL = ""
        try:
            update = _make_update()
            with patch("httpx.AsyncClient") as mock_client:
                await cmd_operating_picture(update, MagicMock())
                mock_client.assert_not_called()
        finally:
            _mod.LCARS_PORTAL_URL = orig
        text = update.message.reply_text.call_args[0][0]
        assert "LCARS" in text or "not configured" in text.lower() or "unavailable" in text.lower()

    async def test_markdown_escaping(self):
        """MarkdownV2 special chars must be escaped in the reply."""
        resp = _make_resp(200, _FULL_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_operating_picture(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        kwargs = update.message.reply_text.call_args[1]
        assert kwargs.get("parse_mode") == "MarkdownV2"
        # Hyphens in IDs should be escaped
        assert "USS-TJR-MSN" not in text

    async def test_no_direct_supabase_calls(self):
        """Operating picture must be read-only via API; no bot-side Supabase writes."""
        sb_client = _sb.create_client.return_value
        sb_client.reset_mock()
        resp = _make_resp(200, _FULL_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_operating_picture(update, MagicMock())
        if sb_client.table.called:
            for call in sb_client.table.call_args_list:
                tbl = str(call)
                assert "missions" not in tbl
                assert "mission_state_transitions" not in tbl


if __name__ == "__main__":
    unittest.main()
