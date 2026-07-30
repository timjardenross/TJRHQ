"""
Governance redundancy & escalation watchdog (Phase A §Governance).

Detects workflow stalls and produces escalation FINDINGS — it never mutates
state or auto-approves (human-in-loop is the whole point of the gates). A
scheduled caller runs `escalation_report(...)` and routes findings to the XO /
Captain per the ori officer manifest (requires_xo / requires_captain).

Rules implemented:
  * No signal stuck mid-workflow (SCORED/VERIFYING/VERIFIED/READY_FOR_BRIEF) > 72h.
  * No brief stuck pre-publication (IN_REVIEW/QA_PASSED) > 72h.
  * Intelligence-Lead-unavailable > 48h -> escalate to backup / XO.

Times are passed in (now, last_lead_activity) so the watchdog is deterministic
and testable; callers pass datetime.now(timezone.utc).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

SIGNAL_STUCK_HOURS = 72
BRIEF_STUCK_HOURS = 72
LEAD_UNAVAILABLE_HOURS = 48

# Signal / brief statuses that are "in flight" (not terminal / not published).
_SIGNAL_IN_FLIGHT = ("SCORED", "VERIFYING", "VERIFIED", "READY_FOR_BRIEF")
# 2026-07-18: consolidated from the original 5-state pre-publish ladder
# (IN_REVIEW/DATA_QA_PASSED/FACTUAL_QA_PASSED/ANALYTICAL_QA_PASSED/QA_READY)
# down to the 2 states that remain under migration 0084.
_BRIEF_PRE_PUBLISH = ("IN_REVIEW", "QA_PASSED")

# Where an escalation goes (per governance/authority/ori.yaml).
ESCALATE_XO = "xo"
ESCALATE_CAPTAIN = "captain"


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_hours(ts: Any, now: datetime) -> Optional[float]:
    dt = _parse_dt(ts)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 3600.0


def find_stuck_signals(repo, now: datetime, hours: int = SIGNAL_STUCK_HOURS) -> list[dict]:
    """Signals in flight (not IN_BRIEF/ARCHIVED/DUPLICATE) older than `hours`.

    Uses collected_at as the age proxy (no per-status change timestamp exists)."""
    findings = []
    for ev in repo.list_events():
        status = ev.get("signal_status")
        if status not in _SIGNAL_IN_FLIGHT:
            continue
        age = _age_hours(ev.get("collected_at"), now)
        if age is not None and age >= hours:
            findings.append({
                "type": "stuck_signal", "event_id": ev.get("event_id"),
                "signal_status": status, "age_hours": round(age, 1),
                "escalate_to": ESCALATE_XO,
                "detail": f"signal in {status} for {round(age, 1)}h (>{hours}h)",
            })
    return findings


def find_stuck_briefs(repo, now: datetime, hours: int = BRIEF_STUCK_HOURS) -> list[dict]:
    """Briefs stuck pre-publication older than `hours` (generated_at age proxy)."""
    findings = []
    for br in repo.list_briefs():
        status = br.get("approval_status")
        if status not in _BRIEF_PRE_PUBLISH:
            continue
        age = _age_hours(br.get("generated_at") or br.get("created_at"), now)
        if age is not None and age >= hours:
            # A brief already QA_PASSED awaiting the Executive Approver escalates
            # to the Captain; earlier stalls (still IN_REVIEW) escalate to the XO.
            escalate = ESCALATE_CAPTAIN if status == "QA_PASSED" else ESCALATE_XO
            findings.append({
                "type": "stuck_brief", "brief_id": br.get("brief_id"),
                "approval_status": status, "age_hours": round(age, 1),
                "escalate_to": escalate,
                "detail": f"brief in {status} for {round(age, 1)}h (>{hours}h)",
            })
    return findings


def check_lead_availability(now: datetime, last_lead_activity: Any,
                            hours: int = LEAD_UNAVAILABLE_HOURS) -> Optional[dict]:
    """Flag if the Intelligence Lead has been silent longer than `hours`."""
    age = _age_hours(last_lead_activity, now)
    if age is None or age < hours:
        return None
    return {
        "type": "lead_unavailable", "age_hours": round(age, 1),
        "escalate_to": ESCALATE_XO,
        "detail": f"Intelligence Lead inactive {round(age, 1)}h (>{hours}h); "
                  f"activate backup approver / route to XO",
    }


def escalation_report(repo, now: Optional[datetime] = None,
                      last_lead_activity: Any = None) -> dict:
    """Aggregate all escalation findings for a scheduled watchdog run."""
    now = now or datetime.now(timezone.utc)
    findings: list[dict] = []
    findings.extend(find_stuck_signals(repo, now))
    findings.extend(find_stuck_briefs(repo, now))
    lead = check_lead_availability(now, last_lead_activity) if last_lead_activity else None
    if lead:
        findings.append(lead)
    return {
        "generated_at": now.isoformat(),
        "count": len(findings),
        "escalations_required": bool(findings),
        "findings": findings,
    }
