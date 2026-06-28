"""
Captain's Daily Brief Generator — USS TJR MSN-0200.

Produces concise, Telegram-formatted briefs combining:
- Operational Resilience Intelligence (latest ORI brief)
- Internal data: active missions, health capacity, decisions
- Formatted for Telegram HTML delivery

Brief types: morning | midday | eod | weekly
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("captains-brief")

# Timezone — ZoneInfo available Python 3.9+; fall back to fixed UTC+10 if absent
try:
    from zoneinfo import ZoneInfo
    _AEST = ZoneInfo("Australia/Brisbane")
except ImportError:
    from datetime import timezone as _tz
    _AEST = _tz(timedelta(hours=10))

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_get(table: str, query: str = "") -> list[dict]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    url = f"{_SUPABASE_URL}/rest/v1/{table}{'?' + query if query else ''}"
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.warning("Supabase fetch failed (%s): %s", table, exc)
        return []


# ── Telegram delivery ─────────────────────────────────────────────────────────

def _send_telegram(text: str) -> bool:
    if not _TELEGRAM_TOKEN or not _TELEGRAM_CHAT:
        log.warning("Telegram not configured — printing to stdout")
        print(text)
        return False
    url = f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": _TELEGRAM_CHAT,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as exc:
        log.error("Telegram send failed: %s", exc)
        return False


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _get_latest_ori_brief() -> Optional[dict]:
    rows = _sb_get("intelligence_briefs", "order=generated_at.desc&limit=1")
    return rows[0] if rows else None


def _get_active_missions(limit: int = 8) -> list[dict]:
    return _sb_get(
        "missions",
        f"status=not.in.(Closed,Archived,Idea)&order=priority.asc,updated_at.desc"
        f"&limit={limit}&select=mission_id,title,status,priority,department",
    )


def _get_todays_health() -> Optional[dict]:
    today = date.today().isoformat()
    rows = _sb_get(
        "captains_log_entries",
        f"log_date=eq.{today}&limit=1"
        f"&select=capacity_score,energy,pain_score,sleep_hours,health_status",
    )
    return rows[0] if rows else None


def _persist_brief(brief_type: str, text: str, signals_count: int = 0, health: Optional[dict] = None) -> None:
    """Persist a generated brief to captains_daily_briefs for historical retrieval."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return
    url = f"{_SUPABASE_URL}/rest/v1/captains_daily_briefs"
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = json.dumps({
        "brief_type":      brief_type,
        "brief_date":      date.today().isoformat(),
        "brief_text":      text[:8000],
        "signals_count":   signals_count,
        "health_snapshot": health or {},
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8):
            pass
        log.info("[brief-persist] %s brief stored", brief_type)
    except Exception as exc:
        log.warning("[brief-persist] failed to persist %s brief: %s", brief_type, exc)


def _get_new_signals_since(since_iso: str) -> list[dict]:
    return _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since_iso}&suppressed=eq.false"
        f"&risk_rating=in.(HIGH,MEDIUM)"
        f"&order=rank_score.desc&limit=10"
        f"&select=raw_title,event_type,geography,risk_rating,rank_score",
    )


def _get_recent_signals(hours: int = 24) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since}&suppressed=eq.false"
        f"&order=rank_score.desc&limit=5"
        f"&select=raw_title,event_type,geography,risk_rating,rank_score",
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _risk_emoji(risk: str) -> str:
    return {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
        (risk or "").upper(), "⚪"
    )


def _priority_label(p: str) -> str:
    return {"P0": "🔥", "P1": "⚡", "P2": "📌", "P3": "📎"}.get(
        (p or "").upper(), "  "
    )


def _cap_emoji(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "⚪"
    return "🟢" if s >= 70 else "🟡" if s >= 40 else "🔴"


def _now_aest() -> datetime:
    return datetime.now(_AEST)


# ── Brief generators ──────────────────────────────────────────────────────────

def generate_morning_brief() -> str:
    now = _now_aest()
    brief = _get_latest_ori_brief()
    missions = _get_active_missions(limit=5)
    health = _get_todays_health()
    signals = _get_recent_signals(hours=24)

    lines = [
        f"<b>☀️ MORNING BRIEF — {now.strftime('%A %d %B %Y')}</b>",
        f"<i>Stardate {now.strftime('%Y.%j')} · {now.strftime('%H:%M')} AEST</i>",
        "",
    ]

    # Capacity block
    if health:
        cap = health.get("capacity_score", "?")
        pain = health.get("pain_score", 0)
        energy = health.get("energy", "?")
        sleep = health.get("sleep_hours", "?")
        lines += [
            "<b>⚡ CAPACITY</b>",
            f"  {_cap_emoji(cap)} Score <b>{cap}</b>  ·  Pain {pain}"
            f"  ·  Energy {energy}  ·  Sleep {sleep}h",
            "",
        ]
    else:
        lines += [
            "<b>⚡ CAPACITY</b>",
            "  No health log yet — /health to log your morning pulse",
            "",
        ]

    # Intelligence signals
    if signals:
        lines.append("<b>📡 INTELLIGENCE (24h)</b>")
        for s in signals[:4]:
            lines.append(
                f"  {_risk_emoji(s.get('risk_rating'))} {s.get('raw_title', '—')}"
            )
        lines.append("")
    elif brief:
        snap = brief.get("executive_snapshot") or brief.get("bottom_line") or ""
        if snap:
            lines += [
                "<b>📡 INTELLIGENCE</b>",
                f"  {snap[:350]}",
                f"  <i>Risk: {brief.get('overall_risk', '?')}"
                f" · ORI brief {brief.get('period_end', '')}</i>",
                "",
            ]

    # Active missions
    if missions:
        lines.append("<b>🎯 ACTIVE MISSIONS</b>")
        for m in missions:
            p = _priority_label(m.get("priority", ""))
            lines.append(
                f"  {p} <b>{m.get('title', '—')}</b>  [{m.get('status', '?')}]"
            )
        lines.append("")

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
    return "\n".join(lines)


def generate_midday_update(signals: list[dict]) -> str:
    now = _now_aest()
    lines = [
        f"<b>🔔 MIDDAY UPDATE — {now.strftime('%H:%M')} AEST</b>",
        f"<i>{len(signals)} new signal(s) since morning brief</i>",
        "",
        "<b>📡 NEW SIGNALS</b>",
    ]
    for s in signals[:5]:
        lines.append(
            f"  {_risk_emoji(s.get('risk_rating'))} {s.get('raw_title', '—')}"
        )
    lines += ["", "🤖 <i>XO · Starship Endeavour</i>"]
    return "\n".join(lines)


def generate_eod_summary() -> str:
    now = _now_aest()
    missions = _get_active_missions(limit=8)
    health = _get_todays_health()

    lines = [
        f"<b>🌙 END-OF-DAY SUMMARY — {now.strftime('%A %d %B')}</b>",
        f"<i>{now.strftime('%H:%M')} AEST</i>",
        "",
    ]

    if health:
        cap = health.get("capacity_score", "?")
        pain = health.get("pain_score", 0)
        lines += [
            "<b>⚡ TODAY</b>",
            f"  {_cap_emoji(cap)} Capacity <b>{cap}</b>  ·  Pain {pain}",
            "",
        ]

    if missions:
        lines.append("<b>🎯 MISSIONS</b>")
        for m in missions:
            p = _priority_label(m.get("priority", ""))
            lines.append(
                f"  {p} {m.get('title', '—')}  [{m.get('status', '?')}]"
            )
        lines.append("")

    lines += [
        "<b>📝 LOG YOUR DAY</b>",
        "  Reply <code>/log</code> to record today's reflection",
        "",
        "🤖 <i>XO · Starship Endeavour</i>",
    ]
    return "\n".join(lines)


def generate_weekly_report() -> str:
    now = _now_aest()
    week_start = (now - timedelta(days=6)).strftime("%d %b")
    brief = _get_latest_ori_brief()
    missions = _get_active_missions(limit=10)

    lines = [
        "<b>📊 WEEKLY INTELLIGENCE REPORT</b>",
        f"<i>{week_start} – {now.strftime('%d %b %Y')}</i>",
        "",
    ]

    if brief:
        risk = brief.get("overall_risk", "Unknown")
        snap = brief.get("executive_snapshot") or ""
        themes = brief.get("emerging_themes") or []
        fw = brief.get("forward_watch") or ""

        lines += [
            "<b>🌐 OPERATIONAL RESILIENCE</b>",
            f"  Overall risk: {_risk_emoji(risk)} <b>{risk}</b>",
        ]
        if snap:
            lines.append(f"  {snap[:400]}")

        if themes:
            lines += ["", "<b>📈 EMERGING THEMES</b>"]
            for t in themes[:4]:
                if isinstance(t, str):
                    lines.append(f"  • {t}")
                elif isinstance(t, dict):
                    label = t.get("theme") or t.get("title") or str(t)
                    lines.append(f"  • {label}")

        if fw:
            lines += ["", "<b>👁 FORWARD WATCH</b>", f"  {str(fw)[:300]}"]
        lines.append("")

    if missions:
        lines.append("<b>🎯 ACTIVE MISSIONS</b>")
        for m in missions:
            p = _priority_label(m.get("priority", ""))
            lines.append(
                f"  {p} {m.get('title', '—')}  [{m.get('status', '?')}]"
            )
        lines.append("")

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def send_brief(brief_type: str, **kwargs) -> bool:
    """Generate and deliver a brief. Returns True if Telegram delivery succeeded."""
    signals: list[dict] = []
    if brief_type == "morning":
        text = generate_morning_brief()
    elif brief_type == "midday":
        signals = kwargs.get("signals", [])
        if not signals:
            log.info("Midday check: no new signals — suppressing brief")
            return True  # Not an error; conditional brief not needed
        text = generate_midday_update(signals)
    elif brief_type == "eod":
        text = generate_eod_summary()
    elif brief_type == "weekly":
        text = generate_weekly_report()
    else:
        log.error("Unknown brief type: %s", brief_type)
        return False
    _persist_brief(brief_type, text, signals_count=len(signals), health=_get_todays_health())
    return _send_telegram(text)


def check_midday_signals(morning_timestamp_iso: str) -> list[dict]:
    """Return new HIGH/MEDIUM signals collected since morning brief."""
    return _get_new_signals_since(morning_timestamp_iso)
