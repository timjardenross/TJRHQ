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

MSN-0326 Wave 3 (explicit-only fail semantics, MSN-0325 §9): a missing
officer manifest is a manifest gap, not a permission decision. Staged
rollout via AUTHORITY_MANIFEST_GAP_MODE env var:
    "log"   (default, Stage 1) — gap logged + audited, still permitted.
    "raise" (Stage 2)          — gap raises ManifestGapError.
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

# MSN-0326 Wave 3, explicit-only fail semantics, staged rollout.
# "log"   — Stage 1. A manifest gap is logged and audited but still
#           permitted — identical external behaviour to pre-Wave-3, purely
#           additive instrumentation. Validated clean (Wave 3 Stage 1
#           report): zero behaviour change to any currently-manifested
#           officer, gap correctly detected and logged for a genuinely
#           missing manifest.
# "raise" — Stage 2 (default as of Wave 3 completion). A manifest gap
#           raises ManifestGapError instead of permitting. Enabled as the
#           default per MSN-0325 §9's resolved decision and MSN-0326 Wave
#           3's success criteria, after Stage 1's evidence (Wave 1 audit +
#           this Wave's own validation) found zero real, currently-live
#           call sites that depend on the fail-open default. Override via
#           AUTHORITY_MANIFEST_GAP_MODE=log if ever needed to revert to
#           Stage 1 behaviour without a code change.
_MANIFEST_GAP_MODE = os.environ.get("AUTHORITY_MANIFEST_GAP_MODE", "raise")


def _log_manifest_gap(officer: str, action: str, reason: str) -> None:
    """Record a manifest-gap event — logged and audited regardless of mode,
    so Stage 1's log-only period produces the same evidence trail Stage 2
    would have enforced against (MSN-0325 §10 item 2: a gap is itself an
    audited event)."""
    log.warning(
        "[authority][MANIFEST_GAP] officer '%s', action '%s': %s (mode=%s)",
        officer, action, reason, _MANIFEST_GAP_MODE,
    )
    audit_authority_action(
        officer=officer,
        action=action,
        approved=(_MANIFEST_GAP_MODE != "raise"),
        reason=f"MANIFEST_GAP ({_MANIFEST_GAP_MODE}): {reason}",
    )


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

    MSN-0326 Wave 3, explicit-only fail semantics (MSN-0325 §9): a missing
    manifest is a manifest gap — an authority question with no explicit
    answer, which is a configuration error, not a permission decision.

    Stage 1 (current, _MANIFEST_GAP_MODE == "log", the default): the gap
    is logged and audited but still permitted — external behaviour is
    byte-for-byte identical to before this Wave. This stage changes what's
    observed, not what's decided.

    Stage 2 (_MANIFEST_GAP_MODE == "raise", not yet enabled by default):
    the same condition raises ManifestGapError instead of permitting.
    """
    manifest = load_manifest(officer)
    if not manifest:
        gap_reason = f"no manifest found for officer '{officer}'"
        _log_manifest_gap(officer, action, gap_reason)
        if _MANIFEST_GAP_MODE == "raise":
            raise ManifestGapError(officer=officer, action=action, reason=gap_reason)
        return True, f"fail-open (Wave 3 Stage 1, logged as gap): {gap_reason}"

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
    """Log an authority decision to the dedicated audit table (non-blocking).

    SUOC Wave 1 (MSN-0210E): writes to authority_audit_log instead of the
    decisions table — decisions had accumulated 5 unrelated consumers by
    this point (see reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md
    §4/§16); this is the first real Audit platform-service table.
    """
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))

        from tools.supabase.client import CommanderSupabaseClient

        reason_text = reason + (" — captain override applied" if captain_override else "")

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[authority] Supabase disabled; audit record not persisted")
            return

        result = client.insert(
            "authority_audit_log",
            {
                "officer": officer,
                "action": action,
                "approved": approved,
                "reason": reason_text,
                "mission_id": mission_id,
                "captain_override": captain_override,
            },
        )
        if not result.ok:
            log.warning("[authority] Audit log write failed: %s", result.error)
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


class ManifestGapError(Exception):
    """MSN-0326 Wave 3 (Stage 2). Raised when an authority question has no
    explicit manifest answer — a missing officer manifest is a
    configuration error, not a permission decision (MSN-0325 §9). Not
    raised while _MANIFEST_GAP_MODE == "log" (Stage 1, the current
    default); the gap is logged and audited instead."""

    def __init__(self, officer: str, action: str, reason: str):
        self.officer = officer
        self.action = action
        self.reason = reason
        super().__init__(f"[authority] Manifest gap: officer '{officer}', action '{action}': {reason}")


__all__ = [
    "load_manifest",
    "load_all_manifests",
    "can_officer",
    "requires_approval",
    "validate_or_raise",
    "get_capacity_gate_rules",
    "audit_authority_action",
    "ManifestGapError",
    "AuthorityError",
]
