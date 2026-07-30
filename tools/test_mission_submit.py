"""MSN-0178 — Tests for /mission_submit Telegram command.

Seven tests covering:
  1. Valid submit (Implemented → Awaiting Captain Approval)
  2. Unknown mission (404)
  3. Ineligible status (409)
  4. Already awaiting Captain approval (409 idempotency)
  5. Audit record written (non-blocking fire-and-forget pattern)
  6. Telegram MarkdownV2 escaping (hyphens escaped in mission IDs)
  7. Missing LCARS_PORTAL_URL guard
"""
from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Dependency stubs (must precede bot import) ────────────────────────────────

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-0178")
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

_tg   = _build_telegram_stub()
_ext  = _build_ext_stub()
sys.modules.setdefault("telegram",      _tg)
sys.modules.setdefault("telegram.ext",  _ext)

_aps = types.ModuleType("apscheduler")
_aps_schedulers = types.ModuleType("apscheduler.schedulers")
_aps_async      = types.ModuleType("apscheduler.schedulers.asyncio")
_aps_async.AsyncIOScheduler = MagicMock
_aps_triggers       = types.ModuleType("apscheduler.triggers")
_aps_triggers_cron  = types.ModuleType("apscheduler.triggers.cron")
_aps_triggers_cron.CronTrigger = MagicMock
sys.modules.setdefault("apscheduler",                    _aps)
sys.modules.setdefault("apscheduler.schedulers",         _aps_schedulers)
sys.modules.setdefault("apscheduler.schedulers.asyncio", _aps_async)
sys.modules.setdefault("apscheduler.triggers",           _aps_triggers)
sys.modules.setdefault("apscheduler.triggers.cron",      _aps_triggers_cron)

_httpx = types.ModuleType("httpx")
_httpx.AsyncClient = MagicMock
sys.modules.setdefault("httpx", _httpx)

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)

_sb = types.ModuleType("supabase")
_sb.create_client = MagicMock(return_value=MagicMock())
sys.modules.setdefault("supabase", _sb)

_tb_modules: dict = {
    "telegram_bots": {},
    "telegram_bots.recovery_officer": {},
    "telegram_bots.recovery_officer.engagement_dispatcher": {
        "RecoveryStatus":     MagicMock,
        "build_daily_summary": MagicMock(return_value=""),
        "get_recovery_status": MagicMock(return_value=MagicMock()),
        "run_dispatch_check":  MagicMock(),
    },
    "telegram_bots.llm": {
        "generate_async": AsyncMock(return_value=""),
    },
    "telegram_bots.wellness_officer": {},
    "telegram_bots.wellness_officer.intelligence": {
        "get_wellness_snapshot": MagicMock(return_value=MagicMock()),
    },
    "telegram_bots.wellness_officer.brief": {
        "generate_wellness_brief_async": AsyncMock(return_value=""),
    },
}
for _name, _attrs in _tb_modules.items():
    _m = types.ModuleType(_name)
    for k, v in _attrs.items():
        setattr(_m, k, v)
    sys.modules.setdefault(_name, _m)

# ── Load bot module ───────────────────────────────────────────────────────────

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "xo_app",
    os.path.join(os.path.dirname(__file__), "..", "telegram-bots", "xo", "app.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

cmd_mission_submit  = _mod.cmd_mission_submit
_lifecycle_api_call = _mod._lifecycle_api_call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_update(text="/mission_submit 0178"):
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


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMissionSubmit(unittest.IsolatedAsyncioTestCase):

    async def test_valid_submit(self):
        """Happy path: Implemented → Awaiting Captain Approval."""
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0178",
            "title":           "Mission Submission Workflow",
            "previous_status": "Implemented",
            "new_status":      "Awaiting Captain Approval",
            "next_captain_action": "Use /captain_approve 0178",
        })
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("0178"))
        text = update.message.reply_text.call_args[0][0]
        assert "Awaiting Captain Approval" in text or "Awaiting" in text
        assert "0178" in text

    async def test_unknown_mission_404(self):
        """404 from API → friendly not-found reply."""
        resp = _make_resp(404, {"error": "Mission not found"})
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("9999"))
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text.lower() or "9999" in text

    async def test_ineligible_status_409(self):
        """409 from API → current status reported."""
        resp = _make_resp(409, {
            "error": "Mission not eligible for submission",
            "current_status": "Idea",
        })
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("0178"))
        text = update.message.reply_text.call_args[0][0]
        assert "eligible" in text.lower() or "Idea" in text

    async def test_already_awaiting_captain_approval(self):
        """409 idempotency: already Awaiting Captain Approval."""
        resp = _make_resp(409, {
            "error": "Mission already awaiting Captain approval",
            "current_status": "Awaiting Captain Approval",
        })
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("0178"))
        text = update.message.reply_text.call_args[0][0]
        assert "already" in text.lower() or "Approval" in text

    async def test_audit_record_fire_and_forget(self):
        """No direct Supabase calls from Telegram — audit is API-side."""
        sb_client = _sb.create_client.return_value
        sb_client.reset_mock()
        resp = _make_resp(200, {
            "mission_id": "USS-TJR-MSN-0178",
            "title": "Mission Submission Workflow",
            "previous_status": "Implemented",
            "new_status": "Awaiting Captain Approval",
        })
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("0178"))
        # Bot must not directly write mission_state_transitions
        if sb_client.table.called:
            for call in sb_client.table.call_args_list:
                assert "mission_state_transitions" not in str(call)

    async def test_markdown_escaping(self):
        """MarkdownV2: hyphens in mission IDs must be escaped."""
        resp = _make_resp(200, {
            "mission_id":      "USS-TJR-MSN-0178",
            "title":           "Mission Submission Workflow",
            "previous_status": "Implemented",
            "new_status":      "Awaiting Captain Approval",
        })
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__  = AsyncMock(return_value=False)
        cm.post = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=cm):
            update = _make_update()
            await cmd_mission_submit(update, _make_context("0178"))
        text = update.message.reply_text.call_args[0][0]
        # Hyphens in mission IDs are escaped; check for the 4-digit tail
        assert "0178" in text
        # Should NOT contain bare unescaped USS-TJR-MSN string
        assert "USS-TJR-MSN" not in text

    async def test_missing_lcars_url(self):
        """No LCARS_PORTAL_URL → returns error without HTTP call."""
        orig = _mod.LCARS_PORTAL_URL
        _mod.LCARS_PORTAL_URL = ""
        try:
            update = _make_update()
            with patch("httpx.AsyncClient") as mock_client:
                await cmd_mission_submit(update, _make_context("0178"))
                mock_client.assert_not_called()
        finally:
            _mod.LCARS_PORTAL_URL = orig
        text = update.message.reply_text.call_args[0][0]
        assert "LCARS" in text or "not configured" in text.lower() or "unavailable" in text.lower()


if __name__ == "__main__":
    unittest.main()
