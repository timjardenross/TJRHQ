"""
Workflow gate — role-based access + lifecycle enforcement for the Phase A
human curation gates. Pure logic, no web framework: the Week 2 API endpoints and
the Week 4 curation UI both call these functions so the same rules apply
everywhere (server, jobs, tests).

Three human roles (Phase A §1.4):

    Analyst            collects/cleans/tiers/scores signals (no sign-off authority)
    Intelligence Lead  verifies facts, selects events, curates watchlist, marks QA ready
    Executive Approver publishes the brief (final gate)

Two enforced invariants:

    1. RBAC          — a role may only perform its allowed actions (`can`/`require`)
    2. Lifecycle     — signal & brief status may only move along legal transitions
                       (`validate_signal_transition`, `validate_brief_transition`),
                       and a brief may only reach QA_READY once the mandatory QA
                       gates are green (`check_brief_gates`).

Every mutation is written to the shared append-only audit trail via `log_mutation`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# ─── Roles ───────────────────────────────────────────────────────────────────
ANALYST = "analyst"
INTELLIGENCE_LEAD = "intelligence_lead"
EXECUTIVE_APPROVER = "executive_approver"

WORKFLOW_ROLES = (ANALYST, INTELLIGENCE_LEAD, EXECUTIVE_APPROVER)

# ─── RBAC: role → permitted actions ──────────────────────────────────────────
# Actions are dotted verbs matching the pipeline stages. Higher roles do NOT
# implicitly inherit lower-role actions — the Executive Approver deliberately
# cannot curate (separation of duties), per Phase A §1.4.
ROLE_ACTIONS: dict[str, frozenset[str]] = {
    ANALYST: frozenset({
        "signal.collect", "signal.clean", "signal.tier", "signal.score",
    }),
    INTELLIGENCE_LEAD: frozenset({
        "signal.verify", "signal.select",
        "brief.curate_watchlist", "brief.mark_qa_ready", "brief.record_lesson",
    }),
    EXECUTIVE_APPROVER: frozenset({
        "brief.publish",
    }),
}

ALL_ACTIONS: frozenset[str] = frozenset().union(*ROLE_ACTIONS.values())


class GovernanceError(Exception):
    """Raised when an action or lifecycle transition is not permitted (-> HTTP 400)."""


class AuthorizationError(GovernanceError):
    """Role is not permitted to perform the action (-> HTTP 403)."""


class NotFoundError(GovernanceError):
    """Target record does not exist (-> HTTP 404)."""


def can(role: str, action: str) -> tuple[bool, str]:
    """Return (allowed, reason). Unknown role/action -> not allowed."""
    role = (role or "").strip().lower()
    if role not in ROLE_ACTIONS:
        return False, f"unknown role '{role}'"
    if action not in ALL_ACTIONS:
        return False, f"unknown action '{action}'"
    if action in ROLE_ACTIONS[role]:
        return True, "permitted"
    return False, f"role '{role}' may not perform '{action}'"


def require(role: str, action: str) -> None:
    """Raise AuthorizationError unless `role` may perform `action`."""
    allowed, reason = can(role, action)
    if not allowed:
        raise AuthorizationError(reason)


# ─── Signal lifecycle state machine ──────────────────────────────────────────
# Mirrors the signal_status CHECK constraint in migration 0077.
SIGNAL_TRANSITIONS: dict[str, frozenset[str]] = {
    # VERIFYING and READY_FOR_BRIEF are optional intermediates; the human gates
    # (verify: SCORED->VERIFIED, select: VERIFIED->IN_BRIEF) are single legal moves.
    "TO_COLLECT":      frozenset({"SCORED", "DUPLICATE", "ARCHIVED"}),
    "SCORED":          frozenset({"VERIFYING", "VERIFIED", "DUPLICATE", "ARCHIVED"}),
    "VERIFYING":       frozenset({"VERIFIED", "SCORED", "ARCHIVED"}),
    "VERIFIED":        frozenset({"READY_FOR_BRIEF", "IN_BRIEF", "ARCHIVED"}),
    "READY_FOR_BRIEF": frozenset({"IN_BRIEF", "ARCHIVED"}),
    "IN_BRIEF":        frozenset({"ARCHIVED"}),
    "DUPLICATE":       frozenset({"ARCHIVED"}),
    "ARCHIVED":        frozenset(),
}


def validate_signal_transition(current: str, target: str) -> tuple[bool, str]:
    """Return (allowed, reason) for a signal_status transition."""
    if current not in SIGNAL_TRANSITIONS:
        return False, f"unknown signal_status '{current}'"
    if target == current:
        return True, "no-op"
    if target in SIGNAL_TRANSITIONS[current]:
        return True, "permitted"
    return False, f"illegal signal transition {current} -> {target}"


# ─── Brief approval state machine + QA gates ─────────────────────────────────
# Mirrors the approval_status CHECK constraint in migration 0077.
BRIEF_TRANSITIONS: dict[str, frozenset[str]] = {
    "IN_REVIEW":            frozenset({"DATA_QA_PASSED"}),
    "DATA_QA_PASSED":       frozenset({"FACTUAL_QA_PASSED"}),
    "FACTUAL_QA_PASSED":    frozenset({"ANALYTICAL_QA_PASSED"}),
    "ANALYTICAL_QA_PASSED": frozenset({"QA_READY"}),
    "QA_READY":             frozenset({"EXECUTIVE_APPROVED"}),
    "EXECUTIVE_APPROVED":   frozenset({"PUBLISHED"}),
    "PUBLISHED":            frozenset(),
}

# Gates that must be 'passed' in approval_audit before a brief may become QA_READY.
# Executive approval is a separate gate applied at publish, not here.
MANDATORY_QA_GATES = ("data_qa", "factual_qa", "analytical_qa")


def validate_brief_transition(current: str, target: str) -> tuple[bool, str]:
    """Return (allowed, reason) for an approval_status transition."""
    if current not in BRIEF_TRANSITIONS:
        return False, f"unknown approval_status '{current}'"
    if target == current:
        return True, "no-op"
    if target in BRIEF_TRANSITIONS[current]:
        return True, "permitted"
    return False, f"illegal brief transition {current} -> {target}"


def check_brief_gates(approval_audit: Optional[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Check the mandatory QA gates.

    Returns (ready, missing_gates). `ready` is True only when every gate in
    MANDATORY_QA_GATES has status == 'passed' in approval_audit.
    """
    audit = approval_audit or {}
    missing = [
        gate for gate in MANDATORY_QA_GATES
        if (audit.get(gate) or {}).get("status") != "passed"
    ]
    return (not missing), missing


# ─── Mutation audit (reuses migration 0054 audit_events) ─────────────────────
def log_mutation(
    table_name: str,
    record_id: str,
    mutation_type: str,
    actor_role: str,
    before_state: Optional[dict[str, Any]] = None,
    after_state: Optional[dict[str, Any]] = None,
    mission_id: Optional[str] = None,
) -> bool:
    """Append a mutation record to the shared audit trail.

    Maps onto audit_events: category='mutation', actor=actor_role,
    action='<TYPE> <table>', outcome='recorded', details carries record_id and
    the before/after snapshots. Non-blocking (never raises) — audit failure must
    not break the workflow, matching record_audit_event's contract.
    """
    try:
        from core.platform.audit_service import record_audit_event

        return record_audit_event(
            category="mutation",
            actor=actor_role or "unknown",
            action=f"{mutation_type} {table_name}",
            outcome="recorded",
            details={
                "table_name": table_name,
                "record_id": record_id,
                "mutation_type": mutation_type,
                "before_state": before_state or {},
                "after_state": after_state or {},
            },
            mission_id=mission_id,
        )
    except Exception as exc:  # audit must never break the workflow
        log.warning("log_mutation: audit write failed (%s); continuing", exc)
        return False
