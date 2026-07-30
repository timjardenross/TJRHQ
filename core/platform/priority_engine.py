"""Priority & Opportunity Engine (Captain Intelligence Platform, MSN-0306 Programme B).

Implements the scoring model designed in MSN-0301 Workstream C and approved
unchanged by the Captain Intelligence Blueprint v1.0 (MSN-0304 §5, §7):
comparative ranking ("given several things that all deserve attention,
which matters more, and why") — genuinely distinct from the Attention
Engine's threshold/filter job.

Every dimension below is sourced from an existing or designed platform
signal, not invented fresh:
- urgency / importance / time_sensitivity  -> `core_events` fields (or a
  synthetic equivalent, in this scaffolding build — see module note below).
- value dimensions (strategic/career/financial/health/...)  -> Relationship
  Model edges linking the event to a mission/capability/domain the Captain
  has previously weighted. Real edges don't exist for most domains yet
  (MSN-0302 found only 6 of 28 capabilities graph-linked) — this module
  accepts a plain `value_dimensions` dict as its input shape so it can be
  fed either real Relationship Model query output later, or synthetic
  fixtures now.
- risk  -> computed as the inverse relationship between `importance` and
  `confidence` (low confidence + high stakes = high risk), not a new score.
- opportunity_value  -> Content Intelligence's existing opportunity-scoring
  logic (`comms/opportunities.py`), generalised as one more scored input
  under the Domain Intelligence Framework — this module does not
  reimplement that scoring, it only accepts the number.

**Explicitly not built this pass** (per MSN-0301 Workstream C and the
MSN-0306 mission brief's own scope): the actual weighting function — how
much each dimension counts is a Learning & Adaptation concern (MSN-0301
Workstream F / Blueprint §14 Wave 3+), tuned against real Captain
dismiss/act feedback, not decided once here and left static. The default
`PriorityWeights` below are a reasonable, documented starting point for
testing against synthetic fixtures — not a claim about correct future
behaviour, and must not be cited as validated against anything but the
synthetic corpus this mission ships alongside it.

MSN-0306 scope boundary: pure functions, no I/O, no Supabase dependency.
Ranking real (not synthetic) events is Wave 3 (Blueprint §14), gated on
2+ domains genuinely emitting — not part of this build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class PriorityWeights:
    """Starting weights for the 6 scoring dimensions. Must sum to 1.0.
    Explicitly a placeholder pending real Learning & Adaptation tuning
    (MSN-0301 Workstream F) — see module docstring."""

    urgency: float = 0.20
    importance: float = 0.20
    time_sensitivity: float = 0.10
    value: float = 0.25
    risk: float = 0.15
    opportunity: float = 0.10

    def __post_init__(self) -> None:
        total = self.urgency + self.importance + self.time_sensitivity + self.value + self.risk + self.opportunity
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"PriorityWeights must sum to 1.0, got {total}")


@dataclass
class PriorityInputs:
    """The per-event inputs this engine scores. Callers assemble this from
    a `core_events`-shaped dict plus whatever Relationship Model / domain
    opportunity data is available (real or synthetic) — this dataclass is
    the seam between "raw event" and "scored/ranked event."
    """

    event_id: Optional[str]
    domain: str
    event_type: str
    importance: Optional[int] = None
    confidence: Optional[int] = None
    relevance: Optional[int] = None
    time_sensitivity: Optional[int] = None  # 0-100; not a core_events column today — see module note
    value_dimensions: dict[str, int] = field(default_factory=dict)  # e.g. {"career": 80, "health": 20}
    opportunity_value: Optional[int] = None  # 0-100, from a domain's own opportunity scoring, if present


@dataclass
class PriorityScore:
    """The ranked output for one event — every component score is exposed
    so the total is explainable, not a black-box number (Blueprint
    Principle 3: 'every Priority ranking... traces to a queryable score')."""

    event_id: Optional[str]
    domain: str
    event_type: str
    total_score: float
    urgency_score: float
    importance_score: float
    time_sensitivity_score: float
    value_score: float
    risk_score: float
    opportunity_score: float
    dominant_value_dimension: Optional[str]
    explanation: str


def _risk_from_importance_confidence(importance: Optional[int], confidence: Optional[int]) -> float:
    """Risk = high importance paired with low confidence (an unverified but
    high-stakes signal). Absent confidence is treated as maximally
    uncertain (worst case), not as neutral — per MSN-0301 Workstream C's
    "inverse relationship" design, not a new independent score."""
    imp = importance if importance is not None else 0
    conf = confidence if confidence is not None else 0
    return round((imp / 100.0) * (1.0 - conf / 100.0) * 100.0, 2)


def score_event(inputs: PriorityInputs, *, weights: Optional[PriorityWeights] = None) -> PriorityScore:
    """Score one event across the 6 dimensions and combine via `weights`.

    "Urgency" and "importance" are scored from the same underlying
    `importance` input today (no separate urgency signal exists on
    `core_events` — see module note); they are kept as distinct dimensions
    in the output because MSN-0301 Workstream C names them distinctly and
    a future domain may supply a genuinely separate urgency score.
    """
    w = weights or PriorityWeights()

    importance = inputs.importance if inputs.importance is not None else 0
    urgency_score = float(importance)
    importance_score = float(importance)
    time_sensitivity_score = float(inputs.time_sensitivity) if inputs.time_sensitivity is not None else 0.0
    risk_score = _risk_from_importance_confidence(inputs.importance, inputs.confidence)
    opportunity_score = float(inputs.opportunity_value) if inputs.opportunity_value is not None else 0.0

    dominant_value_dimension: Optional[str] = None
    value_score = 0.0
    if inputs.value_dimensions:
        dominant_value_dimension = max(inputs.value_dimensions, key=inputs.value_dimensions.get)
        value_score = float(inputs.value_dimensions[dominant_value_dimension])

    total = (
        w.urgency * urgency_score
        + w.importance * importance_score
        + w.time_sensitivity * time_sensitivity_score
        + w.value * value_score
        + w.risk * risk_score
        + w.opportunity * opportunity_score
    )

    explanation_parts = [
        f"importance={importance_score:.0f}(w={w.importance})",
        f"urgency={urgency_score:.0f}(w={w.urgency})",
        f"time_sensitivity={time_sensitivity_score:.0f}(w={w.time_sensitivity})",
        f"risk={risk_score:.0f}(w={w.risk}, from importance/confidence inverse)",
        f"opportunity={opportunity_score:.0f}(w={w.opportunity})",
    ]
    if dominant_value_dimension:
        explanation_parts.append(f"value={value_score:.0f}(w={w.value}, dominant={dominant_value_dimension})")
    explanation = " + ".join(explanation_parts) + f" = {total:.2f}"

    return PriorityScore(
        event_id=inputs.event_id,
        domain=inputs.domain,
        event_type=inputs.event_type,
        total_score=round(total, 2),
        urgency_score=urgency_score,
        importance_score=importance_score,
        time_sensitivity_score=time_sensitivity_score,
        value_score=value_score,
        risk_score=risk_score,
        opportunity_score=opportunity_score,
        dominant_value_dimension=dominant_value_dimension,
        explanation=explanation,
    )


def rank_events(
    inputs_list: list[PriorityInputs],
    *,
    weights: Optional[PriorityWeights] = None,
) -> list[PriorityScore]:
    """Score and rank a batch of events, highest priority first. Stable
    sort — equal-scoring events preserve their input order rather than
    reordering arbitrarily, so re-running against the same batch is
    deterministic (a precondition for the ranking-validation tests this
    mission ships alongside this module)."""
    scores = [score_event(i, weights=weights) for i in inputs_list]
    return sorted(scores, key=lambda s: s.total_score, reverse=True)


__all__ = [
    "PriorityWeights",
    "PriorityInputs",
    "PriorityScore",
    "score_event",
    "rank_events",
]
