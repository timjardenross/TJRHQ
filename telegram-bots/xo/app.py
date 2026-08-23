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
import re
import subprocess
import sys
import time
import uuid
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

# httpx logs every request at INFO, including the full URL - which for
# python-telegram-bot's polling/send calls means the bot token in plaintext
# on every log line. WARNING still surfaces real failures, just not the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

# ── Telemetry ─────────────────────────────────────────────────────────────────
try:
    from platform_runtime.lib.telemetry import configure_tracing
    configure_tracing("xo-bot")
except Exception:
    pass

from telegram_bots.recovery_officer.engagement_dispatcher import (
    RecoveryStatus,
    get_recovery_status,
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
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase = None

def _get_supabase():
    """Returns the bot's single Supabase client (memoised).

    Prefers the scoped `xo_bot` Postgres role (migration
    0135_xo_bot_scoped_role.sql) — reached via a self-minted JWT, see
    scoped_supabase.py — over the historical `service_role` key
    (SUPABASE_KEY), which bypasses RLS on all 112 public tables even
    though this bot's code only ever touches 13. Falls back to the
    unchanged SUPABASE_KEY/service_role path whenever scoping isn't
    configured (no SUPABASE_JWT_SECRET / XO_BOT_SCOPED_TOKEN yet, or no
    SUPABASE_ANON_KEY for the gateway apikey) — this is the safe default
    today; do not treat a scoping failure as "disable Supabase entirely",
    that would take down every command handler for a hardening step that
    hasn't been provisioned yet. See
    .claude/skills/bot-reviews/fixes-2026-08-09/xo-bot-scoped-role-implemented.md
    for the cutover record and what's still blocking it.
    """
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL:
            log.warning("SUPABASE_URL not set — Supabase disabled")
            return _supabase
        try:
            from telegram_bots.xo import scoped_supabase
        except ImportError:
            scoped_supabase = None
        if scoped_supabase is not None:
            try:
                scoped = scoped_supabase.build_scoped_client(SUPABASE_URL)
            except Exception as exc:
                log.warning("[supabase] scoped xo_bot client construction failed, falling back to service_role: %s", exc)
                scoped = None
            if scoped is not None:
                _supabase = scoped
                log.info("Supabase client initialised — scoped xo_bot role")
                return _supabase
        if not SUPABASE_KEY:
            log.warning("SUPABASE_KEY not set — Supabase disabled")
        else:
            try:
                from supabase import create_client
                _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                log.info("Supabase client initialised — service_role (scoped xo_bot role not configured; "
                         "see xo-bot-scoped-role-implemented.md)")
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
        f"- Pulses: {status.pulses_completed}/3 complete\n"
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


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*XO online* — @Starship\\_endeavour\\_xO\\_bot\n\n"
        f"Chat ID: `{update.effective_chat.id}`\n\n"
        "_Capacity tracking moved to @tjrmindbody\\_capacitybot\\._\n\n"
        "*Intelligence*\n"
        "/brief · /signals · /themes · /source\\_status\n\n"
        "*Ops*\n"
        "/db\\_status · /restart\\_bots\n\n"
        "_Or just talk to me\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*XO — Commands*\n\n"
        "*Intelligence*\n"
        "/brief — latest OR Intelligence Brief \\(risk, events, themes\\)\n"
        "/signals \\[today|high|cyber|all\\] — top intelligence events, last 24\\-48h\n"
        "/themes — emerging themes from the latest ORI intelligence brief\n"
        "/source\\_status — health of intelligence collection sources\n\n"
        "*Capacity Tracking*\n"
        "_Moved to @tjrmindbody\\_capacitybot — /capacity, /deepcheck, /evening, /today, /week, /month, "
        "/capacity\\_patterns, /actions, /therapy\\._\n\n"
        "*Capture*\n"
        "/note \\<text\\> — quick capture \\(e\\.g\\. `/note Follow up on sleep tracker`\\)\n\n"
        "*Advisory*\n"
        "/advise \\<question\\> — full officer panel consult\n"
        "/challenge \\<plan\\> — red\\-team a plan or decision\n\n"
        "*Content*\n"
        "/revs\\_generate \\<brief path\\> \\[formats\\] — REVS: design brief \\-\\> 7 formats "
        "\\(e\\.g\\. `/revs_generate examples/sample_brief.md poster,social`\\)\n\n"
        "*Health*\n"
        "/mood\\_chart — log mood \\(1\\-10 scale\\) with optional context\n\n"
        "*System*\n"
        "/db\\_status — Supabase connectivity test\n"
        "/restart\\_bots \\[slack\\|telegram\\|all\\] — restart starfleet services\n\n"
        "_Or just talk to me — I understand plain English\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_mood_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log mood (1-10 scale) at different times of day with optional context."""
    from telegram_bots.xo.mood_chart import _TOD_LABELS, kb_time_of_day, _current_time_of_day
    tod = _current_time_of_day()
    label = _TOD_LABELS.get(tod, tod)
    await update.message.reply_text(
        f"📊 *Mood Chart*\n\n"
        f"Rate your mood from 1 \\(worst\\) to 10 \\(best\\)\\.\n"
        f"Add optional context about sleep, pain, anxiety, substance use\\.\n\n"
        f"When did you feel this way?",
        parse_mode="MarkdownV2",
        reply_markup=kb_time_of_day(),
    )


# ── MY CAPACITY TODAY (2026-08-21, replaces Recovery Pulse) ──────────────────

async def cmd_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick capacity check-in. See capacity_today.py for the full flow."""
    from telegram_bots.xo import capacity_today
    await update.message.reply_text(
        "MY CAPACITY TODAY\n\nHow is your capacity right now?",
        reply_markup=capacity_today.kb_capacity(),
    )


async def cmd_deepcheck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deeper reflection, standalone (not following a quick check-in)."""
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    saved, row, err = await capacity_today.write_quick_checkin(db, {})
    if not saved or not row:
        await update.message.reply_text(f"⚠️ Could not start deep check-in: {err}")
        return
    await update.message.reply_text(
        "Going deeper.\n\nWhat was the main load — physical, cognitive, sensory, emotional, social, or environmental?",
        reply_markup=capacity_today.kb_deep_load_category(str(row["id"])),
    )


async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    await update.message.reply_text(
        "Evening reflection\n\nDid your capacity improve, stay the same, or decline today?",
        reply_markup=capacity_today.kb_evening_trajectory(),
    )


async def cmd_capacity_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today — show today's check-ins."""
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    rows = await capacity_today.fetch_recent(db, days=0)
    today = datetime.now(_TZ).date().isoformat()
    rows = [r for r in rows if r.get("log_date") == today]
    if not rows:
        await update.message.reply_text("No check-ins logged today yet. /capacity to start one.")
        return
    parts = [capacity_today.render_summary(r) for r in rows if r.get("checkin_type") == "capacity"]
    await update.message.reply_text("\n\n---\n\n".join(parts) if parts else "No capacity check-ins today yet.")


async def cmd_capacity_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    rows = await capacity_today.fetch_recent(db, days=7)
    await update.message.reply_text(capacity_today.render_trend_summary(rows, "WEEKLY CAPACITY REVIEW"))


async def cmd_capacity_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    rows = await capacity_today.fetch_recent(db, days=30)
    await update.message.reply_text(capacity_today.render_trend_summary(rows, "MONTHLY CAPACITY REVIEW"))


async def cmd_capacity_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    rows = await capacity_today.fetch_recent(db, days=30)
    await update.message.reply_text(capacity_today.render_trend_summary(rows, "CAPACITY PATTERNS — LAST 30 DAYS"))


async def cmd_capacity_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    db = _get_supabase()
    rows = await capacity_today.fetch_recent(db, days=30)
    await update.message.reply_text(capacity_today.render_actions_summary(rows))


async def cmd_therapy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram_bots.xo import capacity_today
    await update.message.reply_text(
        "Therapy summary — how far back?",
        reply_markup=capacity_today.kb_therapy_window(),
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
            f"recovery\\_confidence\\_today: {conf}% · {pulses}/3 pulses",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(
            f"⚠️ *Supabase: connected but query failed*\n\n`{_escape(str(exc))}`",
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


_brief_regen_started_at: float | None = None  # monotonic timestamp — cooldown guard, not a completion signal
_BRIEF_REGEN_COOLDOWN_SECONDS = 25 * 60  # a detached Popen can't report back when it's actually done


def _launch_brief_regen_detached() -> None:
    """Kick off `python -m intelligence.scheduler --once` (trigger="on_demand",
    intelligence/scheduler.py:run_once) as a DETACHED background process —
    2026-08-22: this was originally a synchronous subprocess.run() with a
    180s timeout, but a live timed run (2026-08-22, post the collection-
    widening change — 1,193 items vs ~200 before) took ~25 minutes end to
    end, dominated by brief_generator.py's per-item Supabase dedup-check
    loop (event_hash_exists/event_canonical_url_exists/event_title_date_exists,
    one round-trip per item — a real N+1 pattern, not yet fixed) plus the
    now-7-stage Mistral pipeline on top. A 180s timeout would have failed
    on every single call. Fire-and-forget is the honest fix for a chat
    command — blocking Telegram for 20-30 minutes isn't a real option
    either way."""
    subprocess.Popen(
        [sys.executable, "-m", "intelligence.scheduler", "--once"],
        cwd=str(_REPO_ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/brief — shows the latest Captain's Brief digest now, and kicks off a
    fresh regenerate in the background (takes ~15-25 min; run /brief again
    after that to see it)."""
    global _brief_regen_started_at
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return

    now_mono = time.monotonic()
    cooling_down = (
        _brief_regen_started_at is not None
        and (now_mono - _brief_regen_started_at) < _BRIEF_REGEN_COOLDOWN_SECONDS
    )
    if cooling_down:
        await update.message.reply_text("⚙️ A regenerate was started recently and is likely still running — showing the latest available digest for now.")
    else:
        try:
            _launch_brief_regen_detached()
            _brief_regen_started_at = now_mono
            await update.message.reply_text(
                "⚙️ Kicked off a fresh regenerate in the background (~15-25 min — full source "
                "collection + LLM synthesis). Showing the latest available digest below now; "
                "run /brief again once that's had time to land."
            )
        except Exception as exc:
            log.warning("[brief] failed to launch on-demand regenerate: %s", exc)
            await update.message.reply_text("⚠️ Couldn't start a regenerate — showing the last available digest instead.")

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
        # --format markdown gives the CLI's own AdvisoryResponse.to_markdown()
        # (sections, bullets, prose) instead of a raw json.dumps() blob — the
        # default json format was what was actually landing in Telegram before.
        response = await asyncio.get_event_loop().run_in_executor(
            None, _advisory_cli_call, [*cli_args, "--format", "markdown"], timeout)
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
    # Plain text, no parse_mode: response is now GFM markdown (# headers, **bold**),
    # not HTML — HTML parse_mode would show the raw ** / # characters literally,
    # and Telegram's MarkdownV2 is strict enough that unescaped LLM-generated
    # punctuation would risk an outright send failure. Plain text renders the
    # section breaks/bullets/prose fine without either risk.
    await update.message.reply_text(f"{title}\n\n{response[:3800]}")


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
            try:
                from telegram_bots.xo import debrief_engine as de
            except ImportError:
                de = None
                log.warning(
                    "[cmd_message] debrief_engine not present on this deploy — "
                    "degrading to plain LLM reply, no debrief routing available"
                )
            if de is not None:
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


# ── Inline mood chart callbacks ──────────────────────────────────────────────────

async def handle_mood_chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mood chart tap flow: time_of_day → mood_score → optional context."""
    from telegram_bots.xo.mood_chart import (
        parse_cb, kb_mood_score, kb_confirm_or_add_context,
        _TOD_LABELS, _MOOD_EMOJI, write_mood_entry, format_mood_entry
    )

    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("mc|"):
        return

    cb = parse_cb(data)
    tod = cb.get("tod")
    ms = cb.get("ms")  # mood_score as string
    done = cb.get("done") == "1"
    context_flag = cb.get("context") == "1"

    # Step 1: Time of day selected, show mood scale
    if tod and not ms:
        label = _TOD_LABELS.get(tod, tod)
        await query.edit_message_text(
            f"📊 *{_escape(label)}*\n\n"
            f"{_escape('How is your mood? (1=worst · 10=best)')}",
            parse_mode="MarkdownV2",
            reply_markup=kb_mood_score(tod),
        )
        return

    # Step 2: Mood score selected, show confirm or add context
    if tod and ms and not done and not context_flag:
        label = _TOD_LABELS.get(tod, tod)
        mood_int = int(ms)
        mood_emoji = _MOOD_EMOJI.get(mood_int, "?")
        await query.edit_message_text(
            f"📊 *{_escape(label)}*\n"
            f"{mood_emoji} *{mood_int}/10*\n\n"
            f"{_escape('Save now or add context (sleep, pain, anxiety, etc.)?')}",
            parse_mode="MarkdownV2",
            reply_markup=kb_confirm_or_add_context(tod, mood_int),
        )
        return

    # Step 3: Save (minimal) or add context (opens text input flow)
    if done:
        mood_int = int(ms) if ms else 5
        db = _get_supabase()
        saved, err_msg = await write_mood_entry(db, tod, mood_int)
        icon = "✅" if saved else "⚠️"
        label = _TOD_LABELS.get(tod, tod)
        mood_emoji = _MOOD_EMOJI.get(mood_int, "?")
        error_line = f"\n\n_Error: {_escape_strict(err_msg)}_" if err_msg else ""
        await query.edit_message_text(
            f"{icon} *{_escape(label)} logged*\n\n"
            f"{mood_emoji} *{mood_int}/10*"
            f"{error_line}",
            parse_mode="MarkdownV2",
        )
        return

    if context_flag:
        await query.edit_message_text(
            "📝 *Add optional context*\n\n"
            "Send your notes about sleep, pain, anxiety, stress, "
            "substance use, or anything else relevant\\.\n\n"
            "Or reply /done to finish\\.",
            parse_mode="MarkdownV2",
        )
        context.user_data = context.user_data or {}
        context.user_data["mood_entry"] = {"tod": tod, "ms": ms}
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
    try:
        from telegram_bots.xo import debrief_engine as de
    except ImportError:
        de = None
        log.warning(
            "[cmd_voice_note] debrief_engine not present on this deploy — "
            "degrading to plain quick-capture, no active-session check or intent scoring"
        )

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
    # debrief_engine missing (de is None) degrades to plain quick-capture below —
    # no active-session check, no intent scoring, always tier == "low".
    session = de.get_active_session(db, update.effective_chat.id) if de else None
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
    tier = de.score_debrief_intent(transcript, voice_type, confidence) if de else "low"
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
            try:
                from telegram_bots.xo import debrief_engine as de
            except ImportError:
                await query.edit_message_text("⚠️ Debrief is unavailable — the module isn't present on this deploy.")
                return
            transcript = row.get("raw_text", "")
            db.table("captured_items").delete().eq("id", capture_id).execute()
            result = await de.start_session_with_first_turn(db, update.effective_chat.id, transcript)
            await query.edit_message_text(result["reply"])
            return

    except Exception as exc:
        log.error("[voice-debrief-cb] %s failed: %s", action, exc)
        await query.edit_message_text(f"⚠️ Action failed: {exc}")


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
        import uuid
        from datetime import timezone

        db = _get_supabase()
        now_iso = datetime.now(timezone.utc).isoformat()
        db.table("captured_items").insert({
            # Canonical portal envelope (see voice_capture.py's proven insert) —
            # captured_items has no "source" column; source_type is a checked
            # enum (0031b) and source_channel_id/source_message_id/_ts/title
            # are all NOT NULL.
            "id": str(uuid.uuid4()),
            "captured_by": "captain-tjr",
            "captured_at": now_iso,
            "source_type": "channel_message",
            "source_channel_id": "telegram-xo-note",
            "source_message_id": str(update.message.message_id),
            "source_message_ts": str(int(time.time() * 1000)),
            "item_type": "text_note",
            "title": content[:200],
            "classification": "reference",
            "raw_text": content,
            "processing_status": "pending",
        }).execute()
        # Chief Engineer 2026-08-09 EOD alert verification: 'captured_items'
        # had zero record_heartbeat() call sites anywhere in the repo.
        # Non-blocking.
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat("captured_items", status="ok", detail="voice_type=text_note")
        except Exception:
            pass
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


# ── REVS Content Agents ───────────────────────────────────────────────────────
# services/revs-content-agents in this same monorepo (SUOC Platform Registry entry:
# knowledge/SUOC-Platform-Registry.md), but a different local clone
# (/opt/TJRHQ, not this one) - its own venv/deps (Pillow, google-genai,
# Weasyprint, ...) collide with this bot's, so it's shelled out to exactly like
# the advisory CLI above, never imported in-process. Design brief -> 7 formats
# (article/poster/social/worksheet/presentation/podcast/video); each run is
# versioned under outputs/{concept_id}/v{N}/ with a matching asset_manifest.json.

_REVS_ROOT = Path("/opt/TJRHQ/services/revs-content-agents")
_REVS_PYTHON = _REVS_ROOT / "venv" / "bin" / "python"
_REVS_FORMATS = {"article", "poster", "social", "worksheet", "presentation", "podcast", "video"}
_REVS_SUMMARY_RE = re.compile(r"^(\S+) v(\d+): (\d+)/(\d+) format\(s\) -> (.+)$")
# Pending /revs_generate confirmations, keyed by a short id (not the full brief_path -
# Telegram callback_data is capped at 64 bytes, a real path can easily exceed that).
# In-memory only, single-process bot - fine for a confirm step with a short lifetime.
_revs_pending: dict[str, tuple[str, str | None]] = {}


def _revs_generate_call(brief_path: str, formats: str | None, timeout: int) -> tuple[int, str]:
    """Run the REVS pipeline's own CLI as a subprocess (separate venv - see
    module note above). Returns (returncode, combined stdout+stderr)."""
    args = [str(_REVS_PYTHON), "-m", "src.main", "--brief", brief_path, "--output-dir", "outputs"]
    if formats:
        args += ["--formats", formats]
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, cwd=str(_REVS_ROOT),
    )
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


async def _run_revs_generate(reply_fn, brief_path: str, formats: str | None) -> None:
    """Actually run the pipeline and report the result. `reply_fn` is an async
    callable(str) -> None - either update.message.reply_text or query.edit_message_text,
    so this same logic serves both the confirm-callback path and any future direct-run path."""
    try:
        returncode, output = await asyncio.get_event_loop().run_in_executor(
            None, _revs_generate_call, brief_path, formats, 600)
    except subprocess.TimeoutExpired:
        await reply_fn("⚠️ REVS generation timed out (10min).")
        return
    except Exception as exc:
        log.error("[revs] generate failed: %s", exc)
        await reply_fn(f"⚠️ REVS generation failed: {str(exc)[:200]}")
        return

    if returncode != 0:
        await reply_fn(f"⚠️ REVS generation error:\n\n{output[-1500:]}")
        return

    summary_match = None
    for line in reversed(output.splitlines()):
        summary_match = _REVS_SUMMARY_RE.match(line.strip())
        if summary_match:
            break
    if not summary_match:
        await reply_fn(f"✅ Ran, but couldn't parse the summary line:\n\n{output[-1000:]}")
        return

    concept_id, version, ok, total, version_dir = summary_match.groups()
    try:
        manifest = json.loads((_REVS_ROOT / version_dir / "asset_manifest.json").read_text())
        reply = [f"✅ {concept_id} v{version} — {ok}/{total} format(s) in {manifest['duration_seconds']}s"]
        for o in manifest["outputs"]:
            icon = "✅" if o["status"] == "success" else "❌"
            detail = "" if o["status"] == "success" else f" — {o.get('error', '')[:80]}"
            reply.append(f"{icon} {o['format']} ({o['duration_seconds']}s){detail}")
        reply.append(f"\n📁 {version_dir}")
        await reply_fn("\n".join(reply))
    except Exception:
        await reply_fn(f"✅ {concept_id} v{version} — {ok}/{total} format(s)\n📁 {version_dir}")


async def cmd_revs_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate REVS content assets from a design brief. Usage:
    /revs_generate <brief path> [formats]
    Brief path is relative to revs-content-agents/ (e.g. examples/sample_brief.md)
    or absolute. Formats is an optional comma list (e.g. poster,social) - default all 7.
    A cold 7-format run costs real Gemini API spend and can take ~8min; reruns of
    an unchanged brief hit the pipeline's own cache and finish in seconds. Asks for
    confirmation before running, since unlike this bot's other commands this one
    spends real money per invocation."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /revs_generate &lt;brief path&gt; [formats]\n"
            "Example: /revs_generate examples/sample_brief.md\n"
            "Example: /revs_generate examples/sample_brief.md poster,social\n"
            f"Formats: {', '.join(sorted(_REVS_FORMATS))}",
            parse_mode="HTML",
        )
        return

    brief_path, formats = args[0], (args[1] if len(args) > 1 else None)
    if formats:
        unknown = set(formats.split(",")) - _REVS_FORMATS
        if unknown:
            await update.message.reply_text(
                f"⚠️ Unknown format(s): {', '.join(sorted(unknown))}\n"
                f"Choices: {', '.join(sorted(_REVS_FORMATS))}"
            )
            return

    # Path(a) / b discards `a` entirely when `b` is absolute, so this also catches an
    # absolute-path escape attempt, not just relative "../" traversal - resolve() +
    # is_relative_to() below is the actual confinement check either way.
    check_path = (_REVS_ROOT / brief_path).resolve()
    if not check_path.is_relative_to(_REVS_ROOT.resolve()) or not check_path.exists():
        await update.message.reply_text(f"⚠️ Brief not found or outside {_REVS_ROOT}: `{brief_path}`")
        return
    brief_path = str(check_path)  # use the validated path, not the raw user input, downstream

    request_id = uuid.uuid4().hex[:8]
    _revs_pending[request_id] = (brief_path, formats)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"rg|confirm|{request_id}"),
        InlineKeyboardButton("❌ Cancel",  callback_data=f"rg|cancel|{request_id}"),
    ]])
    await update.message.reply_text(
        f"Generate REVS content from `{brief_path}`" + (f" ({formats})" if formats else " (all 7 formats)")
        + "?\nA cold run costs real Gemini API spend and can take several minutes; "
          "reruns of an unchanged brief hit the cache and are fast/cheap.",
        reply_markup=keyboard,
    )


async def handle_mission_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mission status-change approval/dismiss buttons sent by the Attention Engine."""
    query = update.callback_query
    await query.answer()

    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return

    parts = query.data.split("|")  # ms|action|mission_id[|event_id]
    if len(parts) < 3:
        return
    _, action, mission_id = parts[0], parts[1], parts[2]
    event_id = parts[3] if len(parts) >= 4 else None

    if action == "ack":
        await query.edit_message_text(f"✅ Mission {mission_id} acknowledged.")
        try:
            from core.platform.event_bus import mark_event_status
            if event_id:
                mark_event_status(event_id, "acknowledged")
        except Exception:
            pass
    elif action == "dismiss":
        await query.edit_message_text("🔕 Dismissed.")
        try:
            from core.platform.event_bus import mark_event_status
            if event_id:
                mark_event_status(event_id, "dismissed")
        except Exception:
            pass


async def handle_revs_generate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Confirm/Cancel on a pending /revs_generate request."""
    query = update.callback_query
    await query.answer()

    if not _chat_is_allowed(update.effective_chat.id, TELEGRAM_CHAT_ID):
        return

    parts = query.data.split("|")  # rg|action|request_id
    if len(parts) != 3:
        return
    _, action, request_id = parts

    pending = _revs_pending.pop(request_id, None)
    if pending is None:
        await query.edit_message_text("⚠️ This confirmation expired or was already handled.")
        return

    brief_path, formats = pending
    if action == "cancel":
        await query.edit_message_text(f"❌ Cancelled: `{brief_path}`" + (f" ({formats})" if formats else ""))
        return

    await query.edit_message_text(
        f"⚙️ Generating REVS content from `{brief_path}`" + (f" ({formats})" if formats else "")
        + " — this can take a few minutes on a cold run…"
    )
    await _run_revs_generate(query.edit_message_text, brief_path, formats)


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    # Intelligence
    ("brief",           "Intelligence brief on demand"),
    ("signals",         "Top intelligence events from the last 24-48h  e.g. /signals high"),
    ("themes",          "Emerging themes from the latest ORI intelligence brief"),
    ("source_status",   "Health of intelligence collection sources"),
    # Capture
    ("note",            "Quick capture  e.g. /note Follow up on sleep tracker"),
    # Advisory
    ("advise",          "Advisory consult (full officer panel)  e.g. /advise What to focus this week?"),
    ("challenge",       "Red-team a plan or decision  e.g. /challenge My plan to take 2 weeks off"),
    # Content
    ("revs_generate",   "REVS: brief -> 7 formats  e.g. /revs_generate examples/sample_brief.md"),
    # Health & recovery
    ("mood_chart",      "Log mood (1-10 scale) with optional context"),
    # System
    ("restart_bots",    "Restart starfleet services  e.g. /restart_bots all"),
    ("db_status",       "Supabase connectivity test"),
    ("start",           "XO introduction and quick-start"),
    ("help",            "Commands"),
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


async def _global_auth_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs before every other handler (group -1). Per-handler `_chat_is_allowed`
    checks only existed on 10 of ~36 handlers - this closes that gap platform-wide
    in one place instead of auditing every handler individually. Silent drop
    (no reply) on an unauthorized chat, matching the existing gated handlers'
    behavior - doesn't confirm the bot's existence/command surface to a stranger."""
    chat = update.effective_chat
    if chat is None or not _chat_is_allowed(chat.id, TELEGRAM_CHAT_ID):
        raise ApplicationHandlerStop


def main() -> None:
    log.info("XO Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_error_handler(_on_error)

    app.add_handler(TypeHandler(Update, _global_auth_gate), group=-1)

    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("help",            cmd_help))
    app.add_handler(CommandHandler("mood_chart",      cmd_mood_chart))
    app.add_handler(CommandHandler("signals",         cmd_signals))
    app.add_handler(CommandHandler("themes",          cmd_themes))
    app.add_handler(CommandHandler("source_status",   cmd_source_status))
    app.add_handler(CommandHandler("advise",          cmd_advise))
    app.add_handler(CommandHandler("challenge",       cmd_challenge))
    app.add_handler(CommandHandler("revs_generate",   cmd_revs_generate))
    app.add_handler(CommandHandler("note",            cmd_note))
    app.add_handler(CommandHandler("db_status",       cmd_db_status))
    app.add_handler(CommandHandler("brief",           cmd_brief))
    app.add_handler(CommandHandler("restart_bots",    cmd_restart_bots))
    app.add_handler(CallbackQueryHandler(handle_mood_chart_callback,         pattern=r"^mc\|"))
    app.add_handler(CallbackQueryHandler(handle_voice_capture_callback,      pattern=r"^vc\|"))
    app.add_handler(CallbackQueryHandler(handle_voice_debrief_decision_callback, pattern=r"^vd\|"))
    app.add_handler(CallbackQueryHandler(handle_revs_generate_callback,      pattern=r"^rg\|"))
    app.add_handler(CallbackQueryHandler(handle_mission_approval_callback,   pattern=r"^ms\|"))
    app.add_handler(MessageHandler(filters.VOICE,                   cmd_voice_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
