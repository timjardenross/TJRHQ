"""Initiative Reviews, Strategic Outcomes Dashboard & Executive Strategic Review
(EXEC-006 WP6 / WP7 / WP9).

WP6 — Evidence-based initiative reviews: What changed? What improved? What
failed? What was learned? Continue / pivot / stop?

WP7 — Strategic Outcomes Dashboard layer: surface progress (objectives,
initiatives, health, outcome trends, strategic risks/opportunities) rather than
operational activity.

WP9 — Executive Strategic Review: recurring (monthly) strategic review package
for Captain / XO / Number One / Strategic Planning.

Principle: the Captain should see progress, not simply activity.

Reuse: initiatives, outcomes, alignment, portfolio_intelligence, objectives,
learning brief. No new tables.

Storage (initiative review records, decisions table):
  statement = "[INITIATIVE REVIEW] {init_id}: {recommendation}"
  owner     = "initiative_review:{init_id}"

Public API:
    InitiativeReview, StrategicDashboard, ExecutiveStrategicReview
    review_initiative(init_id, inputs)        -> InitiativeReview | None
    build_strategic_dashboard(inputs)         -> StrategicDashboard
    run_executive_strategic_review(inputs)    -> ExecutiveStrategicReview
    format_strategic_dashboard(dashboard)     -> str
    format_executive_review(review)           -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import (
    Initiative, InitiativeHealth, get_initiative, list_initiatives,
)
from lib.strategy.outcomes import assess_health, get_outcome_history, HealthAssessment
from lib.strategy.portfolio_intelligence import (
    recommend_for_initiative, recommend_all, analyse_portfolio,
    InitiativeRecommendation, Recommendation,
)
from lib.strategy.initiative_alignment import run_alignment_scan, AlignmentReport

_REVIEW_OWNER_PREFIX = "initiative_review:"
_REVIEW_STATEMENT    = "[INITIATIVE REVIEW]"


# ── WP6: Initiative review ────────────────────────────────────────────────────

@dataclass
class InitiativeReview:
    initiative_id: str
    title: str
    what_changed: str
    what_improved: str
    what_failed: str
    what_was_learned: str
    recommendation: Recommendation
    health: InitiativeHealth
    should_continue: bool
    should_pivot: bool
    should_stop: bool
    reviewed_at: datetime = field(default_factory=datetime.utcnow)


def review_initiative(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> InitiativeReview | None:
    """Produce an evidence-based review package for one initiative (WP6)."""
    init = get_initiative(initiative_id)
    if init is None:
        return None

    assessment: HealthAssessment = assess_health(init, inputs=inputs)
    rec: InitiativeRecommendation = recommend_for_initiative(init, inputs)
    history = get_outcome_history(initiative_id)

    # What changed — movement from baseline to current
    if init.baseline and init.current and init.baseline != init.current:
        what_changed = f"Outcome moved from '{init.baseline}' to '{init.current}'."
    elif history:
        what_changed = f"{len(history)} outcome measurement(s) recorded."
    else:
        what_changed = "No measured outcome change yet."

    # What improved / failed
    prog = assessment.progress
    if prog.progress_pct is not None and prog.progress_pct > 0:
        what_improved = f"{prog.progress_label} ({assessment.trend.value})."
    else:
        what_improved = "No measurable improvement toward target."
    what_failed = "; ".join(assessment.risk_flags) if assessment.risk_flags else "No notable failures."

    # What was learned — pull lesson candidates referencing linked work, else generic
    what_learned = _learning_note(init)

    return InitiativeReview(
        initiative_id=initiative_id,
        title=init.title,
        what_changed=what_changed,
        what_improved=what_improved,
        what_failed=what_failed,
        what_was_learned=what_learned,
        recommendation=rec.recommendation,
        health=assessment.health,
        should_continue=rec.recommendation in (Recommendation.CONTINUE, Recommendation.ACCELERATE),
        should_pivot=rec.recommendation in (Recommendation.PAUSE, Recommendation.MERGE),
        should_stop=rec.recommendation == Recommendation.STOP,
    )


def _learning_note(init: Initiative) -> str:
    try:
        from lib.learning.lessons import get_lesson_candidates
        cands = get_lesson_candidates(limit=20, pending_only=False)
        relevant = [c for c in cands if init.objective_id and init.objective_id in (c.context or "")]
        if relevant:
            return f"{len(relevant)} lesson(s) linked to this objective."
    except Exception:
        pass
    return "No specific lessons captured yet."


def persist_initiative_review(review: InitiativeReview) -> bool:
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"{_REVIEW_STATEMENT} {review.initiative_id}: {review.recommendation.value}",
            rationale=(
                f"HEALTH: {review.health.value} | REC: {review.recommendation.value} | "
                f"CHANGED: {review.what_changed[:80]} | IMPROVED: {review.what_improved[:80]} | "
                f"FAILED: {review.what_failed[:80]} | LEARNED: {review.what_was_learned[:80]}"
            ),
            owner=f"{_REVIEW_OWNER_PREFIX}{review.initiative_id}",
        )
        return True
    except Exception as exc:
        log.debug("[strategy.review] persist_initiative_review failed: %s", exc)
        return False


# ── WP7: Strategic Outcomes Dashboard ─────────────────────────────────────────

@dataclass
class StrategicDashboard:
    objectives: list[dict] = field(default_factory=list)
    initiatives: list[Initiative] = field(default_factory=list)
    health_summary: dict[str, int] = field(default_factory=dict)   # green/amber/red counts
    outcome_trends: list[dict] = field(default_factory=list)
    strategic_risks: list[str] = field(default_factory=list)
    strategic_opportunities: list[str] = field(default_factory=list)
    alignment: AlignmentReport | None = None
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_initiatives(self) -> int:
        return len(self.initiatives)


def build_strategic_dashboard(inputs: dict[str, Any] | None = None) -> StrategicDashboard:
    """Assemble the strategic outcomes dashboard (progress, not activity)."""
    inputs = inputs or {}
    dash = StrategicDashboard()

    dash.initiatives = list_initiatives(include_closed=False)

    # Health summary + outcome trends
    counts = {"green": 0, "amber": 0, "red": 0, "unknown": 0}
    for init in dash.initiatives:
        assessment = assess_health(init, inputs=inputs)
        counts[assessment.health.value] = counts.get(assessment.health.value, 0) + 1
        dash.outcome_trends.append({
            "initiative_id": init.initiative_id,
            "title": init.title,
            "health": assessment.health.value,
            "trend": assessment.trend.value,
            "progress": assessment.progress.progress_label,
        })
        if assessment.health == InitiativeHealth.RED:
            dash.strategic_risks.append(f"{init.title[:60]} off track ({assessment.rationale})")
        if assessment.health == InitiativeHealth.GREEN and assessment.trend.value == "improving":
            dash.strategic_opportunities.append(f"{init.title[:60]} improving — candidate to accelerate")
    dash.health_summary = counts

    # Objectives snapshot (reuse existing strategy module)
    try:
        from lib.strategy.objectives import fetch_snapshot
        snap = fetch_snapshot()
        dash.objectives = [
            {"objective_id": o.objective_id, "title": o.title, "domain": o.domain,
             "priority": o.priority, "progress": o.progress_label()}
            for o in snap.active[:10]
        ]
    except Exception as exc:
        log.debug("[strategy.review] objective snapshot failed: %s", exc)

    # Alignment
    try:
        dash.alignment = run_alignment_scan()
    except Exception as exc:
        log.debug("[strategy.review] alignment scan failed: %s", exc)

    return dash


# ── WP9: Executive Strategic Review ───────────────────────────────────────────

@dataclass
class ExecutiveStrategicReview:
    strategic_progress: str
    health_summary: dict[str, int]
    outcome_achievement: str
    key_learnings: str
    recommended_changes: list[InitiativeRecommendation]
    emerging_risks: list[str]
    emerging_opportunities: list[str]
    portfolio_note: str
    generated_at: datetime = field(default_factory=datetime.utcnow)


def run_executive_strategic_review(inputs: dict[str, Any] | None = None) -> ExecutiveStrategicReview:
    """Produce the recurring executive strategic review package (WP9)."""
    inputs = inputs or {}
    dash = build_strategic_dashboard(inputs)
    recs = recommend_all(inputs)
    portfolio = analyse_portfolio()

    green = dash.health_summary.get("green", 0)
    total = max(dash.total_initiatives, 1)
    strategic_progress = (
        f"{green}/{dash.total_initiatives} initiatives on track "
        f"({round(green / total * 100)}%). "
        f"{len(dash.strategic_risks)} off-track, {len(dash.strategic_opportunities)} accelerate candidate(s)."
    )

    achieved = [t for t in dash.outcome_trends if "100%" in t.get("progress", "")]
    outcome_achievement = (
        f"{len(achieved)} initiative(s) hit target outcome; "
        f"{len(portfolio.weak_outcome_initiatives)} weak-outcome initiative(s) flagged."
    )

    # Key learnings via the EXEC-005 learning brief
    key_learnings = "No learning summary available."
    try:
        from lib.learning.learning_brief import assemble_learning_brief
        lb = assemble_learning_brief(None)
        bits = []
        if lb.patterns:
            bits.append(f"{len(lb.patterns)} recurring pattern(s)")
        if lb.lesson_candidates_pending:
            bits.append(f"{lb.lesson_candidates_pending} lesson candidate(s)")
        if lb.knowledge_quality:
            bits.append(f"knowledge {lb.knowledge_quality.grade}")
        if bits:
            key_learnings = "; ".join(bits) + "."
    except Exception as exc:
        log.debug("[strategy.review] learning brief failed: %s", exc)

    disinvest = [r for r in recs if r.is_disinvestment]
    portfolio_note = (
        f"{portfolio.total_initiatives} initiatives; "
        f"{len(disinvest)} recommended for stop/pause/merge; "
        f"{len(portfolio.strong_outcome_initiatives)} strong performer(s)."
    )

    return ExecutiveStrategicReview(
        strategic_progress=strategic_progress,
        health_summary=dash.health_summary,
        outcome_achievement=outcome_achievement,
        key_learnings=key_learnings,
        recommended_changes=recs,
        emerging_risks=dash.strategic_risks,
        emerging_opportunities=dash.strategic_opportunities,
        portfolio_note=portfolio_note,
    )


# ── Formatting ────────────────────────────────────────────────────────────────

def format_strategic_dashboard(dash: StrategicDashboard) -> str:
    if not dash.initiatives:
        return "*Strategic Outcomes:* _No initiatives defined yet._"
    hs = dash.health_summary
    lines = [
        "*:dart: STRATEGIC OUTCOMES*",
        f"  Initiatives: {dash.total_initiatives} "
        f"(:large_green_circle:{hs.get('green',0)} :large_yellow_circle:{hs.get('amber',0)} :red_circle:{hs.get('red',0)})",
    ]
    if dash.objectives:
        lines.append(f"  Active objectives: {len(dash.objectives)}")
    # Show a few outcome trends
    for t in dash.outcome_trends[:4]:
        icon = {"green": ":large_green_circle:", "amber": ":large_yellow_circle:", "red": ":red_circle:"}.get(t["health"], ":white_circle:")
        lines.append(f"    {icon} {t['title'][:50]} — {t['progress']} ({t['trend']})")
    if dash.strategic_risks:
        lines.append(f"  :rotating_light: Strategic risks: {len(dash.strategic_risks)}")
    if dash.strategic_opportunities:
        lines.append(f"  :sparkles: Accelerate candidates: {len(dash.strategic_opportunities)}")
    if dash.alignment:
        lines.append(f"  Alignment: {dash.alignment.coverage_pct:.0%} mission coverage")
    return "\n".join(lines)


def format_executive_review(review: ExecutiveStrategicReview) -> str:
    lines = [
        "*:scroll: EXECUTIVE STRATEGIC REVIEW*",
        "",
        f"*Strategic progress:* {review.strategic_progress}",
        f"*Outcome achievement:* {review.outcome_achievement}",
        f"*Key learnings:* {review.key_learnings}",
        f"*Portfolio:* {review.portfolio_note}",
    ]
    disinvest = [r for r in review.recommended_changes if r.is_disinvestment]
    if disinvest:
        lines.append("\n*Recommended stop / pause / merge:*")
        for r in disinvest[:5]:
            lines.append(f"  :octagonal_sign: *{r.recommendation.value.upper()}* {r.title[:55]} — {r.rationale}")
    accelerate = [r for r in review.recommended_changes if r.recommendation == Recommendation.ACCELERATE]
    if accelerate:
        lines.append("\n*Recommended accelerate:*")
        for r in accelerate[:3]:
            lines.append(f"  :fast_forward: {r.title[:55]} — {r.rationale}")
    if review.emerging_risks:
        lines.append(f"\n*Emerging strategic risks:* {len(review.emerging_risks)}")
        for r in review.emerging_risks[:3]:
            lines.append(f"  • {r}")
    if review.emerging_opportunities:
        lines.append(f"\n*Emerging strategic opportunities:* {len(review.emerging_opportunities)}")
        for o in review.emerging_opportunities[:3]:
            lines.append(f"  • {o}")
    return "\n".join(lines)


__all__ = [
    "InitiativeReview",
    "StrategicDashboard",
    "ExecutiveStrategicReview",
    "review_initiative",
    "persist_initiative_review",
    "build_strategic_dashboard",
    "run_executive_strategic_review",
    "format_strategic_dashboard",
    "format_executive_review",
]
