"""
Proactive Cadence Jobs — migrated from platform-runtime/proactive_scheduler.py.

Previously Slack-bot-coupled (BackgroundScheduler + Slack WebClient). Now runs
inside the canonical intelligence/scheduler.py (BlockingScheduler) with Telegram
delivery via core/platform/notification_service.py.

Jobs registered here:
  decision_review          Fri 16:00  — pending decisions needing review
  weekly_review            Fri 16:30  — weekly summary (stale missions, decisions, health)
  knowledge_freshness      Wed 09:00  — knowledge files not updated in 90+ days
  decision_outcome_reminder Wed 09:15 — decisions overdue for outcome review
  monthly_lessons_digest   1st 08:00  — lessons digest from Lessons-Learned.md
  ko_monthly_brief         1st 08:30  — Knowledge Officer monthly brief
  forgotten_decisions      Mon+Thu 09:30 — unresolved governance decisions/ADRs
  fortnightly_idea_review  Mon 08:45 (odd ISO weeks) — triage Idea-status missions
  lifecycle_recommendations daily 08:15 — pending approvals (gated by LIFECYCLE_RECS_ENABLED)
  shakedown_digest         RETIRED 2026-08-27 — was daily 20:00, see the
                           retirement comment at its scheduler.add_job() site
  mission_registry_sync    daily 06:45 — sync Supabase missions → registry (background)
  content_pipeline         daily 06:15 — content signal promotion + draft worker (background)
  pending_research_sweep   every 5 min — recover stuck captured_items (background)

Migration: 2026-08-23. Slack bot (starfleet-slack-bot.service) decommissioned.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]

_STALE_DAYS              = int(os.environ.get("STALE_MISSION_DAYS", "7"))
_KNOWLEDGE_STALENESS_DAYS = 90
_DECISION_OUTCOME_DAYS   = 14
_PAIN_THRESHOLD          = int(os.environ.get("PAIN_ALERT_THRESHOLD", "7"))
_PAIN_DAYS               = int(os.environ.get("PAIN_ALERT_DAYS", "3"))

_KNOWLEDGE_WATCH_DIRS = ["knowledge", "governance", "Captains-Log"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _today() -> date:
    """Return today as a date in local (system) time."""
    return date.today()


def _today_iso() -> str:
    return _today().isoformat()


def _tg_notify(text: str) -> bool:
    """Send text to Captain via Telegram. Returns True on success."""
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.platform.notification_service import notify, Severity, Transport
        result = notify(text, severity=Severity.INFO, transport=Transport.TELEGRAM)
        return result.ok
    except Exception as exc:
        log.error("[proactive] Telegram notify failed: %s", exc)
        return False


def _shakedown_log(job_id: str, status: str, detail: str = "") -> None:
    """Best-effort shakedown event write. Never disrupts job execution."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from shakedown_logger import log_event
        log_event(job_id, status, detail, "telegram")
    except Exception as exc:
        log.debug("[shakedown] log_event failed (non-critical): %s", exc)
    try:
        # Relied on intelligence/scheduler.py having already inserted this
        # path as a side effect of its own heartbeat calls (true in the live
        # daemon, since scheduler.py is always the entrypoint) — but that
        # made this module's heartbeat writes silently ImportError whenever
        # proactive_cadences is imported/run standalone (found 2026-08-25
        # ad-hoc testing several jobs this way). Self-contained now.
        sys.path.insert(0, str(_REPO_ROOT / "core" / "platform"))
        from heartbeat import record_heartbeat
        hb = {"success": "ok", "failure": "failed", "skipped": "skipped"}.get(status, "failed")
        if not record_heartbeat(job_id, status=hb, detail=detail or None,
                                error_message=detail if hb == "failed" else None):
            log.warning("[heartbeat] record_heartbeat(%s) returned False (see heartbeat.py logs)", job_id)
    except Exception as exc:
        log.warning("[heartbeat] record_heartbeat(%s) raised: %s", job_id, exc)


def _get_stale_missions() -> list[dict]:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
        from client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not c.is_enabled():
            return []
        cutoff = (date.today() - timedelta(days=_STALE_DAYS)).isoformat()
        rows = c.get(
            f"missions?select=id,title,status,updated_at"
            f"&status=in.(Active,IN_PROGRESS,Blocked,BLOCKED,Planned,TRIAGED)"
            f"&updated_at=lte.{cutoff}T00:00:00Z"
            f"&order=updated_at.asc&limit=10"
        )
        return [{"id": r.get("id", ""), "title": r.get("title", ""), "status": r.get("status", "")}
                for r in (rows or [])]
    except Exception as exc:
        log.warning("[proactive] Stale mission check failed: %s", exc)
        return []


def _get_pending_decisions() -> list[dict]:
    import json as _json
    decisions_dir = _REPO_ROOT / "USS-TJR-Control" / "logs" / "decisions"
    if not decisions_dir.exists():
        decisions_dir = _REPO_ROOT / "logs" / "decisions"
    if not decisions_dir.exists():
        return []
    try:
        pending = []
        for f in sorted(decisions_dir.glob("*.json"))[-50:]:
            try:
                data = _json.loads(f.read_text())
                outcome = data.get("captain_outcome") or data.get("outcome") or data.get("captain_review")
                if not outcome or outcome in (None, "null", ""):
                    pending.append({
                        "id": data.get("decision_id") or f.stem,
                        "question": data.get("question") or data.get("title") or "(no title)",
                        "date": data.get("date") or data.get("timestamp", "")[:10],
                    })
            except Exception:
                continue
        return pending[:10]
    except Exception as exc:
        log.warning("[proactive] Pending decision check failed: %s", exc)
        return []


def _get_stale_knowledge_files(limit: int = 10) -> list[dict]:
    cutoff = datetime.now().timestamp() - (_KNOWLEDGE_STALENESS_DAYS * 86400)
    stale = []
    for rel in _KNOWLEDGE_WATCH_DIRS:
        base = _REPO_ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            try:
                mtime = path.stat().st_mtime
                if mtime < cutoff:
                    age_days = int((datetime.now().timestamp() - mtime) / 86400)
                    stale.append({"path": str(path.relative_to(_REPO_ROOT)), "age_days": age_days})
            except OSError:
                continue
    stale.sort(key=lambda f: f["age_days"], reverse=True)
    return stale[:limit]


def _get_decisions_overdue_outcome(limit: int = 8) -> list[dict]:
    import re as _re
    decisions_dir = _REPO_ROOT / "knowledge" / "decisions"
    if not decisions_dir.exists():
        return []
    cutoff = datetime.now().timestamp() - (_DECISION_OUTCOME_DAYS * 86400)
    overdue = []
    for path in sorted(decisions_dir.glob("*.md")):
        try:
            mtime = path.stat().st_mtime
            if mtime > cutoff:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            if any(m in content.lower() for m in [
                "captain_outcome_review", "outcome review:", "outcome recorded",
                "decision outcome:", "review complete",
            ]):
                continue
            id_match = _re.search(r"decision id:\s*(DEC-\S+)", content, _re.IGNORECASE)
            dec_id = id_match.group(1).upper() if id_match else path.stem
            age_days = int((datetime.now().timestamp() - mtime) / 86400)
            overdue.append({"id": dec_id, "age_days": age_days})
        except OSError:
            continue
    overdue.sort(key=lambda d: d["age_days"], reverse=True)
    return overdue[:limit]


def _generate_lessons_digest() -> str:
    import re as _re
    lessons_path = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
    if not lessons_path.exists():
        return ""
    content = lessons_path.read_text(encoding="utf-8", errors="replace")
    entries = _re.split(r"(?=^## LL-\d+)", content, flags=_re.MULTILINE)
    if len(entries) <= 1:
        return ""
    today = _today()
    last_month = today.replace(day=1) - timedelta(days=1)
    month_pattern = last_month.strftime("%Y-%m")
    this_month_pattern = today.strftime("%Y-%m")
    recent = [e for e in entries if month_pattern in e or this_month_pattern in e]
    all_entries = [e for e in entries if e.strip().startswith("## LL-")]
    lines = [f"Monthly Lessons Digest — {today.strftime('%B %Y')}", ""]
    if recent:
        lines.append(f"{len(recent)} lesson(s) this period:")
        for entry in recent:
            id_match = _re.search(r"## (LL-\d+)", entry)
            mission_match = _re.search(r"Mission:\s*(.+)", entry)
            outcome_match = _re.search(r"Outcome:\s*(.+)", entry)
            eid = id_match.group(1) if id_match else "?"
            mission = mission_match.group(1).strip()[:60] if mission_match else "unknown"
            outcome = outcome_match.group(1).strip()[:80] if outcome_match else "see record"
            lines.append(f"  • {eid} — {mission}: {outcome}")
    else:
        lines.append(f"No new lessons recorded this period. {len(all_entries)} total in register.")
        lines.append("Use 'close mission [ID] outcome: ...' when closing missions.")
    return "\n".join(lines)


def _generate_ko_monthly_brief() -> str:
    import re as _re
    today = _today()
    lessons_path = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
    knowledge_records_dir = _REPO_ROOT / "knowledge" / "missions"
    adr_dir = _REPO_ROOT / "core" / "governance" / "architecture-decision-records"
    lesson_count = 0
    if lessons_path.exists():
        content = lessons_path.read_text(encoding="utf-8", errors="replace")
        lesson_count = len(_re.findall(r"^## LL-\d+", content, _re.MULTILINE))
    kr_count = len(list(knowledge_records_dir.glob("*-knowledge-record.md"))) if knowledge_records_dir.exists() else 0
    adr_count = len(list(adr_dir.glob("ADR-*.txt")) + list(adr_dir.glob("ADR-*.md"))) if adr_dir.exists() else 0
    stale = _get_stale_knowledge_files(limit=3)
    lines = [
        f"Knowledge Officer Monthly Brief — {today.strftime('%B %Y')}",
        "",
        "Knowledge State:",
        f"  • Lessons Learned register: {lesson_count} entries",
        f"  • Mission knowledge records: {kr_count} records",
        f"  • Architecture Decision Records: {adr_count} ADRs",
        "",
    ]
    if stale:
        lines.append("Stale knowledge (90+ days unchanged):")
        for f in stale:
            lines.append(f"  • {f['path']} — {f['age_days']} days")
        lines.append("")
    lines.append("Number One asks: What knowledge gaps exist that would change a current decision?")
    return "\n".join(lines)


def _get_idea_missions() -> list[dict]:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not c.is_enabled():
            return []
        rows = c.get("missions?select=*&status=ilike.Idea&order=created_at.asc&limit=30")
        return rows or []
    except Exception as exc:
        log.debug("[proactive] Idea missions unavailable: %s", exc)
        return []


def _format_idea_review(missions: list[dict]) -> str:
    if not missions:
        return ""
    now = datetime.utcnow()
    lines = [
        "Number One — Fortnightly Idea Review",
        f"Cycle: {_today().strftime('%Y-%m-%d')}",
        "",
        f"{len(missions)} idea{'s' if len(missions) != 1 else ''} awaiting triage:",
        "",
    ]
    for m in missions:
        mid = m.get("id") or m.get("mission_id", "?")
        title = m.get("title", "Untitled")
        created_raw = m.get("created_at", "")
        age_str = ""
        if created_raw:
            try:
                from datetime import timezone as _tz
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00").replace("+00:00", ""))
                age_days = (now - created).days
                age_str = f" · {age_days}d old"
                if age_days >= 28:
                    age_str += " (overdue)"
            except (ValueError, TypeError):
                pass
        lines.append(f"  • {mid} — {title}{age_str}")
    lines += [
        "",
        "Triage each idea:",
        "  Promote — /mission-status <id> planned",
        "  Hold    — /mission-status <id> idea",
        "  Archive — /mission-status <id> closed",
        "",
        "No autonomous promotion. Captain decides.",
    ]
    return "\n".join(lines)


def _is_fortnightly_monday() -> bool:
    today = _today()
    return today.weekday() == 0 and today.isocalendar()[1] % 2 == 1


def _check_health_logged_today() -> bool:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return False
        today = _today_iso()
        rows = supabase_get(f"captains_log_entries?log_date=eq.{today}&limit=1")
        if rows:
            return True
        pulses = supabase_get("recovery_confidence_today?select=pulses_completed&limit=1")
        return bool(pulses and pulses[0].get("pulses_completed", 0) > 0)
    except Exception:
        return False


# ── Scheduled job functions ───────────────────────────────────────────────────

def job_decision_review() -> None:
    """Fri 16:00 — surface pending decisions for review."""
    pending = _get_pending_decisions()
    if not pending:
        log.info("[proactive] No pending decisions for review")
        _shakedown_log("decision_review", "skipped", "No pending decisions")
        return
    lines = [f"{len(pending)} decision(s) awaiting your review:", ""]
    for d in pending[:8]:
        lines.append(f"  • {d['id']} ({d['date']}) — {d['question'][:80]}")
    lines.append("\nReview in Captain's Chair → Decisions.")
    ok = _tg_notify("\n".join(lines))
    _shakedown_log("decision_review", "success" if ok else "failure",
                   f"{len(pending)} decisions surfaced")


def job_weekly_review() -> None:
    """Fri 16:30 — weekly review summary."""
    stale = _get_stale_missions()
    pending = _get_pending_decisions()
    health_logged = _check_health_logged_today()
    lines = [
        f"Weekly Review — Starship Endeavour",
        f"Week ending {_today().strftime('%Y-%m-%d')}",
        "",
        f"Stale missions: {len(stale)} missions with no update in {_STALE_DAYS}+ days",
        f"Pending decisions: {len(pending)} awaiting review",
        f"Health check-in today: {'logged' if health_logged else 'not logged'}",
        "",
        "Number One asks: What did you learn this week that should enter permanent knowledge?",
    ]
    ok = _tg_notify("\n".join(lines))
    _shakedown_log("weekly_review", "success" if ok else "failure")


def job_knowledge_freshness() -> None:
    """Wed 09:00 — flag knowledge files not updated in 90+ days."""
    stale = _get_stale_knowledge_files()
    if not stale:
        log.info("[proactive] Knowledge freshness: all files current")
        _shakedown_log("knowledge_freshness", "skipped", "All knowledge files current")
        return
    lines = [
        f"Knowledge Freshness Alert — {len(stale)} file(s) not updated in {_KNOWLEDGE_STALENESS_DAYS}+ days:",
        "",
    ]
    for f in stale[:8]:
        lines.append(f"  • {f['path']} — {f['age_days']} days")
    lines.append("\nReview and update to keep the knowledge base current.")
    ok = _tg_notify("\n".join(lines))
    _shakedown_log("knowledge_freshness", "success" if ok else "failure",
                   f"{len(stale)} stale files alerted")


def job_decision_outcome_reminder() -> None:
    """Wed 09:15 — decisions overdue for outcome review."""
    overdue = _get_decisions_overdue_outcome()
    if not overdue:
        log.info("[proactive] Decision outcome: all decisions have outcomes")
        _shakedown_log("decision_outcome_reminder", "skipped", "All decisions have outcomes")
        return
    lines = [
        f"{len(overdue)} decision(s) overdue for outcome review ({_DECISION_OUTCOME_DAYS}+ days):",
        "",
    ]
    for d in overdue[:6]:
        lines.append(f"  • {d['id']} — {d['age_days']} days old")
    lines.append("\nAdd captain_outcome_review: to each decision record.")
    ok = _tg_notify("\n".join(lines))
    _shakedown_log("decision_outcome_reminder", "success" if ok else "failure",
                   f"{len(overdue)} decisions surfaced")


def job_monthly_lessons_digest() -> None:
    """1st of month 08:00 — monthly lessons digest. Never had a heartbeat
    wired in (found 2026-08-25 ad-hoc testing) — added below."""
    digest = _generate_lessons_digest()
    if not digest:
        log.info("[proactive] Monthly lessons digest: no lessons to surface")
        _shakedown_log("monthly_lessons_digest", "skipped", "No lessons to surface")
        return
    ok = _tg_notify(digest)
    log.info("[proactive] Monthly lessons digest sent")
    _shakedown_log("monthly_lessons_digest", "success" if ok else "failure", "")


def job_ko_monthly_brief() -> None:
    """1st of month 08:30 — Knowledge Officer monthly brief. Never had a
    heartbeat wired in (found 2026-08-25 ad-hoc testing) — added below."""
    brief = _generate_ko_monthly_brief()
    if not brief:
        log.info("[proactive] KO monthly brief: nothing to surface")
        _shakedown_log("ko_monthly_brief", "skipped", "No brief content")
        return
    ok = _tg_notify(brief)
    log.info("[proactive] KO monthly brief sent")
    _shakedown_log("ko_monthly_brief", "success" if ok else "failure", "")


def job_forgotten_decisions() -> None:
    """Mon+Thu 09:30 — unresolved governance decisions/ADRs."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "platform-runtime"))
        from captain_notifications import (
            get_config as _get_notif_config,
            get_forgotten_decisions,
            format_forgotten_decisions,
        )
    except ImportError:
        log.debug("[proactive] captain_notifications unavailable — forgotten_decisions skipped")
        return
    cfg = _get_notif_config()
    if not cfg.forgotten_decisions:
        log.debug("[proactive] Forgotten decisions disabled by config")
        return
    try:
        items = get_forgotten_decisions()
        if not items:
            log.info("[proactive] No forgotten decisions found")
            _shakedown_log("forgotten_decisions", "skipped", "No forgotten decisions found")
            return
        msg = format_forgotten_decisions(items)
        ok = _tg_notify(msg)
        log.info("[proactive] Forgotten decisions alert sent (%d items)", len(items))
        _shakedown_log("forgotten_decisions", "success" if ok else "failure",
                       f"{len(items)} items")
    except Exception as exc:
        log.error("[proactive] Forgotten decisions job failed: %s", exc)
        _shakedown_log("forgotten_decisions", "failure", str(exc))


def job_fortnightly_idea_review() -> None:
    """Mon 08:45, odd ISO weeks — triage Idea-status missions."""
    if not _is_fortnightly_monday():
        return
    try:
        missions = _get_idea_missions()
        if not missions:
            log.info("[proactive] No Idea-status missions — skipping fortnightly review")
            return
        msg = _format_idea_review(missions)
        if msg:
            _tg_notify(msg)
            log.info("[proactive] Fortnightly idea review sent (%d ideas)", len(missions))
    except Exception as exc:
        log.error("[proactive] Fortnightly idea review failed: %s", exc)


def job_lifecycle_recommendations() -> None:
    """Daily 08:15 — pending approvals (gated by LIFECYCLE_RECS_ENABLED)."""
    if os.environ.get("LIFECYCLE_RECS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.coordination.pending_actions import build_pending_actions
        payload = build_pending_actions()
        totals = payload.get("totals", {})
        awaiting = totals.get("awaiting_approval", 0)
        review = totals.get("review", 0)
        needing = awaiting + review
        if not needing:
            return
        lines = [f"XO to Captain — {needing} request(s) need your review/approval:"]
        if awaiting:
            lines.append(f"\nAwaiting your approval — triaged, Gate 1 ({awaiting}):")
            for a in payload.get("awaiting_approval", [])[:8]:
                prio = a.get("suggested_priority", "")
                tag = f" [{prio}]" if prio else ""
                lines.append(f"  • {a.get('id')}{tag} — approve / defer / request clarification")
        if review:
            lines.append(f"\nAwaiting your review — delivered, Gate 2 ({review}):")
            for r in payload.get("review", [])[:8]:
                lines.append(f"  • {r.get('id')} — {r.get('next_actor', '')}")
        lines.append("\nAdvisory only — nothing is approved or merged without your sign-off.")
        ok = _tg_notify("\n".join(lines))
        log.info("[proactive] Lifecycle recommendations sent (%d items)", needing)
        _shakedown_log("lifecycle_recommendations", "success" if ok else "failure",
                       f"{needing} items")
    except Exception as exc:
        log.error("[proactive] Lifecycle recommendations failed: %s", exc)
        _shakedown_log("lifecycle_recommendations", "failure", str(exc))


def job_shakedown_digest() -> None:
    """Daily 20:00 — operational shakedown day summary."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from shakedown_logger import get_day_summary, format_day_summary_for_slack
        summary = get_day_summary(_today())
        msg = format_day_summary_for_slack(summary)
        ok = _tg_notify(msg)
        log.info("[proactive] Shakedown digest sent (events=%d, failures=%d)",
                 summary["total_events"], summary["failure_count"])
        _shakedown_log("shakedown_digest", "success" if ok else "failure",
                       f"Day {summary['day_n']}: {summary['total_events']} events, "
                       f"{summary['failure_count']} failures")
    except Exception as exc:
        log.error("[proactive] Shakedown digest failed: %s", exc)
        _shakedown_log("shakedown_digest", "failure", str(exc))


def job_mission_registry_sync() -> None:
    """Daily 06:45 — sync Supabase missions → mission-index.txt (no delivery)."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "tools"))
        from sync_supabase_to_registry import sync, load_registry_ids
        before = load_registry_ids()
        sync(dry_run=False)
        added = len(load_registry_ids()) - len(before)
        if added > 0:
            log.info("[proactive] Mission registry sync: %d new mission(s) appended", added)
            _shakedown_log("mission_registry_sync", "success", f"{added} new mission(s)")
        else:
            log.info("[proactive] Mission registry sync: already up to date")
            _shakedown_log("mission_registry_sync", "skipped", "Registry already up to date")
    except Exception as exc:
        log.error("[proactive] Mission registry sync failed: %s", exc)
        _shakedown_log("mission_registry_sync", "failure", str(exc))


def job_content_pipeline() -> None:
    """Daily 06:15 — content signal promotion + draft worker (no delivery)."""
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.content.signal_opportunity_converter import create_opportunities_from_signals
        promoted = create_opportunities_from_signals(limit=5, min_rank_score=70.0)
        log.info("[proactive] Content signal promotion: %s (%d/%d created)",
                 promoted.get("status"), promoted.get("created", 0), promoted.get("requested", 0))
    except Exception as exc:
        log.error("[proactive] Content signal promotion failed: %s", exc)
        _shakedown_log("content_pipeline", "failure", f"promotion: {exc}")
        return
    try:
        from core.content.draft_worker import fetch_pending, process_item
        items = fetch_pending(limit=5)
        drafted = sum(1 for item in items if process_item(item, dry_run=False))
        log.info("[proactive] Content drafting: %d/%d item(s) drafted", drafted, len(items))
        _shakedown_log("content_pipeline", "success",
                       f"promoted={promoted.get('created', 0)} drafted={drafted}/{len(items)}")
    except Exception as exc:
        log.error("[proactive] Content drafting failed: %s", exc)
        _shakedown_log("content_pipeline", "failure", f"drafting: {exc}")


def job_pending_research_sweep() -> None:
    """Every 5 min — recover stuck captured_items (no delivery). Never had a
    heartbeat wired in (found 2026-08-25: runs successfully every 5 min per
    journalctl, zero heartbeats ever) — added below."""
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.inbox.orchestrator import _run_research, _db, process_captured_item
        if not _db.enabled():
            _shakedown_log("pending_research_sweep", "skipped", "inbox DB disabled")
            return
        unprocessed = (
            _db._client.table("captured_items")
            .select("id, title")
            .eq("processing_status", "pending")
            .order("captured_at", desc=False)
            .limit(10)
            .execute()
        )
        pass1_ids: set = set()
        for item in (unprocessed.data or []):
            try:
                log.info("[proactive] Orchestrating unprocessed item: %s",
                         item.get("title", item["id"])[:60])
                pass1_ids.add(item["id"])
                process_captured_item(item["id"])
            except Exception as exc:
                log.error("[proactive] Orchestration failed for %s: %s", item["id"], exc)
        queued = (
            _db._client.table("captured_items")
            .select("*")
            .eq("research_status", "pending")
            .order("captured_at", desc=False)
            .limit(5)
            .execute()
        )
        research_items = [r for r in (queued.data or []) if r["id"] not in pass1_ids]
        for item in research_items:
            try:
                _run_research(item["id"], item)
            except Exception as exc:
                log.error("[proactive] Research failed for %s: %s", item["id"], exc)
        _shakedown_log(
            "pending_research_sweep", "success",
            f"processed={len(pass1_ids)} researched={len(research_items)}",
        )
    except Exception as exc:
        log.error("[proactive] Pending research sweep failed: %s", exc)
        _shakedown_log("pending_research_sweep", "failure", str(exc))


# ── Registration ──────────────────────────────────────────────────────────────

def register_jobs(scheduler, tz) -> None:
    """Register all proactive cadence jobs into the canonical BlockingScheduler."""
    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        log.error("[proactive] apscheduler not available — proactive cadences not registered")
        return

    # Background pipeline jobs (no Telegram delivery)
    scheduler.add_job(
        job_content_pipeline,
        CronTrigger(hour=6, minute=15, timezone=tz),
        id="content_pipeline",
        name="Content Signal-to-Draft Pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        job_mission_registry_sync,
        CronTrigger(hour=6, minute=45, timezone=tz),
        id="mission_registry_sync",
        name="Mission Registry Sync (ADR-024)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_pending_research_sweep,
        IntervalTrigger(minutes=5),
        id="pending_research_sweep",
        name="Pending Research Sweep",
        replace_existing=True,
    )

    # Telegram delivery jobs
    scheduler.add_job(
        job_lifecycle_recommendations,
        CronTrigger(hour=8, minute=15, timezone=tz),
        id="lifecycle_recommendations",
        name="Lifecycle Pending Actions (MSN-0066)",
        replace_existing=True,
    )
    # fortnightly_idea_review disabled: no dedup/ack, re-nags the same
    # Idea-status missions verbatim every cycle with no resolution path.
    scheduler.add_job(
        job_knowledge_freshness,
        CronTrigger(day_of_week="wed", hour=9, minute=0, timezone=tz),
        id="knowledge_freshness",
        name="Weekly Knowledge Freshness Check",
        replace_existing=True,
    )
    scheduler.add_job(
        job_decision_outcome_reminder,
        CronTrigger(day_of_week="wed", hour=9, minute=15, timezone=tz),
        id="decision_outcome_reminder",
        name="Decision Outcome Reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        job_forgotten_decisions,
        CronTrigger(day_of_week="mon,thu", hour=9, minute=30, timezone=tz),
        id="forgotten_decisions",
        name="Forgotten Decisions & ADR Alert",
        replace_existing=True,
    )
    scheduler.add_job(
        job_decision_review,
        CronTrigger(day_of_week="fri", hour=16, minute=0, timezone=tz),
        id="decision_review",
        name="Friday Decision Review",
        replace_existing=True,
    )
    scheduler.add_job(
        job_weekly_review,
        CronTrigger(day_of_week="fri", hour=16, minute=30, timezone=tz),
        id="weekly_review",
        name="Friday Weekly Review",
        replace_existing=True,
    )
    # shakedown_digest retired 2026-08-27 (Captain-directed): the shakedown
    # concept (core/health/shakedown_logger.py) was a 7-day operational
    # burn-in tracker starting 2026-06-15 (mission M-20260615), never
    # unregistered after that window closed — the daily digest was still
    # reporting "Shakedown Day 74" on nothing more than pending_research_sweep's
    # routine 5-minute heartbeat. job_shakedown_digest() and the underlying
    # shakedown_logger.log_event() calls scattered through this module are
    # left in place (harmless JSONL writes, other jobs' own logging), just
    # unregistered — re-add this scheduler.add_job() to revive it.
    scheduler.add_job(
        job_monthly_lessons_digest,
        CronTrigger(day=1, hour=8, minute=0, timezone=tz),
        id="monthly_lessons_digest",
        name="Monthly Lessons Digest",
        replace_existing=True,
    )
    scheduler.add_job(
        job_ko_monthly_brief,
        CronTrigger(day=1, hour=8, minute=30, timezone=tz),
        id="ko_monthly_brief",
        name="Knowledge Officer Monthly Brief",
        replace_existing=True,
    )

    log.info(
        "[proactive] 12 cadence jobs registered: "
        "content_pipeline 06:15, mission_registry_sync 06:45, lifecycle_recs 08:15, "
        "fortnightly_idea_review Mon 08:45, knowledge_freshness Wed 09:00, "
        "decision_outcome_reminder Wed 09:15, forgotten_decisions Mon+Thu 09:30, "
        "decision_review Fri 16:00, weekly_review Fri 16:30, "
        "monthly_digest+ko_brief 1st-of-month, "
        "pending_research_sweep every 5min "
        "(shakedown_digest retired 2026-08-27)"
    )
