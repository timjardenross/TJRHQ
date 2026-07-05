"""Number One Execution Engine (EXEC-001 WP2 — ADR-0003 Implementation).

Transforms Number One's deterministic analysis into executed actions.
Number One DECIDES; this engine ACTS.

Responsibilities:
  - Assign mission owners on approval (ADR-0003)
  - Set review dates
  - Generate and dispatch escalation messages
  - Produce executive summaries for Captain brief
  - Log all actions to Command Memory for audit

Authority: governed by governance/authority/number_one.yaml
All actions are audited via authority_validator.audit_authority_action().

Design principles:
  - All Supabase writes are non-blocking (try/except)
  - All actions log to Command Memory decisions table
  - Captain override is always available; all overrides are audited
  - Engine never decides — it executes decisions NumberOne already made
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AssignmentAction:
    """A mission assignment executed by Number One."""
    mission_id: str
    assigned_to: str
    review_date: datetime
    rationale: str
    logged_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EscalationAction:
    """An escalation generated and dispatched by Number One."""
    mission_id: str
    escalation_type: str       # STALE | BLOCKED | MISSING_OWNER | CAPACITY
    route_to: str              # "xo" | "captain"
    message: str
    priority: str              # P0 | P1 | P2 | P3
    logged_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExecutiveSummary:
    """Consolidated Number One summary for Captain brief."""
    timestamp: datetime
    in_progress: list[dict]
    stale: list[dict]
    blocked: list[dict]
    completed_this_cycle: list[dict]
    escalations: list[EscalationAction]
    assignments_made: list[AssignmentAction]
    recommended_actions: list[str]
    system_health: str   # "green" | "amber" | "red"
    last_updated: datetime = field(default_factory=datetime.utcnow)


# ── Engine ────────────────────────────────────────────────────────────────────

class NumberOneExecutionEngine:
    """Executes Number One's coordination decisions.

    All methods are non-blocking: failures are logged, not raised.
    All decisions are written to Command Memory for audit.
    """

    REVIEW_DATE_DEFAULT_DAYS = 7

    def __init__(self, captain_override: bool = False):
        """
        Args:
            captain_override: If True, bypass all authority gates.
                              Must be logged at call site. Used only in
                              genuine emergency where Captain explicitly directs.
        """
        self.captain_override = captain_override
        self._client = self._get_client()

    # ── Public API ────────────────────────────────────────────────────────────

    def on_mission_approved(
        self,
        mission_id: str,
        recommended_owner: str,
        *,
        review_days: int | None = None,
    ) -> AssignmentAction | None:
        """Execute assignment when a mission is approved by XO.

        Assigns owner, sets review date, logs to Command Memory.
        ADR-0003 implementation.
        """
        # SUOC Wave 2: delegates the check+audit sequence to the shared
        # authority_enforcement.AuthorityContext instead of duplicating it
        # inline (this used to reimplement can_officer + audit_authority_action
        # directly). AuthorityContext raises AuthorityError on denial where
        # this method returns None — caught below to preserve that exact
        # external behaviour; everything else (fail-open on any other
        # exception, audited approved=True when captain_override applies)
        # is unchanged.
        try:
            from core.governance.authority_enforcement import AuthorityContext
            from core.governance.authority_validator import AuthorityError

            try:
                with AuthorityContext(
                    officer="number_one",
                    action="assign_mission_owner",
                    captain_override=self.captain_override,
                    mission_id=mission_id,
                ):
                    pass
            except AuthorityError as exc:
                log.warning("[exec-engine] Assignment blocked by authority gate: %s", exc.reason)
                return None
        except Exception as exc:
            log.warning("[exec-engine] Authority check failed (non-blocking): %s", exc)

        days = review_days or self.REVIEW_DATE_DEFAULT_DAYS
        review_date = datetime.utcnow() + timedelta(days=days)

        action = AssignmentAction(
            mission_id=mission_id,
            assigned_to=recommended_owner,
            review_date=review_date,
            rationale=f"Number One assignment on XO approval (ADR-0003). Review: {review_date.strftime('%Y-%m-%d')}",
        )

        self._write_assignment(action)
        return action

    def on_mission_stale(
        self,
        mission_id: str,
        mission_title: str,
        days_stale: int,
        priority: str,
        blockers: list[str] | None = None,
    ) -> EscalationAction:
        """Generate and log escalation for a stale mission."""
        has_blockers = bool(blockers)
        route_to = "xo" if has_blockers else "captain_brief"

        blocker_text = ""
        if has_blockers:
            blocker_text = f"\nBlockers: {'; '.join(blockers)}"

        message = (
            f"*[NUMBER ONE ESCALATION — STALE MISSION]*\n"
            f"Mission: `{mission_id}` — {mission_title}\n"
            f"Priority: {priority} | Stale: {days_stale} days{blocker_text}\n"
            f"Route: {route_to.upper()}\n"
            f"Action required: {'Resolve blockers or reassign' if has_blockers else 'Status update needed'}"
        )

        action = EscalationAction(
            mission_id=mission_id,
            escalation_type="STALE",
            route_to=route_to,
            message=message,
            priority=priority,
        )

        self._log_escalation(action)
        return action

    def on_blocked_mission(
        self,
        mission_id: str,
        mission_title: str,
        days_blocked: int,
        priority: str,
        blockers: list[str],
    ) -> EscalationAction:
        """Generate escalation for a blocked mission."""
        route_to = "captain" if priority in ("P0",) else "xo"

        message = (
            f"*[NUMBER ONE ESCALATION — BLOCKED MISSION]*\n"
            f"Mission: `{mission_id}` — {mission_title}\n"
            f"Priority: {priority} | Blocked: {days_blocked} days\n"
            f"Blockers: {'; '.join(blockers)}\n"
            f"Route: {route_to.upper()}\n"
            f"Action required: Resolve blocker or escalate to unblock"
        )

        action = EscalationAction(
            mission_id=mission_id,
            escalation_type="BLOCKED",
            route_to=route_to,
            message=message,
            priority=priority,
        )

        self._log_escalation(action)
        return action

    def on_review_date_reached(
        self,
        mission_id: str,
        mission_title: str,
        assigned_to: str,
    ) -> str:
        """Generate progress request when review date is reached."""
        message = (
            f"*[NUMBER ONE — REVIEW DUE]*\n"
            f"Mission: `{mission_id}` — {mission_title}\n"
            f"Owner: {assigned_to}\n"
            f"Review date reached. Progress update required.\n"
            f"Submit to: Number One Review queue (`Awaiting Number One Review`)"
        )
        self._log_decision(
            statement=f"Review date reached: {mission_id}",
            rationale=f"Review date reached for mission '{mission_title}' owned by {assigned_to}. Progress request dispatched.",
        )
        return message

    def generate_executive_summary(
        self,
        missions: list[dict[str, Any]],
        escalations: list[EscalationAction] | None = None,
        assignments: list[AssignmentAction] | None = None,
    ) -> ExecutiveSummary:
        """Produce Number One's executive summary for Captain brief.

        Organises missions by state, surfaces escalations and recent assignments.
        This is the primary Number One contribution to the daily Captain brief.
        """
        now = datetime.utcnow()
        escalations = escalations or []
        assignments = assignments or []

        in_progress, stale, blocked, completed = [], [], [], []

        STALE_DAYS = 5
        STALE_P0_DAYS = 2
        TERMINAL = {"closed", "archived", "completed", "cancelled"}

        for m in missions:
            status = str(m.get("status") or "").lower()
            priority = str(m.get("priority") or "P3")
            title = m.get("title", "")
            mid = m.get("id") or m.get("mission_id", "")

            if status in TERMINAL:
                completed.append({"id": mid, "title": title})
                continue

            last_updated_str = m.get("updated_at") or m.get("last_updated")
            days_since = 0
            if last_updated_str:
                try:
                    lu = datetime.fromisoformat(str(last_updated_str).replace("Z", "+00:00"))
                    days_since = (now - lu.replace(tzinfo=None)).days
                except Exception:
                    days_since = 0

            stale_threshold = STALE_P0_DAYS if priority == "P0" else STALE_DAYS
            item = {"id": mid, "title": title, "status": status, "priority": priority, "days_since_update": days_since}

            if "block" in status:
                blocked.append(item)
            elif days_since >= stale_threshold and status not in ("idea",):
                stale.append(item)
            elif status not in ("idea",):
                in_progress.append(item)

        # Determine system health
        if any(e.escalation_type == "BLOCKED" and e.priority == "P0" for e in escalations):
            health = "red"
        elif escalations or stale:
            health = "amber"
        else:
            health = "green"

        recommended_actions = self._build_recommendations(in_progress, stale, blocked, escalations, assignments)

        return ExecutiveSummary(
            timestamp=now,
            in_progress=in_progress,
            stale=stale,
            blocked=blocked,
            completed_this_cycle=completed[-5:],
            escalations=escalations,
            assignments_made=assignments,
            recommended_actions=recommended_actions,
            system_health=health,
        )

    def format_captain_brief_section(self, summary: ExecutiveSummary) -> str:
        """Format executive summary as a Slack-ready Captain brief section."""
        health_icon = {"green": ":large_green_circle:", "amber": ":large_yellow_circle:", "red": ":red_circle:"}.get(summary.system_health, ":white_circle:")
        lines = [
            f"{health_icon} *NUMBER ONE EXECUTIVE SUMMARY*",
            f"_{summary.timestamp.strftime('%Y-%m-%d %H:%M')} UTC_",
            "",
        ]

        if summary.recommended_actions:
            lines.append("*Recommended Actions:*")
            for a in summary.recommended_actions[:3]:
                lines.append(f"  • {a}")
            lines.append("")

        lines.append(f"*In Progress:* {len(summary.in_progress)} missions")
        if summary.stale:
            lines.append(f"*Stale (needs attention):* {len(summary.stale)}")
            for m in summary.stale[:3]:
                lines.append(f"  :warning: `{m['id']}` — {m['title']} ({m['days_since_update']}d)")
        if summary.blocked:
            lines.append(f"*Blocked:* {len(summary.blocked)}")
            for m in summary.blocked[:3]:
                lines.append(f"  :no_entry: `{m['id']}` — {m['title']}")
        if summary.escalations:
            lines.append(f"*Escalations:* {len(summary.escalations)}")
            for e in summary.escalations[:3]:
                lines.append(f"  :rotating_light: `{e.mission_id}` → {e.route_to.upper()}")
        if summary.assignments_made:
            lines.append(f"*Assignments made:* {len(summary.assignments_made)}")
            for a in summary.assignments_made[:3]:
                lines.append(f"  :white_check_mark: `{a.mission_id}` → {a.assigned_to} (review: {a.review_date.strftime('%Y-%m-%d')})")

        return "\n".join(lines)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_client(self):
        try:
            from slack_bot.command_memory_integration import get_client
            return get_client()
        except Exception:
            try:
                sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
                from command_memory_integration import get_client
                return get_client()
            except Exception as exc:
                log.warning("[exec-engine] Command Memory client unavailable: %s", exc)
                return None

    def _write_assignment(self, action: AssignmentAction) -> None:
        """Write assignment to missions table and log decision to Command Memory."""
        try:
            if self._client:
                self._client.update(
                    "missions",
                    action.mission_id,
                    {
                        "owner": action.assigned_to,
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                        "updated_by": "number_one",
                    }
                )
                log.info("[exec-engine] Mission %s assigned to %s", action.mission_id, action.assigned_to)
        except Exception as exc:
            log.warning("[exec-engine] Assignment write failed (non-blocking): %s", exc)

        self._log_decision(
            statement=f"Number One assigned {action.mission_id} to {action.assigned_to}",
            rationale=action.rationale,
        )

    def _log_escalation(self, action: EscalationAction) -> None:
        """Log escalation to Command Memory."""
        self._log_decision(
            statement=f"Number One escalation: {action.mission_id} ({action.escalation_type}) → {action.route_to}",
            rationale=action.message,
        )
        log.info("[exec-engine] Escalation logged: %s → %s", action.mission_id, action.route_to)

    def _log_decision(self, statement: str, rationale: str) -> None:
        """Non-blocking write to Command Memory decisions table."""
        try:
            _try_log_decision(statement, rationale, owner="number_one")
        except Exception as exc:
            log.warning("[exec-engine] Decision log failed (non-blocking): %s", exc)

    def _build_recommendations(
        self,
        in_progress: list[dict],
        stale: list[dict],
        blocked: list[dict],
        escalations: list[EscalationAction],
        assignments: list[AssignmentAction],
    ) -> list[str]:
        recs = []
        if blocked:
            p0_blocked = [m for m in blocked if m.get("priority") == "P0"]
            if p0_blocked:
                recs.append(f"URGENT: Unblock {p0_blocked[0]['id']} — P0 mission blocked")
            else:
                recs.append(f"Resolve blockers: {blocked[0]['id']}")
        if stale:
            recs.append(f"Request status update: {stale[0]['id']} ({stale[0]['days_since_update']}d stale)")
        if not in_progress and not stale and not blocked:
            recs.append("All missions progressing normally — no intervention required")
        return recs[:5]


# ── Standalone helper (avoids circular import) ────────────────────────────────

def _try_log_decision(statement: str, rationale: str, owner: str) -> None:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(statement=statement, rationale=rationale, owner=owner)
    except Exception:
        pass


__all__ = [
    "NumberOneExecutionEngine",
    "AssignmentAction",
    "EscalationAction",
    "ExecutiveSummary",
]
