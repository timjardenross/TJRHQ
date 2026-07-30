"""Improvement Validation Scorecard (EXEC-002A WP9).

Every improvement mission must establish baseline state, target state, and
actual state. Validation is mandatory before a mission can be marked complete.

Required questions (WP9):
  1. What changed?
  2. What improved?
  3. What did not improve?
  4. Was the expected benefit realised?
  5. Should the improvement be expanded?
  6. Should the improvement be reversed?

Validation outcomes:
  SUCCESSFUL         — expected benefits realised
  PARTIAL            — some benefits realised
  FAILED             — benefits not realised
  REVERSAL_RECOMMENDED — improvement should be withdrawn

Scorecards use the decisions table (no new tables). Two records per mission:
  "Scorecard CREATED: {mission_id}"   — baseline + target at mission start
  "Scorecard COMPLETED: {mission_id}" — actual + outcome at closure

Public API:
    ValidationOutcome              — outcome enum
    ImprovementMetrics             — measurable benefit dataclass
    ImprovementScorecard           — full scorecard dataclass
    create_scorecard(...)          -> bool
    complete_scorecard(...)        -> bool
    get_scorecard(mission_id)      -> ImprovementScorecard | None
    get_outcomes_report(limit)     -> list[dict]
    format_scorecard_summary(...)  -> str
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Outcome enum ──────────────────────────────────────────────────────────────

class ValidationOutcome(str, Enum):
    SUCCESSFUL           = "successful"           # expected benefits realised
    PARTIAL              = "partial"              # some benefits realised
    FAILED               = "failed"              # benefits not realised
    REVERSAL_RECOMMENDED = "reversal_recommended" # improvement should be withdrawn


# ── Metrics ───────────────────────────────────────────────────────────────────

@dataclass
class ImprovementMetrics:
    """Quantitative benefit metrics (all optional — use what applies)."""
    time_saved:              str | None = None   # e.g. "30 min/day"
    steps_removed:           int | None = None
    capacity_gained:         str | None = None   # e.g. "2 Captain escalations removed/week"
    risk_reduced:            str | None = None   # e.g. "RED → AMBER resilience"
    automation_achieved:     str | None = None   # what was automated
    cost_reduced:            str | None = None
    mission_throughput_gain: str | None = None   # e.g. "+1 mission/week"
    manual_effort_removed:   str | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in asdict(self).values())

    def to_text(self) -> str:
        lines = []
        fields_labels = [
            ("time_saved",              "Time saved"),
            ("steps_removed",           "Steps removed"),
            ("capacity_gained",         "Capacity gained"),
            ("risk_reduced",            "Risk reduced"),
            ("automation_achieved",     "Automation achieved"),
            ("cost_reduced",            "Cost reduced"),
            ("mission_throughput_gain", "Throughput gain"),
            ("manual_effort_removed",   "Manual effort removed"),
        ]
        for attr, label in fields_labels:
            val = getattr(self, attr)
            if val is not None:
                lines.append(f"{label}: {val}")
        return "; ".join(lines) if lines else "No quantitative metrics provided"


# ── Scorecard ─────────────────────────────────────────────────────────────────

@dataclass
class ImprovementScorecard:
    """Full improvement validation scorecard for a single mission."""
    mission_id: str
    officer: str
    baseline_state: str
    target_state: str

    # Completed at closure
    actual_state: str | None = None
    outcome: ValidationOutcome | None = None
    what_changed: str | None = None
    what_improved: str | None = None
    what_did_not_improve: str | None = None
    expected_benefit_realised: bool | None = None
    should_expand: bool | None = None
    should_reverse: bool | None = None
    metrics: ImprovementMetrics = field(default_factory=ImprovementMetrics)

    created_at: datetime = field(default_factory=datetime.utcnow)
    validated_at: datetime | None = None

    @property
    def is_complete(self) -> bool:
        return self.outcome is not None and self.actual_state is not None

    @property
    def outcome_label(self) -> str:
        if not self.outcome:
            return "PENDING"
        return self.outcome.value.upper().replace("_", " ")

    def to_rationale_text(self) -> str:
        """Serialise scorecard to text for decisions.rationale storage."""
        parts = [
            f"BASELINE: {self.baseline_state}",
            f"TARGET: {self.target_state}",
        ]
        if self.actual_state:
            parts.append(f"ACTUAL: {self.actual_state}")
        if self.outcome:
            parts.append(f"OUTCOME: {self.outcome.value}")
        if self.what_changed:
            parts.append(f"CHANGED: {self.what_changed}")
        if self.what_improved:
            parts.append(f"IMPROVED: {self.what_improved}")
        if self.what_did_not_improve:
            parts.append(f"NOT_IMPROVED: {self.what_did_not_improve}")
        if self.expected_benefit_realised is not None:
            parts.append(f"BENEFIT_REALISED: {self.expected_benefit_realised}")
        if self.should_expand is not None:
            parts.append(f"EXPAND: {self.should_expand}")
        if self.should_reverse is not None:
            parts.append(f"REVERSE: {self.should_reverse}")
        if not self.metrics.is_empty():
            parts.append(f"METRICS: {self.metrics.to_text()}")
        return " | ".join(parts)


# ── Storage helpers ───────────────────────────────────────────────────────────

_CREATED_PREFIX   = "Scorecard CREATED: "
_COMPLETED_PREFIX = "Scorecard COMPLETED: "
_OWNER_PREFIX     = "improvement_scorecard:"


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[improvement.scorecard] Supabase unavailable: %s", exc)
        return None


def _log_decision(statement: str, rationale: str, owner: str) -> bool:
    try:
        sys.path.insert(0, str(_BOT))
        from command_memory_integration import log_decision_to_command_memory
        return bool(log_decision_to_command_memory(statement=statement, rationale=rationale, owner=owner))
    except Exception as exc:
        log.warning("[improvement.scorecard] Decision log failed: %s", exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def create_scorecard(
    mission_id: str,
    officer: str,
    baseline_state: str,
    target_state: str,
) -> bool:
    """Create a scorecard at improvement mission start.

    Records baseline and target states in Command Memory.
    Must be called when the mission is created.

    Args:
        mission_id:     The [IMPROVE] mission ID
        officer:        Officer who originated the improvement
        baseline_state: Observable description of the current state before improvement
        target_state:   Observable description of the expected state after improvement

    Returns:
        True if scorecard was created successfully.
    """
    if not baseline_state or not target_state:
        log.warning("[improvement.scorecard] baseline_state and target_state are required for %s", mission_id)
        return False

    scorecard = ImprovementScorecard(
        mission_id=mission_id,
        officer=officer,
        baseline_state=baseline_state,
        target_state=target_state,
    )

    return _log_decision(
        statement=f"{_CREATED_PREFIX}{mission_id}",
        rationale=scorecard.to_rationale_text(),
        owner=f"{_OWNER_PREFIX}{mission_id}",
    )


def complete_scorecard(
    mission_id: str,
    officer: str,
    actual_state: str,
    outcome: ValidationOutcome,
    what_changed: str,
    what_improved: str,
    what_did_not_improve: str = "",
    expected_benefit_realised: bool = True,
    should_expand: bool = False,
    should_reverse: bool = False,
    metrics: ImprovementMetrics | None = None,
) -> bool:
    """Complete a scorecard at improvement mission closure.

    Records actual state and outcome. Validates the six required questions.
    Must be called before a mission can be marked complete.

    Args:
        mission_id:                 The [IMPROVE] mission ID
        officer:                    Officer validating the outcome
        actual_state:               What the state looks like after implementation
        outcome:                    ValidationOutcome enum value
        what_changed:               Concrete description of what was changed
        what_improved:              Observable improvement
        what_did_not_improve:       Honest assessment of what didn't change
        expected_benefit_realised:  Was the expected benefit delivered?
        should_expand:              Should this improvement be widened?
        should_reverse:             Should this improvement be withdrawn?
        metrics:                    Quantitative benefit metrics (optional)

    Returns:
        True if scorecard completion was recorded successfully.
    """
    if not actual_state or not what_changed or not what_improved:
        log.warning(
            "[improvement.scorecard] actual_state, what_changed, what_improved are required for %s",
            mission_id,
        )
        return False

    scorecard = ImprovementScorecard(
        mission_id=mission_id,
        officer=officer,
        baseline_state="(see CREATED record)",
        target_state="(see CREATED record)",
        actual_state=actual_state,
        outcome=outcome,
        what_changed=what_changed,
        what_improved=what_improved,
        what_did_not_improve=what_did_not_improve or "Not assessed",
        expected_benefit_realised=expected_benefit_realised,
        should_expand=should_expand,
        should_reverse=should_reverse,
        metrics=metrics or ImprovementMetrics(),
        validated_at=datetime.utcnow(),
    )

    success = _log_decision(
        statement=f"{_COMPLETED_PREFIX}{mission_id}",
        rationale=scorecard.to_rationale_text(),
        owner=f"{_OWNER_PREFIX}{mission_id}",
    )

    if success and should_reverse:
        log.warning(
            "[improvement.scorecard] REVERSAL recommended for mission %s — "
            "surface to Number One and XO",
            mission_id,
        )

    return success


def get_scorecard(mission_id: str) -> ImprovementScorecard | None:
    """Retrieve the scorecard for a mission.

    Fetches both CREATED and COMPLETED decisions and merges them.
    Returns None if no scorecard found.
    """
    c = _client()
    if c is None:
        return None

    try:
        res = c.raw_client.table("decisions").select(
            "statement,rationale,created_at"
        ).like("owner", f"{_OWNER_PREFIX}{mission_id}").execute()

        rows = list(res.data or [])
        if not rows:
            return None

        created_row   = next((r for r in rows if r["statement"].startswith(_CREATED_PREFIX)), None)
        completed_row = next((r for r in rows if r["statement"].startswith(_COMPLETED_PREFIX)), None)

        if not created_row:
            return None

        scorecard = _parse_rationale(mission_id, created_row["rationale"])
        scorecard.created_at = datetime.fromisoformat(
            created_row["created_at"].rstrip("Z")
        ) if created_row.get("created_at") else datetime.utcnow()

        if completed_row:
            completed = _parse_rationale(mission_id, completed_row["rationale"])
            scorecard.actual_state = completed.actual_state
            scorecard.outcome      = completed.outcome
            scorecard.what_changed = completed.what_changed
            scorecard.what_improved = completed.what_improved
            scorecard.what_did_not_improve = completed.what_did_not_improve
            scorecard.expected_benefit_realised = completed.expected_benefit_realised
            scorecard.should_expand  = completed.should_expand
            scorecard.should_reverse = completed.should_reverse
            scorecard.metrics = completed.metrics
            if completed_row.get("created_at"):
                scorecard.validated_at = datetime.fromisoformat(
                    completed_row["created_at"].rstrip("Z")
                )

        return scorecard
    except Exception as exc:
        log.warning("[improvement.scorecard] Retrieval failed for %s: %s", mission_id, exc)
        return None


def _parse_rationale(mission_id: str, rationale: str) -> ImprovementScorecard:
    """Parse scorecard fields from rationale text (key:value | ... format)."""
    scorecard = ImprovementScorecard(
        mission_id=mission_id,
        officer="unknown",
        baseline_state="",
        target_state="",
    )
    metrics = ImprovementMetrics()

    for part in rationale.split(" | "):
        if ": " not in part:
            continue
        key, _, val = part.partition(": ")
        key = key.strip().upper()
        val = val.strip()

        match key:
            case "BASELINE":  scorecard.baseline_state = val
            case "TARGET":    scorecard.target_state   = val
            case "ACTUAL":    scorecard.actual_state   = val
            case "OUTCOME":
                try:
                    scorecard.outcome = ValidationOutcome(val.lower())
                except ValueError:
                    pass
            case "CHANGED":       scorecard.what_changed            = val
            case "IMPROVED":      scorecard.what_improved           = val
            case "NOT_IMPROVED":  scorecard.what_did_not_improve    = val
            case "BENEFIT_REALISED":
                scorecard.expected_benefit_realised = val.lower() == "true"
            case "EXPAND":   scorecard.should_expand  = val.lower() == "true"
            case "REVERSE":  scorecard.should_reverse = val.lower() == "true"
            case "METRICS":  metrics.time_saved = val  # simplified: store raw text

    scorecard.metrics = metrics
    return scorecard


def get_outcomes_report(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve completed scorecard outcomes for executive reporting."""
    c = _client()
    if c is None:
        return []
    try:
        res = c.raw_client.table("decisions").select(
            "statement,rationale,owner,created_at"
        ).like("statement", f"{_COMPLETED_PREFIX}%").order(
            "created_at", desc=True
        ).limit(limit).execute()

        return list(res.data or [])
    except Exception as exc:
        log.warning("[improvement.scorecard] Outcomes report failed: %s", exc)
        return []


def format_scorecard_summary(scorecard: ImprovementScorecard) -> str:
    """Format a scorecard as a Slack-ready summary."""
    outcome_icon = {
        ValidationOutcome.SUCCESSFUL:           ":white_check_mark:",
        ValidationOutcome.PARTIAL:              ":large_yellow_circle:",
        ValidationOutcome.FAILED:               ":x:",
        ValidationOutcome.REVERSAL_RECOMMENDED: ":warning:",
    }.get(scorecard.outcome, ":white_circle:")

    lines = [
        f"*Improvement Scorecard* — `{scorecard.mission_id}`",
        f"*Outcome:* {outcome_icon} {scorecard.outcome_label}",
        f"*Baseline:* {scorecard.baseline_state}",
        f"*Target:*   {scorecard.target_state}",
    ]
    if scorecard.actual_state:
        lines.append(f"*Actual:*   {scorecard.actual_state}")
    if scorecard.what_improved:
        lines.append(f"*What improved:* {scorecard.what_improved}")
    if scorecard.what_did_not_improve:
        lines.append(f"*What didn't:*   {scorecard.what_did_not_improve}")
    if not scorecard.metrics.is_empty():
        lines.append(f"*Metrics:* {scorecard.metrics.to_text()}")
    if scorecard.should_reverse:
        lines.append(":warning: *Reversal recommended* — surface to XO")
    if scorecard.should_expand:
        lines.append(":arrows_clockwise: *Expansion recommended* — create follow-on mission")

    return "\n".join(lines)


__all__ = [
    "ValidationOutcome",
    "ImprovementMetrics",
    "ImprovementScorecard",
    "create_scorecard",
    "complete_scorecard",
    "get_scorecard",
    "get_outcomes_report",
    "format_scorecard_summary",
]
