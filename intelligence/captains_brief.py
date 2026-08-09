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

# ADR-024 fix #5 (RESIL-INFRA narrative synthesis) — guarded import so a
# problem in the infra-verification module degrades that one section, never
# the whole brief.
try:
    from core.platform.infra_narrative import generate_infra_narrative
except Exception:  # pragma: no cover — import-time guard, not a runtime path
    generate_infra_narrative = None  # type: ignore[assignment]

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

def _sb_request(table: str, query: str = "") -> list[dict]:
    """Raw fetch — raises on any failure (network/HTTP/parse). Used where a
    failed query must NOT be treated the same as a query that succeeded and
    found nothing (USS-TJR-MSN-0339 WP4 — MSN-0338 §8 Gap #1: the midday job
    was silently suppressing every brief because a schema-mismatch query
    failure and 'genuinely zero signals' looked identical)."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise RuntimeError("Supabase not configured (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY unset)")
    url = f"{_SUPABASE_URL}/rest/v1/{table}{'?' + query if query else ''}"
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def _sb_get(table: str, query: str = "") -> list[dict]:
    """Best-effort fetch — swallows failures and returns []. Only for optional/
    decorative data (missions, health, recovery, knowledge counts) where a
    Supabase hiccup should degrade that section, not break the whole brief."""
    try:
        return _sb_request(table, query)
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
        f"&limit={limit}&select=mission_id,title,status,priority",
    )


def _get_todays_health() -> Optional[dict]:
    today = date.today().isoformat()
    rows = _sb_get(
        "captains_log_entries",
        f"log_date=eq.{today}&limit=1"
        f"&select=captain_capacity_rating,energy,pain_score,sleep_hours,health_status",
    )
    return rows[0] if rows else None


def _get_recovery_status() -> Optional[dict]:
    rows = _sb_get("recovery_confidence_today", "limit=1")
    return rows[0] if rows else None


def _get_infra_verification() -> Optional[dict]:
    """ADR-024 fix #5 — RESIL-INFRA narrative synthesis. Returns None (section
    omitted) whenever verification hasn't run or the module isn't available;
    never treated as evidence the platform is healthy."""
    if generate_infra_narrative is None:
        return None
    try:
        return generate_infra_narrative()
    except Exception as exc:
        log.warning("Infra verification narrative failed: %s", exc)
        return None


def _get_content_review_queue(limit: int = 5) -> list[dict]:
    """Content pipeline items awaiting the Captain's own review/publish
    decision — the intelligence-to-writing loop, distinct from RESIL-EXT's
    intelligence signals. 2026-07-18 audit: this pipeline had produced real
    drafts that were never surfaced anywhere, so nobody knew to look."""
    return _sb_get(
        "comms_content",
        "status=in.(draft,review,ready_to_publish)&order=draft_generated_at.desc.nullslast"
        f"&limit={limit}&select=title,pillar,status,draft_generated_at",
    )


def _get_todays_morning_brief_text() -> Optional[str]:
    """Part 1 item 2 (2026-08-09 Telegram usefulness design): fetch this
    morning's already-persisted brief text so the EOD summary can detect
    same-day repeats (Content Review / Platform Health) without
    re-deriving state. Best-effort — a lookup failure just means repeats
    render normally, same as pre-fix behaviour, never breaks the brief."""
    today = date.today().isoformat()
    rows = _sb_get(
        "captains_daily_briefs",
        f"brief_date=eq.{today}&brief_type=eq.morning&order=generated_at.desc"
        f"&limit=1&select=brief_text",
    )
    return rows[0].get("brief_text") if rows else None


def _get_recent_debrief_logs(days: int = 7) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    return _sb_get(
        "debrief_logs",
        f"log_date=gte.{since}&order=log_date.desc"
        f"&select=title,key_themes,stressors,energy_sources,open_loops,"
        f"ideas_captured,decisions_emerging,change_talk,follow_up_candidate,log_date",
    )


def _get_knowledge_platform_summary() -> dict:
    """USS-TJR-MSN-0207A: counts from the document processing pipeline
    (processing_documents). Each query fetches only `id` and takes len() —
    fine at this table's current scale (tens of rows), matching how other
    fetchers in this module read full rows rather than requesting a
    PostgREST exact count header."""
    awaiting_review = len(_sb_get(
        "processing_documents",
        "status=eq.awaiting_review&review_decision=is.null&select=id",
    ))
    needs_followup = len(_sb_get(
        "processing_documents", "review_status=eq.awaiting_followup&select=id",
    ))
    failed = len(_sb_get("processing_documents", "status=eq.failed&select=id"))
    permanently_failed = len(_sb_get(
        "processing_documents", "status=eq.permanently_failed&select=id",
    ))
    excluded = len(_sb_get("processing_documents", "status=eq.excluded&select=id"))
    return {
        "awaiting_review": awaiting_review,
        "needs_followup": needs_followup,
        "failed": failed,
        "permanently_failed": permanently_failed,
        "excluded": excluded,
    }


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


def _derive_risk_label(row: dict) -> str:
    """intelligence_events has never had a risk_rating column (USS-TJR-MSN-0339
    WP4 — MSN-0338 §8 Gap #1) — derive an equivalent HIGH/MEDIUM/LOW label from
    the real scoring columns (rank_score, operational_relevance) instead."""
    try:
        rank = float(row.get("rank_score") or 0)
    except (TypeError, ValueError):
        rank = 0.0
    try:
        relevance = float(row.get("operational_relevance") or 0)
    except (TypeError, ValueError):
        relevance = 0.0
    if rank >= 75 or relevance >= 0.85:
        return "HIGH"
    if rank >= 50 or relevance >= 0.60:
        return "MEDIUM"
    return "LOW"


def _with_risk_label(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["risk_rating"] = _derive_risk_label(row)
    return rows


def _get_new_signals_since(since_iso: str) -> list[dict]:
    """Raises on a genuine Supabase fetch failure (via _sb_request) — the
    caller (check_midday_signals, via scheduler.py's _midday_check_job, which
    already wraps this in its own try/except) must not treat a failed query
    the same as a query that succeeded and found zero signals."""
    rows = _sb_request(
        "intelligence_events",
        f"collected_at=gte.{since_iso}&suppressed=eq.false"
        f"&rank_score=gte.50"
        f"&order=rank_score.desc&limit=10"
        f"&select=raw_title,event_type,geography,operational_relevance,confidence,rank_score",
    )
    return _with_risk_label(rows)


def _get_recent_signals(hours: int = 24) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since}&suppressed=eq.false"
        f"&order=rank_score.desc&limit=5"
        f"&select=raw_title,event_type,geography,operational_relevance,confidence,rank_score",
    )
    return _with_risk_label(rows)


# ── Formatting helpers ────────────────────────────────────────────────────────

# Part 1 item 4 (2026-08-09 Telegram usefulness design): unify the three
# separate severity vocabularies that had grown independently — risk
# (🔴🟡🟢⚪), mission priority (🔥⚡📌📎), capacity (🟢🟡🔴 inverted) — into one
# shared red/yellow/green/none grammar used everywhere in Telegram-facing
# text. 🔴 = urgent/bad, 🟡 = caution/medium, 🟢 = fine/good, ⚪ = unknown/none.
_SEVERITY_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "🟢", "none": "⚪"}


def _severity_emoji(level: str) -> str:
    return _SEVERITY_EMOJI.get((level or "none").lower(), _SEVERITY_EMOJI["none"])


def _risk_emoji(risk: str) -> str:
    level = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get((risk or "").upper())
    return _severity_emoji(level or "none")


def _priority_label(p: str) -> str:
    """Mission priority P0-P3 mapped onto the same red/yellow/green/none
    scale used by risk and capacity, replacing the previous separate
    🔥⚡📌📎 vocabulary."""
    level = {"P0": "red", "P1": "yellow", "P2": "green", "P3": "none"}.get((p or "").upper())
    return _severity_emoji(level or "none")


def _rating_emoji(rating) -> str:
    """captains_log_entries.captain_capacity_rating is a Green/Amber/Red
    text rating, not a 0-100 score - the prior code queried a capacity_score
    column that never existed on this table, causing every brief to silently
    400 on this fetch and render the CAPACITY block as empty."""
    return _severity_emoji({"green": "green", "amber": "yellow", "red": "red"}.get((rating or "").lower(), "none"))


def _confidence_bar(pct) -> str:
    try:
        p = int(pct)
    except (TypeError, ValueError):
        p = 0
    filled = max(0, min(10, p // 10))
    return "█" * filled + "░" * (10 - filled)


def _now_aest() -> datetime:
    return datetime.now(_AEST)


def _relative_age(timestamp: Optional[str]) -> str:
    """Part 1 item 3 (2026-08-09 Telegram usefulness design): a coarse
    relative-age label ("today" / "3 days old" / "4 weeks old") for a
    Content Review item's draft_generated_at, so a draft that has sat for
    weeks doesn't render identically to one generated an hour ago."""
    if not timestamp:
        return "age unknown"
    try:
        ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "age unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - ts).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day old"
    if days < 14:
        return f"{days} days old"
    weeks = days // 7
    return f"{weeks} week{'s' if weeks != 1 else ''} old"


def _truncate_clean(text: str, limit: int) -> str:
    """Truncate at a word boundary with an ellipsis, never mid-word - a bare
    text[:limit] slice was cutting narratives off mid-sentence (sometimes
    mid-word), and since the action-line the infra-narrative prompt now
    requires comes last, that was consistently the part getting eaten."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _format_infra_block(infra: Optional[dict], morning_text: Optional[str] = None) -> list[str]:
    """Shared Platform Health renderer (Part 1 item 2: de-dupe the block that
    was copy-pasted verbatim between generate_morning_brief() and
    generate_eod_summary()). `morning_text`, when supplied (EOD only), is
    this morning's already-persisted brief text — if today's narrative was
    already shown there, the header is marked "(unchanged since this
    morning)" instead of silently re-rendering the identical warning."""
    if not infra or infra.get("state") != "unsure":
        return []
    narrative = _truncate_clean(infra["narrative"], 700)
    unchanged = bool(morning_text) and narrative in morning_text
    suffix = " <i>(unchanged since this morning)</i>" if unchanged else ""
    return [
        f"<b>🛰 PLATFORM HEALTH</b>{suffix}",
        f"  ⚠️ {narrative}",
        "",
    ]


def _format_content_review_block(content_queue: list[dict], morning_text: Optional[str] = None) -> list[str]:
    """Shared Content Review renderer (Part 1 item 2: de-dupe the block that
    was copy-pasted verbatim between generate_morning_brief() and
    generate_eod_summary()). Each item now also shows its age (item 3).
    `morning_text`, when supplied (EOD only), is this morning's already-
    persisted brief text — if every title shown here already appeared
    there, the header is marked "(unchanged since this morning)" instead of
    silently re-listing an identical queue."""
    if not content_queue:
        return []
    titles = [c.get("title") or "(untitled)" for c in content_queue]
    unchanged = bool(morning_text) and all(t in morning_text for t in titles)
    suffix = " <i>(unchanged since this morning)</i>" if unchanged else ""
    lines = [f"<b>✍️ CONTENT REVIEW ({len(content_queue)})</b>{suffix}"]
    for c in content_queue:
        pillar = (c.get("pillar") or "").replace("_", " ") or "—"
        age = _relative_age(c.get("draft_generated_at"))
        lines.append(
            f"  📝 <b>{c.get('title') or '(untitled)'}</b>  [{c.get('status', '?')} · {pillar} · {age}]"
        )
    lines.append("")
    return lines


# ── Brief generators ──────────────────────────────────────────────────────────

def generate_morning_brief() -> str:
    now = _now_aest()
    brief = _get_latest_ori_brief()
    missions = _get_active_missions(limit=5)
    health = _get_todays_health()
    recovery = _get_recovery_status()
    signals = _get_recent_signals(hours=24)
    infra = _get_infra_verification()
    content_queue = _get_content_review_queue()

    lines = [
        f"<b>☀️ MORNING BRIEF — {now.strftime('%A %d %B %Y')}</b>",
        f"<i>Stardate {now.strftime('%Y.%j')} · {now.strftime('%H:%M')} AEST</i>",
        "",
    ]

    # Capacity block
    if health:
        cap = health.get("captain_capacity_rating") or "?"
        pain = health.get("pain_score", 0)
        energy = health.get("energy", "?")
        sleep = health.get("sleep_hours", "?")
        lines += [
            "<b>⚡ CAPACITY</b>",
            f"  {_rating_emoji(cap)} Capacity <b>{cap}</b>  ·  Pain {pain}"
            f"  ·  Energy {energy}  ·  Sleep {sleep}h",
            "",
        ]
    elif recovery and recovery.get("pulses_completed", 0) > 0:
        conf = recovery.get("recovery_confidence", 0)
        signals_str = [
            s for s in (
                f"Energy {recovery['latest_energy'].capitalize()}"
                if recovery.get("latest_energy") else None,
                f"NS {recovery['latest_nervous_system'].capitalize()}"
                if recovery.get("latest_nervous_system") else None,
                f"Body {recovery['latest_body_signals'].capitalize()}"
                if recovery.get("latest_body_signals") else None,
            )
            if s
        ]
        lines += [
            "<b>⚡ CAPACITY</b>",
            f"  <code>{_confidence_bar(conf)}</code> Recovery confidence <b>{conf}%</b>",
        ]
        if signals_str:
            lines.append(f"  {' · '.join(signals_str)}")
        lines.append("")
    else:
        lines += [
            "<b>⚡ CAPACITY</b>",
            "  No pulse logged yet — /recovery_pulse to log your morning pulse",
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
                f"  {_truncate_clean(snap, 350)}",
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

    # Platform self-health — only surfaced when something is actually
    # degraded; silence is a valid, positive state (per verification engine
    # design intent, STARSHIP-REDESIGN.md §9). Morning brief is the first
    # of the day, so there is no "unchanged since this morning" to check.
    lines += _format_infra_block(infra)

    # Content pipeline — intelligence-to-writing drafts awaiting the
    # Captain's own review/publish decision. Only shown when non-empty.
    lines += _format_content_review_block(content_queue)

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
    recovery = _get_recovery_status()
    infra = _get_infra_verification()
    content_queue = _get_content_review_queue()
    # Part 1 item 2: fetch this morning's persisted text so repeated blocks
    # below can be marked "(unchanged since this morning)" instead of
    # silently re-rendering identically.
    morning_text = _get_todays_morning_brief_text()

    lines = [
        f"<b>🌙 END-OF-DAY SUMMARY — {now.strftime('%A %d %B')}</b>",
        f"<i>{now.strftime('%H:%M')} AEST</i>",
        "",
    ]

    if health:
        cap = health.get("captain_capacity_rating") or "?"
        pain = health.get("pain_score", 0)
        lines += [
            "<b>⚡ TODAY</b>",
            f"  {_rating_emoji(cap)} Capacity <b>{cap}</b>  ·  Pain {pain}",
            "",
        ]

    if recovery:
        conf = recovery.get("recovery_confidence", 0)
        done = [
            "✅" if recovery.get("morning_done") else "❌",
            "✅" if recovery.get("midday_done") else "❌",
            "✅" if recovery.get("end_of_day_done") else "❌",
            "✅" if recovery.get("evening_done") else "❌",
        ]
        lines += [
            "<b>🔋 RECOVERY PULSES</b>",
            f"  <code>{_confidence_bar(conf)}</code> {conf}%  ·  {' '.join(done)}",
            "  <i>AM · Mid · EOD · PM</i>",
        ]
        signals = [
            s for s in (
                f"NS {recovery['latest_nervous_system'].capitalize()}"
                if recovery.get("latest_nervous_system") else None,
                f"Body {recovery['latest_body_signals'].capitalize()}"
                if recovery.get("latest_body_signals") else None,
            )
            if s
        ]
        if signals:
            lines.append(f"  {' · '.join(signals)}")
        lines.append("")

    if missions:
        lines.append("<b>🎯 MISSIONS</b>")
        for m in missions:
            p = _priority_label(m.get("priority", ""))
            lines.append(
                f"  {p} {m.get('title', '—')}  [{m.get('status', '?')}]"
            )
        lines.append("")

    lines += _format_infra_block(infra, morning_text)
    lines += _format_content_review_block(content_queue, morning_text)

    lines += [
        "<b>📝 LOG YOUR DAY</b>",
        "  Reply <code>/log</code> to record today's reflection",
        "",
        "🤖 <i>XO · Starship Endeavour</i>",
    ]
    return "\n".join(lines)


def generate_knowledge_ops_brief() -> str:
    """USS-TJR-MSN-0207A: daily digest of the document processing pipeline
    (mac-collector -> vm-transfer -> vm-processing -> Knowledge Library
    approval). Telegram-only per Captain's direction — no Slack routing
    for this pipeline's notifications."""
    now = _now_aest()
    kp = _get_knowledge_platform_summary()

    lines = [
        f"<b>📚 KNOWLEDGE PLATFORM — {now.strftime('%A %d %B')}</b>",
        f"<i>{now.strftime('%H:%M')} AEST</i>",
        "",
    ]

    needs_attention = kp["failed"] > 0 or kp["permanently_failed"] > 0
    nothing_pending = (
        kp["awaiting_review"] == 0 and kp["needs_followup"] == 0 and not needs_attention
    )

    if nothing_pending:
        lines += ["✅ All caught up — nothing awaiting your attention.", ""]
    else:
        lines.append("<b>🗂 REVIEW QUEUE</b>")
        lines.append(f"  📥 Awaiting review: <b>{kp['awaiting_review']}</b>")
        lines.append(f"  🔁 Needs follow-up: <b>{kp['needs_followup']}</b>")
        lines.append("")

        if needs_attention:
            lines.append("<b>⚠️ ACTION NEEDED</b>")
            if kp["failed"] > 0:
                lines.append(f"  ❌ Failed (retriable): <b>{kp['failed']}</b>")
            if kp["permanently_failed"] > 0:
                lines.append(
                    f"  🛑 Permanently failed: <b>{kp['permanently_failed']}</b>"
                    "  — worker.py override to force another attempt"
                )
            lines.append("")

    if kp["excluded"] > 0:
        lines.append(f"<i>🚫 {kp['excluded']} document(s) excluded (content eligibility)</i>")
        lines.append("")

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
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
            lines.append(f"  {_truncate_clean(snap, 400)}")

        if themes:
            lines += ["", "<b>📈 EMERGING THEMES</b>"]
            for t in themes[:4]:
                if isinstance(t, str):
                    lines.append(f"  • {t}")
                elif isinstance(t, dict):
                    label = t.get("theme") or t.get("title") or str(t)
                    lines.append(f"  • {label}")

        if fw:
            lines += ["", "<b>👁 FORWARD WATCH</b>", f"  {_truncate_clean(str(fw), 300)}"]
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


def _recurring(items_lists: list, min_count: int = 2, limit: int = 4) -> list[str]:
    """Flatten jsonb string-array debrief_logs fields across sessions, count
    occurrences, keep only items seen in >=min_count distinct sessions —
    signal over volume per the weekly digest spec (don't surface every trend)."""
    counts: dict[str, int] = {}
    for items in items_lists:
        for item in (items or []):
            if isinstance(item, str) and item.strip():
                key = item.strip()
                counts[key] = counts.get(key, 0) + 1
    recurring = sorted((k for k, v in counts.items() if v >= min_count), key=lambda k: -counts[k])
    return recurring[:limit]


def generate_weekly_debrief_digest() -> str:
    """Weekly digest of recurring signal from debrief_logs (Phase 6 of the
    XO Voice Daily Debrief MVP). Deliberately deterministic frequency
    counting, not an LLM summary — reproducible, cheap, and only surfaces
    items recurring across >=2 sessions."""
    now = _now_aest()
    week_start = (now - timedelta(days=6)).strftime("%d %b")
    logs = _get_recent_debrief_logs(days=7)

    lines = [
        "<b>🗒 WEEKLY DEBRIEF DIGEST</b>",
        f"<i>{week_start} – {now.strftime('%d %b %Y')} · {len(logs)} session(s)</i>",
        "",
    ]

    if not logs:
        lines += ["No debrief sessions this week.", "", "🤖 <i>XO · Starship Endeavour</i>"]
        return "\n".join(lines)

    stressors   = _recurring([l.get("stressors") for l in logs])
    energy      = _recurring([l.get("energy_sources") for l in logs])
    ideas       = _recurring([l.get("ideas_captured") for l in logs])
    open_loops  = _recurring([l.get("open_loops") for l in logs])
    commitments = _recurring([l.get("decisions_emerging") for l in logs])

    follow_ups: list[str] = []
    for l in logs:
        fu = (l.get("follow_up_candidate") or "").strip()
        if fu and fu not in follow_ups:
            follow_ups.append(fu)
    follow_ups = follow_ups[:4]

    changes: list[str] = []
    for l in logs:
        ct = (l.get("change_talk") or "").strip()
        if ct and ct not in changes:
            changes.append(ct)
    changes = changes[:3]

    def _section(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"<b>{title}</b>")
            for it in items:
                lines.append(f"  • {it}")
            lines.append("")

    _section("😣 RECURRING STRESSORS", stressors)
    _section("⚡ RECURRING ENERGY SOURCES", energy)
    _section("💡 RECURRING IDEAS", ideas)
    _section("🔁 UNRESOLVED OPEN LOOPS", open_loops)
    _section("✅ COMMITMENTS MADE", commitments)
    _section("👁 WORTH REVISITING", follow_ups)
    _section("📈 MEANINGFUL CHANGES", changes)

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def send_brief(brief_type: str, **kwargs) -> bool:
    """Generate and deliver a brief. Returns True if Telegram delivery succeeded."""
    signals: list[dict] = []
    if brief_type == "morning":
        text = generate_morning_brief()
        # USS-TJR-MSN-0339 WP4: generate_morning_brief() does its own internal
        # signal fetch for display but doesn't return the count — re-fetch here
        # so the persisted signals_count reflects reality instead of always 0
        # (MSN-0338 §8 Gap #1).
        signals = _get_recent_signals(hours=24)
    elif brief_type == "midday":
        signals = kwargs.get("signals", [])
        if not signals:
            log.info("Midday check: no new signals — suppressing brief")
            return True  # Not an error; conditional brief not needed
        text = generate_midday_update(signals)
    elif brief_type == "eod":
        text = generate_eod_summary()
        signals = _get_recent_signals(hours=24)
    elif brief_type == "weekly":
        text = generate_weekly_report()
        signals = _get_recent_signals(hours=24 * 7)
    elif brief_type == "knowledge_ops":
        text = generate_knowledge_ops_brief()
    elif brief_type == "weekly_debrief":
        text = generate_weekly_debrief_digest()
    else:
        log.error("Unknown brief type: %s", brief_type)
        return False
    _persist_brief(brief_type, text, signals_count=len(signals), health=_get_todays_health())
    return _send_telegram(text)


def check_midday_signals(morning_timestamp_iso: str) -> list[dict]:
    """Return new HIGH/MEDIUM signals collected since morning brief."""
    return _get_new_signals_since(morning_timestamp_iso)
