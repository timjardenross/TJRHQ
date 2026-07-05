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
    require_approval_blocking: bool = False,
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
        require_approval_blocking: SUOC Wave 2 (MSN-0210F, Item F). Default
            False preserves the original behaviour exactly — an action
            requiring captain/xo/number_one approval is logged and still
            executes ("approval assumed at call site"). When True, that
            same situation instead RAISES AuthorityError unless
            captain_override was also passed — i.e. captain_override is
            the only recognised "approval was already granted" signal.
            Opt-in only; existing callers are unaffected until they choose
            to pass this explicitly.
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
                if require_approval_blocking and not captain_override:
                    block_reason = (
                        f"{approval_chain} approval required and not yet granted "
                        f"(captain_override not set)"
                    )
                    if audit:
                        audit_authority_action(
                            officer=officer,
                            action=action,
                            approved=False,
                            reason=block_reason,
                            mission_id=mission_id,
                            captain_override=captain_override,
                        )
                    raise AuthorityError(officer=officer, action=action, reason=block_reason)
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
    require_approval_blocking: bool = False,
):
    """Context manager for inline authority enforcement.

    Raises AuthorityError on entry if not permitted (unless captain_override).
    require_approval_blocking: see enforce_authority()'s docstring — default
    False preserves original behaviour exactly; opt-in only.
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

    approval_chain = requires_approval(officer, action)
    if approval_chain and require_approval_blocking and not captain_override:
        block_reason = (
            f"{approval_chain} approval required and not yet granted "
            f"(captain_override not set)"
        )
        if audit:
            audit_authority_action(
                officer=officer,
                action=action,
                approved=False,
                reason=block_reason,
                mission_id=mission_id,
                captain_override=captain_override,
            )
        raise AuthorityError(officer=officer, action=action, reason=block_reason)
    elif approval_chain:
        log.info(
            "[authority-enforcement] %s / %s requires %s approval — proceeding (approval assumed at call site)",
            officer, action, approval_chain
        )

    yield


__all__ = [
    "enforce_authority",
    "AuthorityContext",
]
