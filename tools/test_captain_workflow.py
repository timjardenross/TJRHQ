"""MSN-0175: Captain Approval Workflow tests.

Tests the Telegram bot command handlers and the API response handling logic.
Uses unittest.mock to avoid live Supabase / HTTP calls.

Run: python3 -m pytest tools/test_captain_workflow.py -v
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Bootstrap: make the xo app importable without its runtime deps ────────────

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Stub heavy dependencies before importing app
_telegram = types.ModuleType("telegram")
for _attr in (
    "Update", "InlineKeyboardButton", "InlineKeyboardMarkup",
    "BotCommand", "ReplyKeyboardMarkup", "KeyboardButton",
):
    setattr(_telegram, _attr, MagicMock)
_telegram.constants = MagicMock()
_ext = types.ModuleType("telegram.ext")
for _attr in (
    "Application", "CommandHandler", "MessageHandler",
    "ContextTypes", "CallbackQueryHandler", "ConversationHandler",
):
    setattr(_ext, _attr, MagicMock)
_ext.filters = MagicMock()
sys.modules.setdefault("telegram", _telegram)
sys.modules.setdefault("telegram.ext", _ext)
_supabase_mod = types.ModuleType("supabase")
_supabase_mod.create_client = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
sys.modules.setdefault("supabase", _supabase_mod)
for _mod in (
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.asyncio",
    "apscheduler.triggers",
    "apscheduler.triggers.cron",
):
    _m = types.ModuleType(_mod)
    _m.AsyncIOScheduler = MagicMock  # type: ignore[attr-defined]
    _m.CronTrigger = MagicMock  # type: ignore[attr-defined]
    sys.modules.setdefault(_mod, _m)
sys.modules.setdefault("dotenv", types.ModuleType("dotenv"))
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None  # type: ignore[attr-defined]
# httpx is a lazy import in bot functions — stub it globally so patch() can find it
_httpx = types.ModuleType("httpx")
_httpx.AsyncClient = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("httpx", _httpx)
# Internal telegram_bots sub-packages — stub with exact exported names
_tb_modules: dict[str, dict] = {
    "telegram_bots": {},
    "telegram_bots.recovery_officer": {},
    "telegram_bots.recovery_officer.engagement_dispatcher": {
        "RecoveryStatus": MagicMock,
        "build_daily_summary": MagicMock(return_value=""),
        "get_recovery_status": MagicMock(return_value=MagicMock()),
        "run_dispatch_check": AsyncMock(return_value=""),
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
for _mod, _attrs in _tb_modules.items():
    _m = types.ModuleType(_mod)
    for _attr, _val in _attrs.items():
        setattr(_m, _attr, _val)
    sys.modules.setdefault(_mod, _m)

import importlib.util
import os

# Provide required env vars so the module loads without a real .env
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

spec = importlib.util.spec_from_file_location(
    "xo_app", REPO_ROOT / "telegram-bots" / "xo" / "app.py"
)
assert spec and spec.loader
xo_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xo_app)  # type: ignore[union-attr]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_update(text: str = "") -> MagicMock:
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = text
    return update


def _make_context(args: list[str]) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args
    return ctx


def _mock_resp(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


# ── Tests: /captain_approve ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_captain_approve_no_args_shows_usage():
    update = _make_update()
    ctx = _make_context([])
    await xo_app.cmd_captain_approve(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "captain_approve" in text.lower() or "Captain Approve" in text


@pytest.mark.asyncio
async def test_captain_approve_missing_url_shows_error():
    update = _make_update()
    ctx = _make_context(["0175"])
    with patch.object(xo_app, "LCARS_PORTAL_URL", ""):
        await xo_app.cmd_captain_approve(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "LCARS_PORTAL_URL" in text


@pytest.mark.asyncio
async def test_captain_approve_valid_mission():
    update = _make_update()
    ctx = _make_context(["0175"])
    mock_resp = _mock_resp(200, {
        "mission_id": "USS-TJR-MSN-0175",
        "title": "Captain Approval Workflow",
        "previous_status": "Awaiting Captain Approval",
        "new_status": "Approved",
        "decision": "approve",
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_approve(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Approved" in text
    assert "0175" in text  # hyphens escaped in MarkdownV2: USS\-TJR\-MSN\-0175


@pytest.mark.asyncio
async def test_captain_approve_unknown_mission_returns_404():
    update = _make_update()
    ctx = _make_context(["9999"])
    mock_resp = _mock_resp(404, {"error": "Mission not found", "id": "9999"})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_approve(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "not found" in text.lower()


@pytest.mark.asyncio
async def test_captain_approve_ineligible_status_returns_409():
    update = _make_update()
    ctx = _make_context(["0167"])
    mock_resp = _mock_resp(409, {
        "error": "Mission not eligible for approval",
        "current_status": "Idea",
        "eligible_statuses": ["Awaiting Captain Approval", "Awaiting XO Approval"],
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_approve(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "not eligible" in text.lower() or "Idea" in text


# ── Tests: /captain_reject ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_captain_reject_no_reason_shows_usage():
    update = _make_update()
    ctx = _make_context(["0175"])  # only 1 arg — missing reason
    await xo_app.cmd_captain_reject(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "reason" in text.lower() or "captain_reject" in text.lower()


@pytest.mark.asyncio
async def test_captain_reject_no_args_shows_usage():
    update = _make_update()
    ctx = _make_context([])
    await xo_app.cmd_captain_reject(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "captain_reject" in text.lower() or "Captain Reject" in text


@pytest.mark.asyncio
async def test_captain_reject_valid_mission_with_reason():
    update = _make_update()
    ctx = _make_context(["0175", "Scope", "too", "broad"])
    mock_resp = _mock_resp(200, {
        "mission_id": "USS-TJR-MSN-0175",
        "title": "Captain Approval Workflow",
        "previous_status": "Awaiting Captain Approval",
        "new_status": "Requires Rework",
        "decision": "reject",
        "reason": "Scope too broad",
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_reject(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Requires Rework" in text or "Rejected" in text
    assert "0175" in text  # hyphens escaped in MarkdownV2


@pytest.mark.asyncio
async def test_captain_reject_passes_reason_in_payload():
    update = _make_update()
    ctx = _make_context(["0175", "Scope", "too", "broad"])
    mock_resp = _mock_resp(200, {
        "mission_id": "USS-TJR-MSN-0175",
        "title": "Test",
        "previous_status": "Validated",
        "new_status": "Requires Rework",
        "decision": "reject",
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_reject(update, ctx)

    call_kwargs = mock_client.post.call_args
    payload = call_kwargs[1].get("json") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
    if not payload and hasattr(call_kwargs, "kwargs"):
        payload = call_kwargs.kwargs.get("json", {})
    # Reason must be in the payload sent to the API
    assert payload.get("reason") == "Scope too broad"


# ── Tests: Telegram output Markdown safety ────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_output_uses_markdownv2_parse_mode():
    update = _make_update()
    ctx = _make_context(["0175"])
    mock_resp = _mock_resp(200, {
        "mission_id": "USS-TJR-MSN-0175",
        "title": "Test mission",
        "previous_status": "Awaiting Captain Approval",
        "new_status": "Approved",
        "decision": "approve",
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await xo_app.cmd_captain_approve(update, ctx)

    kwargs = update.message.reply_text.call_args[1]
    assert kwargs.get("parse_mode") == "MarkdownV2"


# ── Tests: Status map completeness ───────────────────────────────────────────

def test_status_map_includes_new_statuses():
    smap = xo_app._MISSION_STATUS_MAP
    assert "approved" in smap
    assert "awaiting" in smap
    assert "rework" in smap
    assert "Approved" in smap["approved"]
    assert "Awaiting Captain Approval" in smap["awaiting"]
    assert "Requires Rework" in smap["rework"]


# ── Tests: No duplicate ID minting in approval flow ─────────────────────────

@pytest.mark.asyncio
async def test_approve_does_not_call_mint_id():
    """Approval must never mint a new mission ID."""
    update = _make_update()
    ctx = _make_context(["0175"])
    mock_resp = _mock_resp(200, {
        "mission_id": "USS-TJR-MSN-0175",
        "title": "Test",
        "previous_status": "Awaiting Captain Approval",
        "new_status": "Approved",
        "decision": "approve",
    })
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(xo_app, "LCARS_PORTAL_URL", "https://lcars.example.com"), \
         patch("httpx.AsyncClient", return_value=mock_client), \
         patch("subprocess.run") as mock_sub:
        await xo_app.cmd_captain_approve(update, ctx)
        # subprocess.run is how mint_id.py would be called — must not be invoked
        mock_sub.assert_not_called()
