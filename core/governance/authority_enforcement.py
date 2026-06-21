"""Authority Enforcement Wrapper (EXEC-001 WP1).

Provides a decorator and context manager for enforcing officer authority checks
before any action is executed. All enforcement decisions are audited.

Usage:
    from core.governance.authority_enforcement import enforce_authority

    @enforce_authority(officer="number_one", action="assign_mission_owner")
    def assign_owner(mission_id: str, owner: str):
        ...

    # Or inline:
    with AuthorityContext(officer="human_systems", action="trigger_recovery_protocol"):
        trigger_recovery()

    # Captain override:
    with AuthorityContext(officer="human_systems", action="override_red_capacity_gate",
                          captain_override=True, mission_id="MSN-0071"):
        proceed_despite_red()
"""

from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import Any, Callable

from core.governance.authority_validator import (
    can_officer,
    requires_approval,
    audit_authority_action,
    AuthorityError,
)

log = logging.getLogger(__name__)


def enforce_authority(
    officer: str,
    action: str,
    *,
    captain_override: bool = False,
    mission_id: str | None = None,
    audit: bool = True,
) -> Callable:
    """Decorator that validates officer authority before executing a function.

    If the action is disallowed, raises AuthorityError (logged, non-crashing
    in caller context). Captain override bypasses the gate and logs the
    override to Command Memory for full auditability.

    Args:
        officer:          Officer slug (e.g. 'number_one', 'human_systems')
        action:           Action string matching allowed_actions in the YAML
        captain_override: If True, bypass gate and log override to audit
        mission_id:       Optional mission ID for audit context
        audit:            Whether to write to Command Memory audit log
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            approved, reason = can_officer(officer, action)

            if not approved and captain_override:
                approved = True
                reason = f"captain override applied — original: {reason}"
                log.warning(
                    "[authority-enforcement] Captain override: %s / %s (mission=%s)",
                    officer, action, mission_id
                )

            if audit:
                audit_authority_action(
                    officer=officer,
                    action=action,
                    approved=approved,
                    reason=reason,
                    mission_id=mission_id,
                    captain_override=captain_override,
                )

            if not approved:
                raise AuthorityError(officer=officer, action=action, reason=reason)

            approval_chain = requires_approval(officer, action)
            if approval_chain:
                log.info(
                    "[authority-enforcement] %s / %s requires %s approval — proceeding (approval assumed at call site)",
                    officer, action, approval_chain
                )

            return fn(*args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def AuthorityContext(
    officer: str,
    action: str,
    *,
    captain_override: bool = False,
    mission_id: str | None = None,
    audit: bool = True,
):
    """Context manager for inline authority enforcement.

    Raises AuthorityError on entry if not permitted (unless captain_override).
    """
    approved, reason = can_officer(officer, action)

    if not approved and captain_override:
        approved = True
        reason = f"captain override applied — original: {reason}"
        log.warning(
            "[authority-enforcement] Captain override: %s / %s (mission=%s)",
            officer, action, mission_id
        )

    if audit:
        audit_authority_action(
            officer=officer,
            action=action,
            approved=approved,
            reason=reason,
            mission_id=mission_id,
            captain_override=captain_override,
        )

    if not approved:
        raise AuthorityError(officer=officer, action=action, reason=reason)

    yield


__all__ = [
    "enforce_authority",
    "AuthorityContext",
]
