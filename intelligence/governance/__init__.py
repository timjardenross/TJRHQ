"""Phase A intelligence-workflow governance (human curation gates).

This package is the *human* curation-gate layer of the OR-Intelligence pipeline
(Stages 7/11/14: verify facts, select events, curate watchlist + QA/publish
approval). It is deliberately DISTINCT from — and does not duplicate —
core/governance/authority_validator.py, which governs *AI officers* (the ori
officer manifest, requires_captain/xo escalation, etc.). Officer authority
answers "may this agent act autonomously?"; this layer answers "which human role
may take this curation action, and is the lifecycle transition legal?".

All state-changing actions are recorded through the existing append-only audit
trail (core/platform/audit_service.record_audit_event, migration 0054's
audit_events table) with category='mutation' — no separate mutation_audit_log
table is introduced.
"""

from intelligence.governance.workflow_gate import (  # noqa: F401
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    WORKFLOW_ROLES,
    AuthorizationError,
    GovernanceError,
    NotFoundError,
    can,
    check_brief_gates,
    log_mutation,
    require,
    validate_brief_transition,
    validate_signal_transition,
)

__all__ = [
    "ANALYST",
    "INTELLIGENCE_LEAD",
    "EXECUTIVE_APPROVER",
    "WORKFLOW_ROLES",
    "GovernanceError",
    "AuthorizationError",
    "NotFoundError",
    "can",
    "require",
    "validate_signal_transition",
    "validate_brief_transition",
    "check_brief_gates",
    "log_mutation",
]
