"""
Captain Notification Framework — Starship Endeavour

Converts USS TJR OS from pull-based to exception-driven.
Only notifies on genuine exceptions; never generates noise.

Escalation severity model:
  INFO     — routine updates, no urgency
  WARNING  — needs attention within 7 days
  ALERT    — requires attention within 48 hours
  CRITICAL — immediate attention required

Configuration (.env):
  NOTIFICATION_LEVEL          = "WARNING"   # Minimum level to push (INFO/WARNING/ALERT/CRITICAL)
  QUIET_HOURS_START           = "22"        # Hour (24h, AEST) — no pushes after this
  QUIET_HOURS_END             = "07"        # Hour (24h, AEST) — no pushes before this
  WEEKEND_NOTIFICATIONS       = "false"     # Push exceptions on weekends (true/false)
  DAILY_BRIEF_ENABLED         = "true"
  MISSION_ESCALATIONS_ENABLED = "true"
  HEALTH_REMINDERS_ENABLED    = "true"
  FORGOTTEN_DECISIONS_ENABLED = "true"
  MISSION_OPEN_DAYS           = "3"         # Days before OPEN mission escalates
  MISSION_STALE_HOURS         = "48"        # Hours without activity before escalation
  DECISION_STALE_DAYS         = "7"         # Days before unresolved decision/ADR escalates
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Severity model
# ---------------------------------------------------------------------------

SEVERITY_INFO     = "INFO"
SEVERITY_WARNING  = "WARNING"
SEVERITY_ALERT    = "ALERT"
SEVERITY_CRITICAL = "CRITICAL"

_SEVERITY_ORDER = [SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ALERT, SEVERITY_CRITICAL]

_SEVERITY_EMOJI = {
    SEVERITY_INFO:     ":information_source:",
    SEVERITY_WARNING:  ":warning:",
    SEVERITY_ALERT:    ":rotating_light:",
    SEVERITY_CRITICAL: ":sos:",
}

_SEVERITY_LABEL = {
    SEVERITY_INFO:     "Info",
    SEVERITY_WARNING:  "Warning",
    SEVERITY_ALERT:    "Alert",
    SEVERITY_CRITICAL: "Critical",
}


def severity_header(level: str, title: str) -> str:
    """Return a formatted Slack header line for the given severity level."""
    emoji = _SEVERITY_EMOJI.get(level, ":bell:")
    label = _SEVERITY_LABEL.get(level, level)
    return f"{emoji} *{label}: {title}*"


# ---------------------------------------------------------------------------
# Notification controls
# ---------------------------------------------------------------------------

class NotificationConfig:
    """Reads notification control settings from environment variables."""

    def __init__(self) -> None:
        self.level             = os.environ.get("NOTIFICATION_LEVEL", "WARNING").upper()
        self.quiet_start       = int(os.environ.get("QUIET_HOURS_START", "22"))
        self.quiet_end         = int(os.environ.get("QUIET_HOURS_END", "7"))
        self.weekend           = os.environ.get("WEEKEND_NOTIFICATIONS", "false").lower() == "true"
        self.daily_brief       = os.environ.get("DAILY_BRIEF_ENABLED", "true").lower() == "true"
        self.mission_escalations = os.environ.get("MISSION_ESCALATIONS_ENABLED", "true").lower() == "true"
        self.health_reminders  = os.environ.get("HEALTH_REMINDERS_ENABLED", "true").lower() == "true"
        self.forgotten_decisions = os.environ.get("FORGOTTEN_DECISIONS_ENABLED", "true").lower() == "true"
        self.mission_open_days = int(os.environ.get("MISSION_OPEN_DAYS", "3"))
        self.mission_stale_hours = int(os.environ.get("MISSION_STALE_HOURS", "48"))
        self.decision_stale_days = int(os.environ.get("DECISION_STALE_DAYS", "7"))

    def should_send(self, level: str = SEVERITY_INFO, is_routine: bool = False) -> bool:
        """Return True if a notification at this level should be sent now."""
        now = datetime.now()

        # Weekend suppression for routine notifications
        if is_routine and not self.weekend and now.weekday() >= 5:
            return False

        # Quiet hours: do not push between quiet_start and quiet_end
        hour = now.hour
        if self.quiet_start > self.quiet_end:
            # Wraps midnight: quiet from start until end next morning
            in_quiet = hour >= self.quiet_start or hour < self.quiet_end
        else:
            in_quiet = self.quiet_start <= hour < self.quiet_end

        # CRITICAL breaks quiet hours
        if in_quiet and level != SEVERITY_CRITICAL:
            return False

        # Minimum level filter
        if level in _SEVERITY_ORDER and self.level in _SEVERITY_ORDER:
            if _SEVERITY_ORDER.index(level) < _SEVERITY_ORDER.index(self.level):
                return False

        return True


# Module-level singleton
_config: Optional[NotificationConfig] = None


def get_config() -> NotificationConfig:
    global _config
    if _config is None:
        _config = NotificationConfig()
    return _config


# ---------------------------------------------------------------------------
# Mission escalation detection
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = {
    "active", "in_progress", "open", "in progress",
    "awaiting xo approval", "awaiting number one review",
    "blocked", "blocked_ops",
}

_BLOCKED_STATUSES = {"blocked", "blocked_ops", "blocked_by"}
_AWAITING_XO = {"awaiting xo approval"}
_AWAITING_NR1 = {"awaiting number one review"}


def _parse_mission_open_date(mission_id: str, fallback_str: str = "") -> Optional[date]:
    """Extract open date from mission ID (M-YYYYMMDD-... or M-YYYYMMDD)."""
    parts = mission_id.split("-")
    for i, p in enumerate(parts):
        if len(p) == 8 and p.isdigit():
            try:
                return datetime.strptime(p, "%Y%m%d").date()
            except ValueError:
                continue
    # Try fallback timestamp string (e.g. "2026-06-07 13:25")
    if fallback_str:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(fallback_str[:16], fmt).date()
            except ValueError:
                continue
    return None


def _mission_last_activity(mission_id: str) -> Optional[datetime]:
    """
    Return the datetime of the last git commit touching any file named after this
    mission ID, or None if not determinable.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--format=%ci", "--", f"*{mission_id}*"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        if lines:
            # Most recent commit first
            ts = lines[0]
            return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def _read_mission_index() -> list[dict]:
    """Return active missions from Supabase (system of record).

    Falls back to mission-index.txt with a warning if Supabase is unavailable.
    Returns list of dicts: {id, timestamp, domain, status, description}
    """
    # Supabase path (primary)
    try:
        import sys as _sys
        _sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
        from client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if client.is_enabled():
            rows = client.get(
                "missions?select=id,title,status,domain,created_at"
                "&status=not.in.(Closed,Archived,Cancelled,CANCELLED,COMPLETED,Completed)"
                "&order=created_at.asc"
            )
            if rows is not None:
                return [
                    {
                        "id":          r.get("id", ""),
                        "timestamp":   r.get("created_at", ""),
                        "domain":      r.get("domain", ""),
                        "status":      r.get("status", ""),
                        "description": r.get("title", ""),
                    }
                    for r in rows
                ]
    except Exception as exc:
        log.warning("[notifications] Supabase mission read failed: %s", exc)

    # Fallback — file (legacy, not authoritative post MSN-BOT-SOR)
    log.warning(
        "[notifications] FALLBACK: reading missions from mission-index.txt. "
        "Supabase is unavailable or not configured. Data may be stale."
    )
    missions = []
    candidates = [
        _REPO_ROOT / "Missions" / "Mission-Index.md",
        _REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("- "):
                        continue
                    line = line[2:]
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 4:
                        continue
                    missions.append({
                        "id":          parts[0],
                        "timestamp":   parts[1] if len(parts) > 1 else "",
                        "domain":      parts[2] if len(parts) > 2 else "",
                        "status":      parts[3] if len(parts) > 3 else "",
                        "description": parts[4] if len(parts) > 4 else "",
                    })
            break
        except Exception as exc:
            log.warning("[notifications] Failed to read mission index %s: %s", path, exc)
    return missions


def get_mission_escalations() -> list[dict]:
    """
    Return a list of mission escalation dicts, each with:
      {id, title, status, severity, reason, age_days, last_activity_hours}
    Only returns missions that need Captain attention.
    """
    cfg = get_config()
    if not cfg.mission_escalations:
        return []

    now = datetime.now()
    today = now.date()
    escalations = []

    missions = _read_mission_index()
    for m in missions:
        status_lower = m["status"].lower()
        if status_lower not in _ACTIVE_STATUSES:
            continue  # only flag active/open/blocked missions

        mission_id  = m["id"]
        description = m["description"] or m["id"]

        open_date = _parse_mission_open_date(mission_id, m["timestamp"])
        age_days  = (today - open_date).days if open_date else None

        last_activity = _mission_last_activity(mission_id)
        stale_hours   = None
        if last_activity:
            stale_hours = int((now - last_activity).total_seconds() / 3600)

        severity = None
        reasons  = []

        # BLOCKED → ALERT
        if status_lower in _BLOCKED_STATUSES:
            severity = SEVERITY_ALERT
            reasons.append("Mission is BLOCKED")

        # Awaiting XO Approval → ALERT
        if status_lower in _AWAITING_XO:
            severity = max_severity(severity, SEVERITY_ALERT)
            reasons.append("Awaiting XO Approval — Captain action required")

        # Awaiting Number One Review → WARNING
        if status_lower in _AWAITING_NR1:
            severity = max_severity(severity, SEVERITY_WARNING)
            reasons.append("Awaiting Number One Review")

        # No activity > 48h → ALERT
        if stale_hours is not None and stale_hours >= cfg.mission_stale_hours:
            severity = max_severity(severity, SEVERITY_ALERT)
            days_stale = stale_hours // 24
            reasons.append(f"No activity detected for {days_stale}d {stale_hours % 24}h")

        # Open > 3 days without being stale → WARNING
        if age_days is not None and age_days >= cfg.mission_open_days:
            sev = SEVERITY_ALERT if age_days >= 7 else SEVERITY_WARNING
            severity = max_severity(severity, sev)
            if not any("No activity" in r for r in reasons):
                reasons.append(f"Mission open for {age_days} days")

        if severity and reasons:
            escalations.append({
                "id":                   mission_id,
                "title":                description,
                "status":               m["status"],
                "severity":             severity,
                "reasons":              reasons,
                "age_days":             age_days,
                "last_activity_hours":  stale_hours,
            })

    # Sort: CRITICAL → ALERT → WARNING → INFO
    escalations.sort(key=lambda e: -_SEVERITY_ORDER.index(e["severity"]))
    return escalations[:15]


def max_severity(current: Optional[str], candidate: str) -> str:
    """Return the higher of two severity levels."""
    if current is None:
        return candidate
    if _SEVERITY_ORDER.index(candidate) > _SEVERITY_ORDER.index(current):
        return candidate
    return current


def format_mission_escalation(e: dict) -> str:
    """Format a single mission escalation as a Slack message block."""
    header = severity_header(e["severity"], "Mission Escalation")
    lines  = [header, f"*{e['id']}* — {e['title']}"]
    if e["status"]:
        lines.append(f"_Status: {e['status']}_")
    for r in e["reasons"]:
        lines.append(f"• {r}")
    lines.append("*Recommended actions:* Resume · Delegate · Escalate · Close")
    return "\n".join(lines)


def format_mission_escalation_batch(escalations: list[dict]) -> str:
    """Format multiple escalations as a single Slack post."""
    if not escalations:
        return ""
    header = ":rotating_light: *Mission Escalation Report*\n"
    blocks = []
    for e in escalations:
        emoji  = _SEVERITY_EMOJI.get(e["severity"], ":bell:")
        label  = _SEVERITY_LABEL.get(e["severity"], e["severity"])
        status = e["status"] or "unknown"
        reasons = " | ".join(e["reasons"])
        blocks.append(f"{emoji} [{label}] *{e['id']}* — {e['title']} _(Status: {status})_\n  ↳ {reasons}")
    return header + "\n".join(blocks)


# ---------------------------------------------------------------------------
# Forgotten decision alerts
# ---------------------------------------------------------------------------

def get_forgotten_decisions() -> list[dict]:
    """
    Scan the governance decision register for:
      - PROPOSED decisions not approved after DECISION_STALE_DAYS days
      - ADRs awaiting validation for DECISION_STALE_DAYS+ days

    Returns list of dicts: {id, title, date, status, age_days, type}
    """
    cfg = get_config()
    if not cfg.forgotten_decisions:
        return []

    cutoff_date = date.today() - timedelta(days=cfg.decision_stale_days)
    forgotten   = []

    # --- Governance decision register ---
    reg_path = _REPO_ROOT / "core" / "governance" / "decision-register.txt"
    if reg_path.exists():
        try:
            text   = reg_path.read_text()
            blocks = text.split("DECISION ID:")
            for block in blocks[1:]:
                lines  = block.strip().splitlines()
                dec_id = lines[0].strip() if lines else ""
                dec_date, dec_title, dec_status = "", "", ""
                for line in lines[1:10]:
                    if line.startswith("DATE:"):
                        dec_date  = line[5:].strip()[:10]
                    elif line.startswith("TITLE:"):
                        dec_title = line[6:].strip()
                    elif line.startswith("STATUS:"):
                        dec_status = line[7:].strip().upper()
                    if dec_date and dec_title and dec_status:
                        break
                if dec_status in ("PROPOSED", "PENDING") and dec_date:
                    try:
                        d = datetime.strptime(dec_date, "%Y-%m-%d").date()
                        if d <= cutoff_date:
                            forgotten.append({
                                "id":       dec_id,
                                "title":    dec_title,
                                "date":     dec_date,
                                "status":   dec_status,
                                "age_days": (date.today() - d).days,
                                "type":     "governance_decision",
                            })
                    except ValueError:
                        pass
        except Exception as exc:
            log.warning("[notifications] Decision register scan failed: %s", exc)

    # --- ADRs awaiting validation ---
    adr_dirs = [
        _REPO_ROOT / "core" / "governance" / "adrs",
        _REPO_ROOT / "knowledge" / "architecture" / "adrs",
        _REPO_ROOT / "ADRs",
    ]
    for adr_dir in adr_dirs:
        if not adr_dir.exists():
            continue
        try:
            for f in sorted(adr_dir.glob("*.md")):
                text = f.read_text()
                status_line = ""
                date_line   = ""
                for line in text.splitlines()[:20]:
                    l = line.lower()
                    if "status:" in l:
                        status_line = line
                    if "date:" in l:
                        date_line = line
                if "awaiting validation" in status_line.lower() or "proposed" in status_line.lower():
                    dec_date = ""
                    for part in date_line.split(":")[1:]:
                        part = part.strip()
                        if part:
                            dec_date = part[:10]
                            break
                    if dec_date:
                        try:
                            d = datetime.strptime(dec_date, "%Y-%m-%d").date()
                            if d <= cutoff_date:
                                forgotten.append({
                                    "id":       f.stem,
                                    "title":    f.stem.replace("-", " "),
                                    "date":     dec_date,
                                    "status":   "Awaiting Validation",
                                    "age_days": (date.today() - d).days,
                                    "type":     "adr",
                                })
                        except ValueError:
                            pass
        except Exception as exc:
            log.warning("[notifications] ADR scan failed in %s: %s", adr_dir, exc)
        break  # use first valid ADR directory

    # --- Capability: implemented but not validated ---
    cap_reg = _REPO_ROOT / "knowledge" / "Capability-Management" / "Capability-Registry.md"
    if cap_reg.exists():
        try:
            text  = cap_reg.read_text()
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "implemented" in line.lower() and "validated" not in line.lower():
                    # Heuristic: look for a date near this line
                    for nearby in lines[max(0, i-3):i+3]:
                        if "2026-" in nearby or "2025-" in nearby:
                            import re
                            m = re.search(r"(\d{4}-\d{2}-\d{2})", nearby)
                            if m:
                                try:
                                    d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                                    if d <= cutoff_date:
                                        # Extract cap ID if available
                                        cap_id_match = re.search(r"(CAP-\d+|C-\d+)", line)
                                        cap_id = cap_id_match.group(1) if cap_id_match else f"CAP-line-{i}"
                                        forgotten.append({
                                            "id":       cap_id,
                                            "title":    line.strip()[:80],
                                            "date":     m.group(1),
                                            "status":   "Implemented — Not Validated",
                                            "age_days": (date.today() - d).days,
                                            "type":     "capability",
                                        })
                                except ValueError:
                                    pass
                                break
        except Exception as exc:
            log.warning("[notifications] Capability registry scan failed: %s", exc)

    # Deduplicate by id
    seen = set()
    deduped = []
    for f in forgotten:
        if f["id"] not in seen:
            seen.add(f["id"])
            deduped.append(f)

    # Sort by age (oldest first)
    deduped.sort(key=lambda x: x["age_days"], reverse=True)
    return deduped[:10]


def format_forgotten_decisions(items: list[dict]) -> str:
    """Format forgotten decisions/ADRs as a Slack message."""
    if not items:
        return ""
    lines = [":warning: *Governance Attention Required*"]
    for item in items:
        icon = {
            "governance_decision": ":scales:",
            "adr":                 ":scroll:",
            "capability":          ":gear:",
        }.get(item["type"], ":grey_question:")
        lines.append(
            f"{icon} *{item['id']}* — {item['title']}\n"
            f"  Status: {item['status']} | Open for *{item['age_days']} days*\n"
            f"  Risk: System drift / governance gap if unresolved."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daily work queue
# ---------------------------------------------------------------------------

def build_work_queue(
    escalations:         list[dict],
    pending_decisions:   list[dict],
    awaiting_reviews:    list[dict] | None = None,
    max_items:           int = 10,
) -> str:
    """
    Build a Morning Work Queue summary.
    Prioritises: blocked → CRITICAL/ALERT escalations → decisions → reviews.
    Returns formatted Slack message capped at max_items.
    """
    items = []

    # Blocked missions first
    for e in escalations:
        if "BLOCKED" in e.get("status", "").upper():
            items.append(f":sos: *{e['id']}* BLOCKED — {e['title']}")

    # ALERT/CRITICAL escalations
    for e in escalations:
        if e["severity"] in (SEVERITY_ALERT, SEVERITY_CRITICAL) and not any(e["id"] in i for i in items):
            reasons = e["reasons"][0] if e["reasons"] else ""
            items.append(f":rotating_light: *{e['id']}* — {reasons}")

    # WARNING escalations
    for e in escalations:
        if e["severity"] == SEVERITY_WARNING and not any(e["id"] in i for i in items):
            items.append(f":warning: *{e['id']}* — {e['title'][:60]}")

    # Pending decisions awaiting review
    for d in (pending_decisions or []):
        items.append(f":scales: Decision pending review: _{d.get('question', d.get('id', ''))[:60]}_")

    # Awaiting reviews (missions in review state)
    for r in (awaiting_reviews or []):
        items.append(f":eyes: Review required: *{r.get('id', '')}*")

    # Cap at max_items
    items = items[:max_items]

    if not items:
        return ":white_check_mark: *Work Queue Clear* — no exceptions to action."

    header = f":clipboard: *Daily Work Queue* — {len(items)} item{'s' if len(items) != 1 else ''} requiring attention\n"
    return header + "\n".join(f"  {i+1}. {item}" for i, item in enumerate(items))


# ---------------------------------------------------------------------------
# Health nudge
# ---------------------------------------------------------------------------

def should_send_health_nudge() -> bool:
    """Return True if a health nudge should be sent (health not yet logged today)."""
    cfg = get_config()
    return cfg.health_reminders and cfg.should_send(SEVERITY_INFO, is_routine=True)


def health_nudge_text() -> str:
    return (
        ":pill: *Health Log Reminder*\n"
        "Captain, no health log has been recorded today.\n"
        "Use `/health-check` to log your daily entry.\n"
        "_Logging helps track trends and enables proactive medical intelligence._"
    )


# ---------------------------------------------------------------------------
# Lesson capture enforcement
# ---------------------------------------------------------------------------

def check_lesson_captured(mission_id: str) -> bool:
    """
    Return True if a lesson learned has been captured for this mission.
    Checks the lessons_learned directory and lessons-learned markdown files.
    """
    candidates = [
        _REPO_ROOT / "knowledge" / "Lessons-Learned.md",
        _REPO_ROOT / "knowledge" / "lessons-learned",
        _REPO_ROOT / "logs" / "lessons",
    ]
    for path in candidates:
        if path.is_dir():
            for f in path.rglob("*.md"):
                if mission_id in f.read_text():
                    return True
        elif path.is_file():
            if mission_id in path.read_text():
                return True
    return False


def mission_close_lesson_warning(mission_id: str, mission_title: str) -> Optional[str]:
    """
    Return a Slack warning message if no lesson has been captured for a closed mission.
    Returns None if lesson is already captured (no action needed).
    """
    if check_lesson_captured(mission_id):
        return None
    return (
        f":books: *Lesson Capture Required*\n"
        f"Mission *{mission_id}* ({mission_title}) was closed without a lesson learned captured.\n"
        f"Use `/lesson-capture {mission_id}` to record what was learned.\n"
        f"_Knowledge capture is mandatory for P0/P1 missions and recommended for all others._"
    )
