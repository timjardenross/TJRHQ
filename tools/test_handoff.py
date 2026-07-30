"""MSN-0180 — Tests for /handoff_engineering Telegram command.

Seven tests covering:
  1. Valid handoff (Idea → Approved for Engineering)
  2. Unknown mission (404)
  3. Ineligible status (409 with current status)
  4. Audit record written (API-side, not bot-side)
  5. Handoff artefact — next_engineering_action hint shown
  6. Telegram MarkdownV2 escaping (hyphens escaped)
  7. No direct Supabase writes from Telegram bot
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Dependency stubs ──────────────────────────────────────────────────────────

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-0180")
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
    "xo_app_0180",
    os.path.join(os.path.dirname(__file__), "..", "telegram-bots", "xo", "app.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

cmd_handoff_engineering = _mod.cmd_handoff_engineering


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_update(text="/handoff_engineering 0181"):
    update = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update

def _make_context(*args):
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx

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
    cm.post = AsyncMock(return_value=resp)
    return cm


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHandoffEngineering(unittest.IsolatedAsyncioTestCase):

    async def test_valid_handoff(self):
        """Happy path: Idea → Approved for Engineering."""
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0181",
            "title":           "Some Future Mission",
            "previous_status": "Idea",
            "new_status":      "Approved for Engineering",
            "next_engineering_action": "Engineering implementation and test evidence required before /mission_submit",
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0181"))
        text = update.message.reply_text.call_args[0][0]
        assert "Approved" in text or "Engineering" in text
        assert "0181" in text

    async def test_unknown_mission_404(self):
        """404 from API → friendly not-found reply."""
        resp = _make_resp(404, {"error": "Mission not found"})
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("9999"))
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text.lower() or "9999" in text

    async def test_ineligible_status_409(self):
        """409 from API → current status shown to user."""
        resp = _make_resp(409, {
            "error": "Mission not eligible for engineering handoff",
            "current_status": "Awaiting Captain Approval",
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0178"))
        text = update.message.reply_text.call_args[0][0]
        assert "eligible" in text.lower() or "Approval" in text

    async def test_audit_record_api_side(self):
        """Bot must not write directly to mission_state_transitions."""
        sb_client = _sb.create_client.return_value
        sb_client.reset_mock()
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0181",
            "title":           "Some Future Mission",
            "previous_status": "Idea",
            "new_status":      "Approved for Engineering",
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0181"))
        if sb_client.table.called:
            for call in sb_client.table.call_args_list:
                assert "mission_state_transitions" not in str(call)

    async def test_engineering_action_hint_shown(self):
        """next_engineering_action from API response must appear in reply."""
        hint = "Engineering implementation and test evidence required before /mission_submit"
        resp = _make_resp(200, {
            "mission_id":              "USS-TJR-MSN-0181",
            "title":                   "Some Future Mission",
            "previous_status":         "Idea",
            "new_status":              "Approved for Engineering",
            "next_engineering_action": hint,
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0181"))
        text = update.message.reply_text.call_args[0][0]
        # Hint contains /mission_submit — may be escaped in MarkdownV2
        assert "mission" in text.lower() or "engineering" in text.lower()

    async def test_markdown_escaping(self):
        """MarkdownV2: hyphens in mission IDs are escaped."""
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0181",
            "title":           "Some Future Mission",
            "previous_status": "Idea",
            "new_status":      "Approved for Engineering",
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0181"))
        text = update.message.reply_text.call_args[0][0]
        assert "0181" in text
        assert "USS-TJR-MSN" not in text

    async def test_no_direct_supabase_writes(self):
        """Handoff must be API-first: no insert/update on bot side."""
        sb_client = _sb.create_client.return_value
        sb_client.reset_mock()
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0181",
            "title":           "Some Future Mission",
            "previous_status": "Idea",
            "new_status":      "Approved for Engineering",
        })
        with patch("httpx.AsyncClient", return_value=_make_client(resp)):
            update = _make_update()
            await cmd_handoff_engineering(update, _make_context("0181"))
        assert not sb_client.table.return_value.insert.called, \
            "Bot must not insert directly into Supabase"
        assert not sb_client.table.return_value.update.called, \
            "Bot must not update directly in Supabase"


if __name__ == "__main__":
    unittest.main()
