"""
Proactive Scheduler — Starship Endeavour Number One Heartbeat

Converts USS TJR OS from a reactive command-response platform into a
proactive operating system that initiates interaction with the Captain.

Schedules:
  - Morning Brief push at BRIEF_TIME (default 07:30 local)
  - Health check-in reminder if no entry logged today
  - Stale mission detection (daily, after brief)
  - Pending decision review (Friday, 16:00)
  - Weekly review generation (Friday, 16:30)
  - Weekly health synthesis (Saturday 08:00)  [M-20260614 WP3]
  - Appointment preparation check (daily 08:45)  [M-20260614 WP4]
  - Pain escalation detection (daily, after brief)  [M-20260614 WP6]

Configuration (.env):
  BRIEF_TIME              = "07:30"   # 24h local time for morning push
  BRIEF_CHANNEL           = "D..."    # Slack DM channel or channel ID
  BRIEF_USER_ID           = "U..."    # Captain's Slack user ID (for DM)
  STALE_MISSION_DAYS      = "7"       # Days before a mission is flagged stale
  SCHEDULER_ENABLED       = "true"    # Set false to disable all scheduled jobs
  PAIN_ALERT_THRESHOLD    = "7"       # Pain score >= this triggers escalation alert
  PAIN_ALERT_DAYS         = "3"       # Consecutive days at threshold to trigger alert
  APPOINTMENT_LEAD_DAYS   = "2"       # Days ahead to detect upcoming appointments

Usage:
  from proactive_scheduler import start_scheduler
  start_scheduler(slack_client)   # call after bot is initialised

# LOCAL SCHEDULER: tightly coupled to Slack bot process — cannot migrate to
# canonical scheduler (intelligence/scheduler.py). start_scheduler() accepts
# a live Slack WebClient; every job function takes that client as its first
# argument and delivers via Slack chat_postMessage / _post(). The canonical
# scheduler is a BlockingScheduler with no Slack client. This scheduler runs
# inside platform-runtime/app.py (the Slack bot) and is dormant when that
# process is down.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

try:
    from lib.tz import today_brisbane_iso as _today_iso, today_brisbane as _today_date
except Exception:
    def _today_iso() -> str: return date.today().isoformat()  # type: ignore[misc]
    def _today_date() -> date: return date.today()  # type: ignore[misc]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Import notification framework (graceful fallback if unavailable)
try:
    from captain_notifications import (
        get_config as _get_notif_config,
        get_mission_escalations,
        format_mission_escalation_batch,
        get_forgotten_decisions,
        format_forgotten_decisions,
        build_work_queue,
        should_send_health_nudge,
        health_nudge_text,
        mission_close_lesson_warning,
        SEVERITY_WARNING,
        SEVERITY_ALERT,
        SEVERITY_CRITICAL,
    )
    _NOTIFICATIONS_AVAILABLE = True
except ImportError:
    _NOTIFICATIONS_AVAILABLE = False
    log.warning("[scheduler] captain_notifications not available — enhanced escalations disabled")

# Import WP1 escalation manager (graceful fallback)
try:
    from escalation_manager import process_escalations as _process_escalations
    _ESCALATION_MANAGER_AVAILABLE = True
except ImportError:
    _ESCALATION_MANAGER_AVAILABLE = False
    log.warning("[scheduler] escalation_manager not available — cadence control disabled")

# Import WP2 alert metrics (graceful fallback)
try:
    from alert_metrics import get_metrics_block_for_brief as _metrics_block
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

# Import WP3 risk scoring (graceful fallback)
try:
    from mission_risk import format_risk_brief_block as _risk_brief_block
    _RISK_AVAILABLE = True
except ImportError:
    _RISK_AVAILABLE = False

_BRIEF_TIME      = os.environ.get("BRIEF_TIME", "07:30")
_BRIEF_CHANNEL   = os.environ.get("BRIEF_CHANNEL", "")
_BRIEF_USER_ID   = os.environ.get("BRIEF_USER_ID", "")
_STALE_DAYS      = int(os.environ.get("STALE_MISSION_DAYS", "7"))
_ENABLED         = os.environ.get("SCHEDULER_ENABLED", "true").lower() not in ("false", "0", "no")
_PAIN_THRESHOLD  = int(os.environ.get("PAIN_ALERT_THRESHOLD", "7"))
_PAIN_DAYS       = int(os.environ.get("PAIN_ALERT_DAYS", "3"))
_APPT_LEAD_DAYS  = int(os.environ.get("APPOINTMENT_LEAD_DAYS", "2"))

# ---------------------------------------------------------------------------
# Slack post helper
# ---------------------------------------------------------------------------

def _post(client, text: str, blocks=None) -> bool:
    """Post a message to the configured channel/DM. Returns True on success."""
    channel = _BRIEF_CHANNEL or _BRIEF_USER_ID
    if not channel:
        log.warning("[scheduler] BRIEF_CHANNEL and BRIEF_USER_ID not set — cannot push message")
        return False
    try:
        kwargs: dict = {"channel": channel, "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        client.chat_postMessage(**kwargs)
        return True
    except Exception as exc:
        log.error("[scheduler] Slack post failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Brief generation
# ---------------------------------------------------------------------------

def _fetch_captain_brief_text() -> str:
    """Call the context service and return a formatted brief string."""
    try:
        import urllib.request, json as _json
        api_base = os.environ.get("COMMAND_CENTRE_API", "http://localhost:5050")
        url = f"{api_base}/api/v1/context/captain-brief"
        headers = {}
        api_key = os.environ.get("BACKEND_API_KEY")
        if api_key:
            headers["X-Api-Key"] = api_key
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        return _format_brief(data)
    except Exception as exc:
        log.warning("[scheduler] HTTP brief fetch failed (%s), trying subprocess", exc)
        return _fetch_brief_subprocess()


def _fetch_brief_subprocess() -> str:
    """Fallback: run context_service.py captain-brief via subprocess."""
    import subprocess
    script = _REPO_ROOT / "core" / "context-assembly" / "context_service.py"
    if not script.exists():
        return "_(Captain's Brief unavailable — context service not found)_"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "captain-brief"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": str(_REPO_ROOT / "core" / "context-assembly")},
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:2000]
        return "_(Captain's Brief generation failed — check context service logs)_"
    except Exception as exc:
        return f"_(Captain's Brief unavailable: {exc})_"


def _format_brief(data: dict) -> str:
    lines = ["*:star: Good morning, Captain. Number One reporting.*", ""]
    if data.get("assembled_at"):
        lines.append(f"_Brief assembled: {data['assembled_at'][:16].replace('T', ' ')} UTC_")
        lines.append("")

    missions = data.get("missions") or data.get("top_priorities") or []
    if missions:
        lines.append("*Active Missions:*")
        for m in missions[:5]:
            mid = m.get("id") or m.get("mission_id", "")
            title = m.get("title", "")
            status = m.get("status", "")
            lines.append(f"  • {mid} — {title} `{status}`")
        lines.append("")

    blockers = data.get("blockers") or []
    if blockers:
        lines.append(f"*:warning: Blockers ({len(blockers)}):*")
        for b in blockers[:3]:
            lines.append(f"  • {b.get('mission_id', '')} — {b.get('reason', b.get('description', ''))}")
        lines.append("")

    rec = data.get("recommended_next_action") or data.get("recommendation") or {}
    if rec:
        lines.append(f"*Number One recommends:* {rec.get('action', rec.get('rationale', ''))}")
        lines.append("")

    health = data.get("health") or {}
    wl = health.get("workload_constraint", "unknown")
    dq = health.get("data_quality", "missing")
    if dq == "missing":
        lines.append(":heart: *Health:* No check-in data — please log /health-check today.")
    else:
        lines.append(f":heart: *Health:* Workload capacity `{wl}` (data quality: `{dq}`)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health check-in reminder
# ---------------------------------------------------------------------------

def _check_health_logged_today() -> bool:
    """Return True if a health check-in or capacity check-in exists for today.

    recovery_confidence_today is a view over the retired recovery_pulses
    table (zero writes since 2026-08-21) — capacity_checkins_today is the
    live equivalent since the 2026-08-22 MY CAPACITY TODAY migration
    (core/infrastructure/supabase/migrations/0150, 0181).
    """
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return False
        today = _today_iso()
        rows = supabase_get(f"captains_log_entries?log_date=eq.{today}&limit=1")
        if rows:
            return True
        checkins = supabase_get("capacity_checkins_today?select=checkins_today&limit=1")
        return bool(checkins and checkins[0].get("checkins_today", 0) > 0)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Stale mission detection
# ---------------------------------------------------------------------------

def _get_stale_missions() -> list[dict]:
    """Return active missions from Supabase that have not been updated in _STALE_DAYS days."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
        from client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.warning("[scheduler] Supabase not configured — stale mission check skipped.")
            return []
        cutoff = (date.today() - timedelta(days=_STALE_DAYS)).isoformat()
        rows = client.get(
            f"missions?select=id,title,status,updated_at"
            f"&status=in.(Active,IN_PROGRESS,Blocked,BLOCKED,Planned,TRIAGED)"
            f"&updated_at=lte.{cutoff}T00:00:00Z"
            f"&order=updated_at.asc&limit=10"
        )
        return [{"id": r.get("id", ""), "title": r.get("title", ""), "status": r.get("status", "")} for r in (rows or [])]
    except Exception as exc:
        log.warning("[scheduler] Stale mission check failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Pending decisions
# ---------------------------------------------------------------------------

def _get_pending_decisions() -> list[dict]:
    """Return runtime decision logs with no Captain outcome review."""
    decisions_dir = _REPO_ROOT / "USS-TJR-Control" / "logs" / "decisions"
    if not decisions_dir.exists():
        decisions_dir = _REPO_ROOT / "logs" / "decisions"
    if not decisions_dir.exists():
        return []
    try:
        import json as _json
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
                        "file": str(f),
                    })
            except Exception:
                continue
        return pending[:10]
    except Exception as exc:
        log.warning("[scheduler] Pending decision check failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Knowledge freshness check (Month 2)
# ---------------------------------------------------------------------------

_KNOWLEDGE_STALENESS_DAYS = 90
_KNOWLEDGE_WATCH_DIRS = [
    "knowledge",
    "governance",
    "Captains-Log",
]


def _get_stale_knowledge_files(limit: int = 10) -> list[dict]:
    """Return knowledge files not modified in 90+ days."""
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
                    stale.append({
                        "path": str(path.relative_to(_REPO_ROOT)),
                        "age_days": age_days,
                    })
            except OSError:
                continue
    stale.sort(key=lambda f: f["age_days"], reverse=True)
    return stale[:limit]


# ---------------------------------------------------------------------------
# Decision outcome reminders (Month 3)
# ---------------------------------------------------------------------------

_DECISION_OUTCOME_DAYS = 14


def _get_decisions_overdue_outcome(limit: int = 8) -> list[dict]:
    """Return decision records > 14 days old with no outcome review recorded."""
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
                continue  # too recent
            content = path.read_text(encoding="utf-8", errors="replace")
            # Skip if outcome review already present
            if any(marker in content.lower() for marker in [
                "captain_outcome_review", "outcome review:", "outcome recorded",
                "decision outcome:", "review complete",
            ]):
                continue
            id_match = _re.search(r"decision id:\s*(DEC-\S+)", content, _re.IGNORECASE)
            dec_id = id_match.group(1).upper() if id_match else path.stem
            age_days = int((datetime.now().timestamp() - mtime) / 86400)
            overdue.append({"id": dec_id, "age_days": age_days, "file": path.name})
        except OSError:
            continue
    overdue.sort(key=lambda d: d["age_days"], reverse=True)
    return overdue[:limit]


# ---------------------------------------------------------------------------
# Monthly lessons digest (Month 3)
# ---------------------------------------------------------------------------

def _generate_lessons_digest() -> str:
    """Read Lessons-Learned.md and produce a summary of entries from the last 30 days."""
    import re as _re
    lessons_path = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
    if not lessons_path.exists():
        return ""

    content = lessons_path.read_text(encoding="utf-8", errors="replace")
    # Lessons are delimited by ## LL-XXX headers
    entries = _re.split(r"(?=^## LL-\d+)", content, flags=_re.MULTILINE)
    if len(entries) <= 1:
        return ""

    # Pick entries that contain last month's date pattern (approximate)
    today = _today_date()
    last_month = today.replace(day=1) - timedelta(days=1)
    month_pattern = last_month.strftime("%Y-%m")
    this_month_pattern = today.strftime("%Y-%m")

    recent = [e for e in entries if month_pattern in e or this_month_pattern in e]
    all_entries = [e for e in entries if e.strip().startswith("## LL-")]

    lines = [f":books: *Monthly Lessons Digest — {today.strftime('%B %Y')}*", ""]
    if recent:
        lines.append(f"*{len(recent)} lesson(s) this period:*")
        for entry in recent:
            id_match = _re.search(r"## (LL-\d+)", entry)
            mission_match = _re.search(r"Mission:\s*(.+)", entry)
            outcome_match = _re.search(r"Outcome:\s*(.+)", entry)
            eid = id_match.group(1) if id_match else "?"
            mission = mission_match.group(1).strip()[:60] if mission_match else "unknown"
            outcome = outcome_match.group(1).strip()[:80] if outcome_match else "see record"
            lines.append(f"  • `{eid}` — {mission}: {outcome}")
    else:
        lines.append(f"_No new lessons recorded this period. {len(all_entries)} total in register._")
        lines.append("_Use `close mission [ID] outcome: ...` when closing missions to build the register._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Knowledge Officer monthly brief (Month 3)
# ---------------------------------------------------------------------------

def _generate_ko_monthly_brief() -> str:
    """Generate a KO brief: lessons count, knowledge records, stale files, ADR count."""
    import re as _re
    today = _today_date()

    lessons_path = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
    knowledge_records_dir = _REPO_ROOT / "knowledge" / "missions"
    adr_dir = _REPO_ROOT / "core" / "governance" / "architecture-decision-records"

    # Lesson count
    lesson_count = 0
    if lessons_path.exists():
        content = lessons_path.read_text(encoding="utf-8", errors="replace")
        lesson_count = len(_re.findall(r"^## LL-\d+", content, _re.MULTILINE))

    # Knowledge record count
    kr_count = len(list(knowledge_records_dir.glob("*-knowledge-record.md"))) if knowledge_records_dir.exists() else 0

    # ADR count
    adr_count = len(list(adr_dir.glob("ADR-*.txt")) + list(adr_dir.glob("ADR-*.md"))) if adr_dir.exists() else 0

    # Stale files
    stale = _get_stale_knowledge_files(limit=3)

    lines = [
        f":anchor: *Knowledge Officer Monthly Brief — {today.strftime('%B %Y')}*",
        "",
        "*Knowledge State:*",
        f"  • Lessons Learned register: {lesson_count} entries",
        f"  • Mission knowledge records: {kr_count} records",
        f"  • Architecture Decision Records: {adr_count} ADRs",
        "",
    ]
    if stale:
        lines.append(f"*Stale knowledge (90+ days unchanged):*")
        for f in stale:
            lines.append(f"  • `{f['path']}` — {f['age_days']} days")
        lines.append("")
    lines.append("*Number One asks:* What knowledge gaps exist that would change a current decision?")
    lines.append("_Review lessons register with `/knowledge lessons` or close open missions with outcome reviews._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Captain Readiness Score helper  [M-20260614 WP7]
# ---------------------------------------------------------------------------

def _fetch_readiness_block() -> str:
    """Generate Captain Readiness Score block for inclusion in morning brief."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))
        from readiness_score import compute_readiness_score, format_readiness_for_slack
        from capacity_score import capacity_zone_from_checkin
        from supabase_client import supabase_get, is_configured

        if not is_configured():
            return ""

        today = _today_iso()
        # MY CAPACITY TODAY (2026-08-21) replaced Recovery Pulse/
        # captains_log_entries as the Captain's day-to-day capacity input —
        # see capacity_zone_from_checkin()'s docstring.
        rows = supabase_get(
            f"capacity_checkins?log_date=eq.{today}&checkin_type=eq.capacity"
            "&order=captured_at.desc&limit=1"
        ) or []
        entry = rows[0] if rows else {}
        cap_score, cap_status = capacity_zone_from_checkin(entry) if entry else (None, "Unknown")

        # Fetch missions for ops component — Supabase is system of record (MSN-BOT-SOR)
        missions = []
        try:
            from client import CommanderSupabaseClient as _SupaClient
            _sc = _SupaClient()
            if _sc.is_enabled():
                _rows = _sc.get(
                    "missions?select=id,title,priority,status"
                    "&status=not.in.(Closed,Archived,Cancelled,CANCELLED,COMPLETED,Completed)"
                    "&order=created_at.asc&limit=50"
                )
                missions = [
                    {
                        "mission_id": r.get("id", ""),
                        "title": r.get("title", ""),
                        "priority": r.get("priority", "P3"),
                        "status": r.get("status", ""),
                    }
                    for r in (_rows or [])
                ]
            else:
                log.warning("[scheduler] Supabase not configured — readiness ops component empty.")
        except Exception as _exc:
            log.warning("[scheduler] Supabase mission fetch for readiness failed: %s", _exc)

        result = compute_readiness_score(cap_score, cap_status, missions)
        return "\n" + format_readiness_for_slack(result)
    except Exception as exc:
        log.debug("[scheduler] Readiness score unavailable: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Pain escalation detection  [M-20260614 WP6]
# ---------------------------------------------------------------------------

def _check_pain_escalation() -> Optional[dict]:
    """
    Return escalation info if pain has been >= _PAIN_THRESHOLD for >= _PAIN_DAYS consecutive days.
    Returns None if no escalation warranted or data is unavailable.
    """
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return None

        cutoff = (_today_date() - timedelta(days=_PAIN_DAYS + 2)).isoformat()
        rows = supabase_get(
            f"analytics_health_daily"
            f"?log_date=gte.{cutoff}"
            f"&order=log_date.desc"
            f"&limit={_PAIN_DAYS + 2}"
        ) or []

        if len(rows) < _PAIN_DAYS:
            return None

        # Check most recent _PAIN_DAYS rows all exceed threshold
        recent = rows[:_PAIN_DAYS]
        scores = [r.get("pain_score") for r in recent if r.get("pain_score") is not None]
        if len(scores) < _PAIN_DAYS:
            return None

        if all(s >= _PAIN_THRESHOLD for s in scores):
            return {
                "consecutive_days": _PAIN_DAYS,
                "threshold": _PAIN_THRESHOLD,
                "scores": scores,
                "avg_pain": round(sum(scores) / len(scores), 1),
                "latest_date": recent[0].get("log_date", ""),
            }
        return None
    except Exception as exc:
        log.warning("[scheduler] Pain escalation check failed: %s", exc)
        return None


def _job_pain_escalation(client) -> None:
    """Post pain escalation alert if threshold exceeded for consecutive days."""
    escalation = _check_pain_escalation()
    if not escalation:
        _shakedown_log("pain_escalation", "skipped",
                       f"Pain below threshold (threshold={_PAIN_THRESHOLD}, days={_PAIN_DAYS})")
        return

    scores_str = ", ".join(str(s) for s in escalation["scores"])
    lines = [
        f":rotating_light: *Medical Officer — Pain Escalation Alert*",
        f"",
        f"Pain score has been *≥{escalation['threshold']}/10 for {escalation['consecutive_days']} consecutive days*.",
        f"Recent scores: {scores_str}  (average: {escalation['avg_pain']}/10)",
        f"",
        f"*Recommended actions:*",
        f"  • Review pain management plan",
        f"  • Consider whether a GP or specialist contact is warranted",
        f"  • Reduce operational load — consider switching to RED capacity mode",
        f"  • Log today's check-in if not already done (`/health-check`)",
        f"",
        f"_This is an advisory alert. Consult your healthcare provider for clinical guidance._",
    ]
    posted = _post(client, "\n".join(lines))
    log.warning(
        "[scheduler] Pain escalation alert posted: %d consecutive days >= %d (avg %.1f)",
        escalation["consecutive_days"], escalation["threshold"], escalation["avg_pain"]
    )
    _shakedown_log("pain_escalation", "success" if posted else "failure",
                   f"Pain ≥{escalation['threshold']} for {escalation['consecutive_days']} days (avg {escalation['avg_pain']})",
                   _BRIEF_CHANNEL)


# ---------------------------------------------------------------------------
# Weekly health synthesis  [M-20260614 WP3]
# ---------------------------------------------------------------------------

def _job_weekly_health_synthesis(client) -> None:
    """Saturday: run weekly health synthesis and post brief to Captain."""
    log.info("[scheduler] Running weekly health synthesis")
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from commands.health_synthesis import run_weekly_synthesis
        result = run_weekly_synthesis(period_days=7)
        if result and result.summary:
            channel = _BRIEF_CHANNEL or _BRIEF_USER_ID
            if channel:
                header = ":medical_symbol: *Medical Officer — Weekly Health Brief*\n"
                posted = _post(client, header + result.summary)
                log.info("[scheduler] Weekly health synthesis posted (period: 7 days)")
                _shakedown_log("weekly_health_synthesis", "success" if posted else "failure",
                               f"period={result.period_start}→{result.period_end}", _BRIEF_CHANNEL)
            else:
                log.warning("[scheduler] Weekly synthesis generated but no channel configured")
                _shakedown_log("weekly_health_synthesis", "failure", "No channel configured")
        else:
            log.warning("[scheduler] Weekly synthesis returned no summary")
            _shakedown_log("weekly_health_synthesis", "skipped", "No summary returned — insufficient health data")
    except Exception as exc:
        log.error("[scheduler] Weekly health synthesis failed: %s", exc)
        _shakedown_log("weekly_health_synthesis", "failure", str(exc))
        channel = _BRIEF_CHANNEL or _BRIEF_USER_ID
        if channel:
            _post(client, f":warning: *Medical Officer:* Weekly health synthesis failed — {exc}\nUse `/health-brief` to trigger manually.")


# ---------------------------------------------------------------------------
# Appointment preparation check  [M-20260614 WP4]
# ---------------------------------------------------------------------------

def _job_appointment_prep(client) -> None:
    """Daily: check for upcoming appointments and post preparation briefs."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from commands.health_appointment_prep import check_upcoming_appointments
        count = check_upcoming_appointments(client, lead_days=_APPT_LEAD_DAYS)
        if count:
            log.info("[scheduler] Appointment prep: %d brief(s) posted", count)
            _shakedown_log("appointment_prep", "success",
                           f"{count} preparation brief(s) posted", _BRIEF_CHANNEL)
        else:
            log.debug("[scheduler] Appointment prep: no upcoming appointments within %d days", _APPT_LEAD_DAYS)
            _shakedown_log("appointment_prep", "skipped",
                           f"No appointments within {_APPT_LEAD_DAYS} days")
    except Exception as exc:
        log.error("[scheduler] Appointment prep check failed: %s", exc)
        _shakedown_log("appointment_prep", "failure", str(exc))


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shakedown Logger import helper  [M-20260615]
# ---------------------------------------------------------------------------

_HEARTBEAT_DOMAIN_ALIASES = {
    "stale_missions": "stale_missions_job",  # avoid colliding with the "missions" data-freshness domain
}


def _shakedown_log(job_id: str, status: str, detail: str = "", delivered_to: str = "") -> None:
    """Write one shakedown event. Fails silently — never disrupts job execution."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from shakedown_logger import log_event
        log_event(job_id, status, detail, delivered_to)
    except Exception as exc:
        log.debug("[shakedown] log_event failed (non-critical): %s", exc)

    # STARSHIP-REDESIGN.md §4.1: every internal job is a domain too, watched
    # by the same heartbeat mechanism as external data. Best-effort, never
    # disrupts job execution.
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "platform"))
        from heartbeat import record_heartbeat
        domain_key = _HEARTBEAT_DOMAIN_ALIASES.get(job_id, job_id)
        hb_status = {"success": "ok", "failure": "failed", "skipped": "skipped"}.get(status, "failed")
        record_heartbeat(domain_key, status=hb_status, detail=detail or None,
                          error_message=detail if hb_status == "failed" else None)
    except Exception as exc:
        log.debug("[heartbeat] record_heartbeat failed (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# Daily shakedown digest  [M-20260615]
# ---------------------------------------------------------------------------

def _job_shakedown_digest(client) -> None:
    """Evening: compile today's shakedown observations and post summary to channel."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
        from shakedown_logger import get_day_summary, format_day_summary_for_slack
        summary = get_day_summary(_today_date())
        msg = format_day_summary_for_slack(summary)
        if _post(client, msg):
            log.info("[shakedown] Day %d digest posted (events=%d, failures=%d)",
                     summary["day_n"], summary["total_events"], summary["failure_count"])
        _shakedown_log("shakedown_digest", "success",
                       f"Day {summary['day_n']}: {summary['total_events']} events, {summary['failure_count']} failures",
                       _BRIEF_CHANNEL)
    except Exception as exc:
        log.error("[shakedown] Digest job failed: %s", exc)
        _shakedown_log("shakedown_digest", "failure", str(exc))


def _job_morning_brief(client) -> None:
    log.info("[scheduler] Generating morning brief")
    brief_text = _fetch_captain_brief_text()

    # Append Captain Readiness Score  [M-20260614 WP7]
    readiness_block = _fetch_readiness_block()
    if readiness_block:
        brief_text += "\n" + readiness_block

    health_logged = _check_health_logged_today()
    if not health_logged:
        brief_text += "\n\n:bell: *Health check-in not yet logged today.* Use `/health-check` to log your daily entry."

    # WP3: Append top high-risk missions block  [M-20260615 WP3]
    if _RISK_AVAILABLE:
        try:
            risk_block = _risk_brief_block(limit=3)
            if risk_block:
                brief_text += "\n\n" + risk_block
        except Exception as _re:
            log.debug("[scheduler] Risk brief block failed: %s", _re)

    # WP2: Append alert metrics block  [M-20260615 WP2]
    if _METRICS_AVAILABLE:
        try:
            metrics_block = _metrics_block()
            if metrics_block:
                brief_text += "\n\n" + metrics_block
        except Exception as _me:
            log.debug("[scheduler] Metrics brief block failed: %s", _me)

    posted = _post(client, brief_text)
    log.info("[scheduler] Morning brief pushed")
    _shakedown_log(
        "morning_brief",
        "success" if posted else "failure",
        f"readiness_block={'yes' if readiness_block else 'no'}, health_logged={health_logged}",
        _BRIEF_CHANNEL,
    )

    # Post-brief async notification jobs — RETIRED D-3C-04 (2026-06-27)
    # Stale missions and pain escalation now handled by Command Centre notification engine.
    # threading.Thread(target=_job_stale_missions,  args=(client,), daemon=True).start()
    # threading.Thread(target=_job_pain_escalation, args=(client,), daemon=True).start()


def _job_stale_missions(client) -> None:
    stale = _get_stale_missions()
    if not stale:
        _shakedown_log("stale_missions", "skipped", "No stale missions found")
        return
    lines = [f":hourglass: *Stale missions — no update in {_STALE_DAYS}+ days:*"]
    for m in stale:
        lines.append(f"  • `{m['id']}` — {m['title']}")
    lines.append("\nUse `/mission-status <id>` to review or `/mission-close <id>` to close.")
    posted = _post(client, "\n".join(lines))
    log.info("[scheduler] Stale mission alert pushed (%d missions)", len(stale))
    _shakedown_log("stale_missions", "success" if posted else "failure",
                   f"{len(stale)} stale missions alerted", _BRIEF_CHANNEL)


def _job_decision_review(client) -> None:
    """Friday: surface pending decision reviews."""
    pending = _get_pending_decisions()
    if not pending:
        log.info("[scheduler] No pending decisions for review")
        _shakedown_log("decision_review", "skipped", "No pending decisions")
        return
    lines = [f":ballot_box_with_ballot: *{len(pending)} decision(s) awaiting your review:*", ""]
    for d in pending[:8]:
        lines.append(f"  • `{d['id']}` ({d['date']}) — {d['question'][:80]}")
    lines.append("\nReview via `/decision-log` to record outcomes.")
    posted = _post(client, "\n".join(lines))
    log.info("[scheduler] Decision review push sent (%d items)", len(pending))
    _shakedown_log("decision_review", "success" if posted else "failure",
                   f"{len(pending)} decisions surfaced", _BRIEF_CHANNEL)


def _job_mission_registry_sync(client) -> None:
    """Daily: sync Supabase `missions` into the plain-text
    core/mission-control/registry/mission-index.txt (ADR-024 second-pass
    audit fix #3). Additive-only (tools/sync_supabase_to_registry.py never
    deletes/modifies existing rows), silent on success — this closes the
    gap where the registry was found ~150 mission numbers behind the live
    table because the sync script existed but nothing ever ran it."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "tools"))
        from sync_supabase_to_registry import sync, load_registry_ids
        # sync()'s return value is a CLI exit code (always 0 on success, not
        # a count), so diff the registry ourselves to know what actually
        # happened.
        before = load_registry_ids()
        sync(dry_run=False)
        added = len(load_registry_ids()) - len(before)
    except Exception as exc:
        log.error("[scheduler] Mission registry sync failed: %s", exc)
        _shakedown_log("mission_registry_sync", "failure", str(exc))
        return
    if added > 0:
        log.info("[scheduler] Mission registry sync: %d new mission(s) appended", added)
        _shakedown_log("mission_registry_sync", "success", f"{added} new mission(s) appended")
    else:
        log.info("[scheduler] Mission registry sync: already up to date")
        _shakedown_log("mission_registry_sync", "skipped", "Registry already up to date")


def _job_content_pipeline(client) -> None:
    """Daily: the intelligence-to-writing pipeline this Captain actually asked
    for. Promotes top-ranked content_signals to comms_content opportunities,
    then runs the two-pass research+writing draft worker over whatever is
    pending. Previously existed only as manual CLI scripts — 2026-07-18 audit
    found 1,200 signals had produced only 13 opportunities ever, because
    nothing ever ran this. Silent on success/no-op; only logs on failure —
    the CONTENT REVIEW section in the morning/EOD brief is what surfaces
    pending drafts to the Captain, not this job."""
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.content.signal_opportunity_converter import create_opportunities_from_signals
        promoted = create_opportunities_from_signals(limit=5, min_rank_score=70.0)
        log.info(
            "[scheduler] Content signal promotion: %s (%d/%d created)",
            promoted.get("status"), promoted.get("created", 0), promoted.get("requested", 0),
        )
    except Exception as exc:
        log.error("[scheduler] Content signal promotion failed: %s", exc)
        _shakedown_log("content_pipeline", "failure", f"promotion: {exc}")
        return

    try:
        from core.content.draft_worker import fetch_pending, process_item
        items = fetch_pending(limit=5)
        drafted = sum(1 for item in items if process_item(item, dry_run=False))
        log.info("[scheduler] Content drafting: %d/%d item(s) drafted", drafted, len(items))
        _shakedown_log(
            "content_pipeline", "success",
            f"promoted={promoted.get('created', 0)} drafted={drafted}/{len(items)}",
        )
    except Exception as exc:
        log.error("[scheduler] Content drafting failed: %s", exc)
        _shakedown_log("content_pipeline", "failure", f"drafting: {exc}")


def _job_knowledge_freshness(client) -> None:
    """Weekly: flag knowledge files not updated in 90+ days."""
    stale = _get_stale_knowledge_files()
    if not stale:
        log.info("[scheduler] Knowledge freshness check: all files current")
        _shakedown_log("knowledge_freshness", "skipped", "All knowledge files current")
        return
    lines = [
        f":file_cabinet: *Knowledge Freshness Alert — {len(stale)} file(s) not updated in {_KNOWLEDGE_STALENESS_DAYS}+ days:*",
        "",
    ]
    for f in stale[:8]:
        lines.append(f"  • `{f['path']}` — {f['age_days']} days")
    lines.append("\nReview and update these files to keep the knowledge base current.")
    posted = _post(client, "\n".join(lines))
    log.info("[scheduler] Knowledge freshness alert pushed (%d stale files)", len(stale))
    _shakedown_log("knowledge_freshness", "success" if posted else "failure",
                   f"{len(stale)} stale files alerted", _BRIEF_CHANNEL)


def _job_decision_outcome_reminder(client) -> None:
    """Weekly: remind Captain of decisions overdue for outcome review."""
    overdue = _get_decisions_overdue_outcome()
    if not overdue:
        log.info("[scheduler] Decision outcome check: all decisions have outcomes")
        # Chief Engineer 2026-08-09 EOD alert verification: unlike every
        # other job in this file, this one never called _shakedown_log() —
        # so domain_heartbeats had zero rows for "decision_outcome_reminder"
        # regardless of how many times this job actually ran.
        _shakedown_log("decision_outcome_reminder", "skipped", "All decisions have outcomes")
        return
    lines = [
        f":ballot_box_with_ballot: *{len(overdue)} decision(s) overdue for outcome review ({_DECISION_OUTCOME_DAYS}+ days):*",
        "",
    ]
    for d in overdue[:6]:
        lines.append(f"  • `{d['id']}` — {d['age_days']} days old")
    lines.append(
        "\nAdd `captain_outcome_review:` to each decision record or note in `/decision-log`."
    )
    posted = _post(client, "\n".join(lines))
    log.info("[scheduler] Decision outcome reminder pushed (%d overdue)", len(overdue))
    _shakedown_log("decision_outcome_reminder", "success" if posted else "failure",
                   f"{len(overdue)} decisions surfaced", _BRIEF_CHANNEL)


def _job_monthly_lessons_digest(client) -> None:
    """First of month: push lessons digest."""
    digest = _generate_lessons_digest()
    if not digest:
        log.info("[scheduler] Monthly lessons digest: no lessons to surface")
        return
    _post(client, digest)
    log.info("[scheduler] Monthly lessons digest pushed")


def _job_ko_monthly_brief(client) -> None:
    """First of month: push Knowledge Officer monthly brief."""
    brief = _generate_ko_monthly_brief()
    if brief:
        _post(client, brief)
    log.info("[scheduler] KO monthly brief pushed")


def _job_weekly_review(client) -> None:
    """Friday: weekly review summary."""
    stale = _get_stale_missions()
    pending = _get_pending_decisions()
    health_logged = _check_health_logged_today()

    lines = [
        ":anchor: *Weekly Review — Starship Endeavour*",
        f"_Week ending {_today_date().strftime('%Y-%m-%d')}_",
        "",
        f"*Stale missions:* {len(stale)} missions with no update in {_STALE_DAYS}+ days",
        f"*Pending decisions:* {len(pending)} runtime decisions awaiting review",
        f"*Health check-in today:* {'✅ logged' if health_logged else '❌ not logged'}",
        "",
        "*Number One asks:* What did you learn this week that should enter permanent knowledge?",
        "",
        "_Use `/captain-brief` for a full picture, `/mission-list` for mission status._",
    ]
    _post(client, "\n".join(lines))
    log.info("[scheduler] Weekly review pushed")


# ---------------------------------------------------------------------------
# Scheduler bootstrap
# ---------------------------------------------------------------------------

def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute)."""
    try:
        h, m = time_str.split(":")
        return int(h), int(m)
    except Exception:
        log.warning("[scheduler] Invalid BRIEF_TIME '%s', defaulting to 07:30", time_str)
        return 7, 30


# ---------------------------------------------------------------------------
# Mission escalation job  [M-20260615 Proactive Notifications]
# ---------------------------------------------------------------------------

def _job_mission_escalation(client) -> None:
    """Daily: detect and push mission escalations to Captain, respecting cadence rules."""
    if not _NOTIFICATIONS_AVAILABLE:
        log.debug("[escalation] captain_notifications not available — skipping")
        return
    cfg = _get_notif_config()
    if not cfg.mission_escalations:
        log.debug("[escalation] Mission escalations disabled by config")
        return
    try:
        escalations = get_mission_escalations()
        if not escalations:
            log.info("[escalation] No mission escalations detected")
            return

        # WP1: apply cadence control — only push what's due today
        if _ESCALATION_MANAGER_AVAILABLE:
            escalations = _process_escalations(escalations)
            if not escalations:
                log.info("[escalation] All escalations suppressed by cadence control")
                return

        msg = format_mission_escalation_batch(escalations)
        if _post(client, msg):
            log.info("[escalation] Mission escalation report posted (%d items)", len(escalations))
        else:
            log.warning("[escalation] Mission escalation report failed to post")
    except Exception as exc:
        log.error("[escalation] Mission escalation job failed: %s", exc)


# ---------------------------------------------------------------------------
# Health nudge job  [M-20260615 Proactive Notifications]
# ---------------------------------------------------------------------------

def _job_health_nudge(client) -> None:
    """Evening: push a health log reminder if no entry recorded today."""
    if not _NOTIFICATIONS_AVAILABLE:
        return
    cfg = _get_notif_config()
    if not cfg.health_reminders:
        return
    try:
        if _check_health_logged_today():
            log.info("[health_nudge] Health already logged today — no reminder needed")
            return
        if not cfg.should_send(SEVERITY_INFO, is_routine=True):
            log.info("[health_nudge] Suppressed by notification controls")
            return
        msg = health_nudge_text()
        if _post(client, msg):
            log.info("[health_nudge] Health nudge posted")
    except Exception as exc:
        log.error("[health_nudge] Health nudge job failed: %s", exc)


# ---------------------------------------------------------------------------
# Forgotten decisions job  [M-20260615 Proactive Notifications]
# ---------------------------------------------------------------------------

def _job_forgotten_decisions(client) -> None:
    """Bi-weekly: surface governance decisions/ADRs that have been left unresolved."""
    if not _NOTIFICATIONS_AVAILABLE:
        return
    cfg = _get_notif_config()
    if not cfg.forgotten_decisions:
        return
    try:
        items = get_forgotten_decisions()
        if not items:
            log.info("[forgotten_decisions] No forgotten decisions found")
            return
        msg = format_forgotten_decisions(items)
        if _post(client, msg):
            log.info("[forgotten_decisions] Forgotten decisions alert posted (%d items)", len(items))
    except Exception as exc:
        log.error("[forgotten_decisions] Forgotten decisions job failed: %s", exc)


def _get_idea_missions() -> list[dict]:
    """Return Idea-status missions from Supabase, sorted oldest first."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return []
        rows = client.get("missions?select=*&status=ilike.Idea&order=created_at.asc&limit=30")
        return rows or []
    except Exception as exc:
        log.debug("[idea_review] Supabase unavailable: %s", exc)
        return []


def _format_idea_review(missions: list[dict]) -> str:
    """Format Number One fortnightly Idea review for posting."""
    if not missions:
        return ""
    now = datetime.utcnow()
    lines = [
        ":bulb: *Number One — Fortnightly Idea Review*",
        f"_Cycle: {_today_date().strftime('%Y-%m-%d')}_",
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
                from datetime import timezone
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00").replace("+00:00", ""))
                age_days = (now - created).days
                age_str = f" · {age_days}d old"
                if age_days >= 28:
                    age_str += " :hourglass:"
            except (ValueError, TypeError):
                pass
        lines.append(f"  • `{mid}` — {title}{age_str}")

    lines += [
        "",
        "*Number One recommends Captain triage each idea:*",
        "  :arrow_up: *Promote* — `/mission-status <id> planned`",
        "  :pause_button: *Hold* — `/mission-status <id> idea` (retain, no action)",
        "  :twisted_rightwards_arrows: *Merge* — note in mission description, then `/mission-status <id> closed`",
        "  :wastebasket: *Archive* — `/mission-status <id> closed` (no further action required)",
        "",
        "_No autonomous promotion. Captain decides._",
        "_Full list: `/mission-list idea`_",
    ]
    return "\n".join(lines)


def _is_fortnightly_monday() -> bool:
    """Return True on the first Monday of the fortnightly cycle (week numbers 1, 3, 5, ...)."""
    today = _today_date()
    # Odd ISO week numbers fall on fortnightly Mondays (week 1, 3, 5 ...)
    return today.weekday() == 0 and today.isocalendar()[1] % 2 == 1


def _job_fortnightly_idea_review(client) -> None:
    """Fortnightly Monday 08:45: review Idea-status missions and post triage recommendations."""
    if not _is_fortnightly_monday():
        return
    try:
        missions = _get_idea_missions()
        if not missions:
            log.info("[idea_review] No Idea-status missions — skipping fortnightly review")
            return
        msg = _format_idea_review(missions)
        if msg and _post(client, msg):
            log.info("[idea_review] Fortnightly idea review posted (%d ideas)", len(missions))
    except Exception as exc:
        log.error("[idea_review] Fortnightly idea review job failed: %s", exc)


def _job_lifecycle_recommendations(client) -> None:
    """[MSN-0066] XO-to-Captain Slack notification of items needing review/approval.

    Posts the requests waiting on the Captain's decision — items the advancer has
    moved to *Triage Ready* (awaiting your APPROVAL, Gate 1) and delivered work at
    *Review* (awaiting your REVIEW, Gate 2). It is purely a notification: it
    writes nothing, approves nothing, runs no code — nothing proceeds without the
    Captain's own sign-off (ADR-013).

    DOUBLE-GATED so it ships inert: even when the scheduler is on, this job does
    nothing unless LIFECYCLE_RECS_ENABLED is truthy (default off).
    """
    if os.environ.get("LIFECYCLE_RECS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        repo_root = str(Path(__file__).resolve().parents[1])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from core.coordination.pending_actions import build_pending_actions

        payload = build_pending_actions()
        totals = payload.get("totals", {})
        awaiting = totals.get("awaiting_approval", 0)
        review = totals.get("review", 0)
        needing = awaiting + review
        if not needing:
            return  # nothing needs the Captain's review/approval — stay quiet

        lines = [f":star2: *XO to Captain* — {needing} request(s) need your review/approval:"]
        if awaiting:
            lines.append(f"\n*Awaiting your approval* — triaged, Gate 1 ({awaiting}):")
            for a in payload.get("awaiting_approval", [])[:8]:
                prio = a.get("suggested_priority", "")
                tag = f" [{prio}]" if prio else ""
                lines.append(f"  • {a.get('id')}{tag} — approve / defer / request clarification")
        if review:
            lines.append(f"\n*Awaiting your review* — delivered, Gate 2 ({review}):")
            for r in payload.get("review", [])[:8]:
                # 2026-09-06: one-click link straight to the draft PR — a
                # bare handoff ID left the Captain to go find the PR
                # manually on GitHub every time. Slack mrkdwn's <url|label>
                # makes the actor text itself the tappable link (this
                # message already uses mrkdwn *bold*/_italic_ above, so the
                # bot's chat_postMessage text param renders it). Falls back
                # to plain text for non-handoff review items (missions/
                # build_requests never set pr_url).
                pr_url = r.get("pr_url")
                next_actor = r.get("next_actor", "")
                actor_text = f"<{pr_url}|{next_actor}>" if pr_url else next_actor
                lines.append(f"  • {r.get('id')} — {actor_text}")
        lines.append("\n_Advisory only — nothing is approved or merged without your sign-off._")

        # Own destination, independent of BRIEF_CHANNEL — so enabling this one
        # notification does NOT switch on the whole proactive-brief suite.
        # Prefer the channel the bot already posts briefs to; the captain's-inbox
        # channel is a last resort (the bot may not be a member there).
        channel = (os.environ.get("LIFECYCLE_RECS_CHANNEL")
                   or _BRIEF_CHANNEL or _BRIEF_USER_ID
                   or os.environ.get("CAPTAINS_INBOX_CHANNEL_ID"))
        if not channel:
            log.warning("[lifecycle_recs] no channel configured (set LIFECYCLE_RECS_CHANNEL "
                        "or CAPTAINS_INBOX_CHANNEL_ID) — skipping")
            return
        try:
            client.chat_postMessage(channel=channel, text="\n".join(lines))
            log.info("[lifecycle_recs] Posted XO review/approval notification (%d items)", needing)
        except Exception as exc:  # noqa: BLE001
            log.error("[lifecycle_recs] Slack post failed: %s", exc)
    except Exception as exc:  # noqa: BLE001 - advisory job must never crash the scheduler
        log.error("[lifecycle_recs] Lifecycle review/approval notification failed: %s", exc)


def _job_pending_research_sweep(_client) -> None:
    """Every 5 min: recover stuck captured_items in two passes.

    Pass 1 — pre-orchestration stuck items (processing_status='pending'):
        Items captured but never processed (e.g. mobile UI captures, old test
        items, bot-restart orphans). Runs process_captured_item() which
        classifies them and auto-queues research if eligible. Capped at 10
        per sweep; test/empty items will classify as unclassified and skip
        research automatically.

    Pass 2 — post-orchestration research queue (research_status='pending'):
        Items that were classified but whose research thread died. Runs
        _run_research() directly. Capped at 5 per sweep to avoid quota pressure.
    """
    try:
        import sys
        sys.path.insert(0, str(_REPO_ROOT))
        from core.inbox.orchestrator import _run_research, _db, process_captured_item  # noqa: PLC0415

        if not _db.enabled():
            return

        # Pass 1: unprocessed items
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
                log.info("[pending-research-sweep] Orchestrating unprocessed item: %s", item.get("title", item["id"])[:60])
                pass1_ids.add(item["id"])
                process_captured_item(item["id"])
            except Exception as exc:  # noqa: BLE001
                log.error("[pending-research-sweep] Orchestration failed for %s: %s", item["id"], exc)

        # Pass 2: items queued for research but thread died
        # Skip any item already handled in Pass 1 this sweep to avoid double-triggering.
        queued = (
            _db._client.table("captured_items")
            .select("*")
            .eq("research_status", "pending")
            .order("captured_at", desc=False)
            .limit(5)
            .execute()
        )
        research_items = [r for r in (queued.data or []) if r["id"] not in pass1_ids]
        if research_items:
            log.info("[pending-research-sweep] Found %d item(s) queued for research", len(research_items))
        for item in research_items:
            try:
                _run_research(item["id"], item)
            except Exception as exc:  # noqa: BLE001
                log.error("[pending-research-sweep] Research failed for %s: %s", item["id"], exc)

    except Exception as exc:  # noqa: BLE001
        log.error("[pending-research-sweep] Sweep failed: %s", exc)


def start_scheduler(client) -> None:
    """Start the APScheduler background scheduler. Call once after bot initialises."""
    if not _ENABLED:
        log.info("[scheduler] Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("[scheduler] apscheduler not installed — scheduled jobs disabled. Run: pip install apscheduler")
        return

    brief_hour, brief_minute = _parse_time(_BRIEF_TIME)

    scheduler = BackgroundScheduler(timezone="Australia/Sydney")

    # Mission registry sync — daily 06:45, before the morning brief.
    # ADR-024 second-pass audit fix #3: mission-index.txt had no scheduled
    # sync at all (tools/sync_supabase_to_registry.py existed but nothing
    # ever ran it), so it drifted ~150 mission numbers behind the live
    # Supabase `missions` table. Additive-only, silent on success.
    scheduler.add_job(
        _job_mission_registry_sync,
        CronTrigger(hour=6, minute=45),
        args=[client],
        id="mission_registry_sync",
        name="Mission Registry Sync (ADR-024)",
        replace_existing=True,
    )

    # Content pipeline — daily 06:15, before the morning brief so any drafts
    # generated this run are already reflected in its CONTENT REVIEW section.
    # 2026-07-18 audit: this was never scheduled at all — 1,200 content
    # signals had produced 13 opportunities, ever, entirely by hand.
    scheduler.add_job(
        _job_content_pipeline,
        CronTrigger(hour=6, minute=15),
        args=[client],
        id="content_pipeline",
        name="Content Signal-to-Draft Pipeline",
        replace_existing=True,
    )

    # Morning brief — every day at BRIEF_TIME
    scheduler.add_job(
        _job_morning_brief,
        CronTrigger(hour=brief_hour, minute=brief_minute),
        args=[client],
        id="morning_brief",
        name="Morning Brief Push",
        replace_existing=True,
    )

    # Decision review — Friday at 16:00
    scheduler.add_job(
        _job_decision_review,
        CronTrigger(day_of_week="fri", hour=16, minute=0),
        args=[client],
        id="decision_review",
        name="Friday Decision Review",
        replace_existing=True,
    )

    # Weekly review — Friday at 16:30
    scheduler.add_job(
        _job_weekly_review,
        CronTrigger(day_of_week="fri", hour=16, minute=30),
        args=[client],
        id="weekly_review",
        name="Friday Weekly Review",
        replace_existing=True,
    )

    # Knowledge freshness check — Wednesday 09:00
    scheduler.add_job(
        _job_knowledge_freshness,
        CronTrigger(day_of_week="wed", hour=9, minute=0),
        args=[client],
        id="knowledge_freshness",
        name="Weekly Knowledge Freshness Check",
        replace_existing=True,
    )

    # Decision outcome reminder — Wednesday 09:15
    scheduler.add_job(
        _job_decision_outcome_reminder,
        CronTrigger(day_of_week="wed", hour=9, minute=15),
        args=[client],
        id="decision_outcome_reminder",
        name="Decision Outcome Reminder",
        replace_existing=True,
    )

    # Monthly lessons digest — 1st of month 08:00
    scheduler.add_job(
        _job_monthly_lessons_digest,
        CronTrigger(day=1, hour=8, minute=0),
        args=[client],
        id="monthly_lessons_digest",
        name="Monthly Lessons Digest",
        replace_existing=True,
    )

    # KO monthly brief — 1st of month 08:30
    scheduler.add_job(
        _job_ko_monthly_brief,
        CronTrigger(day=1, hour=8, minute=30),
        args=[client],
        id="ko_monthly_brief",
        name="Knowledge Officer Monthly Brief",
        replace_existing=True,
    )

    # Weekly health synthesis — Saturday 08:00  [M-20260614 WP3]
    scheduler.add_job(
        _job_weekly_health_synthesis,
        CronTrigger(day_of_week="sat", hour=8, minute=0),
        args=[client],
        id="weekly_health_synthesis",
        name="Medical Officer Weekly Health Synthesis",
        replace_existing=True,
    )

    # Appointment preparation check — daily 08:45  [M-20260614 WP4]
    scheduler.add_job(
        _job_appointment_prep,
        CronTrigger(hour=8, minute=45),
        args=[client],
        id="appointment_prep",
        name="Medical Officer Appointment Preparation Check",
        replace_existing=True,
    )

    # Shakedown digest — daily 20:00  [M-20260615]
    scheduler.add_job(
        _job_shakedown_digest,
        CronTrigger(hour=20, minute=0),
        args=[client],
        id="shakedown_digest",
        name="Operational Shakedown Daily Digest",
        replace_existing=True,
    )

    # Mission escalation check — RETIRED D-3C-04 (2026-06-27)
    # Owned by Command Centre notification engine (checkRepeatedEscalations + checkStagnantMissions).
    # scheduler.add_job(_job_mission_escalation, ...)

    # Health nudge — RETIRED D-3C-04 (2026-06-27)
    # Owned by Command Centre notification engine (checkHealthDecline). Recovery-gap
    # coverage moved to human_systems_scheduler.py's morning/degradation pushes
    # (2026-08-13, Command Centre's checkRecoveryGap retired as a duplicate).
    # scheduler.add_job(_job_health_nudge, ...)

    # Forgotten decisions alert — Monday + Thursday 09:30  [M-20260615]
    scheduler.add_job(
        _job_forgotten_decisions,
        CronTrigger(day_of_week="mon,thu", hour=9, minute=30),
        args=[client],
        id="forgotten_decisions",
        name="Forgotten Decisions & ADR Alert",
        replace_existing=True,
    )

    # fortnightly_idea_review disabled: no dedup/ack, re-nags the same
    # Idea-status missions verbatim every cycle with no resolution path.
    # (was [M-20260614-GOVERNANCE-LIFECYCLE-CLOSURE WP4])

    # Lifecycle pending-actions digest — daily 08:15 (between morning brief and
    # mission escalation). [MSN-0066] Self-gated by LIFECYCLE_RECS_ENABLED, so
    # registering it is inert until the Captain enables it.
    scheduler.add_job(
        _job_lifecycle_recommendations,
        CronTrigger(hour=8, minute=15),
        args=[client],
        id="lifecycle_recommendations",
        name="Lifecycle Pending Actions (MSN-0066)",
        replace_existing=True,
    )

    # Pending research sweep — every 5 minutes. Picks up items queued for Mistral research
    # whose background thread died (bot restart, one-liner runs) or were captured via
    # mobile UI which doesn't hold a long-running process.
    scheduler.add_job(
        _job_pending_research_sweep,
        CronTrigger(minute="*/5"),
        args=[client],
        id="pending_research_sweep",
        name="Pending Research Sweep (Mistral)",
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "[scheduler] Proactive scheduler started — brief at %02d:%02d AEST, "
        "mission escalation 09:00 daily, "
        "stale mission + pain escalation checks post-brief daily, "
        "health nudge 20:30 daily, "
        "forgotten decisions Mon+Thu 09:30, "
        "appointment prep daily 08:45, "
        "weekly health synthesis Saturdays 08:00, "
        "decision review Fridays 16:00, weekly review Fridays 16:30, "
        "knowledge freshness Wednesdays 09:00, "
        "decision outcome reminder Wednesdays 09:15, "
        "monthly digest 1st of month 08:00, "
        "fortnightly idea review Mondays 08:45 (odd ISO weeks)",
        brief_hour, brief_minute,
    )
    if _NOTIFICATIONS_AVAILABLE:
        from captain_notifications import get_config as _nc
        _cfg = _nc()
        log.info(
            "[scheduler] Notification controls: level=%s, quiet=%02d:00–%02d:00, "
            "weekend=%s, mission_escalations=%s, health_reminders=%s, forgotten_decisions=%s",
            _cfg.level, _cfg.quiet_start, _cfg.quiet_end,
            _cfg.weekend, _cfg.mission_escalations, _cfg.health_reminders, _cfg.forgotten_decisions,
        )
    log.info("[scheduler] Target channel: %s", _BRIEF_CHANNEL or _BRIEF_USER_ID or "(not configured — set BRIEF_CHANNEL or BRIEF_USER_ID)")
    log.info(
        "[scheduler] Pain alert: threshold=%d/10 for %d consecutive days | "
        "Appointment lead: %d days | Stale mission threshold: %d days",
        _PAIN_THRESHOLD, _PAIN_DAYS, _APPT_LEAD_DAYS, _STALE_DAYS,
    )
