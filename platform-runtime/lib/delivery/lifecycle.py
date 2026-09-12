"""EDO — canonical delivery lifecycle (MSN-EDO-004).

Pure, network-free. Mirrors the SQL `edo_canonical_state()` mapping (migration
0023) so Python and the database agree on state, and defines the allowed
transitions the delivery flow enforces — closing the "0-day binary, no
intermediate states" gap found in the rebaseline.
"""

from __future__ import annotations

# Canonical delivery states, in lifecycle order.
CANONICAL_STATES = (
    "proposed", "planned", "in_progress", "in_review",
    "validated", "closed", "archived", "blocked",
)

# mission.status (any casing) → canonical delivery state. Mirrors SQL 0023.
_STATUS_TO_STATE = {
    "proposed": "proposed",
    "designed": "planned",
    "implemented": "in_progress",
    "tested": "in_review",
    "awaiting number one review": "in_review",
    "validated": "validated",
    "awaiting xo approval": "validated",
    "closed": "closed",
    "archived": "archived",
    "blocked": "blocked",
}

# Forward transitions allowed by the delivery flow. `blocked` is reachable from
# any active state and returns to its prior state on unblock (handled by caller).
_ALLOWED = {
    "proposed": {"planned", "blocked", "archived"},
    "planned": {"in_progress", "blocked", "archived"},
    "in_progress": {"in_review", "blocked", "planned"},
    "in_review": {"validated", "in_progress", "blocked"},
    "validated": {"closed", "in_review", "blocked"},
    "closed": {"archived"},
    "archived": set(),
    "blocked": set(CANONICAL_STATES) - {"blocked"},
}

# States that count as "open" (still consuming delivery capacity).
OPEN_STATES = ("proposed", "planned", "in_progress", "in_review", "validated", "blocked")
TERMINAL_STATES = ("closed", "archived")


def canonical_state(status: str | None) -> str:
    """Map a raw mission.status to a canonical delivery state."""
    if not status:
        return "other"
    return _STATUS_TO_STATE.get(status.strip().lower(), "other")


def is_open(status_or_state: str | None) -> bool:
    s = (status_or_state or "").strip().lower()
    s = s if s in CANONICAL_STATES else canonical_state(s)
    return s in OPEN_STATES


def validate_transition(from_state: str | None, to_state: str) -> tuple[bool, str]:
    """Return (ok, reason) for a proposed canonical-state transition."""
    to_state = (to_state or "").strip().lower()
    if to_state not in CANONICAL_STATES:
        return False, f"unknown target state '{to_state}'"
    frm = (from_state or "").strip().lower()
    if not frm:
        # Initial entry — only into the early states.
        if to_state in ("proposed", "planned"):
            return True, "initial entry"
        return False, f"cannot start a mission directly in '{to_state}'"
    if frm not in CANONICAL_STATES:
        frm = canonical_state(frm)
    if to_state in _ALLOWED.get(frm, set()):
        return True, "ok"
    return False, f"transition {frm} → {to_state} is not allowed"


# ── Data hygiene (MSN-EDO-002 QW2) ────────────────────────────────────────────

def normalize_task_type(value: str | None) -> str:
    return (value or "unspecified").strip().lower() or "unspecified"


_VALID_PRIORITIES = ("p0", "p1", "p2", "p3", "p4", "p5")


def normalize_priority(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in _VALID_PRIORITIES else "unset"
