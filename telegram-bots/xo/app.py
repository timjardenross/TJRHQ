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
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Australia/Brisbane")

from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────

_BOT_DIR   = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]

load_dotenv(_BOT_DIR / ".env")


def _ensure_mistral_env() -> None:
    """Single-source the Mistral embeddings key: this process loads only its
    own telegram-bots/xo/.env, but core/advisory/cli.py's embedding path
    (tools/supabase/embedding_client.py) needs MISTRAL_API_KEY when invoked
    as a subprocess — which inherits this process's environment. Pull it from
    platform-runtime/.env, the canonical credentials file for Mistral (see
    STARSHIP-ENDEAVOUR-VM-CONTEXT.md), if not already set locally. Existing
    env always wins; no other secrets are imported. Mirrors the equivalent
    GLM-borrowing pattern used elsewhere in the Telegram bot lineage."""
    if os.environ.get("MISTRAL_API_KEY"):
        return
    envf = _REPO_ROOT / "platform-runtime" / ".env"
    try:
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MISTRAL_API_KEY") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_ensure_mistral_env()

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

# SUOC Wave 2 (MSN-0210F, Item C): canonical chat-ID allowlist gate.
# TELEGRAM_CHAT_ID is passed as bootstrap_captain_chat_id — a fallback
# only, kept for exact behavioural parity when TELEGRAM_ALLOWED_CHAT_IDS
# is unset; the long-term authority model is the explicit env allowlist.
from core.platform.telegram_access import is_allowed as _chat_is_allowed

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
    # EOS Phase 2 Priority 3: extracted to pulse_time.py so voice_capture.py's
    # automatic recovery-pulse promotion can reuse the exact same bucketing
    # instead of a second, drifting copy - one source of truth, per the
    # mission's own "no duplicated business logic" requirement.
    from telegram_bots.xo.pulse_time import current_pulse_type
    return current_pulse_type()

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
        "*Captain Intelligence*\n"
        "/captain — narrative: what changed, why it matters, what to do\n"
        "/learning — learning health \\+ compliance, insights, leadership candidates\n"
        "/patterns \\[category\\] — Operational Pattern Library: reusable engineering process knowledge\n"
        "/pending — attention queue \\+ quick outcome capture \\(tap buttons\\)\n\n"
        "*Intelligence*\n"
        "/brief — intelligence brief on demand\n\n"
        "*Health \\& Recovery*\n"
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
        "*System*\n"
        "/dispatch — manual dispatch check\n"
        "/brief — latest OR Intelligence Brief \\(risk, events, themes\\)\n"
        "/daily \\[morning|eod|weekly\\] — Captain's daily operating picture\n"
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

# XO is the only Telegram bot (Captain decision 2026-07-05); tg-engineer /
# tg-engineering-dept are retired. The "telegram" group is therefore empty here —
# XO self-restarts tg-xo.service separately below (restart_xo).
_RESTARTABLE_SERVICES = {
    "slack":    ["starfleet-slack-bot.service"],
    "telegram": [],
    "all":      ["starfleet-slack-bot.service"],
}


async def cmd_restart_bots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart_bots [slack|telegram|all]  — restart starfleet services. XO restarts itself last."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
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

_RISK_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/brief — latest OR Intelligence Brief from intelligence_briefs table."""
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    await update.message.reply_text("⚙️ Fetching latest OR Intelligence Brief…")
    try:
        res = (
            db.table("intelligence_briefs")
            .select(
                "brief_id,generated_at,period_start,period_end,overall_risk,"
                "executive_snapshot,bottom_line,emerging_themes,forward_watch,"
                "events_included,events_evaluated,sources_checked,narrative_available"
            )
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            await update.message.reply_text(
                "No OR Intelligence Brief found. Run the scheduler to generate one:\n"
                "<code>python -m intelligence.scheduler --once</code>",
                parse_mode="HTML",
            )
            return

        b = rows[0]
        bid      = (b.get("brief_id") or "")[:8]
        risk     = b.get("overall_risk") or "UNKNOWN"
        risk_icon = _RISK_ICON.get(str(risk).upper(), "⚪")
        p_start  = (b.get("period_start") or "")[:10]
        p_end    = (b.get("period_end") or "")[:10]
        gen_at   = (b.get("generated_at") or "")[:16].replace("T", " ")
        snap     = b.get("executive_snapshot") or ""
        bottom   = b.get("bottom_line") or ""
        themes   = b.get("emerging_themes") or []
        fw       = b.get("forward_watch")
        ev_in    = b.get("events_included", 0)
        ev_total = b.get("events_evaluated", 0)
        sources  = b.get("sources_checked", 0)

        lines = [
            f"<b>🛡 OR Intelligence Brief — {bid}</b>",
            f"{risk_icon} Risk: <b>{risk}</b>",
            f"<i>Period {p_start} → {p_end} · Generated {gen_at} UTC</i>",
            "",
        ]

        if bottom:
            lines += ["<b>Bottom Line</b>", bottom[:600], ""]

        if snap and snap != bottom:
            lines += ["<b>Snapshot</b>", snap[:500], ""]

        if themes:
            lines.append("<b>Emerging Themes</b>")
            for t in themes[:5]:
                label = t if isinstance(t, str) else (t.get("theme") or t.get("title") or str(t))
                lines.append(f"  • {str(label)[:100]}")
            lines.append("")

        if fw:
            fw_text = fw if isinstance(fw, str) else json.dumps(fw)
            lines += ["<b>Forward Watch</b>", str(fw_text)[:300], ""]

        ev_suppressed = ev_total - ev_in if ev_total and ev_in else None
        ev_line = f"Events: {ev_in} included"
        if ev_suppressed is not None:
            ev_line += f" · {ev_suppressed} suppressed"
        ev_line += f" · {sources} sources checked"
        lines.append(f"<i>{ev_line}</i>")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        log.info("[brief] OR brief %s delivered (risk=%s)", bid, risk)

    except Exception as exc:
        log.error("[brief] OR brief fetch failed: %s", exc)
        await update.message.reply_text(f"⚠️ Brief fetch failed: {str(exc)[:120]}")


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/daily [morning|eod|weekly] — Captain's Daily Operating Picture (ephemeral, time-aware)."""
    args = context.args or []
    brief_type = (args[0].lower() if args else None)

    if brief_type not in ("morning", "eod", "weekly", "midday"):
        hour = datetime.now(_TZ).hour
        brief_type = "morning" if hour < 17 else "eod"

    await update.message.reply_text("⚙️ Generating daily picture…")
    try:
        from intelligence.captains_brief import (
            generate_morning_brief, generate_eod_summary, generate_weekly_report,
        )
        if brief_type == "eod":
            text = await asyncio.get_event_loop().run_in_executor(None, generate_eod_summary)
        elif brief_type == "weekly":
            text = await asyncio.get_event_loop().run_in_executor(None, generate_weekly_report)
        else:
            text = await asyncio.get_event_loop().run_in_executor(None, generate_morning_brief)
        await update.message.reply_text(text, parse_mode="HTML")
        log.info("[daily] %s brief delivered", brief_type)
    except Exception as exc:
        log.error("[daily] generation failed: %s", exc)
        await update.message.reply_text(f"⚠️ Daily brief failed: {str(exc)[:120]}")


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


def _plain(s) -> str:
    """Strip MarkdownV2 format chars from dynamic content (it is re-escaped by _escape)."""
    return str(s or "").replace("*", "").replace("_", "")


def _load_learning():
    """Import the reused learning service (core/knowledge/outcome_capture). Returns the
    module or None. The bot already runs with the repo root on sys.path; core/knowledge
    is added defensively (it is not a package)."""
    try:
        import sys
        from pathlib import Path
        kp = str(Path(__file__).resolve().parents[2] / "core" / "knowledge")
        if kp not in sys.path:
            sys.path.insert(0, kp)
        import outcome_capture  # type: ignore
        return outcome_capture
    except Exception as exc:  # pragma: no cover
        log.warning("[learning] outcome_capture unavailable: %s", exc)
        return None


async def cmd_learning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MSN-0086 WP3/WP6: concise learning + leadership intelligence on demand.

    Reuses outcome_capture.learning_status() + leadership_outcomes() — no duplicate
    logic, no new storage. Internal only; nothing published."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        await update.message.reply_text("Not authorised\\.", parse_mode="MarkdownV2")
        return
    oc = _load_learning()
    if oc is None:
        await update.message.reply_text(
            "⚠️ Learning module not available in this environment\\.",
            parse_mode="MarkdownV2",
        )
        return
    try:
        s = oc.learning_status()
        if not getattr(s, "data_available", False):
            await update.message.reply_text(
                "📊 *Learning Status*\nUnavailable \\(Supabase not configured\\)\\.",
                parse_mode="MarkdownV2",
            )
            return
        emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(s.health, "⚪")
        leads = oc.leadership_outcomes(limit=3) or []

        msg = [
            "*Learning Status*",
            f"Health: {emoji} {_plain(s.health)}",
            f"Capture compliance: {_plain(s.capture_compliance_pct)}%",
            f"Reusable insights: {_plain(s.reusable_insights)}",
            f"Leadership candidates: {_plain(s.leadership_candidates)}",
            f"Outcomes pending: {_plain(s.pending_outcomes)} "
            f"({_plain(s.overdue_outcomes)} overdue)",
        ]
        if s.sensitive_pending:
            msg.append(f"Sensitive drafts pending approval: {_plain(s.sensitive_pending)}")
        if leads:
            top = leads[0]
            insight = _plain((top.get("reusable_insight") or top.get("title") or "")[:160])
            if insight:
                msg += ["", "*Leadership insight:*", insight]
        msg += ["", "_/comms leadership for the full brief. Internal only; nothing published._"]
        await update.message.reply_text(_escape("\n".join(msg)), parse_mode="MarkdownV2")
        log.info("[learning] delivered health=%s pending=%s", s.health, s.pending_outcomes)
    except Exception as exc:
        log.error("[learning] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Learning status failed: `{_escape(str(exc))}`",
            parse_mode="MarkdownV2",
        )


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MSN-0343: first real consumer of the Operational Pattern Library
    (`core/platform/operational_pattern_library.py`, built MSN-0210J,
    zero consumers until now). Read-only — surfaces reusable engineering
    process knowledge on demand before risky work, distinct from `/learning`
    (MSN-0086's leadership/content learning — a different "learning" that
    happens to share the name; not the same capability)."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        await update.message.reply_text("Not authorised\\.", parse_mode="MarkdownV2")
        return
    category = " ".join(context.args).strip() if context.args else None
    try:
        from core.platform.operational_pattern_library import get_patterns

        patterns = get_patterns(category=category or None)
    except Exception as exc:
        log.error("[patterns] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Pattern Library lookup failed: `{_escape(str(exc))}`",
            parse_mode="MarkdownV2",
        )
        return
    if not patterns:
        hint = f" for category `{_plain(category)}`" if category else ""
        await update.message.reply_text(
            _escape(f"No patterns found{hint}. Try /patterns with no argument to list all."),
            parse_mode="MarkdownV2",
        )
        return
    msg = [f"*Operational Patterns*{f' — {_plain(category)}' if category else ''}"]
    for p in patterns[:8]:
        msg.append("")
        msg.append(f"*{_plain(p.get('pattern_name', '?'))}* \\({_plain(p.get('confidence', '?'))}%\\)")
        msg.append(_plain((p.get("description") or "")[:200]))
        msg.append(f"_When: {_plain((p.get('when_to_use') or '')[:120])}_")
    if len(patterns) > 8:
        msg += ["", f"_...and {len(patterns) - 8} more. Narrow with /patterns <category>._"]
    await update.message.reply_text(_escape("\n".join(msg)), parse_mode="MarkdownV2")
    log.info("[patterns] delivered count=%s category=%s", len(patterns), category)


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
    """Captain's Operating Picture — synthesised executive view. Usage: /operating_picture"""
    await update.message.reply_text("⚙️ Building operating picture…")
    try:
        from core.intelligence.operating_picture import get_operating_picture
        data = await asyncio.get_event_loop().run_in_executor(None, get_operating_picture)

        flags    = data.get("attention_flags", [])
        health   = data.get("health", {})
        missions = data.get("missions", {})
        intel    = data.get("intelligence", {})
        summary  = data.get("situation_summary", "")

        _risk_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        _cap_icon  = lambda s: "🟢" if s and int(s) >= 70 else ("🟡" if s and int(s) >= 40 else "🔴")

        lines = [
            "<b>🎯 CAPTAIN'S OPERATING PICTURE</b>",
            f"<i>{summary}</i>",
            "",
        ]

        # Health
        cap = health.get("capacity_score")
        if cap is not None:
            try:
                icon = _cap_icon(cap)
            except Exception:
                icon = "⚪"
            pain  = health.get("pain_score", "?")
            sleep = health.get("sleep_hours", "?")
            lines += [
                "<b>⚡ HEALTH</b>",
                f"  {icon} Capacity <b>{cap}</b>  · Pain {pain}  · Sleep {sleep}h",
                "",
            ]

        # Missions
        total   = missions.get("total_active", 0)
        blocked = missions.get("blocked_count", 0)
        p0p1    = missions.get("high_priority", [])
        lines += [
            "<b>🎯 MISSIONS</b>",
            f"  Active: {total}  · Blocked: {blocked}  · P0/P1: {len(p0p1)}",
        ]
        for m in p0p1[:3]:
            lines.append(f"  🔥 {m.get('title', '—')} [{m.get('status', '?')}]")
        for m in (missions.get("blocked", []))[:2]:
            lines.append(f"  🚧 {m.get('title', '—')}")
        lines.append("")

        # Intelligence
        signals = intel.get("signals_24h", {})
        hi = signals.get("high", 0)
        md = signals.get("medium", 0)
        if hi or md:
            lines += [
                "<b>📡 INTELLIGENCE (24h)</b>",
                f"  🔴 {hi} high  · 🟡 {md} medium signals",
            ]
            for s in (signals.get("top_signals") or [])[:3]:
                lines.append(f"  {_risk_icon.get(s.get('risk_rating'), '⚪')} {s.get('raw_title', '—')[:70]}")
            lines.append("")

        # Attention flags
        high_flags = [f for f in flags if f.get("severity") in ("high",)]
        if high_flags:
            lines.append("<b>🚨 ATTENTION REQUIRED</b>")
            for f in high_flags[:3]:
                lines.append(f"  • {f.get('message', '')}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        log.info("[operating-picture] delivered: flags=%d", len(flags))

    except Exception as exc:
        log.error("[operating-picture] failed: %s", exc)
        await update.message.reply_text(f"⚠️ Operating picture failed: {str(exc)[:120]}")


# ── Intelligence query commands (MSN-0201) ───────────────────────────────────

async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/signals [today|high|cyber|all] — top intelligence events from the last 24-48h"""
    args = context.args or []
    filt = (args[0].lower() if args else "today")

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    try:
        from datetime import timezone as _utczone
        # Time window
        hours = 48 if filt == "all" else 24
        since = (datetime.now(_utczone.utc) - __import__("datetime").timedelta(hours=hours)).isoformat()

        query = (
            db.table("intelligence_events")
            .select("raw_title,event_type,geography,risk_rating,rank_score,collected_at")
            .eq("suppressed", False)
            .gte("collected_at", since)
        )
        if filt == "high":
            query = query.eq("risk_rating", "HIGH")
        elif filt == "cyber":
            query = query.ilike("event_type", "%cyber%")
        elif filt == "today":
            pass  # already scoped to 24h
        # else "all" → 48h, no extra filter

        res = query.order("rank_score", desc=True).limit(8).execute()
        rows = res.data or []

        if not rows:
            label = _escape_strict(filt)
            await update.message.reply_text(
                f"No signals found for filter \\`{label}\\` in the last {hours}h\\.",
                parse_mode="MarkdownV2",
            )
            return

        _RISK = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        header = f"*📡 Intelligence Signals — {_escape_strict(filt.upper())}* \\({len(rows)}\\)\n"
        lines = [header]
        for r in rows:
            icon  = _RISK.get(r.get("risk_rating", ""), "⚪")
            title = _escape_strict((r.get("raw_title") or "—")[:80])
            geo   = _escape_strict(r.get("geography") or "")
            et    = _escape_strict(r.get("event_type") or "")
            meta  = f" · _{geo}_{' · ' + et if et else ''}" if geo or et else ""
            lines.append(f"{icon} {title}{meta}")

        await update.message.reply_text("\n\n".join(lines), parse_mode="MarkdownV2")
        log.info("[signals] filter=%s rows=%d", filt, len(rows))

    except Exception as exc:
        log.error("[signals] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Signals query failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


async def cmd_themes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/themes — emerging themes from the latest ORI intelligence brief"""
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    try:
        res = (
            db.table("intelligence_briefs")
            .select("brief_id,generated_at,overall_risk,emerging_themes,forward_watch,executive_snapshot,period_start,period_end")
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            await update.message.reply_text("No ORI brief found\\.", parse_mode="MarkdownV2")
            return

        row    = rows[0]
        brief_id = (row.get("brief_id") or "")[:8]
        period   = f"{(row.get('period_start') or '')[:10]} → {(row.get('period_end') or '')[:10]}"
        risk     = row.get("overall_risk", "?")
        snap     = row.get("executive_snapshot") or row.get("bottom_line") or ""
        themes   = row.get("emerging_themes") or []
        fw       = row.get("forward_watch")

        _RISK = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        risk_icon = _RISK.get(str(risk).upper(), "⚪")

        lines = [
            f"*📈 Emerging Themes* — `{brief_id}` \\| {risk_icon} {_escape_strict(str(risk))}",
            f"_{_escape_strict(period)}_",
        ]

        if snap:
            lines += ["", f"_{_escape_strict(snap[:300])}_"]

        if themes:
            lines.append("\n*Themes:*")
            for t in themes[:6]:
                label = t if isinstance(t, str) else (t.get("theme") or t.get("title") or str(t))
                lines.append(f"  • {_escape_strict(str(label)[:100])}")

        if fw:
            fw_text = fw if isinstance(fw, str) else json.dumps(fw)[:200]
            lines += ["", f"*👁 Forward Watch:* {_escape_strict(fw_text[:250])}"]

        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
        log.info("[themes] brief_id=%s", brief_id)

    except Exception as exc:
        log.error("[themes] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Themes query failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


async def cmd_source_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/source_status — health of intelligence collection sources"""
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    try:
        # Latest health check per source (using a window via order+distinct would need RPC;
        # instead fetch most recent 100 rows and de-dup in Python — fast enough at 40-50 sources)
        res = (
            db.table("intelligence_source_health")
            .select("source_id,checked_at,status,items_retrieved,error_message")
            .order("checked_at", desc=True)
            .limit(200)
            .execute()
        )
        rows = res.data or []

        # De-dup to latest per source_id
        seen: dict[str, dict] = {}
        for r in rows:
            sid = r.get("source_id") or ""
            if sid not in seen:
                seen[sid] = r

        # Fetch source names
        src_res = (
            db.table("intelligence_source_registry")
            .select("source_id,source_name,category")
            .eq("active", True)
            .execute()
        )
        name_map = {r["source_id"]: r for r in (src_res.data or [])}

        _STATUS_ICON = {"ok": "✅", "stale": "🟡", "failed": "❌", "degraded": "⚠️", "skipped": "⏭"}
        buckets: dict[str, list[str]] = {"failed": [], "degraded": [], "stale": [], "ok": [], "skipped": []}

        for sid, h in seen.items():
            st = (h.get("status") or "unknown").lower()
            src_name = name_map.get(sid, {}).get("source_name", sid[:12]) or sid[:12]
            icon = _STATUS_ICON.get(st, "❓")
            items = h.get("items_retrieved")
            detail = f"{icon} {_escape_strict(src_name)}"
            if items is not None:
                detail += f" \\({items}\\)"
            buckets.setdefault(st, []).append(detail)

        total = len(seen)
        ok    = len(buckets.get("ok", []))
        fail  = len(buckets.get("failed", []))
        stale = len(buckets.get("stale", []))

        lines = [
            f"*📡 Source Health* — {total} sources",
            f"✅ {ok} ok  ·  🟡 {stale} stale  ·  ❌ {fail} failed",
        ]

        if buckets.get("failed"):
            lines += ["", "*Failed:*"]
            lines += buckets["failed"][:6]
        if buckets.get("stale"):
            lines += ["", "*Stale:*"]
            lines += buckets["stale"][:4]

        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
        log.info("[source-status] total=%d ok=%d fail=%d", total, ok, fail)

    except Exception as exc:
        log.error("[source-status] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Source status query failed: `{_escape_strict(str(exc)[:80])}`",
            parse_mode="MarkdownV2",
        )


# ── Advisory CLI (MSN-0200-P3A) ──────────────────────────────────────────────

def _advisory_cli_call(cli_args: list[str], timeout: int) -> str:
    """Run core/advisory/cli.py with the given args; return stdout/stderr text.
    Raises FileNotFoundError if the CLI is absent, subprocess.TimeoutExpired on timeout."""
    advisory_cli = _REPO_ROOT / "core" / "advisory" / "cli.py"
    if not advisory_cli.exists():
        raise FileNotFoundError("advisory cli.py not present")
    result = subprocess.run(
        [sys.executable, str(advisory_cli), *cli_args],
        capture_output=True, text=True, timeout=timeout, cwd=str(_REPO_ROOT),
    )
    return (result.stdout or result.stderr or "No response.").strip()


async def _run_advisory(update: Update, title: str, cli_args: list[str],
                        working_msg: str, timeout: int = 90) -> None:
    """Shared path for /advise and /challenge: post a working message, run the
    advisory CLI off-thread, and reply with the result. Never raises."""
    await update.message.reply_text(working_msg)
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, _advisory_cli_call, cli_args, timeout)
    except FileNotFoundError:
        await update.message.reply_text("⚠️ Advisory CLI not available in this environment.")
        return
    except subprocess.TimeoutExpired:
        await update.message.reply_text(f"⚠️ Advisory timed out ({timeout}s).")
        return
    except Exception as exc:
        log.error("[advisory] %s failed: %s", title, exc)
        await update.message.reply_text(f"⚠️ Advisory failed: {str(exc)[:120]}")
        return
    await update.message.reply_text(f"<b>{title}</b>\n\n{response[:3800]}", parse_mode="HTML")


async def cmd_advise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Advisory consult (full officer panel). Usage: /advise <question>"""
    question = " ".join(context.args or []).strip()
    if not question:
        await update.message.reply_text(
            "Usage: /advise &lt;question&gt;\n"
            "Example: /advise What should I focus on this week?",
            parse_mode="HTML",
        )
        return

    await _run_advisory(update, "Advisory Panel", ["--action", "advice", "--question", question],
                        "⚙️ Consulting the officer panel…")


# ── Narrative intelligence + outcome capture (MSN-0087) ──────────────────────

def _load_narrative():
    """Import the narrative service (core/knowledge/learning_narrative). Returns module or None."""
    try:
        import sys
        from pathlib import Path
        kp = str(Path(__file__).resolve().parents[2] / "core" / "knowledge")
        if kp not in sys.path:
            sys.path.insert(0, kp)
        import learning_narrative  # type: ignore
        return learning_narrative
    except Exception as exc:  # pragma: no cover
        log.warning("[narrative] learning_narrative unavailable: %s", exc)
        return None


async def cmd_captain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MSN-0087 WP6/WP7: narrative intelligence — what changed, why it matters, what
    needs attention, and advisory recommendations. Evidence-backed; advisory only."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        await update.message.reply_text("Not authorised\\.", parse_mode="MarkdownV2")
        return
    nv = _load_narrative()
    if nv is None:
        await update.message.reply_text(
            "⚠️ Narrative module not available\\.", parse_mode="MarkdownV2")
        return
    try:
        text = nv.captain_brief_text()
        await update.message.reply_text(_escape(text), parse_mode="MarkdownV2")
    except Exception as exc:
        log.error("[captain] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Captain narrative failed: `{_escape(str(exc))}`", parse_mode="MarkdownV2")


# MSN-0087 WP3: quick outcome-capture callback codes (short to fit Telegram's 64-byte limit).
_OC_STATUS = {"w": "worked", "p": "partial", "d": "defer"}


def _parse_oc_cb(data: str) -> dict:
    """Pure: parse an 'oc|<w|p|d>|<source_type>|<source_id>' callback. {} if invalid."""
    parts = (data or "").split("|")
    if len(parts) != 4 or parts[0] != "oc" or parts[1] not in _OC_STATUS:
        return {}
    return {"action": _OC_STATUS[parts[1]], "source_type": parts[2], "source_id": parts[3]}


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MSN-0087 WP4: consolidated 'Captain Attention' queue with quick outcome actions."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        await update.message.reply_text("Not authorised\\.", parse_mode="MarkdownV2")
        return
    nv = _load_narrative()
    if nv is None:
        await update.message.reply_text("⚠️ Queue unavailable\\.", parse_mode="MarkdownV2")
        return
    try:
        q = nv.pending_actions()
        if not q.get("data_available"):
            await update.message.reply_text(
                "📋 *Captain Attention*\nUnavailable \\(Supabase not configured\\)\\.",
                parse_mode="MarkdownV2")
            return
        lines = [
            "*Captain Attention*",
            f"Overdue outcomes: {q['pending_total']} pending · {len(q['overdue'])} overdue (15d+)",
            f"Learning debt (30d+): {q['learning_debt']}",
            f"Sensitive drafts pending approval: {q['sensitive_pending']}  (/comms pending)",
            f"Leadership candidates: {q['leadership_candidates']}  (/comms leadership)",
        ]
        await update.message.reply_text(_escape("\n".join(lines)), parse_mode="MarkdownV2")
        # Inline quick-capture for the top overdue items (≤3) — one tap, no typing.
        for item in q["overdue"][:3]:
            st, sid = item.get("source_type", "mission"), str(item.get("source_id", ""))
            title = _plain(item.get("title", sid))[:60]
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✓ Worked", callback_data=f"oc|w|{st}|{sid}"),
                InlineKeyboardButton("~ Partial", callback_data=f"oc|p|{st}|{sid}"),
                InlineKeyboardButton("⏸ Defer", callback_data=f"oc|d|{st}|{sid}"),
            ]])
            await update.message.reply_text(
                _escape(f"Outcome pending: {title}"), parse_mode="MarkdownV2", reply_markup=kb)
    except Exception as exc:
        log.error("[pending] failed: %s", exc)
        await update.message.reply_text(
            f"⚠️ Queue failed: `{_escape(str(exc))}`", parse_mode="MarkdownV2")


async def handle_outcome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MSN-0087 WP3: complete a quick outcome capture from an inline button. Reuses the
    tested outcome_capture.record_outcome (idempotent upsert). Defer = acknowledge only."""
    query = update.callback_query
    await query.answer()
    parsed = _parse_oc_cb(query.data or "")
    if not parsed:
        return
    if parsed["action"] == "defer":
        await query.edit_message_text(
            _escape("⏸ Deferred — stays in the queue."), parse_mode="MarkdownV2")
        return
    oc = _load_learning()
    if oc is None:
        await query.edit_message_text(
            _escape("⚠️ Capture module unavailable."), parse_mode="MarkdownV2")
        return
    try:
        res = oc.record_outcome(oc.OutcomeInput(
            source_type=parsed["source_type"], source_id=parsed["source_id"],
            title=parsed["source_id"], outcome_status=parsed["action"],
            outcome_summary="Quick capture via Telegram (Captain).",
            created_by="telegram-quick", promote_lesson=False,
        ))
        if res.persisted:
            msg = f"✓ Outcome recorded: {parsed['source_id']} → {parsed['action']}."
        elif res.success:
            msg = f"✓ Validated (offline, not persisted): {parsed['action']}."
        else:
            msg = "⚠️ Could not record: " + "; ".join(res.errors)
        await query.edit_message_text(_escape(msg), parse_mode="MarkdownV2")
        log.info("[outcome-cb] %s %s -> %s persisted=%s",
                 parsed["source_type"], parsed["source_id"], parsed["action"], res.persisted)
    except Exception as exc:
        log.error("[outcome-cb] failed: %s", exc)
        await query.edit_message_text(
            f"⚠️ Capture failed: `{_escape(str(exc))}`", parse_mode="MarkdownV2")


# ── Free-text conversation ────────────────────────────────────────────────────

async def cmd_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    # Unlike every other handler in this file, this path had no try/except —
    # any exception here (debrief routing, recovery/wellness/mission lookups)
    # crashed silently: the Captain saw the message marked delivered and
    # never got a reply, with no error visible anywhere except the service
    # log. Wrapped so a failure is always at least visible + logged.
    try:
        db = _get_supabase()

        if db:
            from telegram_bots.xo import debrief_engine as de
            debrief_result = await de.route_debrief_interaction(db, update.effective_chat.id, text)
            if debrief_result["handled"]:
                await update.message.reply_text(debrief_result["reply"])
                return

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
    except Exception as exc:
        log.exception("[cmd_message] failed: %s", exc)
        await update.message.reply_text(
            "⚠️ Something went wrong processing that — try /recovery_status or /dispatch, "
            "or resend your message."
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

def _build_capture_reply(capture_id, voice_type: str, confidence: float, duration: float, transcript: str):
    """Shared by cmd_voice_note's low-tier path and the 'Save as Capture'
    button callback — one canonical capture confirmation card, not duplicated."""
    from telegram_bots.xo import voice_capture as vc

    label    = vc.voice_type_label(voice_type)
    short_id = str(capture_id)[:8]
    preview  = transcript[:300]
    conf_pct = int(confidence * 100)

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
        f"Duration: {_escape(str(round(duration, 1)))}s\n"
        f"ID: `{short_id}…`\n\n"
        f"*Preview:*\n_{_escape_strict(preview)}_"
    )
    return reply, keyboard


async def cmd_voice_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages — acknowledge immediately, then transcribe/route/reply."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return

    msg = update.message
    if not msg or not msg.voice:
        return

    # XO Debrief Responsiveness Improvement: acknowledge BEFORE any expensive
    # work (Supabase check, download, transcription, LLM) — the Captain should
    # never feel like they're waiting on a backend pipeline.
    t0 = time.monotonic()
    timings = {}
    thinking = await msg.reply_text("Received, Captain.")
    timings["ack_ms"] = round((time.monotonic() - t0) * 1000)

    db = _get_supabase()
    if not db:
        await thinking.edit_text("⚠️ Supabase unavailable — voice capture requires database connectivity.")
        return

    # Import here to avoid circular deps at module load
    from telegram_bots.xo import voice_capture as vc
    from telegram_bots.xo import debrief_engine as de

    vc.VOICE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = str(vc.VOICE_TMP_DIR / f"tg_{msg.message_id}.oga")
    try:
        tg_file = await msg.voice.get_file()
        await tg_file.download_to_drive(audio_path)
    except Exception as exc:
        log.error("[voice] download failed: %s", exc)
        await thinking.edit_text(f"⚠️ Could not download voice file: {exc}")
        return

    # Transcribe only here — classification/save is deferred below so a
    # voice note that belongs to an active debrief never lands in
    # captured_items (debrief takes priority over quick-capture).
    try:
        t = vc.transcribe_audio(audio_path)
    except Exception as exc:
        log.error("[voice] transcription error: %s", exc)
        await thinking.edit_text(f"⚠️ Capture failed: {exc}")
        return
    finally:
        import os
        try:
            os.unlink(audio_path)
        except OSError:
            pass
    timings["transcribed_ms"] = round((time.monotonic() - t0) * 1000)

    if not t.get("ok"):
        err = _escape(t.get("error", "Unknown error"))
        await thinking.edit_text(f"⚠️ Voice capture failed: {err}", parse_mode="MarkdownV2")
        return

    transcript = (t.get("text") or "").strip()
    if not transcript:
        await thinking.edit_text(
            "⚠️ Transcription produced no text — audio may be silent or too short\\.",
            parse_mode="MarkdownV2",
        )
        return
    duration = float(t.get("duration") or 0.0)

    def _log_timing(used_llm: bool | None) -> None:
        timings["first_reply_ms"] = round((time.monotonic() - t0) * 1000)
        if used_llm:
            timings["llm_reply_ms"] = timings["first_reply_ms"]
        log.info("[voice-timing] %s", timings)

    # Active debrief always continues, regardless of what this voice note says.
    session = de.get_active_session(db, update.effective_chat.id)
    if session is not None:
        debrief_result = await de.route_debrief_interaction(
            db, update.effective_chat.id, transcript,
            audio_file=audio_path, confidence=t.get("language_probability"),
        )
        timings["routed_ms"] = timings["transcribed_ms"]
        await thinking.edit_text(debrief_result["reply"])
        _log_timing(debrief_result.get("used_llm"))
        return

    # No active session — classify for capture AND score debrief intent
    # together, so a rich reflective narrative isn't silently boxed into a
    # quick-capture card just because it happened to match a keyword rule.
    voice_type, confidence = vc.classify_text(transcript)
    tier = de.score_debrief_intent(transcript, voice_type, confidence)
    timings["routed_ms"] = round((time.monotonic() - t0) * 1000)

    if tier == "high":
        debrief_result = await de.route_debrief_interaction(
            db, update.effective_chat.id, transcript,
            audio_file=audio_path, confidence=t.get("language_probability"),
            force_start=True,
        )
        await thinking.edit_text(debrief_result["reply"])
        _log_timing(debrief_result.get("used_llm"))
        return

    if tier == "moderate":
        # Staged as needs_decision — invisible to every real capture consumer
        # until the Captain resolves it via the buttons below.
        saved = vc.save_capture(
            db, transcript, voice_type, confidence,
            update.effective_chat.id, msg.message_id, duration, audio_path,
            processing_status="needs_decision",
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗣 Start Debrief",   callback_data=f"vd|debrief|{saved['id']}"),
                InlineKeyboardButton("📋 Save as Capture", callback_data=f"vd|capture|{saved['id']}"),
            ],
            [InlineKeyboardButton("✖ Cancel", callback_data=f"vd|cancel|{saved['id']}")],
        ])
        await thinking.edit_text(
            "Captain, this sounds more like a debrief than a quick capture\\.\n\n"
            "Would you like to start a debrief\\?",
            parse_mode="MarkdownV2", reply_markup=keyboard,
        )
        _log_timing(used_llm=False)
        return

    # tier == "low" — existing capture flow, unchanged.
    saved = vc.save_capture(
        db, transcript, voice_type, confidence,
        update.effective_chat.id, msg.message_id, duration, audio_path,
    )
    reply, keyboard = _build_capture_reply(saved["id"], voice_type, confidence, duration, transcript)
    await thinking.edit_text(reply, parse_mode="MarkdownV2", reply_markup=keyboard)
    _log_timing(used_llm=False)
    log.info("[voice] captured id=%s type=%s conf=%d%%", str(saved["id"])[:8], voice_type, int(confidence * 100))


# ── Debrief commands ──────────────────────────────────────────────────────────

async def cmd_debrief_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/debrief_close — explicit escape hatch, force-closes the active debrief
    regardless of natural-language close-phrase detection or LLM inference."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable.")
        return

    from telegram_bots.xo import debrief_engine as de
    session = de.get_active_session(db, update.effective_chat.id)
    if not session:
        await update.message.reply_text("No active debrief session, Captain.")
        return

    turns = de.fetch_turns(db, session["id"])
    log_row = await de.close_session(db, session, turns)
    await update.message.reply_text(de.format_log_reply(log_row))


async def cmd_debrief_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/debrief_weekly — manual trigger for the weekly debrief digest (Phase 6)."""
    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return
    from intelligence.captains_brief import generate_weekly_debrief_digest
    text = await asyncio.get_event_loop().run_in_executor(None, generate_weekly_debrief_digest)
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_voice_capture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses on voice capture confirmations."""
    query = update.callback_query
    await query.answer()

    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
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
            db.table("captured_items").update({
                "classification": "mission",
                "importance":     "high",
                "requires_review": True,
            }).eq("id", capture_id).execute()
            await query.edit_message_text(
                "🚀 Marked as *Mission Idea*\\.\n"
                "Review in LCARS Portal → Capture Inbox to promote to active mission\\.",
                parse_mode="MarkdownV2",
            )

        elif action == "note":
            db.table("captured_items").update({
                "classification": "reference",
                "importance":     "medium",
            }).eq("id", capture_id).execute()
            await query.edit_message_text(
                "📋 Saved as *Note*\\. In LCARS Portal → Capture Inbox\\.",
                parse_mode="MarkdownV2",
            )

    except Exception as exc:
        log.error("[voice-cb] %s failed: %s", action, exc)
        await query.edit_message_text(f"⚠️ Action failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


async def handle_voice_debrief_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resolves the moderate-tier 'sounds like a debrief?' buttons.

    The row is staged with processing_status='needs_decision' (invisible to
    every real capture consumer) until one of these three outcomes:
      - debrief: staged row deleted outright, a real debrief session starts
      - capture: row transitions to 'pending' — only now is it a real capture
      - cancel:  row dismissed, same as a normal capture dismiss
    Exactly one storage location at any time — no voice note ever enters
    both workflows.
    """
    query = update.callback_query
    await query.answer()

    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return

    parts = query.data.split("|")  # vd|action|capture_id
    if len(parts) != 3:
        return
    _, action, capture_id = parts

    db = _get_supabase()
    if not db:
        await query.edit_message_text("⚠️ Supabase unavailable.")
        return

    row_result = db.table("captured_items").select("*").eq("id", capture_id).execute()
    if not row_result.data:
        await query.edit_message_text("⚠️ That capture no longer exists.")
        return
    row = row_result.data[0]

    try:
        if action == "cancel":
            db.table("captured_items").update({"processing_status": "dismissed"}) \
              .eq("id", capture_id).execute()
            await query.edit_message_text("Dismissed.")
            return

        if action == "capture":
            db.table("captured_items").update({"processing_status": "pending"}) \
              .eq("id", capture_id).execute()
            summary = json.loads(row.get("summary") or "{}")
            voice_type = summary.get("voice_type", "unknown")
            confidence = float(summary.get("confidence", 0.5))
            duration = float(summary.get("duration_s", 0.0))
            reply, keyboard = _build_capture_reply(
                capture_id, voice_type, confidence, duration, row.get("raw_text", ""),
            )
            await query.edit_message_text(reply, parse_mode="MarkdownV2", reply_markup=keyboard)
            return

        if action == "debrief":
            from telegram_bots.xo import debrief_engine as de
            transcript = row.get("raw_text", "")
            db.table("captured_items").delete().eq("id", capture_id).execute()
            result = await de.start_session_with_first_turn(db, update.effective_chat.id, transcript)
            await query.edit_message_text(result["reply"])
            return

    except Exception as exc:
        log.error("[voice-debrief-cb] %s failed: %s", action, exc)
        await query.edit_message_text(f"⚠️ Action failed: {exc}")


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


async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick capture: /note <content>  — writes to captured_items as a reference."""
    content = " ".join(context.args or []).strip()
    if not content:
        await update.message.reply_text(
            "Usage: /note &lt;content&gt;\nExample: /note Follow up on sleep tracker calibration",
            parse_mode="HTML",
        )
        return

    try:
        db = _get_supabase()
        db.table("captured_items").insert({
            "source": "telegram-xo-note",
            "classification": "reference",
            "raw_text": content,
            "processing_status": "pending",
        }).execute()
        await update.message.reply_text(
            f"✅ <b>Note captured</b>\n<i>{_escape(content[:200])}</i>",
            parse_mode="HTML",
        )
        log.info("[note] captured %d chars", len(content))
    except Exception as exc:
        log.error("[note] failed: %s", exc)
        await update.message.reply_text(f"⚠️ Capture failed: {str(exc)[:120]}")


async def cmd_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Red-team / challenge advisory: /challenge <question>  — adversarial review."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /challenge &lt;question or plan&gt;\nExample: /challenge My plan to take 2 weeks off next month",
            parse_mode="HTML",
        )
        return

    question = " ".join(args).strip()
    await _run_advisory(update, "Challenge Assessment", ["--action", "challenge", "--question", question],
                        "⚙️ Running red-team challenge…")


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    # Captain intelligence — primary daily interface
    ("captain",         "Narrative: what changed, why it matters, what to do"),
    ("learning",        "Learning health, compliance, insights, leadership candidates"),
    ("patterns",        "Operational Pattern Library: reusable engineering process knowledge"),
    ("pending",         "Captain attention queue + quick outcome capture"),
    # Intelligence
    ("brief",           "Intelligence brief on demand"),
    # Missions & capture
    ("missions",        "Active missions  e.g. /missions active  or  /missions blocked"),
    ("note",            "Quick capture  e.g. /note Follow up on sleep tracker"),
    # Advisory
    ("advise",          "Advisory consult (full officer panel)  e.g. /advise What to focus this week?"),
    ("challenge",       "Red-team a plan or decision  e.g. /challenge My plan to take 2 weeks off"),
    # Daily debrief
    ("debrief_close",   "Force-close the active debrief and get today's log"),
    ("debrief_weekly",  "Weekly debrief digest — recurring stressors, ideas, open loops"),
    # Health & recovery
    ("recovery_pulse",  "Log a pulse (energy → nervous system → body signals)"),
    ("recovery_status", "Today's confidence bar + pulse ledger"),
    ("log_activity",    "Log activity  e.g. /log_activity walk 30 light"),
    ("log_weight",      "Log weight  e.g. /log_weight 82.5"),
    # System
    ("dispatch",        "Manual XO dispatch check"),
    ("restart_bots",    "Restart starfleet services  e.g. /restart_bots all"),
    ("db_status",       "Supabase connectivity test"),
    ("daily",           "Captain's daily picture  e.g. /daily  or  /daily eod"),
    ("start",           "XO introduction and quick-start"),
    ("help",            "Commands + proactive schedule"),
]


async def _post_init(app) -> None:
    """Register the command menu inside the running event loop."""
    from telegram import BotCommand
    await app.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in _BOT_COMMANDS])
    log.info("[startup] Telegram command menu registered (%d commands)", len(_BOT_COMMANDS))


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Belt-and-suspenders: no handler in this file previously had a backstop,
    so any exception outside an individual handler's own try/except vanished
    with no trace. Logs the full exception so a silent-to-the-Captain failure
    is at least diagnosable via journalctl. Does not attempt to reply — the
    update may be partial or missing depending on where the error occurred."""
    log.exception("[unhandled] %s", context.error)


def main() -> None:
    log.info("XO Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_error_handler(_on_error)

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
    app.add_handler(CommandHandler("signals",              cmd_signals))
    app.add_handler(CommandHandler("themes",              cmd_themes))
    app.add_handler(CommandHandler("source_status",       cmd_source_status))
    app.add_handler(CommandHandler("operating_picture",   cmd_operating_picture))
    app.add_handler(CommandHandler("advise",              cmd_advise))
    app.add_handler(CommandHandler("challenge",           cmd_challenge))
    app.add_handler(CommandHandler("note",                cmd_note))
    app.add_handler(CommandHandler("missions",            cmd_mission_list))
    app.add_handler(CommandHandler("log_activity",    cmd_log_activity))
    app.add_handler(CommandHandler("log_weight",      cmd_log_weight))
    app.add_handler(CommandHandler("db_status",       cmd_db_status))
    app.add_handler(CommandHandler("dispatch",        cmd_dispatch))
    app.add_handler(CommandHandler("brief",           cmd_brief))
    app.add_handler(CommandHandler("daily",           cmd_daily))
    app.add_handler(CommandHandler("learning",        cmd_learning))
    app.add_handler(CommandHandler("patterns",        cmd_patterns))
    app.add_handler(CommandHandler("captain",         cmd_captain))
    app.add_handler(CommandHandler("pending",         cmd_pending))
    app.add_handler(CommandHandler("restart_bots",    cmd_restart_bots))
    app.add_handler(CommandHandler("debrief_close",   cmd_debrief_close))
    app.add_handler(CommandHandler("debrief_weekly",  cmd_debrief_weekly))
    app.add_handler(CallbackQueryHandler(handle_pulse_callback,         pattern=r"^pl\|"))
    app.add_handler(CallbackQueryHandler(handle_outcome_callback,       pattern=r"^oc\|"))
    app.add_handler(CallbackQueryHandler(handle_voice_capture_callback, pattern=r"^vc\|"))
    app.add_handler(CallbackQueryHandler(handle_voice_debrief_decision_callback, pattern=r"^vd\|"))
    app.add_handler(MessageHandler(filters.VOICE,                   cmd_voice_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
