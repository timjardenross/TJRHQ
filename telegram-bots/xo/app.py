"""XO Bot — @Starship_endeavour_xO_bot

Executive Officer: Captain's primary Telegram companion.
Recovery-gated mission governance. Conversational via Ollama Cloud.
Inline pulse logging (tap buttons — no portal required).
Recovery dispatch lives here only (CE and Eng-Dept do not run dispatch).

Run:  python -m telegram_bots.xo.app
Env:  telegram-bots/xo/.env
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Australia/Brisbane")

from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────

_BOT_DIR   = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]

load_dotenv(_BOT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = int(os.environ["TELEGRAM_CHAT_ID"])
SUPABASE_URL       = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY", "")
# MSN-0172: LCARS portal base URL for POST /api/missions (no trailing slash)
LCARS_PORTAL_URL   = os.environ.get("LCARS_PORTAL_URL", "").rstrip("/")
LCARS_API_SECRET   = os.environ.get("LCARS_API_SECRET", "")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("xo-bot")

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    RecoveryStatus,
    build_daily_summary,
    get_recovery_status,
    run_dispatch_check,
)
from telegram_bots.llm import generate_async
from telegram_bots.wellness_officer.intelligence import get_wellness_snapshot
from telegram_bots.wellness_officer.brief import generate_wellness_brief_async

# ── Telegram ──────────────────────────────────────────────────────────────────

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase = None

def _get_supabase():
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL:
            log.warning("SUPABASE_URL not set — Supabase disabled")
        elif not SUPABASE_KEY:
            log.warning("SUPABASE_KEY not set — Supabase disabled")
        else:
            try:
                from supabase import create_client
                _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                log.info("Supabase client initialised")
            except Exception as exc:
                log.warning("Supabase client failed: %s", exc)
    return _supabase


# ── MarkdownV2 escaping ───────────────────────────────────────────────────────

def _bot_headers() -> dict:
    if LCARS_API_SECRET:
        return {"X-Bot-Secret": LCARS_API_SECRET}
    return {}


def _escape(text: str) -> str:
    result = []
    for ch in text:
        if ch in r"\`[]()~>#+=|{}.!-" and ch not in ("*", "_"):
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def _escape_strict(text: str) -> str:
    """Escape ALL MarkdownV2 specials including _ and * (use for content embedded inside _…_ or *…* spans)."""
    result = []
    for ch in str(text):
        if ch in r"\_*`[]()~>#+=|{}.!-":
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def _bar(pct: int) -> str:
    return "█" * int(pct / 10) + "░" * (10 - int(pct / 10))


# ── XO system prompt ──────────────────────────────────────────────────────────

def _get_open_missions(db) -> str:
    """Fetch open missions from Supabase, formatted compactly for the system prompt."""
    if not db:
        return ""
    try:
        res = db.table("missions").select(
            "mission_id,title,status,priority"
        ).not_.in_(
            "status", ["Closed", "completed", "cancelled", "deferred", "Archived"]
        ).order("priority").limit(20).execute()
        rows = res.data or []
        if not rows:
            return ""
        lines = []
        for r in rows:
            pri  = f"[{r['priority']}] " if r.get("priority") else ""
            mid  = r.get("mission_id", "?")
            st   = r.get("status", "?")
            title = (r.get("title") or "")[:70]
            lines.append(f"{pri}{mid} ({st}): {title}")
        return "\n".join(lines)
    except Exception as exc:
        log.warning("[missions] fetch failed: %s", exc)
        return ""


def _xo_system_prompt(status: RecoveryStatus, snap=None, missions: str = "") -> str:
    signals = ", ".join(filter(None, [
        f"energy={status.latest_energy}"              if status.latest_energy          else None,
        f"ns={status.latest_nervous_system}"          if status.latest_nervous_system  else None,
        f"body={status.latest_body_signals}"          if status.latest_body_signals    else None,
    ])) or "no signals yet today"

    wellness_ctx = ""
    if snap is not None:
        parts = []
        if snap.sleep_hours is not None:
            cpap = " (CPAP ✓)" if snap.cpap_compliant else (" (CPAP ✗)" if snap.cpap_compliant is False else "")
            parts.append(f"sleep={snap.sleep_hours}h{cpap}")
        if snap.nervous_system_state:
            parts.append(f"nervous_system={snap.nervous_system_state}")
        if snap.has_insights and snap.risk_flags:
            parts.append(f"risk_flags={'; '.join(snap.risk_flags[:2])}")
        if parts:
            wellness_ctx = f"\nWellness context: {', '.join(parts)}"

    missions_ctx = f"\n\nOpen missions (current manifest):\n{missions}" if missions else \
                   "\n\nOpen missions: none on record."

    return (
        "You are the Executive Officer (XO) of USS TJR, a personal command vessel.\n"
        "You serve Captain TJR (Tim Jardenross), who operates on ROS-001 v1.1 — "
        "currently in Stage 1 Stabilisation, moving toward Stage 2 Capacity Restoration.\n\n"
        "RECOVERY FIRST. Mission work is gated by the Captain's capacity. Never push beyond it.\n\n"
        f"Today's recovery state:\n"
        f"- Confidence: {status.recovery_confidence}% [{_bar(status.recovery_confidence)}]\n"
        f"- Pulses: {status.pulses_completed}/4 complete\n"
        f"- Signals: {signals}\n"
        f"- Escalation: L{status.escalation_level} (0=clear 1=low 2=concern 3=critical)"
        f"{wellness_ctx}"
        f"{missions_ctx}\n\n"
        "Your role:\n"
        "- Primary daily companion. The Captain talks to you first.\n"
        "- Help make decisions through a capacity lens — can we do this given recovery state?\n"
        "- Surface mission concerns and recommend deferrals when confidence is low.\n"
        "- Receive direction: 'defer that mission', 'what's my capacity today', 'anything blocking?'\n"
        "- Speak with authority and care. Concise, direct, no fluff.\n\n"
        "Keep responses SHORT. This is Telegram on mobile — 2-4 sentences max unless "
        "detail is genuinely needed. Respond as XO, not as an AI. No disclaimers."
    )


# ── Inline pulse flow ─────────────────────────────────────────────────────────
# Callback data format: pl|pt=<type>|e=<energy>|m=<nervous_system>|s=<body_signals>
# Steps: capacity → nervous system → body signals → write to DB

_PULSE_LABELS = {
    "morning":    "🌅 Morning Readiness",
    "midday":     "🌤 Midday Status",
    "end_of_day": "🌇 End of Workday",
    "evening":    "🌃 Evening Recovery",
}

def _current_pulse_type() -> str:
    h = datetime.now(_TZ).hour
    if 5  <= h < 12: return "morning"
    if 12 <= h < 16: return "midday"
    if 16 <= h < 20: return "end_of_day"
    return "evening"

def _parse_cb(data: str) -> dict:
    result = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result

def _kb_energy(pt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ High",     callback_data=f"pl|pt={pt}|e=high"),
        InlineKeyboardButton("〜 Moderate", callback_data=f"pl|pt={pt}|e=moderate"),
        InlineKeyboardButton("🔋 Low",      callback_data=f"pl|pt={pt}|e=low"),
    ]])

def _kb_mood(pt: str, e: str) -> InlineKeyboardMarkup:
    """Step 2: Nervous system state (PNE/PRT core signal)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Calm",        callback_data=f"pl|pt={pt}|e={e}|m=calm"),
        InlineKeyboardButton("🟡 Activated",   callback_data=f"pl|pt={pt}|e={e}|m=activated"),
        InlineKeyboardButton("🔴 Dysregulated", callback_data=f"pl|pt={pt}|e={e}|m=dysregulated"),
    ]])

def _kb_stress(pt: str, e: str, m: str) -> InlineKeyboardMarkup:
    """Step 3: Body signals (PNE framing — context not score)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🤫 Quiet",      callback_data=f"pl|pt={pt}|e={e}|m={m}|s=quiet"),
        InlineKeyboardButton("💬 Present",    callback_data=f"pl|pt={pt}|e={e}|m={m}|s=present"),
        InlineKeyboardButton("📢 Significant", callback_data=f"pl|pt={pt}|e={e}|m={m}|s=significant"),
    ]])


async def _write_pulse(pt: str, energy: str, nervous_system: str, body_signals: str) -> tuple[bool, RecoveryStatus, str | None]:
    db = _get_supabase()
    saved = False
    err_msg: str | None = None
    if not db:
        err_msg = "Supabase unavailable (check SUPABASE_KEY)"
        log.error("[pulse] %s", err_msg)
    else:
        try:
            res = db.table("recovery_pulses").upsert(
                {
                    "log_date":       datetime.now(_TZ).date().isoformat(),
                    "pulse_type":     pt,
                    "energy":         energy,
                    "nervous_system": nervous_system,
                    "body_signals":   body_signals,
                    "source":         "telegram",
                },
                on_conflict="log_date,pulse_type",
            ).execute()
            saved = True
            log.info("Pulse written: %s energy=%s ns=%s body=%s rows=%s",
                     pt, energy, nervous_system, body_signals, len(res.data) if res.data else 0)
        except Exception as exc:
            err_msg = str(exc)
            log.error("pulse upsert failed: %s | energy=%s ns=%s body=%s", exc, energy, nervous_system, body_signals)
    status = get_recovery_status(db)
    return saved, status, err_msg


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*XO online* — @Starship\\_endeavour\\_xO\\_bot\n\n"
        f"Chat ID: `{update.effective_chat.id}`\n\n"
        "*Recovery*\n"
        "/recovery\\_status · /recovery\\_pulse\n\n"
        "*Missions*\n"
        "/mission\\_list \\[active|idea|blocked|all\\]\n"
        "/mission\\_status \\<id\\>\n"
        "/mission\\_create \\<title\\>\n\n"
        "*Logging*\n"
        "/log\\_activity · /log\\_weight\n\n"
        "*Ops*\n"
        "/dispatch · /db\\_status\n\n"
        "_Proactive Daily Operating Picture arrives at 07:00 AEST\\._\n"
        "_Or just talk to me\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*XO — Commands*\n\n"
        "*Recovery*\n"
        "/recovery\\_status — today's confidence bar \\+ pulse ledger \\(AM/Mid/EOD/PM\\)\n"
        "/recovery\\_pulse — log a pulse inline \\(energy → mood → stress, tap buttons\\)\n\n"
        "*Missions*\n"
        "/mission\\_list \\[active|idea|blocked|completed|all\\] — list missions by status\n"
        "/mission\\_status \\<id\\> — mission detail \\(e\\.g\\. `/mission_status 0167` or full ID\\)\n"
        "/mission\\_create \\<title\\> — create a new Idea mission \\(e\\.g\\. `/mission_create Build ops dashboard`\\)\n\n"
        "*Captain Governance*\n"
        "/captain\\_approve \\<id\\> — approve a mission \\(e\\.g\\. `/captain_approve 0175`\\)\n"
        "/captain\\_reject \\<id\\> \\<reason\\> — reject with reason \\(e\\.g\\. `/captain_reject 0175 Scope too broad`\\)\n"
        "/mission\\_submit \\<id\\> — submit for Captain approval \\(Tested/Validated/Implemented\\)\n"
        "/handoff\\_engineering \\<id\\> — hand off to Engineering \\(Idea/Designed/Approved/Requires Rework\\)\n"
        "/operating\\_picture — Captain's live operating picture\n\n"
        "*Logging*\n"
        "/log\\_activity — log activity \\(e\\.g\\. `/log_activity walk 30 light`\\)\n"
        "/log\\_weight — log weight \\(e\\.g\\. `/log_weight 82\\.5`\\)\n\n"
        "*Ops*\n"
        "/dispatch — manual dispatch check\n"
        "/brief — OR intelligence brief on demand\n"
        "/db\\_status — Supabase connectivity test\n"
        "/restart\\_bots \\[slack\\|telegram\\|all\\] — restart starfleet services\n\n"
        "*Proactive pushes \\(auto, no command needed\\)*\n"
        "07:00 — Daily Operating Picture \\(capacity · decision · missions · delivery · resilience\\)\n"
        "21:00 — Evening Recovery Reflection\n"
        "Mon 08:00 — Weekly Human Systems Review\n"
        "Mon 08:30 — Weekly Thought Leadership Brief \\(when opportunities exist\\)\n"
        "15:00 — Capacity Degradation Alert \\(only when threshold crossed\\)\n\n"
        "_Or just talk to me — I understand plain English\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_recovery_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    pt = status.next_suggested_pulse or _current_pulse_type()
    label = _PULSE_LABELS.get(pt, pt)
    conf = status.recovery_confidence
    await update.message.reply_text(
        f"📡 *{_escape(label)}*\n\n"
        f"Confidence: `{_escape(_bar(conf))}` {conf}%\n\n"
        "Capacity right now?",
        parse_mode="MarkdownV2",
        reply_markup=_kb_energy(pt),
    )


async def cmd_db_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test Supabase connectivity and report result."""
    db = _get_supabase()
    if not db:
        await update.message.reply_text(
            "⚠️ *Supabase: not connected*\n\n"
            "SUPABASE\\_URL or SUPABASE\\_KEY missing or client init failed\\.\n"
            "Check bot screen session logs\\.",
            parse_mode="MarkdownV2",
        )
        return
    try:
        res = db.table("recovery_confidence_today").select("recovery_confidence,pulses_completed").execute()
        row = res.data[0] if res.data else {}
        conf   = row.get("recovery_confidence", 0)
        pulses = row.get("pulses_completed", 0)
        await update.message.reply_text(
            f"✅ *Supabase: connected*\n\n"
            f"recovery\\_confidence\\_today: {conf}% · {pulses}/4 pulses",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(
            f"⚠️ *Supabase: connected but query failed*\n\n`{_escape(str(exc))}`",
            parse_mode="MarkdownV2",
        )


async def cmd_log_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick activity log: /log_activity walk 30 light"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Log Activity*\n\nUsage: `/log_activity <type> [minutes] [intensity]`\n\n"
            "Types: walk · swim · physio · stretch · strength · cycle · yoga · other\n"
            "Intensity: light · moderate · vigorous\n\n"
            "_Example: `/log_activity walk 30 light`_",
            parse_mode="MarkdownV2",
        )
        return

    valid_types = {"walk","swim","physio","stretch","strength","cycle","yoga","other"}
    activity_type = args[0].lower() if args[0].lower() in valid_types else "other"
    duration = None
    intensity = None
    for arg in args[1:]:
        if arg.isdigit():
            duration = int(arg)
        elif arg.lower() in ("light","moderate","vigorous"):
            intensity = arg.lower()

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable — check SUPABASE\\_KEY in \\`\\.env\\`", parse_mode="MarkdownV2")
        return

    payload = {
        "log_date":      datetime.now(_TZ).date().isoformat(),
        "activity_type": activity_type,
        "source":        "telegram",
        "completed":     True,
    }
    if duration:  payload["duration_minutes"] = duration
    if intensity: payload["intensity"]        = intensity

    try:
        db.table("activity_logs").insert(payload).execute()
        parts = [activity_type]
        if duration:  parts.append(f"{duration} min")
        if intensity: parts.append(intensity)
        await update.message.reply_text(
            f"✅ *Activity logged:* {_escape(' · '.join(parts))}",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


async def cmd_log_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick weight log: /log_weight 82.5"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Log Weight*\n\nUsage: `/log_weight <kg>`\n\n_Example: `/log_weight 82\\.5`_",
            parse_mode="MarkdownV2",
        )
        return

    try:
        kg = float(args[0])
        assert 30 < kg < 500
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ Enter a valid weight in kg \\(e\\.g\\. `/log_weight 82\\.5`\\)", parse_mode="MarkdownV2")
        return

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable — check SUPABASE\\_KEY in \\`\\.env\\`", parse_mode="MarkdownV2")
        return

    try:
        db.table("weight_logs").upsert(
            {"log_date": datetime.now(_TZ).date().isoformat(), "weight_kg": kg, "source": "telegram"},
            on_conflict="log_date",
        ).execute()
        await update.message.reply_text(
            f"✅ *Weight logged:* {_escape(str(kg))} kg",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running dispatch check…")
    result = run_dispatch_check(
        _BotAdapter(context.bot),
        TELEGRAM_CHAT_ID,
        supabase_client=_get_supabase(),
    )
    conf   = result.get("confidence", 0)
    action = result.get("action", "none")
    sent   = result.get("message_sent", False)
    await update.message.reply_text(
        f"Dispatch: {_escape(action)} \\| conf={conf}% \\| sent={'yes' if sent else 'no'}",
        parse_mode="MarkdownV2",
    )


# ── Bot restart ──────────────────────────────────────────────────────────────

_RESTARTABLE_SERVICES = {
    "slack":    ["starfleet-slack-bot.service"],
    "telegram": ["tg-engineer.service", "tg-engineering-dept.service"],
    "all":      ["starfleet-slack-bot.service", "tg-engineer.service", "tg-engineering-dept.service"],
}


async def cmd_restart_bots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart_bots [slack|telegram|all]  — restart starfleet services. XO restarts itself last."""
    if update.effective_chat.id != TELEGRAM_CHAT_ID:
        return

    arg = (context.args[0].lower() if context.args else "all")
    services = _RESTARTABLE_SERVICES.get(arg, _RESTARTABLE_SERVICES["all"])
    names = ", ".join(s.replace(".service", "") for s in services)

    await update.message.reply_text(
        f"🔄 Restarting: {_escape(names)}\\.\\.\\.",
        parse_mode="MarkdownV2",
    )

    lines = []
    for svc in services:
        try:
            r = subprocess.run(
                ["systemctl", "restart", svc],
                capture_output=True, text=True, timeout=15,
            )
            icon = "✅" if r.returncode == 0 else f"⚠️ rc={r.returncode}"
            lines.append(f"{icon} {svc.replace('.service', '')}")
        except Exception as exc:
            lines.append(f"❌ {svc.replace('.service', '')}: {_escape(str(exc))}")

    restart_xo = arg in ("telegram", "all")
    suffix = "\n\n_XO rebooting in 3s\\.\\.\\._" if restart_xo else ""

    await update.message.reply_text(
        f"*Restart results*\n\n{_escape(chr(10).join(lines))}{suffix}",
        parse_mode="MarkdownV2",
    )

    if restart_xo:
        await asyncio.sleep(3)
        subprocess.Popen(["systemctl", "restart", "tg-xo.service"])


# ── OR Intelligence brief ─────────────────────────────────────────────────────

async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an OR intelligence brief on demand and write it to Supabase."""
    await update.message.reply_text(
        "⚙️ Generating OR intelligence brief\\.\\.\\. this may take 30\\-60 seconds\\.",
        parse_mode="MarkdownV2",
    )
    try:
        from intelligence.scheduler import run_once
        import asyncio
        brief = await asyncio.get_event_loop().run_in_executor(None, run_once)
        risk_icon = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(brief.overall_risk, "⚪")
        lines = [
            f"*OR Intelligence Brief — {_escape(brief.brief_id[:8])}*\n",
            f"{risk_icon} Risk: *{_escape(brief.overall_risk)}*",
        ]
        if brief.bottom_line:
            lines.append(f"\n*Bottom Line*\n{_escape(brief.bottom_line)}")
        if brief.executive_snapshot:
            lines.append(f"\n*Snapshot*\n{_escape(brief.executive_snapshot)}")
        lines.append(f"\n_Events: {brief.events_included} included · {brief.events_suppressed} suppressed_")
        lines.append("_LCARS Astrometrics updated\\._")
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
        log.info("[brief] generated brief_id=%s risk=%s", brief.brief_id, brief.overall_risk)
    except ImportError:
        await update.message.reply_text(
            "⚠️ Intelligence module not available in this environment\\.",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        log.error("[brief] generation failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Brief generation failed: `{_escape(str(exc))}`",
            parse_mode="MarkdownV2",
        )


# ── Mission read commands (MSN-0167) ─────────────────────────────────────────

# Valid Supabase status values (constraint: Idea|Designed|Implemented|Tested|
# Awaiting Number One Review|Validated|Awaiting XO Approval|Closed|Blocked|Archived)
_MISSION_STATUS_MAP = {
    "active":      ["Implemented", "Tested", "Awaiting Number One Review", "Validated", "Awaiting XO Approval"],
    "idea":        ["Idea"],
    "blocked":     ["Blocked"],
    "designed":    ["Designed"],
    "implemented": ["Implemented"],
    "tested":      ["Tested"],
    "validated":   ["Validated"],
    "approved":    ["Approved"],
    "awaiting":    ["Awaiting Captain Approval", "Awaiting XO Approval"],
    "rework":      ["Requires Rework"],
    "closed":      ["Closed", "Archived"],
    "all":         [],  # sentinel — handled by show_all path
}
_CLOSED_STATUSES = ["Closed", "Archived"]


async def cmd_mission_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Read-only mission list. Usage: /mission_list [active|idea|blocked|completed|all]"""
    args = context.args or []
    filter_key = (args[0].lower() if args else "active")
    status_values = _MISSION_STATUS_MAP.get(filter_key)
    show_all = (filter_key == "all")

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    try:
        query = db.table("missions").select("mission_id,title,status,priority")
        if status_values:
            query = query.in_("status", status_values)
        elif not show_all:
            query = query.not_.in_("status", _CLOSED_STATUSES)
        else:
            # all — exclude only terminal
            query = query.not_.in_("status", ["cancelled", "deferred"])

        res = query.order("priority", desc=False).limit(10).execute()
        rows = res.data or []

        if not rows:
            label = _escape_strict(filter_key.title())
            await update.message.reply_text(
                f"No {label} missions found\\.", parse_mode="MarkdownV2"
            )
            return

        label = _escape_strict(filter_key.title())
        count = len(rows)
        header = f"*{label} Missions* \\({count}\\)\n"
        lines = [header]
        for r in rows:
            mid   = r.get("mission_id", "?")
            st    = _escape_strict(r.get("status") or "?")
            title = _escape_strict((r.get("title") or "Untitled")[:55])
            lines.append(f"`{mid}` — {st}\n{title}")

        await update.message.reply_text(
            "\n\n".join(lines), parse_mode="MarkdownV2"
        )

    except Exception as exc:
        log.error("[mission-list] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Mission list unavailable: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


async def cmd_mission_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Look up a single mission. Usage: /mission_status <id_or_fragment>"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Mission Status*\n\n"
            "Usage: `/mission_status <id>`\n\n"
            "_Examples: `/mission_status 0165` or `/mission_status USS\\-TJR\\-MSN\\-0165`_",
            parse_mode="MarkdownV2",
        )
        return

    query_str = " ".join(args).strip()
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    try:
        res = (
            db.table("missions")
            .select("mission_id,title,status,priority,created_by,created_at,description")
            .ilike("mission_id", f"%{query_str}%")
            .limit(3)
            .execute()
        )
        rows = res.data or []

        if not rows:
            await update.message.reply_text(
                f"No mission found matching `{_escape_strict(query_str[:40])}`\\.",
                parse_mode="MarkdownV2",
            )
            return

        row        = rows[0]
        mid        = row.get("mission_id", "?")
        title      = _escape_strict((row.get("title") or "Untitled")[:80])
        st         = _escape_strict(row.get("status") or "?")
        pri        = _escape_strict(str(row.get("priority") or "—"))
        created_by = _escape_strict(str(row.get("created_by") or "—"))
        dt         = _escape_strict((row.get("created_at") or "")[:10])
        desc       = (row.get("description") or "")[:200].strip()

        parts = [
            f"*Mission:* `{mid}`",
            f"*{title}*",
            f"",
            f"*Status:* {st}",
            f"*Priority:* {pri}",
            f"*Created by:* {created_by}",
            f"*Created:* {dt}",
        ]
        if desc:
            parts.append(f"\n_{_escape_strict(desc)}_")
        if len(rows) > 1:
            others = ", ".join(f"`{r.get('mission_id', '')}`" for r in rows[1:])
            parts.append(f"\n_Also matched: {others}_")

        await update.message.reply_text(
            "\n".join(parts), parse_mode="MarkdownV2"
        )

    except Exception as exc:
        log.error("[mission-status] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Lookup failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


# ── Mission create command (MSN-0172) ────────────────────────────────────────

async def cmd_mission_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new mission via the Mission Control API. Usage: /mission_create <title>"""
    args = context.args or []
    title = " ".join(args).strip()
    if not title:
        await update.message.reply_text(
            "*Mission Create*\n\n"
            "Usage: `/mission_create <title>`\n\n"
            "_Example: `/mission_create Build ops dashboard`_",
            parse_mode="MarkdownV2",
        )
        return

    if not LCARS_PORTAL_URL:
        await update.message.reply_text(
            "⚠️ `LCARS_PORTAL_URL` not configured — mission creation unavailable\\.",
            parse_mode="MarkdownV2",
        )
        return

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_bot_headers()) as client:
            resp = await client.post(
                f"{LCARS_PORTAL_URL}/api/missions",
                json={"title": title, "status": "Idea"},
            )
        if resp.status_code == 201:
            mission = resp.json().get("mission", {})
            mid = mission.get("mission_id", "?")
            st  = _escape_strict(mission.get("status", "Idea"))
            t   = _escape_strict((mission.get("title") or title)[:80])
            await update.message.reply_text(
                f"✅ *Mission created*\n\n"
                f"`{mid}` — {st}\n{t}",
                parse_mode="MarkdownV2",
            )
        else:
            detail = _escape_strict(str(resp.text)[:120])
            await update.message.reply_text(
                f"⚠️ API returned `{resp.status_code}`:\n`{detail}`",
                parse_mode="MarkdownV2",
            )
    except Exception as exc:
        log.error("[mission-create] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Mission creation failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


# ── Captain governance commands (MSN-0175) ───────────────────────────────────

async def _captain_decision_via_api(
    update,
    mission_ref: str,
    decision: str,
    reason: str = "",
) -> None:
    """Shared logic for /captain_approve and /captain_reject via LCARS API."""
    if not LCARS_PORTAL_URL:
        await update.message.reply_text(
            "⚠️ `LCARS_PORTAL_URL` not configured — captain governance unavailable\\.",
            parse_mode="MarkdownV2",
        )
        return

    endpoint = "approve" if decision == "approve" else "reject"
    payload: dict = {"source": "Telegram", "owner": "Captain"}
    if reason:
        payload["reason"] = reason

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_bot_headers()) as client:
            resp = await client.post(
                f"{LCARS_PORTAL_URL}/api/missions/{mission_ref}/{endpoint}",
                json=payload,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            mid   = _escape_strict(data.get("mission_id", mission_ref))
            title = _escape_strict((data.get("title") or "")[:60])
            prev  = _escape_strict(data.get("previous_status", ""))
            new_s = _escape_strict(data.get("new_status", ""))
            verb  = "✅ *Mission Approved*" if decision == "approve" else "⛔ *Mission Rejected — Requires Rework*"
            await update.message.reply_text(
                f"{verb}\n\n`{mid}`\n{title}\n\n_{prev}_ → *{new_s}*",
                parse_mode="MarkdownV2",
            )
        elif resp.status_code == 404:
            await update.message.reply_text(
                f"⚠️ Mission `{_escape_strict(mission_ref)}` not found\\.",
                parse_mode="MarkdownV2",
            )
        elif resp.status_code == 409:
            data    = resp.json()
            current = _escape_strict(data.get("current_status", "unknown"))
            await update.message.reply_text(
                f"⚠️ Mission `{_escape_strict(mission_ref)}` is `{current}` — not eligible for {decision}\\.",
                parse_mode="MarkdownV2",
            )
        elif resp.status_code == 400:
            data = resp.json()
            err  = _escape_strict(str(data.get("error", resp.text))[:100])
            await update.message.reply_text(
                f"⚠️ Bad request: `{err}`",
                parse_mode="MarkdownV2",
            )
        else:
            detail = _escape_strict(str(resp.text)[:120])
            await update.message.reply_text(
                f"⚠️ API returned `{resp.status_code}`:\n`{detail}`",
                parse_mode="MarkdownV2",
            )
    except Exception as exc:
        log.error("[captain-%s] failed: %s", decision, exc)
        await update.message.reply_text(
            f"⚠️ Captain {decision} failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


async def cmd_captain_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a mission. Usage: /captain_approve <mission_id>"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Captain Approve*\n\n"
            "Usage: `/captain_approve <mission_id>`\n\n"
            "_Example: `/captain_approve 0175`_\n\n"
            "Eligible statuses: `Awaiting Captain Approval`, `Awaiting XO Approval`, `Validated`, `Tested`",
            parse_mode="MarkdownV2",
        )
        return
    await _captain_decision_via_api(update, args[0].strip(), "approve")


async def cmd_captain_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a mission and require rework. Usage: /captain_reject <mission_id> <reason>"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "*Captain Reject*\n\n"
            "Usage: `/captain_reject <mission_id> <reason>`\n\n"
            "_A reason is required\\._\n\n"
            "_Example: `/captain_reject 0175 Scope too broad — split into two missions`_",
            parse_mode="MarkdownV2",
        )
        return
    await _captain_decision_via_api(
        update,
        args[0].strip(),
        "reject",
        " ".join(args[1:]).strip(),
    )


# ── Mission lifecycle commands (MSN-0178 / MSN-0179 / MSN-0180) ──────────────

async def _lifecycle_api_call(
    update,
    mission_ref: str,
    endpoint: str,
    payload: dict,
    action_label: str,
) -> None:
    """Generic helper: POST to LCARS API lifecycle endpoint and reply."""
    if not LCARS_PORTAL_URL:
        await update.message.reply_text(
            "⚠️ `LCARS_PORTAL_URL` not configured\\.",
            parse_mode="MarkdownV2",
        )
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_bot_headers()) as client:
            resp = await client.post(
                f"{LCARS_PORTAL_URL}/api/missions/{mission_ref}/{endpoint}",
                json=payload,
            )
        if resp.status_code in (200, 201):
            data  = resp.json()
            mid   = _escape_strict(data.get("mission_id", mission_ref))
            title = _escape_strict((data.get("title") or "")[:60])
            prev  = _escape_strict(data.get("previous_status", ""))
            new_s = _escape_strict(data.get("new_status", ""))
            note  = _escape_strict(
                data.get("next_captain_action") or
                data.get("next_engineering_action") or ""
            )
            msg = f"✅ *{_escape_strict(action_label)}*\n\n`{mid}`\n{title}\n\n_{prev}_ → *{new_s}*"
            if note:
                msg += f"\n\n_{note}_"
            await update.message.reply_text(msg, parse_mode="MarkdownV2")
        elif resp.status_code == 404:
            await update.message.reply_text(
                f"⚠️ Mission `{_escape_strict(mission_ref)}` not found\\.",
                parse_mode="MarkdownV2",
            )
        elif resp.status_code == 409:
            data    = resp.json()
            current = _escape_strict(data.get("current_status", "unknown"))
            err     = _escape_strict(data.get("error", "Not eligible"))
            await update.message.reply_text(
                f"⚠️ {err}: `{current}`\\.",
                parse_mode="MarkdownV2",
            )
        else:
            detail = _escape_strict(str(resp.text)[:120])
            await update.message.reply_text(
                f"⚠️ API returned `{resp.status_code}`:\n`{detail}`",
                parse_mode="MarkdownV2",
            )
    except Exception as exc:
        log.error("[%s] failed: %s", endpoint, exc)
        await update.message.reply_text(
            f"⚠️ {_escape_strict(action_label)} failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


async def cmd_mission_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Submit mission for Captain approval. Usage: /mission_submit <mission_id>"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Mission Submit*\n\n"
            "Usage: `/mission_submit <mission_id>`\n\n"
            "_Example: `/mission_submit 0171`_\n\n"
            "Eligible statuses: `Tested`, `Validated`, `Implemented`",
            parse_mode="MarkdownV2",
        )
        return
    await _lifecycle_api_call(
        update, args[0].strip(), "submit",
        {"source": "Telegram", "submitter": "Engineering"},
        "Mission Submitted for Captain Approval",
    )


async def cmd_handoff_engineering(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hand off mission to Engineering. Usage: /handoff_engineering <mission_id>"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Handoff to Engineering*\n\n"
            "Usage: `/handoff_engineering <mission_id>`\n\n"
            "_Example: `/handoff_engineering 0178`_\n\n"
            "Eligible statuses: `Idea`, `Designed`, `Approved`, `Requires Rework`",
            parse_mode="MarkdownV2",
        )
        return
    await _lifecycle_api_call(
        update, args[0].strip(), "handoff",
        {"source": "Telegram", "officer": "Captain"},
        "Mission Handed Off to Engineering",
    )


async def cmd_operating_picture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Captain's Operating Picture. Usage: /operating_picture"""
    if not LCARS_PORTAL_URL:
        await update.message.reply_text(
            "⚠️ `LCARS_PORTAL_URL` not configured — operating picture unavailable\\.",
            parse_mode="MarkdownV2",
        )
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=_bot_headers()) as client:
            resp = await client.get(f"{LCARS_PORTAL_URL}/api/operating-picture")
        if resp.status_code != 200:
            await update.message.reply_text(
                f"⚠️ Operating picture unavailable \\(`{resp.status_code}`\\)\\.",
                parse_mode="MarkdownV2",
            )
            return
        data      = resp.json()
        missions  = data.get("missions", {})
        decisions = data.get("decisions", {})
        actions   = data.get("next_actions", [])
        recent    = data.get("recent_transitions", [])
        counters  = data.get("counters") or {}

        lines = [
            "*Captain's Operating Picture*\n",
            f"Active: `{missions.get('active_count', 0)}`",
            f"Awaiting approval: `{missions.get('awaiting_approval_count', 0)}`",
            f"Blocked: `{missions.get('blocked_count', 0)}`",
            f"Approved: `{missions.get('approved_count', 0)}`",
            f"Open decisions: `{decisions.get('open_count', 0)}`",
        ]

        if counters.get("next_MSN"):
            lines.append(f"Next ID: `{_escape_strict(counters['next_MSN'])}`")

        if actions:
            lines.append("\n*Next Actions:*")
            for i, action in enumerate(actions[:5], 1):
                lines.append(f"{i}\\. {_escape_strict(str(action))}")

        if recent:
            lines.append("\n*Recent Decisions:*")
            for t in recent[:3]:
                mid  = _escape_strict(str(t.get("mission_id", ""))[-4:])
                to_s = _escape_strict(str(t.get("to_state", "")))
                lines.append(f"• `{mid}` → {to_s}")

        # Degraded data warning
        if "error" in data:
            lines.append(f"\n⚠️ _Partial data: {_escape_strict(str(data['error'])[:60])}_")

        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")

    except Exception as exc:
        log.error("[operating-picture] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Operating picture failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


# ── Free-text conversation ────────────────────────────────────────────────────

async def cmd_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    db       = _get_supabase()
    status   = get_recovery_status(db)
    snap     = get_wellness_snapshot(db)
    missions = _get_open_missions(db)
    await update.message.chat.send_action("typing")
    reply = await generate_async(text, _xo_system_prompt(status, snap, missions))
    if reply:
        await update.message.reply_text(_escape(reply), parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(
            "XO here\\. LLM unreachable — use /recovery\\_status or /dispatch for now\\.",
            parse_mode="MarkdownV2",
        )


# ── Inline pulse callbacks ────────────────────────────────────────────────────

async def handle_pulse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("pl|"):
        return

    f = _parse_cb(data)
    pt = f.get("pt", _current_pulse_type())
    e  = f.get("e")
    m  = f.get("m")
    s  = f.get("s")
    label = _PULSE_LABELS.get(pt, pt)

    if e and m and s:
        saved, status, err_msg = await _write_pulse(pt, e, m, s)
        icon = "✅" if saved else "⚠️"
        conf = status.recovery_confidence
        done = " ".join([
            "✅" if status.morning_done    else "❌",
            "✅" if status.midday_done     else "❌",
            "✅" if status.end_of_day_done else "❌",
            "✅" if status.evening_done    else "❌",
        ])
        e_cap = _escape(e.capitalize())
        m_cap = _escape(m.capitalize())
        s_cap = _escape(s.capitalize())
        error_line = f"\n\n_Error: {_escape_strict(err_msg)}_" if err_msg else ""
        await query.edit_message_text(
            f"{icon} *{_escape(label)} logged*\n\n"
            f"Capacity: {e_cap} · NS: {m_cap} · Body: {s_cap}\n\n"
            f"Confidence: `{_escape(_bar(conf))}` {conf}%\n"
            f"Pulses: {_escape(done)}  AM · Mid · EOD · PM"
            f"{error_line}",
            parse_mode="MarkdownV2",
        )
        return

    if e and m:
        await query.edit_message_text(
            f"📡 *{_escape(label)}*\n\n"
            f"Capacity: {_escape(e.capitalize())} · NS: {_escape(m.capitalize())}\n\n"
            "Body signals right now?",
            parse_mode="MarkdownV2",
            reply_markup=_kb_stress(pt, e, m),
        )
        return

    if e:
        await query.edit_message_text(
            f"📡 *{_escape(label)}*\n\n"
            f"Capacity: {_escape(e.capitalize())}\n\n"
            "Nervous system state?",
            parse_mode="MarkdownV2",
            reply_markup=_kb_mood(pt, e),
        )
        return


# ── Voice-to-Capture ──────────────────────────────────────────────────────────

async def cmd_voice_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages — transcribe locally and write to capture inbox."""
    if update.effective_chat.id != TELEGRAM_CHAT_ID:
        return

    msg = update.message
    if not msg or not msg.voice:
        return

    db = _get_supabase()
    if not db:
        await msg.reply_text("⚠️ Supabase unavailable — voice capture requires database connectivity.")
        return

    # Import here to avoid circular deps at module load
    from telegram_bots.xo import voice_capture as vc

    # Ensure temp dir exists
    vc.VOICE_TMP_DIR.mkdir(parents=True, exist_ok=True)

    # Download voice note
    audio_path = str(vc.VOICE_TMP_DIR / f"tg_{msg.message_id}.oga")
    thinking = await msg.reply_text("🎙 Transcribing…")
    try:
        tg_file = await msg.voice.get_file()
        await tg_file.download_to_drive(audio_path)
    except Exception as exc:
        log.error("[voice] download failed: %s", exc)
        await thinking.edit_text(f"⚠️ Could not download voice file: {exc}")
        return

    # Run full pipeline
    try:
        result = vc.handle_capture_from_voice(
            db, audio_path,
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
        )
    except Exception as exc:
        log.error("[voice] pipeline error: %s", exc)
        await thinking.edit_text(f"⚠️ Capture failed: {exc}")
        return
    finally:
        import os
        try:
            os.unlink(audio_path)
        except OSError:
            pass

    if not result.get("ok"):
        err = _escape(result.get("error", "Unknown error"))
        await thinking.edit_text(f"⚠️ Voice capture failed: {err}", parse_mode="MarkdownV2")
        return

    transcript  = result["transcript"]
    voice_type  = result["voice_type"]
    confidence  = result["confidence"]
    capture_id  = result["capture_id"]
    duration    = result.get("duration", 0.0)
    label       = vc.voice_type_label(voice_type)
    short_id    = str(capture_id)[:8]
    preview     = transcript[:300]
    conf_pct    = int(confidence * 100)

    # Inline action buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"vc|confirm|{capture_id}"),
            InlineKeyboardButton("🗑 Dismiss",  callback_data=f"vc|dismiss|{capture_id}"),
        ],
        [
            InlineKeyboardButton("🚀 → Mission", callback_data=f"vc|promote|{capture_id}"),
            InlineKeyboardButton("📋 → Note",    callback_data=f"vc|note|{capture_id}"),
        ],
    ])

    reply = (
        f"🎙 *Voice captured\\.*\n\n"
        f"Type: `{_escape(label)}`\n"
        f"Confidence: {conf_pct}%\n"
        f"Status: `needs\\_review`\n"
        f"Duration: {round(duration, 1)}s\n"
        f"ID: `{short_id}…`\n\n"
        f"*Preview:*\n_{_escape(preview)}_"
    )
    await thinking.edit_text(reply, parse_mode="MarkdownV2", reply_markup=keyboard)
    log.info("[voice] captured id=%s type=%s conf=%d%%", short_id, voice_type, conf_pct)


async def handle_voice_capture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses on voice capture confirmations."""
    query = update.callback_query
    await query.answer()

    if update.effective_chat.id != TELEGRAM_CHAT_ID:
        return

    parts = query.data.split("|")  # vc|action|capture_id
    if len(parts) != 3:
        return
    _, action, capture_id = parts

    db = _get_supabase()
    if not db:
        await query.edit_message_text("⚠️ Supabase unavailable.")
        return

    try:
        if action == "confirm":
            await query.edit_message_text(
                f"✅ Capture confirmed\\.\nIn LCARS Portal → Capture Inbox for review\\.",
                parse_mode="MarkdownV2",
            )

        elif action == "dismiss":
            db.table("captured_items").update({"processing_status": "dismissed"}) \
              .eq("id", capture_id).execute()
            await query.edit_message_text("🗑 Capture dismissed\\.", parse_mode="MarkdownV2")

        elif action == "promote":
            db.table("captured_items").update({"item_type": "idea"}) \
              .eq("id", capture_id).execute()
            await query.edit_message_text(
                "🚀 Marked as *Mission Idea*\\.\n"
                "Review in LCARS Portal → Capture Inbox to promote to active mission\\.",
                parse_mode="MarkdownV2",
            )

        elif action == "note":
            db.table("captured_items").update({"item_type": "note"}) \
              .eq("id", capture_id).execute()
            await query.edit_message_text(
                "📋 Saved as *Note*\\. In LCARS Portal → Capture Inbox\\.",
                parse_mode="MarkdownV2",
            )

    except Exception as exc:
        log.error("[voice-cb] %s failed: %s", action, exc)
        await query.edit_message_text(f"⚠️ Action failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


# ── Telegram adapter ──────────────────────────────────────────────────────────

class _BotAdapter:
    def __init__(self, bot):
        self._bot = bot

    def send_message(self, chat_id, text, parse_mode="Markdown"):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self._bot.send_message(
                    chat_id=chat_id,
                    text=_escape(text),
                    parse_mode="MarkdownV2",
                )
            )
        except Exception as exc:
            log.error("send_message failed: %s", exc)


# ── Scheduled dispatch (XO only) ──────────────────────────────────────────────

async def _scheduled_morning_brief(bot) -> None:
    """07:00 — Wellness & Recovery Officer Daily Brief (insight-over-metrics)."""
    log.info("[scheduler] morning wellness brief")
    try:
        db   = _get_supabase()
        snap = get_wellness_snapshot(db)
        brief = await generate_wellness_brief_async(snap, generate_async)

        today = datetime.now(_TZ).strftime("%a %d %b")
        msg = (
            f"🌅 *Daily Wellness Brief — {_escape(today)}*\n\n"
            f"{_escape(brief)}\n\n"
            f"Recovery: `{_escape(_bar(snap.recovery_confidence))}` {snap.recovery_confidence}% · "
            f"{snap.pulses_completed}/4 pulses"
        )
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="MarkdownV2",
        )
        log.info("[scheduler] morning brief sent, conf=%s%%", snap.recovery_confidence)
    except Exception as exc:
        log.error("[scheduler] morning brief failed: %s", exc)
        # fall back to standard dispatch on error
        await _scheduled_dispatch(bot)


async def _scheduled_dispatch(bot) -> None:
    log.info("[scheduler] xo dispatch tick")
    try:
        result = run_dispatch_check(_BotAdapter(bot), TELEGRAM_CHAT_ID, supabase_client=_get_supabase())
        log.info("[scheduler] action=%s sent=%s conf=%s%%",
                 result.get("action"), result.get("message_sent"), result.get("confidence"))
    except Exception as exc:
        log.error("[scheduler] dispatch failed: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    ("recovery_status", "Today's confidence bar + pulse ledger"),
    ("recovery_pulse",  "Log a pulse inline (energy → mood → stress)"),
    ("mission_list",    "List missions  e.g. /mission_list active"),
    ("mission_status",  "Mission detail  e.g. /mission_status 0167"),
    ("mission_create",   "Create mission  e.g. /mission_create Build ops dashboard"),
    ("captain_approve",      "Approve mission  e.g. /captain_approve 0175"),
    ("captain_reject",       "Reject mission   e.g. /captain_reject 0175 Scope too broad"),
    ("mission_submit",       "Submit for Captain approval  e.g. /mission_submit 0178"),
    ("handoff_engineering",  "Hand off to Engineering  e.g. /handoff_engineering 0181"),
    ("operating_picture",    "Captain's operating picture"),
    ("log_activity",    "Log activity  e.g. /log_activity walk 30 light"),
    ("log_weight",      "Log weight  e.g. /log_weight 82.5"),
    ("brief",           "OR intelligence brief on demand"),
    ("dispatch",        "Manual XO dispatch check"),
    ("db_status",       "Supabase connectivity test"),
    ("restart_bots",    "Restart starfleet services  e.g. /restart_bots all"),
    ("help",            "Full command reference + proactive schedule"),
]


async def _post_init(app) -> None:
    """Register the command menu and start the scheduler inside the running event loop."""
    from telegram import BotCommand
    await app.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in _BOT_COMMANDS])
    log.info("[startup] Telegram command menu registered (%d commands)", len(_BOT_COMMANDS))

    bot = app.bot
    scheduler = AsyncIOScheduler(timezone="Australia/Brisbane")
    scheduler.add_job(_scheduled_morning_brief, CronTrigger(hour=7,  minute=0),  id="morning", args=[bot])
    scheduler.add_job(_scheduled_dispatch,      CronTrigger(hour=12, minute=30), id="midday",  args=[bot])
    scheduler.add_job(_scheduled_dispatch,      CronTrigger(hour=21, minute=0),  id="evening", args=[bot])
    scheduler.start()
    log.info("[startup] Scheduler started")


def main() -> None:
    log.info("XO Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("help",            cmd_help))
    app.add_handler(CommandHandler("recovery_status", cmd_recovery_status))
    app.add_handler(CommandHandler("recovery_pulse",  cmd_recovery_pulse))
    app.add_handler(CommandHandler("pulse_check",     cmd_recovery_pulse))
    app.add_handler(CommandHandler("mission_list",    cmd_mission_list))
    app.add_handler(CommandHandler("mission_status",  cmd_mission_status))
    app.add_handler(CommandHandler("mission_create",   cmd_mission_create))
    app.add_handler(CommandHandler("captain_approve",     cmd_captain_approve))
    app.add_handler(CommandHandler("captain_reject",      cmd_captain_reject))
    app.add_handler(CommandHandler("mission_submit",      cmd_mission_submit))
    app.add_handler(CommandHandler("handoff_engineering", cmd_handoff_engineering))
    app.add_handler(CommandHandler("operating_picture",   cmd_operating_picture))
    app.add_handler(CommandHandler("log_activity",    cmd_log_activity))
    app.add_handler(CommandHandler("log_weight",      cmd_log_weight))
    app.add_handler(CommandHandler("db_status",       cmd_db_status))
    app.add_handler(CommandHandler("dispatch",        cmd_dispatch))
    app.add_handler(CommandHandler("brief",           cmd_brief))
    app.add_handler(CommandHandler("restart_bots",    cmd_restart_bots))
    app.add_handler(CallbackQueryHandler(handle_pulse_callback,         pattern=r"^pl\|"))
    app.add_handler(CallbackQueryHandler(handle_voice_capture_callback, pattern=r"^vc\|"))
    app.add_handler(MessageHandler(filters.VOICE,                   cmd_voice_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
