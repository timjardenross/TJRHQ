"""Officer Authority Validator (EXEC-001 WP1).

Loads machine-readable authority manifests from governance/authority/*.yaml and
validates officer actions against them before execution. All validation results
are auditable via audit_authority_action().

Public API:
    load_manifest(officer: str) -> dict
    can_officer(officer: str, action: str) -> tuple[bool, str]
    requires_approval(officer: str, action: str) -> str | None
    validate_or_raise(officer: str, action: str) -> None
    audit_authority_action(officer, action, approved, reason, mission_id) -> None
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_DIR = _REPO_ROOT / "governance" / "authority"

# Cache — manifests are static governance documents; no hot-reload needed.
_manifest_cache: dict[str, dict] = {}


# ── Manifest loading ──────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("[authority] Failed to load %s: %s", path, exc)
        return {}


def load_manifest(officer: str) -> dict:
    """Load authority manifest for an officer. Cached after first load."""
    key = officer.lower().replace(" ", "_").replace("-", "_")
    if key in _manifest_cache:
        return _manifest_cache[key]

    manifest_path = _AUTHORITY_DIR / f"{key}.yaml"
    if not manifest_path.exists():
        log.warning("[authority] No manifest found for officer '%s' at %s", officer, manifest_path)
        return {}

    manifest = _load_yaml(manifest_path)
    _manifest_cache[key] = manifest
    return manifest


def load_all_manifests() -> dict[str, dict]:
    """Load all officer manifests. Returns dict keyed by officer slug."""
    result = {}
    if not _AUTHORITY_DIR.exists():
        log.warning("[authority] Authority directory not found: %s", _AUTHORITY_DIR)
        return result
    for path in sorted(_AUTHORITY_DIR.glob("*.yaml")):
        key = path.stem
        result[key] = _load_yaml(path)
        _manifest_cache[key] = result[key]
    return result


# ── Validation ────────────────────────────────────────────────────────────────

def can_officer(officer: str, action: str) -> tuple[bool, str]:
    """Check whether an officer is permitted to perform an action.

    Returns (approved: bool, reason: str).
    Fails open: if the manifest is missing, logs a warning and returns True
    (governance is advisory during transition; enforcement hardens progressively).
    """
    manifest = load_manifest(officer)
    if not manifest:
        log.warning(
            "[authority] No manifest for officer '%s'; action '%s' permitted (fail-open)",
            officer, action
        )
        return True, "fail-open: no manifest found"

    # Explicit disallow takes priority
    disallowed = manifest.get("disallowed_actions", [])
    if action in disallowed:
        reason = f"action '{action}' is explicitly disallowed for officer '{officer}'"
        return False, reason

    # Check allowed_actions (if present and non-empty, acts as allowlist)
    allowed = manifest.get("allowed_actions", [])
    if allowed and action not in allowed:
        reason = f"action '{action}' is not in the allowed_actions list for officer '{officer}'"
        return False, reason

    return True, "permitted"


def requires_approval(officer: str, action: str) -> str | None:
    """Return approval authority required for an action, or None if self-authorised.

    Returns one of: 'captain', 'xo', 'number_one', or None.
    Checks requires_captain, requires_xo, requires_number_one lists.
    """
    manifest = load_manifest(officer)
    if not manifest:
        return None

    if action in manifest.get("requires_captain", []):
        return "captain"
    if action in manifest.get("requires_xo", []):
        return "xo"
    if action in manifest.get("requires_number_one", []):
        return "number_one"
    return None


def validate_or_raise(officer: str, action: str) -> None:
    """Validate an action or raise AuthorityError if not permitted."""
    approved, reason = can_officer(officer, action)
    if not approved:
        raise AuthorityError(officer=officer, action=action, reason=reason)


def get_capacity_gate_rules(officer: str = "human_systems") -> dict:
    """Return D-055 capacity gate rules from the Human Systems manifest."""
    manifest = load_manifest(officer)
    return manifest.get("capacity_gates", {})


# ── Audit logging ─────────────────────────────────────────────────────────────

def audit_authority_action(
    officer: str,
    action: str,
    approved: bool,
    reason: str,
    mission_id: str | None = None,
    captain_override: bool = False,
) -> None:
    """Log an authority decision to Command Memory (non-blocking).

    Uses the decisions table with statement = "Authority: officer / action"
    so audit events appear in /decisions queries and are permanently
    recorded in Command Memory.
    """
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))

        from slack_bot.command_memory_integration import log_decision_to_command_memory

        status_word = "APPROVED" if approved else "DENIED"
        override_note = " [CAPTAIN OVERRIDE]" if captain_override else ""
        statement = (
            f"Authority {status_word}{override_note}: "
            f"{officer} / {action}"
            + (f" (mission: {mission_id})" if mission_id else "")
        )
        rationale = reason + (" — captain override applied" if captain_override else "")

        log_decision_to_command_memory(
            statement=statement,
            rationale=rationale,
            owner=f"authority_validator:{officer}",
        )
    except Exception as exc:
        log.warning("[authority] Audit log failed (non-blocking): %s", exc)


# ── Exception ─────────────────────────────────────────────────────────────────

class AuthorityError(Exception):
    """Raised when an officer attempts an action outside their authority."""

    def __init__(self, officer: str, action: str, reason: str):
        self.officer = officer
        self.action = action
        self.reason = reason
        super().__init__(f"[authority] Officer '{officer}' denied action '{action}': {reason}")


__all__ = [
    "load_manifest",
    "load_all_manifests",
    "can_officer",
    "requires_approval",
    "validate_or_raise",
    "get_capacity_gate_rules",
    "audit_authority_action",
    "AuthorityError",
]
