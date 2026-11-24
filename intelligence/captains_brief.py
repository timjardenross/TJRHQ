"""
Captain's Daily Brief Generator — USS TJR MSN-0200.

Produces concise, Telegram-formatted briefs combining:
- Operational Resilience Intelligence (latest ORI brief; weekly report uses a
  7-day OSINT roll-up instead — see generate_weekly_report())
- Internal data: health capacity, content pipeline
- Formatted for Telegram HTML delivery

Brief types: morning | midday | eod | weekly
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape as _html_escape
from html import unescape as _html_unescape

# Shared pain vocabulary. Guarded like the other core.* imports here: a problem
# importing it must degrade the pain wording only, never the whole brief.
try:
    from core.health.pain_vocab import describe_pain
except Exception:  # pragma: no cover — import-time guard  # noqa: BLE001 - guarded import (see comment above)
    def describe_pain(pain_state, pain_score=None):  # type: ignore[misc]
        return None

log = logging.getLogger("captains-brief")

# ADR-024 fix #5 (RESIL-INFRA narrative synthesis) — guarded import so a
# problem in the infra-verification module degrades that one section, never
# the whole brief.
try:
    from core.platform.infra_narrative import generate_infra_narrative
except Exception:  # pragma: no cover — import-time guard, not a runtime path  # noqa: BLE001 - guarded import — a problem in the infra-verification module must degrade that one section, never the whole brief (see comment above)
    generate_infra_narrative = None  # type: ignore[assignment]

# 2026-08-22: the daily digest — combines the OSINT/world-news brief above
# with the platform's own multi-domain events (engineering/learning/
# opportunities; health is already covered by _get_capacity_today() above
# via a more specific query) into one LLM narrative. Same guarded-import
# convention as generate_infra_narrative:
# a problem here degrades this one section, never the whole brief.
try:
    from intelligence.brief.daily_digest import build_daily_digest
except Exception:  # pragma: no cover — import-time guard, not a runtime path  # noqa: BLE001 - guarded import — a problem in the daily-digest module must degrade that one section, never the whole brief (see comment above)
    build_daily_digest = None  # type: ignore[assignment]

# Weekly OSINT exec-summary narration (2026-08-10) — reuses the exact same
# shared provider chain as core/platform/infra_narrative.py rather than a
# third bespoke LLM call implementation. Guarded the same way: a problem
# importing the provider chain degrades the two exec-summary sections only
# (they fall back to the raw severity-count display), never the whole brief.
try:
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama
except Exception:  # pragma: no cover — import-time guard, not a runtime path  # noqa: BLE001 - guarded import — a problem in the LLM provider chain must degrade the exec-summary sections only, never the whole brief (see comment above)
    call_gemini = call_mistral = call_ollama = None  # type: ignore[assignment]

# Timezone — ZoneInfo available Python 3.9+; fall back to fixed UTC+10 if absent (approximation: ignores daylight saving)
try:
    from zoneinfo import ZoneInfo
    _AEST = ZoneInfo("Australia/Melbourne")
except ImportError:
    from datetime import timezone as _tz
    _AEST = _tz(timedelta(hours=10))

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# Same env vars core/platform/infra_narrative.py uses for its LLM narration —
# one shared provider-config convention, not a second set of names.
_GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
_MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_WEEKLY_MODEL = os.getenv("OLLAMA_WEEKLY_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")


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
    with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
        return json.loads(resp.read())


def _sb_get(table: str, query: str = "") -> list[dict]:
    """Best-effort fetch — swallows failures and returns []. Only for optional/
    decorative data (missions, health, recovery, knowledge counts) where a
    Supabase hiccup should degrade that section, not break the whole brief."""
    try:
        return _sb_request(table, query)
    except Exception as exc:  # noqa: BLE001 - best-effort fetch for optional/decorative data, already logged (see docstring above — a Supabase hiccup degrades that section, not the whole brief)
        log.warning("Supabase fetch failed (%s): %s", table, exc)
        return []


# ── Telegram delivery ─────────────────────────────────────────────────────────
# Migrated 2026-08-29 onto core/platform/notification_service.py's notify()
# (see tools/check_notification_senders.py) — its chunk=True mode now does
# the same word-boundary splitting this module implemented locally after
# the 2026-08-29 mid-sentence-truncation fix (see git history), so a brief
# longer than one Telegram message still arrives in full across multiple
# messages rather than getting cut off.

_TELEGRAM_MSG_LIMIT = 4096


def _send_telegram(text: str) -> bool:
    if not _TELEGRAM_TOKEN or not _TELEGRAM_CHAT:
        log.warning("Telegram not configured — printing to stdout")
        print(text)
        return False
    from core.platform.notification_service import Transport, notify

    result = notify(text, template="raw", transport=Transport.TELEGRAM, chunk=True)
    if not result.ok:
        log.error("Telegram send failed: %s", result.error)
    return result.ok


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _get_latest_ori_brief() -> dict | None:
    rows = _sb_get("intelligence_briefs", "order=generated_at.desc&limit=1")
    return rows[0] if rows else None


def _get_capacity_today() -> dict | None:
    """MY CAPACITY TODAY (2026-08-22 migration) replaced Recovery Pulse /
    captains_log_entries as the Captain's day-to-day capacity input —
    captains_log_entries stopped being written 2026-06-28, recovery_pulses
    stopped 2026-08-21 (see core/infrastructure/supabase/migrations/0148 +
    0150). capacity_checkins_today is the honest replacement view: a raw
    check-in count + latest reading, no fabricated slot-based percentage
    (that concept doesn't exist under "allow more than one check-in a day,
    never overwrite")."""
    rows = _sb_get("capacity_checkins_today", "limit=1")
    if not rows:
        return None
    row = dict(rows[0])
    # The view exposes only the legacy numeric latest_pain_score. Pain is now
    # captured as "compared with your usual baseline" (pain_state), so read the
    # latest pain_state straight from capacity_checkins (no view change needed).
    today = datetime.now(_AEST).date().isoformat()
    latest = _sb_get(
        "capacity_checkins",
        f"checkin_type=eq.capacity&log_date=eq.{today}&pain_state=not.is.null"
        f"&order=captured_at.desc&limit=1&select=pain_state",
    )
    row["latest_pain_state"] = latest[0].get("pain_state") if latest else None
    return row


def _get_infra_verification() -> dict | None:
    """ADR-024 fix #5 — RESIL-INFRA narrative synthesis. Returns None (section
    omitted) whenever verification hasn't run or the module isn't available;
    never treated as evidence the platform is healthy."""
    if generate_infra_narrative is None:
        return None
    try:
        return generate_infra_narrative()
    except Exception as exc:  # noqa: BLE001 - already logged; infra narrative is optional/degradable per the surrounding contract
        log.warning("Infra verification narrative failed: %s", exc)
        return None


def _get_todays_morning_brief_text() -> str | None:
    """Part 1 item 2 (2026-08-09 Telegram usefulness design): fetch this
    morning's already-persisted brief text so the EOD summary can detect
    same-day repeats (Content Review / Platform Health) without
    re-deriving state. Best-effort — a lookup failure just means repeats
    render normally, same as pre-fix behaviour, never breaks the brief."""
    today = datetime.now(_AEST).date().isoformat()
    rows = _sb_get(
        "captains_daily_briefs",
        f"brief_date=eq.{today}&brief_type=eq.morning&order=generated_at.desc"
        f"&limit=1&select=brief_text",
    )
    return rows[0].get("brief_text") if rows else None


def _get_recent_debrief_logs(days: int = 7) -> list[dict]:
    since = (datetime.now(_AEST).date() - timedelta(days=days)).isoformat()
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


def _collection_coverage_caveat(domain_key: str) -> str | None:
    """HQ V1 Integration QA §21 (Deferred Gap I7): checks the feeding
    collection job's own heartbeat (same domain_heartbeats_latest row HQ
    Status already reads) so a brief's persisted coverage metadata can
    distinguish "collection ran fine" from "collection lagged/failed
    before this brief generated." Mirrors _health_osint_collector_caveat's
    shape. Returns None (no caveat) when the job looks healthy or when
    this check itself can't reach Supabase — never fabricates a claim
    either way on an unreachable status check."""
    rows = _sb_get(
        "domain_heartbeats_latest",
        f"domain_key=eq.{domain_key}&select=status,checked_at&limit=1",
    )
    if not rows:
        return f"{domain_key} status could not be confirmed as of generation time"
    if rows[0].get("status") == "failed":
        return f"{domain_key} reported a failure before this brief generated — evidence may be incomplete"
    return None


def _persist_brief(
    brief_type: str, text: str, signals_count: int = 0, health: dict | None = None,
    evidence_window_hours: int | None = None, collection_caveat: str | None = None,
) -> None:
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
        "brief_date":      datetime.now(_AEST).date().isoformat(),
        "brief_text":      text[:8000],
        "signals_count":   signals_count,
        "health_snapshot": health or {},
        "evidence_window_hours": evidence_window_hours,
        "collection_caveat":     collection_caveat,
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8):  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
            pass
        log.info("[brief-persist] %s brief stored", brief_type)
    except Exception as exc:  # noqa: BLE001 - best-effort brief persistence, already logged as a warning; the brief itself was already generated/sent by this point
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


# Statutory outage registers publish an outage only after it is rectified: confirmation and restoration evidence for analysis and the portal,
# never a live signal. They must not appear as HIGH "live" lines in OTHER SIGNALS or fire a midday alert (24 Nov preview, defect D3).
_RETROSPECTIVE_SOURCE_MARKERS = ("outage register",)


def _drop_retrospective(rows: list[dict]) -> list[dict]:
    return [r for r in rows
            if not any(m in ((r.get("intelligence_source_registry") or {}).get("source_name") or "").lower() for m in _RETROSPECTIVE_SOURCE_MARKERS)]


def _with_risk_label(rows: list[dict]) -> list[dict]:
    rows = _drop_retrospective(rows)
    for row in rows:
        row["risk_rating"] = _derive_risk_label(row)
    return rows


# 2026-11-02 (Captain): GitHub Status incident items are noise in the briefs -
# excluded from every brief signal query. PostgREST value, space URL-encoded.
_EXCLUDE_GITHUB_STATUS = "&raw_title=not.ilike.GitHub%20Status:*"


def _get_new_signals_since(since_iso: str) -> list[dict]:
    """Raises on a genuine Supabase fetch failure (via _sb_request) — the
    caller (check_midday_signals, via scheduler.py's _midday_check_job, which
    already wraps this in its own try/except) must not treat a failed query
    the same as a query that succeeded and found zero signals."""
    rows = _sb_request(
        "intelligence_events",
        f"collected_at=gte.{urllib.parse.quote(since_iso, safe='')}&suppressed=eq.false&signal_status=neq.DUPLICATE"
        f"&rank_score=gte.50"
        f"&raw_title=not.ilike.CVE-*{_EXCLUDE_GITHUB_STATUS}"
        f"&or=(raw_summary.is.null,raw_summary.not.ilike.*CVSSv3*)"
        f"&order=rank_score.desc&limit=10"
        f"&select=raw_title,event_type,geography,operational_relevance,confidence,rank_score,raw_summary,"
        f"intelligence_source_registry(source_name)",
    )
    return _with_risk_label(rows)


def _get_recent_signals(hours: int = 24, limit: int = 12) -> list[dict]:
    """2026-08-13: excludes raw vulnerability-bulletin noise (Captain:
    "I thought we excluded CVEs") — a live brief had all 4 HIGH slots
    filled by generic vendor CVSS bulletins (1 literal CVE-titled, 3
    Fortinet PSIRT advisories with no CVE- prefix but the same templated
    "CVSSv3 Score: X.X ... [CWE-nnn] ..." shape and zero Captain-specific
    relevance). event_type/sector don't distinguish these from real cyber
    incident news (both are 'cyber'/'cyber_security' — a sector-level
    exclusion would also hide genuine breach/ransomware/outage reporting),
    so this matches on the two concrete fingerprints instead: a CVE-*
    title, or a raw_summary in the CVSSv3-bulletin template. The `or=` OR
    on raw_summary explicitly re-admits NULL — PostgREST's `not.ilike`
    alone silently drops NULL rows (NULL NOT ILIKE '%x%' is NULL, not
    true), which would have dropped every event with no raw_summary at
    all, not just the bulletins."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since}&suppressed=eq.false&signal_status=neq.DUPLICATE"
        f"&raw_title=not.ilike.CVE-*{_EXCLUDE_GITHUB_STATUS}"
        f"&or=(raw_summary.is.null,raw_summary.not.ilike.*CVSSv3*)"
        f"&order=rank_score.desc&limit={limit}"
        f"&select=raw_title,event_type,geography,operational_relevance,confidence,rank_score,raw_summary,"
        f"intelligence_source_registry(source_name)",
    )
    return _with_risk_label(rows)


def _format_signal_title(s: dict) -> str:
    """2026-08-13 (Captain: "titles what's actually impacted") — many raw
    titles don't name the impacted product/company at all: "Degraded
    performance for multiple models" turned out to be Anthropic's own
    status feed (source_name via the intelligence_source_registry FK
    embed), with the actual impacted models named in raw_summary, not the
    title. GitHub/Cloudflare-sourced titles already self-identify
    ("GitHub Status: ...") and are left alone; only titles that don't
    already mention the source get it prefixed."""
    title = s.get("raw_title") or "—"
    source = ((s.get("intelligence_source_registry") or {}).get("source_name") or "").strip()
    if not source:
        return title
    label = source.removesuffix(" Status")
    words = [w for w in re.split(r"[^A-Za-z0-9]+", label) if len(w) > 2]
    if any(w.lower() in title.lower() for w in words):
        return title
    return f"{label}: {title}"


def _format_signal_commentary(s: dict) -> str | None:
    """One-line real commentary from raw_summary — never fabricated. The
    enrichment columns meant to hold analysis (analysis_summary,
    enriched_summary) are unpopulated on live data (checked 2026-08-13:
    100% NULL across recent events), so raw_summary — the actual scraped
    description, present on roughly half of events — is the only honest
    source available. Signals without one just show the title; no filler
    text stands in for it."""
    summary = (s.get("raw_summary") or "").strip()
    if not summary:
        return None
    return _truncate_clean(summary, 170)


def _bucket_for_display(s: dict) -> str:
    """2026-09-02 (Platform Health investigation): risk_rating is scored once
    at ingestion and never re-checked against the source feed's own later
    "resolved" update, so a closed incident can sit at HIGH indefinitely in
    every brief until it's re-scored. intelligence_analyst.py now downgrades
    resolved incidents going forward; this is the safety net for events
    already scored HIGH in the DB before that fix shipped. Reuses the same
    is_resolved_incident() phrase-matcher as the scorer, not a second
    heuristic to keep in sync."""
    from intelligence.classification.classifier import is_resolved_incident

    rating = s.get("risk_rating")
    if rating == "HIGH" and is_resolved_incident(s.get("raw_title"), s.get("raw_summary")):
        return "MEDIUM"
    return rating


def _format_signals_block(signals: list[dict], header: str, *, max_high: int = 4, max_medium: int = 3) -> list[str]:
    """Shared HIGH/MEDIUM signal renderer for Morning Brief and EOD Summary
    (2026-08-13, replaces each brief's own flat top-N list). LOW/none-rated
    signals are never shown here — same "only surface what's worth a
    look" principle _format_infra_block already uses."""
    high = [s for s in signals if _bucket_for_display(s) == "HIGH"][:max_high]
    medium = [s for s in signals if _bucket_for_display(s) == "MEDIUM"][:max_medium]
    if not high and not medium:
        return []

    count_bits = []
    if high:
        count_bits.append(f"{len(high)} HIGH")
    if medium:
        count_bits.append(f"{len(medium)} MEDIUM")
    lines = [f"<b>{header}</b> <i>({', '.join(count_bits)})</i>"]
    for s in high + medium:
        lines.append(f"  {_risk_emoji(_bucket_for_display(s))} {_esc(_format_signal_title(s))}")
        commentary = _format_signal_commentary(s)
        if commentary:
            lines.append(f"     <i>{_esc(commentary)}</i>")
    lines.append("")
    return lines


# ── Weekly OSINT roll-up (2026-08-10 weekly report redesign) ──────────────────
#
# generate_weekly_report() used to be built on _get_latest_ori_brief() — a
# single latest-row snapshot from intelligence_briefs. Per Captain's direction
# it's now built on a real 7-day aggregation across both OSINT domains,
# reusing the same table/bucketing pattern as each workbench's own
# "Intelligence Summary" tab (lcars-portal/src/app/api/intelligence-workbench/
# intelligence-summary/route.ts for Tech OSINT, .../health-osint/
# intelligence-summary/route.ts for Health OSINT) rather than inventing a new
# query shape — just windowed to 7 days instead of those routes' single fetch.

def _get_weekly_tech_signals(days: int = 7, limit: int = 1000) -> list[dict]:
    """Tech/Intelligence Workbench roll-up — same table (intelligence_events)
    and confidence field (osint_confidence_level) as intelligence-workbench/
    intelligence-summary/route.ts, windowed to the last `days` days. Unlike
    that route's UI-display cap of 150, `limit` here is set high enough to
    capture a full week's volume (~600 rows observed 2026-08-10) so the
    HIGH/MEDIUM/LOW counts in the weekly report are real totals, not a
    truncated sample."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since}&suppressed=eq.false{_EXCLUDE_GITHUB_STATUS}"
        f"&order=rank_score.desc&limit={limit}"
        f"&select=raw_title,sector,rank_score,osint_confidence_level,collected_at,"
        f"intelligence_source_registry(source_name)",
    )


def _get_weekly_health_signals(days: int = 7, limit: int = 1000) -> list[dict]:
    """Health OSINT Workbench roll-up — same table (health_signals) and
    confidence field (confidence_level) as health-osint/intelligence-summary/
    route.ts, windowed to the last `days` days. `limit` set high enough to
    capture a full week's volume (~320 rows observed 2026-08-10) so the
    HIGH/MEDIUM/LOW counts are real totals, not a truncated sample."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _sb_get(
        "health_signals",
        f"collected_at=gte.{since}&suppressed=eq.false"
        f"&order=rank_score.desc&limit={limit}"
        f"&select=title,health_domain,rank_score,confidence_level,collected_at,"
        f"health_source_registry(source_name)",
    )


def _health_osint_collector_caveat() -> str | None:
    """HQ V1 Integration QA §21/§9 fix: a genuinely quiet health-OSINT week
    and a week where the Sunday 02:00 health_osint_weekly_fetch collector
    silently failed for all 7 days previously rendered identically in this
    report ("No signals collected this week."). Checks the same
    domain_heartbeats_latest row HQ Status already reads for this job —
    no new signal source, just a read of one already-canonical row — and
    returns a short caveat when there's positive evidence of trouble.
    Returns None (no caveat added) when the collector looks healthy or
    when this check itself can't reach Supabase — an unreachable status
    check must not fabricate a claim of failure any more than of health."""
    rows = _sb_get(
        "domain_heartbeats_latest",
        "domain_key=eq.health_osint_weekly_fetch&select=status,checked_at&limit=1",
    )
    if not rows:
        return "collector status could not be confirmed this week — treat an empty section with that in mind"
    status = rows[0].get("status")
    if status == "failed":
        return "the weekly collector reported a failure this week — this may be missing signals, not a genuinely quiet week"
    return None


def _get_weekly_content_activity(days: int = 7, limit: int = 8) -> list[dict]:
    """Content published or moved to review/approval in the last `days` days —
    windows by updated_at (comms_content has no dedicated status-change
    timestamp), for the weekly report only (the daily briefs' own pending-queue
    snapshot was removed 2026-08-13)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _sb_get(
        "comms_content",
        f"status=in.(published,review,ready_to_publish,approved)&updated_at=gte.{since}"
        f"&order=updated_at.desc&limit={limit}&select=title,pillar,status,updated_at",
    )


def _get_weekly_outage_alerts(days: int = 7) -> list[dict]:
    """Durable record of outage-push activity (2026-08-10 fix, XO product
    review finding #5) -- audit_events rows written by intelligence_store.py's
    _maybe_push_outage_alert() (see _log_outage_alert_fired there) whenever
    the outage-severity gate fires and a Telegram push is attempted.
    category='notification'/action='outage_alert_push' distinguishes these
    from the 'mutation'/'approval' audit rows the same shared table already
    carries (migration 0054, core/platform/audit_service.py)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _sb_get(
        "audit_events",
        f"category=eq.notification&action=eq.outage_alert_push&created_at=gte.{since}"
        f"&order=created_at.desc&select=created_at,outcome,details",
    )


def _get_weekly_capacity(days: int = 7) -> dict:
    """captains_log_entries rows across the last `days` days (inclusive of
    today) — a real weekly trend, not the single-day snapshot the daily
    briefs use.

    2026-08-10 fix (XO product review): captains_log_entries stopped being
    written to on 2026-06-28 — this was the one fetcher in the file that
    still trusted it unconditionally, so the weekly Capacity block silently
    rendered "No capacity logs this week" every week regardless of reality.
    Falls back to recovery_pulses, aggregated across the window instead of a
    single day. Returns {"source": "log"|"pulse"|"checkin"|"none", "entries": [...]}
    so the renderer can tell which shape it got.

    2026-09-13 fix (capability-portfolio data-quality pass): both
    captains_log_entries and recovery_pulses have been permanently frozen
    since 2026-06-28/2026-08-21 respectively, so by now this fetcher's first
    two tiers can never return anything real — every week silently rendered
    "No capacity logs or recovery pulses this week", identical to a
    genuinely quiet week, when the truth was "the only two sources this
    function knows how to read stopped being written to months ago." This
    was flagged as a known open gap in this function's own prior comment
    (_get_capacity_today() already made the same cutover for the daily
    briefs back on 2026-08-22; this weekly fetcher just never followed).
    Third tier now reads capacity_checkins (checkin_type='capacity') — the
    live replacement — before finally giving up. "none" is now a real,
    meaningful signal (the Captain logged zero check-ins all week) rather
    than a masked structural failure, since capacity_checkins is written
    interactively by the XO bot on every check-in, not by a dead
    scheduled job."""
    since = (datetime.now(_AEST).date() - timedelta(days=days - 1)).isoformat()
    log_entries = _sb_get(
        "captains_log_entries",
        f"log_date=gte.{since}&order=log_date.asc"
        f"&select=log_date,captain_capacity_rating,energy,pain_score,sleep_hours",
    )
    if log_entries:
        return {"source": "log", "entries": log_entries}

    pulses = _sb_get(
        "recovery_pulses",
        f"log_date=gte.{since}&order=log_date.asc,captured_at.asc"
        f"&select=log_date,pulse_type,energy,nervous_system,body_signals,readiness",
    )
    if pulses:
        return {"source": "pulse", "entries": pulses}

    checkins = _sb_get(
        "capacity_checkins",
        f"checkin_type=eq.capacity&log_date=gte.{since}&order=log_date.asc,captured_at.asc"
        f"&select=log_date,capacity_state,stimulation_state,pain_score,regulation_state",
    )
    if checkins:
        return {"source": "checkin", "entries": checkins}

    return {"source": "none", "entries": []}


def _get_weekly_capacity_v1(days: int = 7) -> dict:
    """captains_log_entries rows across the last `days` days (inclusive of
    today) — a real weekly trend, not the single-day snapshot the daily
    briefs use.

    2026-08-10 fix (XO product review): captains_log_entries stopped being
    written to on 2026-06-28 — this was the one fetcher in the file that
    still trusted it unconditionally, so the weekly Capacity block silently
    rendered "No capacity logs this week" every week regardless of reality.
    Falls back to recovery_pulses, aggregated across the window instead of a
    single day. Returns {"source": "log"|"pulse"|"checkin"|"none", "entries": [...]}
    so the renderer can tell which shape it got.

    2026-09-13 fix (capability-portfolio data-quality pass): both
    captains_log_entries and recovery_pulses have been permanently frozen
    since 2026-06-28/2026-08-21 respectively, so by now this fetcher's first
    two tiers can never return anything real — every week silently rendered
    "No capacity logs or recovery pulses this week", identical to a
    genuinely quiet week, when the truth was "the only two sources this
    function knows how to read stopped being written to months ago." This
    was flagged as a known open gap in this function's own prior comment
    (_get_capacity_today() already made the same cutover for the daily
    briefs back on 2026-08-22; this weekly fetcher just never followed).
    Third tier now reads capacity_checkins (checkin_type='capacity') — the
    live replacement — before finally giving up. "none" is now a real,
    meaningful signal (the Captain logged zero check-ins all week) rather
    than a masked structural failure, since capacity_checkins is written
    interactively by the XO bot on every check-in, not by a dead
    scheduled job."""
    today = datetime.now(_AEST).date()
    since = (today - timedelta(days=days - 1)).isoformat()
    until = today.isoformat()
    # Captain's review (Gate 1): a record dated after today is never a real
    # observation (the live recovery_pulses table holds two rows dated
    # 2099-01-01). Bound every tier above AND drop them again here, so a source
    # that ignores the filter can't leak a future-dated row into the week.
    excluded = 0

    def _kept(rows: list[dict]) -> list[dict]:
        nonlocal excluded
        keep = []
        for r in rows:
            d = str(r.get("log_date") or "")[:10]
            if d and d > until:
                excluded += 1
                continue
            keep.append(r)
        return keep

    def _result(source: str, rows: list[dict]) -> dict:
        out: dict = {"source": source, "entries": rows}
        if excluded:
            out["excluded_future"] = excluded
        return out

    log_entries = _kept(_sb_get(
        "captains_log_entries",
        f"log_date=gte.{since}&log_date=lte.{until}&order=log_date.asc"
        f"&select=log_date,captain_capacity_rating,energy,pain_score,sleep_hours",
    ))
    if log_entries:
        return _result("log", log_entries)

    pulses = _kept(_sb_get(
        "recovery_pulses",
        f"log_date=gte.{since}&log_date=lte.{until}&order=log_date.asc,captured_at.asc"
        f"&select=log_date,pulse_type,energy,nervous_system,body_signals,readiness",
    ))
    if pulses:
        return _result("pulse", pulses)

    checkins = _kept(_sb_get(
        "capacity_checkins",
        f"checkin_type=eq.capacity&log_date=gte.{since}&log_date=lte.{until}"
        f"&order=log_date.asc,captured_at.asc"
        f"&select=log_date,capacity_state,stimulation_state,pain_score,regulation_state",
    ))
    if checkins:
        return _result("checkin", checkins)

    return _result("none", [])


# ── Weekly OSINT LLM exec summaries (2026-08-10) ──────────────────────────────
#
# Replaces (well, augments — see _format_weekly_osint_block) the raw
# HIGH/MEDIUM/LOW count + top-item dump with an actual narrative synthesis of
# the week's events, one per OSINT domain (never combined — Captain wants two
# separate summaries). Built the same way core/platform/infra_narrative.py
# builds its narrative: same shared provider chain (core/llm/provider_chain.py
# call_gemini -> call_mistral -> call_ollama), same try-each-in-order /
# never-raise contract. Unlike infra_narrative.py this always has real data to
# summarize when signals exist (there's no "nominal, skip the LLM" case), so
# it's called whenever the week produced rows.

_TECH_OSINT_SUMMARY_SYSTEM_PROMPT = (
    "You are the Intelligence Officer for USS Starship Endeavour, writing the "
    "Tech OSINT section of the Captain's weekly Telegram report. You are given "
    "a list of this week's actual technical/security OSINT events — each with "
    "its severity (HIGH/MEDIUM/LOW confidence), title, sector, and source. "
    "Synthesize what is actually being seen across the week: real recurring "
    "sectors, sources, or themes, and anything notable — not a restatement of "
    "counts, and not a list of the same titles back at the reader. "
    "Rules: only use the events provided below — never invent a threat, a "
    "cause, or a trend the data doesn't support. If the week's events are thin "
    "or scattered with no real pattern, say that plainly rather than "
    "manufacturing one. "
    "Write 2-4 tight sentences, plain English, no headers, no bullet points, "
    "no markdown formatting — this is inserted directly into a Telegram "
    "message so keep it to Telegram-appropriate length."
)

_HEALTH_OSINT_SUMMARY_SYSTEM_PROMPT = (
    "You are the Health Intelligence Officer for USS Starship Endeavour, "
    "writing the Health OSINT section of the Captain's weekly Telegram "
    "report. You are given a list of this week's actual health/longevity/"
    "medical OSINT signals — each with its severity (HIGH/MEDIUM/LOW "
    "confidence), title, health domain, and source. "
    "Synthesize what is actually being seen across the week: real recurring "
    "domains, sources, or themes, and anything notable — not a restatement "
    "of counts, and not a list of the same titles back at the reader. "
    "Rules: only use the signals provided below — never invent a study "
    "finding, a causal claim, or a trend the data doesn't support. If the "
    "week's signals are thin or scattered with no real pattern, say that "
    "plainly rather than manufacturing one. "
    "Write 2-4 tight sentences, plain English, no headers, no bullet points, "
    "no markdown formatting — this is inserted directly into a Telegram "
    "message so keep it to Telegram-appropriate length."
)


def _call_weekly_summary_providers(system_prompt: str, prompt: str, label: str) -> str | None:
    """Try the shared provider chain in order — identical fallback pattern to
    core/platform/infra_narrative.py's _generate(). Never raises; returns None
    on total failure (missing import, no signals, or every provider down) so
    the caller falls back to the existing raw severity-count display."""
    if call_gemini is None:
        return None
    providers = [
        ("gemini-3.5-flash-lite", lambda p: call_gemini(system_prompt, p, api_key=_GEMINI_API_KEY, max_output_tokens=400).text),
        ("mistral-small",    lambda p: call_mistral(system_prompt, p, api_key=_MISTRAL_API_KEY, max_tokens=400).text),
        (_OLLAMA_WEEKLY_MODEL, lambda p: call_ollama(
            system_prompt, p, base_url=_OLLAMA_BASE_URL, model=_OLLAMA_WEEKLY_MODEL, num_predict=350,
        ).text),
    ]
    for name, fn in providers:
        try:
            result = fn(prompt)
            if result:
                log.info("[weekly-report] %s exec summary generated via %s", label, name)
                return result
        except Exception as exc:  # noqa: BLE001 - per-provider exec-summary attempt inside a fallback chain — one provider failing must not abort the chain; already logged
            log.warning("[weekly-report] %s exec summary provider %s failed: %s", label, name, exc)
    log.warning("[weekly-report] %s exec summary unavailable — all providers failed", label)
    return None


def _generate_tech_osint_summary(rows: list[dict], limit: int = 40) -> str | None:
    """LLM exec summary for the weekly Tech OSINT block, built from real event
    data (title, sector, source, severity) — not just the bucket counts. None
    when there's nothing to summarize or every provider fails; caller falls
    back to the raw severity-count + top-items display."""
    if not rows:
        return None
    events = []
    for r in rows[:limit]:
        severity = (r.get("osint_confidence_level") or "UNKNOWN").upper()
        source = (r.get("intelligence_source_registry") or {}).get("source_name") or "Unknown"
        sector = r.get("sector") or "—"
        events.append(f"- [{severity}] {r.get('raw_title') or '—'}  (sector: {sector}, source: {source})")
    prompt = (
        f"This week's Tech OSINT events ({len(rows)} total this week, showing "
        f"the {min(limit, len(rows))} highest-ranked):\n" + "\n".join(events)
    )
    summary = _call_weekly_summary_providers(_TECH_OSINT_SUMMARY_SYSTEM_PROMPT, prompt, "Tech OSINT")
    return _truncate_clean(summary, 700) if summary else None


def _generate_health_osint_summary(rows: list[dict], limit: int = 40) -> str | None:
    """LLM exec summary for the weekly Health OSINT block — health-domain
    counterpart to _generate_tech_osint_summary, built from real signal data
    (title, health domain, source, severity)."""
    if not rows:
        return None
    events = []
    for r in rows[:limit]:
        severity = (r.get("confidence_level") or "UNKNOWN").upper()
        source = (r.get("health_source_registry") or {}).get("source_name") or "Unknown"
        domain = r.get("health_domain") or "—"
        events.append(f"- [{severity}] {r.get('title') or '—'}  (domain: {domain}, source: {source})")
    prompt = (
        f"This week's Health OSINT signals ({len(rows)} total this week, "
        f"showing the {min(limit, len(rows))} highest-ranked):\n" + "\n".join(events)
    )
    summary = _call_weekly_summary_providers(_HEALTH_OSINT_SUMMARY_SYSTEM_PROMPT, prompt, "Health OSINT")
    return _truncate_clean(summary, 700) if summary else None


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


def _capacity_state_emoji(state) -> str:
    """capacity_checkins.capacity_state is green/orange/red (MY CAPACITY
    TODAY's own vocabulary) — orange maps onto the same yellow/caution
    glyph amber does everywhere else in these briefs."""
    return _severity_emoji({"green": "green", "orange": "yellow", "red": "red"}.get((state or "").lower(), "none"))


def _confidence_bar(pct) -> str:
    try:
        p = int(pct)
    except (TypeError, ValueError):
        p = 0
    filled = max(0, min(10, p // 10))
    return "█" * filled + "░" * (10 - filled)


def _now_aest() -> datetime:
    return datetime.now(_AEST)


def _clock_label(now: datetime) -> str:
    """"HH:MM ZZZZ" in the zone the brief jobs are scheduled in (OR_INTEL_SCHEDULE_TZ, default
    Australia/Melbourne), so the header shows AEDT in daylight saving and matches the clock the job
    fired on. `_AEST` was Brisbane (no DST) until 2026-10, so formatting `now` directly printed 06:00 AEST for a
    job that ran at 07:00 AEDT. It is now Melbourne, but the label still follows the schedule setting. Dates and day windows still use `_AEST`; only the displayed label changes."""
    try:
        local = now.astimezone(ZoneInfo(os.getenv("OR_INTEL_SCHEDULE_TZ", "Australia/Melbourne")))
        return local.strftime("%H:%M %Z")
    except Exception:  # noqa: BLE001 - label only: no zoneinfo/tzdata -> the previous fixed label
        return f"{now.strftime('%H:%M')} AEST"


def _relative_age(timestamp: str | None) -> str:
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


def _esc(value: object) -> str:
    """Escape database/model text for Telegram's HTML parse_mode. Every brief is sent through
    notify(template="raw"), which passes the body through untouched, so each builder here must
    escape its own dynamic text (stored events can carry redaction placeholders such as <NRP>,
    which Telegram rejects as an unsupported tag, failing the whole message). Escape AFTER
    truncating (_truncate_clean) so an entity is never cut in half. The literal <b>/<i>/<code>
    wrappers are never passed through this.

    Feed text can arrive already entity-encoded (an RSS title carrying "&#x5b;Guest Diary&#x5d;"
    for "[Guest Diary]" because the feed double-encoded it, and rss_adapter stores the title as
    parsed). Escaping that as-is turns the "&" into "&amp;" and Telegram, the email and the card
    show the entity text literally. The text is decoded once first, so it reads as plain text, then
    escaped once for HTML; plain text such as "AT&T" or "<NRP>" is unaffected by the decode."""
    return _html_escape(_html_unescape(str(value)), quote=False)


def _truncate_clean(text: str, limit: int) -> str:
    """Truncate at a word boundary with an ellipsis, never mid-word - a bare
    text[:limit] slice was cutting narratives off mid-sentence (sometimes
    mid-word), and since the action-line the infra-narrative prompt now
    requires comes last, that was consistently the part getting eaten."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _format_infra_block(infra: dict | None, morning_text: str | None = None) -> list[str]:
    """Shared Platform Health renderer (Part 1 item 2: de-dupe the block that
    was copy-pasted verbatim between generate_morning_brief() and
    generate_eod_summary()). `morning_text`, when supplied (EOD only), is
    this morning's already-persisted brief text — if today's narrative was
    already shown there, the header is marked "(unchanged since this
    morning)" instead of silently re-rendering the identical warning."""
    if not infra or infra.get("state") != "unsure":
        return []
    # Escaped before the comparison: this morning's persisted text holds the escaped form.
    narrative = _esc(_truncate_clean(infra["narrative"], 700))
    unchanged = bool(morning_text) and narrative in morning_text
    suffix = " <i>(unchanged since this morning)</i>" if unchanged else ""
    return [
        f"<b>🛰 PLATFORM HEALTH</b>{suffix}",
        f"  ⚠️ {narrative}",
        "",
    ]


def _format_capacity_block(cap: dict | None, header: str = "⚡ CAPACITY TODAY") -> list[str]:
    """Shared MY CAPACITY TODAY renderer for Morning Brief and EOD Summary —
    replaces the old captains_log_entries/recovery_pulses capacity blocks
    (both tables permanently frozen, see _get_capacity_today()). Renders the
    Captain's own latest capacity_state reading plus whatever companion
    signals (pain, regulation, executive function) were captured alongside
    it — no synthesized score, per capacity_zone_from_checkin()'s "the
    Captain's own report IS the signal" philosophy."""
    if not cap or not cap.get("has_checked_in"):
        return [
            f"<b>{header}</b>",
            "  No check-in yet today — log one via capacitybot (/capacity)",
            "",
        ]
    state = cap.get("latest_capacity_state")
    bits = [f"{_capacity_state_emoji(state)} Capacity <b>{_esc((state or '?').capitalize())}</b>"]
    pain_text = describe_pain(cap.get("latest_pain_state"), cap.get("latest_pain_score"))
    if pain_text:
        bits.append(_esc(pain_text))
    if cap.get("latest_regulation_state"):
        bits.append(f"NS {_esc(cap['latest_regulation_state'].capitalize())}")
    if cap.get("latest_executive_function"):
        bits.append(f"EF {_esc(cap['latest_executive_function'].replace('_', ' ').capitalize())}")
    return [
        f"<b>{header}</b>",
        f"  {'  ·  '.join(bits)}",
        f"  <i>{_esc(cap.get('checkin_label', ''))}</i>",
        "",
    ]


def _format_weekly_osint_block(
    title: str, emoji: str, rows: list[dict], confidence_field: str, title_field: str,
    summary: str | None = None, top_n: int = 3, empty_caveat: str | None = None,
) -> list[str]:
    """Shared weekly OSINT roll-up renderer for generate_weekly_report() —
    same HIGH/MEDIUM/LOW bucketing each workbench's Intelligence Summary tab
    uses (see _get_weekly_tech_signals / _get_weekly_health_signals), applied
    across the whole 7-day window rather than a single latest row.

    `summary`, when supplied, is the LLM-generated exec summary for this
    domain's week (see _generate_tech_osint_summary /
    _generate_health_osint_summary) and is placed directly under the header,
    above the severity-count line — the fast-scan signal stays either way.
    When `summary` is absent (LLM unavailable, or every provider failed),
    this falls back to the original raw severity-count + top-items display,
    which is the graceful-degradation path 2026-08-10's exec-summary change
    is required to preserve.

    `empty_caveat` (HQ V1 Integration QA §21/§9): when supplied, appended
    as an extra line so a silent collector failure never reads identically
    to a genuinely quiet week — see _health_osint_collector_caveat()."""
    if not rows:
        lines = [f"<b>{emoji} {title} — WEEKLY</b>", "  No signals collected this week."]
        if empty_caveat:
            lines.append(f"  <i>⚠ {_esc(empty_caveat)}</i>")
        lines.append("")
        return lines
    counts = Counter((r.get(confidence_field) or "UNKNOWN").upper() for r in rows)
    unknown = len(rows) - counts.get("HIGH", 0) - counts.get("MEDIUM", 0) - counts.get("LOW", 0)
    severity_line = (
        f"  {_risk_emoji('HIGH')} {counts.get('HIGH', 0)} high"
        f"  ·  {_risk_emoji('MEDIUM')} {counts.get('MEDIUM', 0)} medium"
        f"  ·  {_risk_emoji('LOW')} {counts.get('LOW', 0)} low"
    )
    if unknown:
        severity_line += f"  ·  ⚪ {unknown} unscored"

    lines = [f"<b>{emoji} {title} — WEEKLY ({len(rows)})</b>"]
    if summary:
        lines.append(f"  {_esc(summary)}")
        lines.append(severity_line)
    else:
        # Fallback: no exec summary available — original raw-counts +
        # top-items display so the section still reads well degraded.
        lines.append(severity_line)
        # Headline items: prefer HIGH-confidence signals; fall back to the
        # top-ranked signals overall if nothing hit HIGH this week.
        headline = [r for r in rows if (r.get(confidence_field) or "").upper() == "HIGH"]
        if not headline:
            headline = rows
        headline = sorted(headline, key=lambda r: r.get("rank_score") or 0, reverse=True)[:top_n]
        for r in headline:
            text = r.get(title_field) or "—"
            lines.append(f"  {_risk_emoji(r.get(confidence_field))} {_esc(_truncate_clean(text, 110))}")
    lines.append("")
    return lines


def _format_weekly_content_block(items: list[dict]) -> list[str]:
    """Content published or moved to review/approval this week."""
    if not items:
        return ["<b>✍️ CONTENT THIS WEEK</b>", "  Nothing published or moved to review this week.", ""]
    status_counts = Counter(c.get("status", "?") for c in items)
    summary = "  ·  ".join(f"{v} {_esc(k.replace('_', ' '))}" for k, v in status_counts.items())
    # 2026-08-10 fix (XO product review): ready_to_publish/approved were
    # reusing 🟢/🟡 — the same glyphs _SEVERITY_EMOJI uses for "low/fine" and
    # "medium/caution" a few lines above in the same weekly message, meaning
    # opposite things (workflow stage vs. risk severity) in the same
    # message. Swapped for glyphs outside the severity palette so a single
    # 🟢 always means "don't worry about it" everywhere in these briefs.
    status_emoji = {"published": "✅", "ready_to_publish": "📤", "approved": "☑️", "review": "📝"}
    lines = [f"<b>✍️ CONTENT THIS WEEK ({len(items)})</b>", f"  {summary}"]
    for c in items:
        pillar = (c.get("pillar") or "").replace("_", " ") or "—"
        emoji = status_emoji.get(c.get("status"), "•")
        lines.append(
            f"  {emoji} <b>{_esc(c.get('title') or '(untitled)')}</b>  [{_esc(c.get('status', '?'))} · {_esc(pillar)}]"
        )
    lines.append("")
    return lines


def _format_weekly_outage_alerts_block(alerts: list[dict]) -> list[str]:
    """Weekly counterpart to the standalone real-time outage-push feature
    (2026-08-10 fix, XO product review finding #5) -- surfaces "how many
    outage alerts fired this week, and did they actually send" so the
    Captain doesn't have to re-run the intelligence_events qualifying-event
    filter by hand. Only rendered when at least one alert fired this week --
    a quiet week produces no section, same "silence is a valid state"
    convention as _format_infra_block."""
    if not alerts:
        return []
    sent = sum(1 for a in alerts if a.get("outcome") == "sent")
    failed = len(alerts) - sent
    status_line = f"  {sent} sent"
    if failed:
        status_line += f"  ·  {failed} failed to send"
    lines = [f"<b>🚨 OUTAGE ALERTS THIS WEEK ({len(alerts)})</b>", status_line]
    for a in alerts[:5]:
        details = a.get("details") or {}
        title = details.get("event_title") or "—"
        impact = details.get("customer_impact") or "?"
        try:
            conf = f"{float(details.get('confidence')):.2f}"
        except (TypeError, ValueError):
            conf = "?"
        icon = "✅" if a.get("outcome") == "sent" else "❌"
        lines.append(f"  {icon} {_esc(_truncate_clean(title, 90))}  [{_esc(impact)} · conf {conf}]")
    lines.append("")
    return lines


# Captain's review (Gate 1): a trend or "recovery" statement needs enough
# observations. Same floor as core/health/trend_utils.MIN_DAYS_FOR_TREND (4
# values) plus at least 3 distinct days, so one busy day can't masquerade as a week.
MIN_CAPACITY_OBSERVATIONS = 4
MIN_CAPACITY_DAYS = 3


def _capacity_sufficiency_line(n: int, distinct_days: int) -> str | None:
    """None when there is enough to describe a pattern, else an explicit
    'not enough to infer' line. Absence of data is never reported as 'fine'."""
    if n >= MIN_CAPACITY_OBSERVATIONS and distinct_days >= MIN_CAPACITY_DAYS:
        return None
    return (f"  <i>Not enough observations ({n} over {distinct_days} day(s); need "
            f"{MIN_CAPACITY_OBSERVATIONS}+ over {MIN_CAPACITY_DAYS}+ days) to assess recovery "
            f"or a trend — no inference made.</i>")


def _format_weekly_capacity_block(capacity: dict, days: int = 7) -> list[str]:
    """captains_log_entries across the 7-day window — a real weekly
    Green/Amber/Red trend instead of a single day's snapshot.

    2026-08-10 fix (XO product review): when captains_log_entries has
    nothing this week (see _get_weekly_capacity's fallback), render the
    recovery_pulses-based signal instead of unconditionally showing "No
    capacity logs this week" — mirrors Morning/EOD's existing
    recovery-confidence fallback, aggregated across the window. With
    pulse-logging currently sparse (per the same audit), the honest output
    may be as small as "1 pulse logged this week" — that's a real signal
    about logging adherence, not a bug to hide."""
    source = capacity.get("source")
    entries = capacity.get("entries") or []

    if source == "log":
        counts = Counter((e.get("captain_capacity_rating") or "Unknown").capitalize() for e in entries)
        order = ["Green", "Amber", "Red"]
        parts = [f"{counts[c]} {c}" for c in order if counts.get(c)]
        parts += [f"{v} {k}" for k, v in counts.items() if k not in order]
        trend = " ".join(_rating_emoji(e.get("captain_capacity_rating")) for e in entries)
        return [
            f"<b>⚡ CAPACITY THIS WEEK ({len(entries)} log(s))</b>",
            f"  {_esc(' · '.join(parts)) if parts else 'no ratings logged'}",
            f"  <code>{trend}</code>",
            "",
        ]

    if source == "pulse":
        days_logged = len({e.get("log_date") for e in entries})
        possible = max(1, days * 3)
        conf = round(100.0 * len(entries) / possible)
        latest = entries[-1]  # ordered log_date,captured_at ascending
        signals_str = [
            s for s in (
                f"Energy {latest['energy'].capitalize()}" if latest.get("energy") else None,
                f"NS {latest['nervous_system'].capitalize()}" if latest.get("nervous_system") else None,
                f"Body {latest['body_signals'].capitalize()}" if latest.get("body_signals") else None,
            ) if s
        ]
        lines = [
            "<b>⚡ CAPACITY THIS WEEK</b>",
            (f"  <code>{_confidence_bar(conf)}</code> Recovery confidence <b>{conf}%</b>"
             f"  ·  {len(entries)} pulse(s) logged across {days_logged} day(s) (of {days})"),
        ]
        if signals_str:
            lines.append(f"  Latest: {_esc(' · '.join(signals_str))}")
        lines.append("")
        return lines

    if source == "checkin":
        counts = Counter((e.get("capacity_state") or "unknown") for e in entries)
        order = ["green", "orange", "red"]
        parts = [f"{counts[c]} {c.capitalize()}" for c in order if counts.get(c)]
        parts += [f"{v} {k.capitalize()}" for k, v in counts.items() if k not in order]
        days_logged = len({e.get("log_date") for e in entries})
        trend = " ".join(_capacity_state_emoji(e.get("capacity_state")) for e in entries)
        return [
            f"<b>⚡ CAPACITY THIS WEEK ({len(entries)} check-in(s) across {days_logged} day(s))</b>",
            f"  {_esc(' · '.join(parts)) if parts else 'no state recorded'}",
            f"  <code>{trend}</code>",
            "",
        ]

    return ["<b>⚡ CAPACITY THIS WEEK</b>", "  No capacity check-ins, logs, or recovery pulses this week.", ""]


def _format_weekly_capacity_block_v1(capacity: dict, days: int = 7) -> list[str]:
    """Weekly capacity block.

    Every branch states how many observations it rests on and over how many
    days, flags excluded future-dated records, and withholds any recovery
    statement when the sample is too small. Zero observations is reported as
    "not observed" — never as stable or fine.

    History: 2026-08-10/2026-09-13 added the pulse and check-in fallbacks. The
    pulse tier used to print "Recovery confidence N%", which was really
    entries / (days x 3) — logging adherence, not recovery — and it would also
    have counted rows dated 2099-01-01. Both are corrected here."""
    source = capacity.get("source")
    entries = capacity.get("entries") or []
    days_logged = len({e.get("log_date") for e in entries if e.get("log_date")})
    notes: list[str] = []
    if capacity.get("excluded_future"):
        notes.append(f"  <i>⚠ {int(capacity['excluded_future'])} future-dated record(s) excluded "
                     f"— not real observations.</i>")
    thin = _capacity_sufficiency_line(len(entries), days_logged)

    if source == "log":
        counts = Counter((e.get("captain_capacity_rating") or "Unknown").capitalize() for e in entries)
        order = ["Green", "Amber", "Red"]
        parts = [f"{counts[c]} {c}" for c in order if counts.get(c)]
        parts += [f"{v} {k}" for k, v in counts.items() if k not in order]
        trend = " ".join(_rating_emoji(e.get("captain_capacity_rating")) for e in entries)
        return [
            f"<b>⚡ CAPACITY THIS WEEK ({len(entries)} log(s) across {days_logged} day(s))</b>",
            f"  {_esc(' · '.join(parts)) if parts else 'no ratings logged'}",
            f"  <code>{trend}</code>",
            *([thin] if thin else []), *notes, "",
        ]

    if source == "pulse":
        possible = max(1, days * 3)
        coverage = round(100.0 * len(entries) / possible)
        latest = entries[-1]  # ordered log_date,captured_at ascending
        signals_str = [
            s for s in (
                f"Energy {latest['energy'].capitalize()}" if latest.get("energy") else None,
                f"NS {latest['nervous_system'].capitalize()}" if latest.get("nervous_system") else None,
                f"Body {latest['body_signals'].capitalize()}" if latest.get("body_signals") else None,
            ) if s
        ]
        lines = [
            "<b>⚡ CAPACITY THIS WEEK</b>",
            (f"  {len(entries)} pulse(s) logged across {days_logged} day(s) (of {days})"
             f"  ·  logging coverage <b>{coverage}%</b> <i>(how often a pulse was logged, "
             f"not a measure of recovery)</i>"),
        ]
        if signals_str:
            lines.append(f"  Latest: {_esc(' · '.join(signals_str))}")
        if thin:
            lines.append(thin)
        lines += [*notes, ""]
        return lines

    if source == "checkin":
        counts = Counter((e.get("capacity_state") or "unknown") for e in entries)
        order = ["green", "orange", "red"]
        parts = [f"{counts[c]} {c.capitalize()}" for c in order if counts.get(c)]
        parts += [f"{v} {k.capitalize()}" for k, v in counts.items() if k not in order]
        trend = " ".join(_capacity_state_emoji(e.get("capacity_state")) for e in entries)
        return [
            f"<b>⚡ CAPACITY THIS WEEK ({len(entries)} check-in(s) across {days_logged} day(s))</b>",
            f"  {_esc(' · '.join(parts)) if parts else 'no state recorded'}",
            f"  <code>{trend}</code>",
            *([thin] if thin else []), *notes, "",
        ]

    return [
        "<b>⚡ CAPACITY THIS WEEK</b>",
        "  No capacity check-ins, logs, or recovery pulses this week.",
        ("  <i>Not observed — this is a gap in data, not evidence that capacity was fine. "
         "No inference about recovery is made.</i>"),
        *notes, "",
    ]


# ── Brief generators ──────────────────────────────────────────────────────────

# Marker brief_evidence.morning_view puts at the start of its first line when there are zero recent incidents (coverage insufficient).
_EVIDENCE_INSUFFICIENT_MARKER = "EVIDENCE COVERAGE INSUFFICIENT"


def _format_intelligence_posture_block(brief: dict | None, *, evidence_authoritative: bool = False,
                                       evidence_insufficient: bool = False) -> list[str]:
    """Deterministic rendering of the canonical daily brief
    (intelligence_briefs) — the ONE place this Telegram message decides
    posture / what matters / what changed, built on the exact same
    selection Captain's Chair's excerpt uses (Section 9/10/26/29 of
    BRIEFS_CANONICAL_UPLIFT.md). No LLM re-synthesis, no independent
    "overall picture" — everything below is copied or lightly truncated
    from the stored brief."""
    from intelligence.brief.render import RISK_LABEL, build_morning_intelligence_view

    view = build_morning_intelligence_view(brief, max_items=3)
    if evidence_authoritative:
        # The evidence-based picture (BRIEF_EVIDENCE_V1_MORNING) is the authoritative morning assessment. The legacy posture,
        # "What matters today" and "Changed since yesterday" are NOT shown beside it: they are not evidence-checked and can carry
        # stale or contradictory priorities. Only the collection-health warning is kept, as a diagnostic.
        if view["has_brief"] and view["coverage_note"]:
            return ["<b>📡 COLLECTION HEALTH</b>", f"  <i>⚠️ {_esc(view['coverage_note'])}</i>", ""]
        return []
    heading = "📡 INTELLIGENCE POSTURE"
    if evidence_insufficient:
        # The evidence block says coverage is insufficient today, so it cannot be the authority: show the legacy posture, but
        # clearly labelled as the previous, not evidence-checked method.
        heading = "📡 LEGACY POSTURE (previous method, not evidence-checked; evidence coverage insufficient today)"
    if not view["has_brief"]:
        return [
            f"<b>{heading}</b>",
            "  Today's canonical brief has not been generated yet.",
            "",
        ]

    lines = [
        f"<b>{heading}</b>",
        f"  Posture: <b>{_esc(RISK_LABEL.get(view['overall_risk'], view['overall_risk']))}</b>",
    ]
    if view["what_matters"]:
        lines.append("  <b>What matters today</b>")
        for i, item in enumerate(view["what_matters"], 1):
            line = f"  {i}. {item['title']}"
            if item.get("so_what"):
                line += f" — {item['so_what']}"
            lines.append(_esc(_truncate_clean(line, 260)))
    elif view["executive_read"]:
        lines.append(f"  {_esc(_truncate_clean(view['executive_read'], 350))}")

    if view["changed"]:
        changed_bits = []
        for label, key in (("New", "new"), ("Escalated", "escalated"), ("Improved", "improved")):
            for title in view["changed"].get(key) or []:
                changed_bits.append(f"{label}: {title}")
        if changed_bits:
            lines.append("  <b>Changed since yesterday</b>")
            for bit in changed_bits[:5]:
                lines.append(_esc(_truncate_clean(f"  - {bit}", 200)))

    if view["coverage_note"]:
        lines.append(f"  <i>⚠️ {_esc(view['coverage_note'])}</i>")

    lines.append("")
    return lines


CAPACITY_QUALITY_FLAG = "BRIEF_CAPACITY_QUALITY_V1"


def _capacity_quality_enabled() -> bool:
    """Weekly capacity data-quality correction (future-dated rows excluded, observation counts, no recovery claim on a thin sample).
    Independent of BRIEF_EVIDENCE_V1*: default off, and the legacy weekly capacity block is unchanged while it is off."""
    return os.getenv(CAPACITY_QUALITY_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _evidence_unavailable_lines(reason: str) -> list[str]:
    """Morning block (flag on) when the evidence layer yields nothing usable. Starts with the insufficient-coverage marker so the
    brief takes its labelled 'evidence insufficient' path instead of silently reading as all quiet."""
    return [f"⚠️ {_EVIDENCE_INSUFFICIENT_MARKER}: {reason}; nothing below should be read as all quiet.", ""]


def _morning_view_lines(be, ev, events: list[dict], hours: int) -> list[str]:
    """Morning evidence view. DELIVERY_TIERS_V1 (default off) swaps in the clustered, tiered incident view; with it off this is exactly
    ``be.morning_view(ev)`` (tests/test_tiered_brief.py proves identical text). With CAPTAINS_BRIEF_RECORD_EVENTS on, the event ids the
    rendered view contains are noted for ``brief_event_links.flush`` (no-op when off)."""
    from intelligence import brief_event_links as bel
    from intelligence import tiered_brief as tb
    if tb.enabled():
        view, shown = tb.render(events, now=ev.generated_at, window_hours=hours)
        bel.note("morning", shown)
        return view
    view = be.morning_view(ev)
    if bel.enabled():
        text = "\n".join(view)
        bel.note("morning", [rid for i in ev.incidents if i.incident_id in text for rid in i.report_ids])
    return view


def _evidence_lines(kind: str, hours: int) -> list[str]:
    """V1 shared-evidence block for the morning or weekly brief. Returns [] unless its feature flag is on (BRIEF_EVIDENCE_V1 or
    BRIEF_EVIDENCE_V1_MORNING / _WEEKLY); never raises, so the legacy brief always renders unchanged when the flag is off or the
    evidence layer fails."""
    try:
        from intelligence import brief_evidence as be
        if not be.enabled(kind):
            return []
        events = be.load_events(_sb_get, hours=hours)
        if not events:
            if kind == "morning":
                return _evidence_unavailable_lines(f"no reports collected in the last {hours} hours (or the evidence query failed)")
            return []
        ev = be.build_evidence(events, window_hours=hours)
        if kind == "morning":
            view = _morning_view_lines(be, ev, events, hours)
            recent = [i for i in ev.incidents if i.last_seen and i.last_seen >= ev.generated_at - timedelta(hours=24)]
            if not recent and not any(_EVIDENCE_INSUFFICIENT_MARKER in line for line in view):
                # Reports exist (24-72h old) but nothing was collected in the last 24h: the picture is NOT 'all quiet', it is thin.
                view = [f"⚠️ {_EVIDENCE_INSUFFICIENT_MARKER}: no reports collected in the last 24 hours; nothing below should be read as all quiet."] + view
        else:
            path = os.getenv(be.SNAPSHOT_ENV) or None            # the existing SnapshotStore; no path configured = no read and no write
            view = be.weekly_view(ev, be.load_previous_snapshot(path, ev.generated_at))
            be.record_snapshot(path, ev)
        return [_esc(x) for x in view] + [""]
    except Exception as exc:  # noqa: BLE001 - additive feature-flagged block; the legacy brief must still render
        log.warning("Evidence-based %s block unavailable: %s", kind, exc)
        if kind == "morning":
            try:
                from intelligence import brief_evidence as be
                if be.enabled(kind):
                    return _evidence_unavailable_lines("evidence layer unavailable")
            except Exception as exc2:  # noqa: BLE001 - never raise; flag state unknown means the legacy brief renders unchanged
                log.debug("Evidence flag check failed: %s", exc2)
        return []


def _theme_lines() -> list[str]:
    """Topic & Theme lane for the morning brief (flag BRIEF_THEMES_V1[_MORNING], default off): developments and running themes in the
    watched topics. [] when off; never raises, so the legacy brief always renders."""
    try:
        from intelligence import brief_themes as bt
        lines = bt.theme_lines(_sb_get)
        return [_esc(x) for x in lines] + [""] if lines else []
    except Exception as exc:  # noqa: BLE001 - additive feature-flagged block
        log.warning("Theme lane unavailable: %s", exc)
        return []


def _health_lines() -> list[str]:
    """Health watch for the morning brief (flag BRIEF_HEALTH_V1[_MORNING], default off): monitored conditions plus safety-flagged signals.
    [] when off; never raises, so the legacy brief always renders."""
    try:
        from intelligence import brief_health as bh
        lines = bh.health_lines(_sb_get)
        return [_esc(x) for x in lines] + [""] if lines else []
    except Exception as exc:  # noqa: BLE001 - additive feature-flagged block
        log.warning("Health lane unavailable: %s", exc)
        return []


def _coverage_lines() -> list[str]:
    """Coverage block for the morning brief (flag BRIEF_COVERAGE_V1[_MORNING], default off): what the brief looked at, silent sources and
    official warnings. [] when off; never raises."""
    try:
        from intelligence import brief_coverage as bc
        from intelligence.persistence import intelligence_store as store
        lines = bc.coverage_lines(_sb_get, store.load_active_emergency_alerts)
        return [_esc(x) for x in lines] + [""] if lines else []
    except Exception as exc:  # noqa: BLE001 - additive feature-flagged block
        log.warning("Coverage block unavailable: %s", exc)
        return []


def _morning_gap():
    from intelligence import brief_reliability as br
    return br.get_gap(_sb_request, datetime.now(_AEST).date().isoformat())


def generate_morning_brief(gap=None, collection_caveat: str | None = None, catch_up: bool = False) -> str:
    """``gap``/``collection_caveat`` are computed by send_brief and passed in so the text and the persisted window agree."""
    from intelligence import brief_reliability as br
    now = _now_aest()
    gap = gap if gap is not None else _morning_gap()
    brief = _get_latest_ori_brief()
    capacity = _get_capacity_today()
    signals = _get_recent_signals(hours=gap.lookback_hours)
    infra = _get_infra_verification()

    lines = [
        f"<b>☀️ MORNING BRIEF — {now.strftime('%A %d %B %Y')}</b>",
        f"<i>Stardate {now.strftime('%Y.%j')} · {_clock_label(now)}</i>",
        "",
    ]

    # Coverage limitation (missed previous cycle / degraded collection): [] on a normal day, so the default brief is unchanged.
    note = br.coverage_note(gap, collection_caveat)
    if catch_up:
        note.insert(0, "⚠️ LATE BRIEF: generated after a scheduler restart past the usual 07:00 time (catch-up).")
    if gap.missed:
        note.append(f"⚠️ The evidence section below lists incidents seen in the last 24h only; use the {gap.lookback_hours}h signal list for the gap.")
    if note:
        lines += [_esc(x) for x in note] + [""]

    lines += _format_capacity_block(capacity)

    # V1 shared evidence foundation (default off): confirmed vs to-verify incidents, implications, 24-72h forward watch.
    evidence_lines = _evidence_lines("morning", 72)
    lines += evidence_lines
    # Topic & Theme lane (default off): developments and running themes in the watched topics, beside (not inside) the incident picture.
    lines += _theme_lines()
    # Health watch (default off): monitored conditions and safety-flagged signals; and a coverage block (default off) stating what was looked at.
    lines += _health_lines()
    lines += _coverage_lines()
    # INTEL_PRODUCTS_IN_BRIEF hook (default off, fail-soft, prints nothing when nothing qualifies): intelligence/brief_products_block.py
    try:
        from intelligence.brief_products_block import (
            brief_lines as _intel_product_lines,
        )
        lines += [_esc(x) for x in _intel_product_lines()]
    except Exception as exc:  # noqa: BLE001 - additive flag-gated block must never break the brief
        log.debug("Intel products block unavailable: %s", exc)
    # Authority depends on USABLE coverage: lines that announce insufficient coverage are not an authoritative picture.
    evidence_insufficient = any(_EVIDENCE_INSUFFICIENT_MARKER in line for line in evidence_lines)
    evidence_authoritative = bool(evidence_lines) and not evidence_insufficient

    # Audit (#669): with the V1 selection authoritative, intelligence can still reach this message outside it via (1)
    # build_daily_digest ('PLATFORM, TODAY', LLM-synthesised from signals + platform events) and (2) the raw
    # _format_signals_block ('OTHER SIGNALS (24h)'). Neither is evidence-checked; (2) is labelled as such below.

    # Intelligence posture — rendered deterministically from the canonical
    # daily brief. This is the one place that decides posture/what-matters/
    # what-changed for this message; Captain's Chair renders the same
    # selection from the same brief (Section 26/29 of
    # BRIEFS_CANONICAL_UPLIFT.md). No LLM re-synthesis of the OSINT picture
    # happens here or in build_daily_digest() below.
    lines += _format_intelligence_posture_block(brief, evidence_authoritative=evidence_authoritative,
                                              evidence_insufficient=evidence_insufficient)

    # Daily digest — platform-only content now: individual HIGH/MEDIUM news
    # signals plus platform events (health/engineering/learning/
    # opportunities/operational_intelligence), synthesised into one
    # educational narrative (Captain feedback 2026-08-26: one summary, not
    # a raw headline-dump section plus a separate narrative section).
    # Best-effort: LLM/event-bus unavailability falls back to the raw
    # signal list rather than a silently empty section.
    digest_text = None
    if build_daily_digest is not None:
        try:
            digest_text = build_daily_digest(signals=signals)
        except Exception as exc:  # noqa: BLE001 - best-effort daily-digest synthesis, already logged; caller falls back to the raw signal list
            log.warning("Daily digest synthesis failed: %s", exc)
            digest_text = None

    if digest_text:
        lines += [
            "<b>🌐 PLATFORM, TODAY</b>",
            f"  {_esc(digest_text)}",
            "",
        ]
    else:
        other_header = "📡 OTHER SIGNALS (24h; not evidence-checked)" if evidence_authoritative else "📡 OTHER SIGNALS (24h)"
        signal_block = _format_signals_block(signals, other_header) if signals else []
        if signal_block:
            lines += signal_block

    # Platform self-health — only surfaced when something is actually
    # degraded; silence is a valid, positive state (per verification engine
    # design intent, STARSHIP-REDESIGN.md §9). Morning brief is the first
    # of the day, so there is no "unchanged since this morning" to check.
    lines += _format_infra_block(infra)

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
    return "\n".join(lines)


def generate_midday_update(signals: list[dict]) -> str:
    now = _now_aest()
    lines = [
        f"<b>🔔 MIDDAY UPDATE — {_clock_label(now)}</b>",
        f"<i>{len(signals)} new signal(s) since morning brief</i>",
        "",
        "<b>📡 NEW SIGNALS</b>",
    ]
    for s in signals[:5]:
        lines.append(
            f"  {_risk_emoji(s.get('risk_rating'))} {_esc(_format_signal_title(s))}"
        )
    lines += ["", "🤖 <i>XO · Starship Endeavour</i>"]
    return "\n".join(lines)


def generate_eod_summary() -> str:
    now = _now_aest()
    capacity = _get_capacity_today()
    infra = _get_infra_verification()
    # 2026-08-13: EOD previously carried no intelligence section at all —
    # the day could close showing zero signal activity regardless of what
    # actually happened. Scoped to "since this morning's 07:00 brief"
    # rather than a flat 24h window, so it reads as today's activity, not
    # a re-run of the same lookback the morning brief already showed.
    hours_since_morning = max(1, min(24, int((now - now.replace(hour=7, minute=0, second=0, microsecond=0)).total_seconds() / 3600)))
    todays_signals = _get_recent_signals(hours=hours_since_morning)
    # Part 1 item 2: fetch this morning's persisted text so repeated blocks
    # below can be marked "(unchanged since this morning)" instead of
    # silently re-rendering identically.
    morning_text = _get_todays_morning_brief_text()

    lines = [
        f"<b>🌙 END-OF-DAY SUMMARY — {now.strftime('%A %d %B')}</b>",
        f"<i>{_clock_label(now)}</i>",
        "",
    ]

    lines += _format_capacity_block(capacity)
    lines += _format_signals_block(todays_signals, "🌙 TODAY'S INTELLIGENCE")
    lines += _format_infra_block(infra, morning_text)

    lines.append("🤖 <i>XO · Starship Endeavour</i>")
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
        f"<i>{_clock_label(now)}</i>",
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
    """Weekly Intelligence Report — redesigned 2026-08-10 per Captain's
    direction: primary intelligence content is now a real 7-day roll-up
    across both OSINT domains (Tech/Intelligence Workbench + Health OSINT),
    not a single latest-row ORI brief snapshot, each with its own
    LLM-generated exec summary (see _generate_tech_osint_summary /
    _generate_health_osint_summary — two separate summaries, never combined).
    Missions are deliberately NOT included — the Captain does not want
    missions in the weekly report. Decisions are also deliberately NOT
    included (2026-08-10) — decision_records is stale/broken and was showing
    "No decisions logged this week" every week; removed until that pipeline
    is fixed separately, rather than keep showing a section that's always
    empty.

    2026-08-10 fix (XO product review finding #5): adds an OUTAGE ALERTS
    THIS WEEK section, sourced from the durable audit_events record the
    standalone outage-push feature now writes (see
    _get_weekly_outage_alerts / intelligence_store.py's
    _log_outage_alert_fired) — closes the gap where that feature's activity
    never appeared in any of the three regular briefs and had no queryable
    history of its own."""
    now = _now_aest()
    week_start = (now - timedelta(days=6)).strftime("%d %b")

    tech_signals = _get_weekly_tech_signals(days=7)
    health_signals = _get_weekly_health_signals(days=7)
    tech_summary = _generate_tech_osint_summary(tech_signals)
    health_summary = _generate_health_osint_summary(health_signals)
    content_items = _get_weekly_content_activity(days=7)
    capacity_quality = _capacity_quality_enabled()
    capacity_entries = (_get_weekly_capacity_v1 if capacity_quality else _get_weekly_capacity)(days=7)
    outage_alerts = _get_weekly_outage_alerts(days=7)

    lines = [
        "<b>📊 WEEKLY INTELLIGENCE REPORT</b>",
        f"<i>{week_start} – {now.strftime('%d %b %Y')}</i>",
        "",
    ]

    # Leads the report — a fired outage push is the highest-severity single
    # item any week can contain (it already interrupted the Captain in
    # real-time); the weekly reference here is retrospective/audit, not the
    # first notice, so it goes first, ahead of the OSINT roll-up.
    lines += _format_weekly_outage_alerts_block(outage_alerts)

    # V1 shared evidence foundation (default off): same incident identities, materiality and provenance as the other briefs.
    lines += _evidence_lines("weekly", 168)

    lines += _format_weekly_osint_block(
        "TECH OSINT", "🛰", tech_signals, "osint_confidence_level", "raw_title",
        summary=tech_summary,
    )
    lines += _format_weekly_osint_block(
        "HEALTH OSINT", "🩺", health_signals, "confidence_level", "title",
        summary=health_summary, empty_caveat=_health_osint_collector_caveat() if not health_signals else None,
    )
    lines += _format_weekly_content_block(content_items)
    lines += (_format_weekly_capacity_block_v1 if capacity_quality else _format_weekly_capacity_block)(capacity_entries)

    # USS-TJR-MSN-0412 Stream 4: the Free plan goes read-only at 500 MB.
    from intelligence import db_size
    lines += [db_size.format_line(db_size.fetch_size_mb()), ""]

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
                lines.append(f"  • {_esc(it)}")
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

# 2026-09-10: morning brief also goes to this ANZ address by explicit
# request, alongside Telegram — not env-configurable, this is the one
# named recipient asked for, not a general CC list.
_MORNING_BRIEF_EMAIL_TO = "tim.jarden-ross@anz.com"


_PERSONAL_BLOCK_HEADERS = ("CAPACITY", "RECOVERY", "PULSE", "SLEEP", "PAIN")


def _strip_personal_blocks(text: str) -> str:
    """R7: drop the personal capacity/recovery blocks from text that leaves the Captain's own
    Telegram chat. A block runs from a header line containing a personal keyword to the next
    blank line."""
    out, skipping = [], False
    for line in text.split("\n"):
        plain = re.sub(r"<[^>]+>", "", line).upper()
        if not skipping and any(k in plain for k in _PERSONAL_BLOCK_HEADERS) and plain.strip()[:1] in ("⚡", "🫀", "😴", "🩺", "🔋") :
            skipping = True
            continue
        if skipping:
            if not line.strip():
                skipping = False
            continue
        out.append(line)
    return "\n".join(out)


def _email_morning_brief(text: str) -> None:
    """Best-effort email copy of the morning brief. Never raises and never
    affects the return value of send_brief() — Telegram is still the
    brief's real delivery/failure signal (see resend_email.send_email's own
    fail-open contract).

    R7: the email goes to a work mailbox, so personal capacity/pain/recovery blocks are removed
    first, and the email is NOT sent at all if personal health content is still detected."""
    from core.notifications.resend_email import send_email
    from core.security import personal_data_policy

    text = _strip_personal_blocks(text)
    leftover = personal_data_policy.contains_personal_health(re.sub(r"<[^>]+>", "", text))
    if leftover:
        log.warning("Morning brief email withheld: personal health content still present (%s)", ", ".join(leftover))
        return
    html = text.replace("\n", "<br>\n")
    subject = f"USS TJR — Morning Brief — {datetime.now(_AEST).date().isoformat()}"
    ok = send_email(_MORNING_BRIEF_EMAIL_TO, subject, html)
    if not ok:
        log.warning("Morning brief email to %s failed (non-blocking)", _MORNING_BRIEF_EMAIL_TO)


def _record_brief_events(brief_type: str) -> None:
    """CAPTAINS_BRIEF_RECORD_EVENTS (default off): record which events this brief contained, keyed by the persisted brief id.
    Never raises; does nothing at all when the flag is off (the legacy persist path is untouched)."""
    try:
        from intelligence import brief_event_links as bel
        if not bel.enabled():
            return
        rows = _sb_get("captains_daily_briefs", f"brief_type=eq.{brief_type}&order=generated_at.desc&limit=1&select=id")
        bel.flush(brief_type, brief_ref=(rows[0].get("id") if rows else None), kind=brief_type)
    except Exception as exc:  # noqa: BLE001 - best-effort audit trail
        log.warning("Brief event recording skipped: %s", exc)


def send_brief(brief_type: str, **kwargs) -> bool:
    """Generate and deliver a brief. Returns True if Telegram delivery succeeded."""
    signals: list[dict] = []
    evidence_window_hours: int | None = None
    collection_caveat: str | None = None
    if brief_type == "morning":
        gap = _morning_gap()
        collection_caveat = _collection_coverage_caveat("intelligence_collection")
        text = generate_morning_brief(gap, collection_caveat, catch_up=bool(kwargs.get("catch_up")))
        # USS-TJR-MSN-0339 WP4: generate_morning_brief() does its own internal
        # signal fetch for display but doesn't return the count — re-fetch here
        # so the persisted signals_count reflects reality instead of always 0
        # (MSN-0338 §8 Gap #1).
        evidence_window_hours = gap.lookback_hours
        signals = _get_recent_signals(hours=evidence_window_hours)
        # HQ V1 Integration QA §21 (Deferred Gap I7): collection_caveat (feeding 06:00 job health) is computed above, once, so the
        # persisted value matches the coverage line shown in the text.
    elif brief_type == "midday":
        signals = kwargs.get("signals", [])
        if not signals:
            log.info("Midday check: no new signals — suppressing brief")
            return True  # Not an error; conditional brief not needed
        text = generate_midday_update(signals)
    elif brief_type == "eod":
        text = generate_eod_summary()
        evidence_window_hours = 24
        signals = _get_recent_signals(hours=evidence_window_hours)
    elif brief_type == "weekly":
        text = generate_weekly_report()
        evidence_window_hours = 24 * 7
        signals = _get_recent_signals(hours=evidence_window_hours)
    elif brief_type == "knowledge_ops":
        text = generate_knowledge_ops_brief()
    elif brief_type == "weekly_debrief":
        text = generate_weekly_debrief_digest()
    else:
        log.error("Unknown brief type: %s", brief_type)
        return False
    _persist_brief(
        brief_type, text, signals_count=len(signals), health=_get_capacity_today(),
        evidence_window_hours=evidence_window_hours, collection_caveat=collection_caveat,
    )
    _record_brief_events(brief_type)
    if brief_type == "morning":
        # USS-TJR-MSN-0412 Stream 4: once-a-day database size guard (warns at
        # >= 450 MB, at most once per 24h; best-effort, never raises).
        from intelligence import db_size
        db_size.check_and_warn()
        try:
            _email_morning_brief(text)
        except Exception as exc:  # noqa: BLE001 - best-effort email delivery, already logged as non-blocking; Telegram is the real delivery/failure signal per this function's contract
            log.warning("Morning brief email failed (non-blocking): %s", exc)
    return _send_telegram(text)


def check_midday_signals(morning_timestamp_iso: str) -> list[dict]:
    """Return new HIGH/MEDIUM signals collected since morning brief."""
    return _get_new_signals_since(morning_timestamp_iso)
