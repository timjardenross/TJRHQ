#!/usr/bin/env python3
"""MSN-0066 Increment 0 — Unified lifecycle status spine (PURE, read-only).

The engineering lifecycle currently runs FOUR independent status vocabularies
that are never reconciled into one spine (see
`Missions/MSN-0066-ENGINEERING-LIFECYCLE-ORCHESTRATION-ASSESSMENT.md`, WP1.1):

  1. Slack mission lifecycle   — platform-runtime/commands/mission_lifecycle.py
       Idea / Planned / Active / Blocked / Review / Completed / Closed
  2. Canonical (ADR-0001)      — migration 0013 / canonical_id_resolver.py
       Idea / Designed / Implemented / Tested / Awaiting Number One Review /
       Validated / Awaiting XO Approval / Closed / Blocked / Archived
  3. Engineering lifecycle     — core/coordination/engineering_handoff_reader.py
       Pending Triage / Assigned / In Progress / Awaiting Review / Completed
  4. Build-request inbox       — migration 0015 / telegram_build_executor.py
       pending_triage / approved / engineering_running /
       engineering_delivered / engineering_failed

A single mission can hold three contradictory "truths" at once, which is the
root cause of the lifecycle dead zones. This module is the reconciliation map:
a pure translation from each source vocabulary onto ONE coarse spine of five
stages. It never writes, never advances a status, and (until something imports
it) changes no behaviour — the lowest-risk increment.

The five stages collapse the ten fine-grained stages of the assessment (WP1.2):

    CAPTURE   ← Mission Capture, Mission Design        (idea / shaping, pre-approval)
    APPROVAL  ← Mission Approval                       (approved, intake pending)
    BUILD     ← Engineering Intake, Pending Triage, Assigned, In Progress
    REVIEW    ← Awaiting Review                        (delivered, awaiting sign-off)
    CLOSED    ← Completed, Closed

One distinction the coarse model preserves and the names obscure: the inbox's
`pending_triage` is a *raw build request awaiting approval* → CAPTURE, whereas an
engineering handoff's "Pending Triage" is *already approved, awaiting pickup* →
BUILD. Same words, different stages — exactly why a single spine is needed.

Reuse-first (ADR-020): the engineering vocabulary is NOT re-encoded here. We
import `EngineeringStatus` and `derive_engineering_status` from
`engineering_handoff_reader` and reuse its tolerant token normaliser, so the two
modules cannot drift.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from core.coordination.engineering_handoff_reader import (
    EngineeringStatus,
    _normalise_token as _norm,  # reuse the reader's tolerant normaliser (same subsystem)
    derive_engineering_status,
)


class LifecycleStage(Enum):
    """The unified operational spine — five coarse stages, capture → closed."""
    CAPTURE = "Capture"
    APPROVAL = "Approval"
    BUILD = "Build"
    REVIEW = "Review"
    CLOSED = "Closed"


# Capture → Closed. Index = how far along a stage sits; used to pick the
# furthest-advanced truth when sources disagree (see `reconcile`).
LIFECYCLE_SPINE = (
    LifecycleStage.CAPTURE,
    LifecycleStage.APPROVAL,
    LifecycleStage.BUILD,
    LifecycleStage.REVIEW,
    LifecycleStage.CLOSED,
)

_SPINE_ORDER = {stage: i for i, stage in enumerate(LIFECYCLE_SPINE)}


def stage_order(stage: LifecycleStage) -> int:
    """Position of a stage on the spine (0 = capture … 4 = closed)."""
    return _SPINE_ORDER[stage]


# ---------------------------------------------------------------------------
# Source-vocabulary → spine maps. Keys are normalised via `_norm` (upper, no
# spaces/-/_) so callers pass raw status strings verbatim. "Blocked" maps to
# BUILD: the spine encodes progress, not health — the blocked condition is
# carried separately by callers (mission_risk already scores it). A failed build
# (`engineering_failed`) is no longer being worked but needs a human, so it sits
# at REVIEW. "Archived" collapses to CLOSED.
# ---------------------------------------------------------------------------

# Vocabulary 1 — Slack mission lifecycle (mission_lifecycle.py:42)
_SLACK_MAP = {
    _norm("Idea"): LifecycleStage.CAPTURE,
    _norm("Planned"): LifecycleStage.CAPTURE,
    _norm("Active"): LifecycleStage.BUILD,
    _norm("Blocked"): LifecycleStage.BUILD,
    _norm("Review"): LifecycleStage.REVIEW,
    _norm("Completed"): LifecycleStage.CLOSED,
    _norm("Closed"): LifecycleStage.CLOSED,
}

# Vocabulary 2 — Canonical / ADR-0001 (migration 0013). Validated and
# Awaiting XO Approval are post-validation, pending final human sign-off → REVIEW.
_CANONICAL_MAP = {
    _norm("Idea"): LifecycleStage.CAPTURE,
    _norm("Designed"): LifecycleStage.CAPTURE,
    _norm("Implemented"): LifecycleStage.BUILD,
    _norm("Tested"): LifecycleStage.REVIEW,
    _norm("Awaiting Number One Review"): LifecycleStage.REVIEW,
    _norm("Validated"): LifecycleStage.REVIEW,
    _norm("Awaiting XO Approval"): LifecycleStage.REVIEW,
    _norm("Closed"): LifecycleStage.CLOSED,
    _norm("Blocked"): LifecycleStage.BUILD,
    _norm("Archived"): LifecycleStage.CLOSED,
}

# Vocabulary 3 — Engineering lifecycle: an approved handoff is already in build.
_ENGINEERING_MAP = {
    EngineeringStatus.PENDING_TRIAGE: LifecycleStage.BUILD,
    EngineeringStatus.ASSIGNED: LifecycleStage.BUILD,
    EngineeringStatus.IN_PROGRESS: LifecycleStage.BUILD,
    EngineeringStatus.AWAITING_REVIEW: LifecycleStage.REVIEW,
    EngineeringStatus.COMPLETED: LifecycleStage.CLOSED,
}

# Vocabulary 4 — Build-request inbox (telegram_build_executor.py:55). NOTE the
# inbox `pending_triage` is a raw request awaiting approval (→ CAPTURE), unlike
# the engineering handoff's already-approved "Pending Triage" (→ BUILD above).
_INBOX_MAP = {
    _norm("pending_triage"): LifecycleStage.CAPTURE,
    _norm("triage_ready"): LifecycleStage.APPROVAL,   # enriched, at Gate 1 (lifecycle_advancer)
    _norm("approved"): LifecycleStage.APPROVAL,
    _norm("engineering_running"): LifecycleStage.BUILD,
    _norm("engineering_delivered"): LifecycleStage.REVIEW,
    _norm("engineering_failed"): LifecycleStage.REVIEW,
}


def from_slack_status(value: Optional[str]) -> Optional[LifecycleStage]:
    """Slack mission status → spine stage (None if unrecognised)."""
    return _SLACK_MAP.get(_norm(value))


def from_canonical_status(value: Optional[str]) -> Optional[LifecycleStage]:
    """Canonical/ADR-0001 mission status → spine stage (None if unrecognised)."""
    return _CANONICAL_MAP.get(_norm(value))


def from_engineering_status(value: "Optional[str | EngineeringStatus]") -> Optional[LifecycleStage]:
    """Engineering status → spine stage.

    Accepts an `EngineeringStatus`, its `.value` ("Pending Triage" …), or a raw
    `Batch Status` token — the latter resolved through the reader's own
    `derive_engineering_status` so the token vocabulary stays single-sourced.
    Returns None for terminal-but-not-completed handoffs (FAILED/CANCELLED/…),
    matching the reader's exclusion semantics. A `None` value means "no
    engineering signal" and returns None — distinct from the reader, which reads
    a blank `Batch Status` on an existing handoff as Pending Triage.
    """
    if value is None:
        return None
    if isinstance(value, EngineeringStatus):
        return _ENGINEERING_MAP.get(value)
    for es in EngineeringStatus:
        if _norm(es.value) == _norm(value):
            return _ENGINEERING_MAP.get(es)
    derived = derive_engineering_status(value if isinstance(value, str) else None)
    return _ENGINEERING_MAP.get(derived) if derived is not None else None


def from_inbox_status(value: Optional[str]) -> Optional[LifecycleStage]:
    """Build-request inbox status → spine stage (None if unrecognised)."""
    return _INBOX_MAP.get(_norm(value))


class ReconciledLifecycle:
    """The unified view of one work item across the source vocabularies.

    `stage` is the furthest-advanced translatable truth (the real frontier of
    the work). `disagreement` flags when sources resolved to different stages —
    the signal the Lifecycle Reconciler (Increment 1) acts on. PURE: no side
    effects, no writes.
    """

    __slots__ = ("stage", "inputs", "disagreement")

    def __init__(
        self,
        stage: Optional[LifecycleStage],
        inputs: dict[str, Optional[LifecycleStage]],
        disagreement: bool,
    ) -> None:
        self.stage = stage
        self.inputs = inputs
        self.disagreement = disagreement

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        s = self.stage.value if self.stage else None
        return f"ReconciledLifecycle(stage={s!r}, disagreement={self.disagreement})"


def reconcile(
    *,
    slack_status: Optional[str] = None,
    canonical_status: Optional[str] = None,
    engineering_status: "Optional[str | EngineeringStatus]" = None,
    inbox_status: Optional[str] = None,
) -> ReconciledLifecycle:
    """Translate every available source status onto the spine and unify them.

    The effective `stage` is the furthest-along translatable input — if
    engineering reports "Awaiting Review" while the mission row still says
    "Active", the work has genuinely reached review, so the frontier wins.
    `disagreement` is True when the resolved inputs span more than one stage,
    which is precisely the dead-zone / MISLABELED condition Increment 1 surfaces.

    Unrecognised or terminal-excluded inputs contribute None and are ignored for
    the frontier calculation but retained in `.inputs` for transparency.
    """
    inputs: dict[str, Optional[LifecycleStage]] = {
        "slack": from_slack_status(slack_status),
        "canonical": from_canonical_status(canonical_status),
        "engineering": from_engineering_status(engineering_status),
        "inbox": from_inbox_status(inbox_status),
    }
    resolved = [s for s in inputs.values() if s is not None]
    if not resolved:
        return ReconciledLifecycle(stage=None, inputs=inputs, disagreement=False)
    frontier = max(resolved, key=stage_order)
    disagreement = len({stage_order(s) for s in resolved}) > 1
    return ReconciledLifecycle(stage=frontier, inputs=inputs, disagreement=disagreement)


__all__ = [
    "LifecycleStage",
    "LIFECYCLE_SPINE",
    "stage_order",
    "from_slack_status",
    "from_canonical_status",
    "from_engineering_status",
    "from_inbox_status",
    "ReconciledLifecycle",
    "reconcile",
]
