"""
Lifecycle vocabulary for HQ Evolution opportunities — one place.

The Captain sees four stages: To decide, In progress, Done, Closed. HQ also has
a hidden fifth, "researching", for candidates it is still looking at. An
opportunity's stored `lifecycle_state` is one of those stages.

The engine still needs finer distinctions, so the original ten states survive
as `stage_detail` (the "fine" state):

    researching : discovered, investigating
    to_decide   : proposed
    in_progress : approved, implementing, verifying
    done        : learned
    closed      : rejected, watching, resolved_before_research

Why keep them: dedup and reconsideration (relevance.py) treat a parked
"watching" idea differently from a "rejected" one; the observation window and
outcome evaluation (evolution_orchestrator.py, outcome_evaluation.py) key off
approved / implementing / verifying; evolution_memory.py recalls learned,
rejected, watching and resolved-before-research as different kinds of memory.
Code that needs those distinctions reads `detail_of(rec)`; everything the
Captain sees and every API consumer reads the simple stage.

Compatibility: nothing already on disk is rewritten. The store is an
append-only log whose older lines carry a fine state in `lifecycle_state`;
`normalise_record` turns any such line into (stage, detail) when it is read, and
`split` does the same for writes that still pass a fine state.
"""

from __future__ import annotations

from typing import Any

# Section 18 (original): the ten states the engine acts on.
FINE_STATES = (
    "discovered",
    "investigating",
    "proposed",
    "approved",
    "implementing",
    "verifying",
    "learned",
    "watching",
    "rejected",
    # A watchlist gap_hypothesis that no longer holds against current repo
    # evidence, determined by HQ itself *before* any external research was
    # spent on it. Distinct from "rejected" (a human decided against it) and
    # "watching" (premature) — and remembered so it is never re-researched.
    "resolved_before_research",
)

STAGES = ("researching", "to_decide", "in_progress", "done", "closed")

# The four the Captain sees ("researching" has no tab).
VISIBLE_STAGES = ("to_decide", "in_progress", "done", "closed")

STAGE_OF = {
    "discovered": "researching",
    "investigating": "researching",
    "proposed": "to_decide",
    "approved": "in_progress",
    "implementing": "in_progress",
    "verifying": "in_progress",
    "learned": "done",
    "watching": "closed",
    "rejected": "closed",
    "resolved_before_research": "closed",
}

# What a stage means when only the stage is known (a record written by a
# caller that has no finer information).
DEFAULT_DETAIL = {
    "researching": "discovered",
    "to_decide": "proposed",
    "in_progress": "approved",
    "done": "learned",
    "closed": "rejected",
}

assert set(STAGE_OF) == set(FINE_STATES)
assert set(STAGE_OF.values()) == set(STAGES)
assert set(DEFAULT_DETAIL) == set(STAGES)


def is_fine(value: Any) -> bool:
    return isinstance(value, str) and value in STAGE_OF


def is_stage(value: Any) -> bool:
    return isinstance(value, str) and value in DEFAULT_DETAIL


def split(value: Any, detail: Any = None) -> tuple[str, str]:
    """Return (stage, detail) for whatever a caller or an old record supplies.

    * a fine state ("verifying")            -> ("in_progress", "verifying")
    * a stage ("in_progress") + a detail
      that belongs to it ("verifying")      -> ("in_progress", "verifying")
    * a stage on its own                    -> (stage, DEFAULT_DETAIL[stage])
    * anything else (corrupt/unknown)       -> ("researching", "discovered"),
      i.e. treated as not yet surfaced, never as something needing a decision.

    A fine `value` always wins over `detail`: it is the explicit new state, and
    `detail` may be a stale leftover from the record being updated.
    """
    if is_fine(value):
        return STAGE_OF[value], value
    if is_stage(value):
        if is_fine(detail) and STAGE_OF[detail] == value:
            return value, detail
        return value, DEFAULT_DETAIL[value]
    return "researching", "discovered"


def detail_of(rec: dict[str, Any]) -> str:
    """The fine state of a record (raw or normalised) — what engine logic that
    needs the finer distinctions should read."""
    return split(rec.get("lifecycle_state"), rec.get("stage_detail"))[1]


def stage_of(rec: dict[str, Any]) -> str:
    return split(rec.get("lifecycle_state"), rec.get("stage_detail"))[0]


def normalise_record(rec: dict[str, Any]) -> dict[str, Any]:
    """A copy of `rec` with lifecycle_state = stage and stage_detail = fine
    state. Idempotent; the input (and the log line it came from) is untouched."""
    stage, detail = split(rec.get("lifecycle_state"), rec.get("stage_detail"))
    return {**rec, "lifecycle_state": stage, "stage_detail": detail}


def matches(rec: dict[str, Any], wanted: set[str] | frozenset[str]) -> bool:
    """True if the record's stage OR fine state is in `wanted` — lets an API
    filter accept either vocabulary ("proposed" or "to_decide")."""
    stage, detail = split(rec.get("lifecycle_state"), rec.get("stage_detail"))
    return stage in wanted or detail in wanted
