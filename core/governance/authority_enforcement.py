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

MSN-0326 Wave 4: approval enforcement is now blocking by default (an
action requiring captain/xo/number_one approval raises AuthorityError
unless captain_override is set) — was opt-in (SUOC Wave 2, MSN-0210F).
Revert via AUTHORITY_APPROVAL_BLOCKING=false (platform-wide) or
require_approval_blocking=False (per call).
"""

from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Any, Callable

from core.governance.authority_validator import (
    can_officer,
    requires_approval,
    audit_authority_action,
    AuthorityError,
)

log = logging.getLogger(__name__)

# MSN-0326 Wave 4: approval enforcement, opt-in -> enforced by default.
# Mirrors Wave 3's AUTHORITY_MANIFEST_GAP_MODE pattern — a single,
# documented, env-overridable lever, not a scattered per-call default.
# "true"  (default) — an action requiring approval blocks (raises
#         AuthorityError) unless captain_override is also set. This is
#         now the platform default, per MSN-0325 §6/§11 item 2 and this
#         Wave's success criteria ("approval enforcement becomes
#         consistent across the platform").
# "false" — reverts to the pre-Wave-4 behaviour: an approval requirement
#         is logged ("approval assumed at call site") and the action
#         still proceeds. Rollback path, no code change required.
_APPROVAL_BLOCKING_DEFAULT = os.environ.get("AUTHORITY_APPROVAL_BLOCKING", "true").strip().lower() != "false"


def enforce_authority(
    officer: str,
    action: str,
    *,
    captain_override: bool = False,
    mission_id: str | None = None,
    audit: bool = True,
    require_approval_blocking: bool = _APPROVAL_BLOCKING_DEFAULT,
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
        require_approval_blocking: MSN-0326 Wave 4 (was SUOC Wave 2,
            MSN-0210F Item F, opt-in). **Now defaults to True** (platform
            default, via _APPROVAL_BLOCKING_DEFAULT / the
            AUTHORITY_APPROVAL_BLOCKING env var) — an action requiring
            captain/xo/number_one approval RAISES AuthorityError unless
            captain_override was also passed. Pass False explicitly (or
            set AUTHORITY_APPROVAL_BLOCKING=false) to revert to the old
            behaviour (logged, "approval assumed at call site," action
            still proceeds) for a specific caller or platform-wide.
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
    require_approval_blocking: bool = _APPROVAL_BLOCKING_DEFAULT,
):
    """Context manager for inline authority enforcement.

    Raises AuthorityError on entry if not permitted (unless captain_override).
    require_approval_blocking: see enforce_authority()'s docstring — MSN-0326
    Wave 4, now defaults to True (platform default); pass False or set
    AUTHORITY_APPROVAL_BLOCKING=false to revert.
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
