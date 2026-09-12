"""Executive Learning Brief (EXEC-005 WP10).

Separates learning from operational reporting. The Captain should understand:
  what happened, what was learned, and what should change.

This brief is distinct from the operational Captain brief (exception_router).
It surfaces:
  - What the ship learned (lessons generated)
  - Cross-domain findings
  - Knowledge gaps
  - Emerging opportunities
  - Patterns identified
  - Reuse opportunities
  - Decision-quality insights

Reuse: aggregates the EXEC-005 learning modules. No new storage.

Public API:
    LearningBrief
    assemble_learning_brief(ctx) -> LearningBrief
    format_learning_brief(brief) -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass
class LearningBrief:
    lessons_generated: int = 0
    lesson_candidates_pending: int = 0
    patterns: list[Any] = field(default_factory=list)            # OrganisationalPattern
    cross_domain_opportunities: list[Any] = field(default_factory=list)  # CrossDomainOpportunity
    knowledge_quality: Any = None                                 # KnowledgeQualityScore
    collaborative_investigations: int = 0
    high_confidence_findings: int = 0
    decision_quality_note: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_content(self) -> bool:
        return any([
            self.lessons_generated,
            self.lesson_candidates_pending,
            self.patterns,
            self.cross_domain_opportunities,
            self.knowledge_quality is not None,
            self.collaborative_investigations,
        ])


def assemble_learning_brief(ctx: Any = None) -> LearningBrief:
    """Assemble the executive learning brief from the learning modules.

    Fully non-blocking — each section degrades independently.
    """
    brief = LearningBrief()

    # Lesson candidates pending review
    try:
        from lib.learning.lessons import get_lesson_candidates
        candidates = get_lesson_candidates(limit=50, pending_only=True)
        brief.lesson_candidates_pending = len(candidates)
        brief.lessons_generated = len([c for c in candidates if c.confidence >= 0.6])
    except Exception as exc:
        log.debug("[learning.brief] Lessons section failed: %s", exc)

    # Patterns
    try:
        from lib.learning.patterns import detect_patterns
        brief.patterns = detect_patterns(lookback_days=30)
    except Exception as exc:
        log.debug("[learning.brief] Patterns section failed: %s", exc)

    # Cross-domain opportunities
    try:
        if ctx is not None:
            from lib.learning.cross_domain import detect_cross_domain_opportunities
            brief.cross_domain_opportunities = detect_cross_domain_opportunities(ctx)
    except Exception as exc:
        log.debug("[learning.brief] Cross-domain section failed: %s", exc)

    # Knowledge quality
    try:
        from lib.learning.knowledge_quality import compute_knowledge_quality
        brief.knowledge_quality = compute_knowledge_quality()
    except Exception as exc:
        log.debug("[learning.brief] Knowledge quality section failed: %s", exc)

    # Collaboration + decision-quality signals from ctx
    try:
        if ctx is not None:
            brief.collaborative_investigations = int(getattr(ctx, "collaborative_investigations", 0) or 0)
            brief.high_confidence_findings = len(getattr(ctx, "high_confidence_findings", []) or [])
    except Exception:
        pass

    # Decision-quality insight
    brief.decision_quality_note = _decision_quality_note(brief)

    log.info(
        "[learning.brief] Assembled: %d patterns, %d cross-domain, %d lesson candidates, KQ=%s",
        len(brief.patterns), len(brief.cross_domain_opportunities),
        brief.lesson_candidates_pending,
        brief.knowledge_quality.grade if brief.knowledge_quality else "n/a",
    )
    return brief


def _decision_quality_note(brief: LearningBrief) -> str:
    """Produce a one-line decision-quality insight."""
    notes: list[str] = []
    if brief.collaborative_investigations:
        notes.append(f"{brief.collaborative_investigations} investigation(s) ran multi-officer")
    if brief.high_confidence_findings:
        notes.append(f"{brief.high_confidence_findings} high-confidence finding(s)")
    if brief.patterns:
        high_sev = [p for p in brief.patterns if getattr(p, "severity", "") == "HIGH"]
        if high_sev:
            notes.append(f"{len(high_sev)} high-severity recurring pattern(s) — repeated-mistake risk")
    if not notes:
        return "Insufficient signal to assess decision quality this cycle."
    return "; ".join(notes) + "."


def format_learning_brief(brief: LearningBrief) -> str:
    """Format the executive learning brief as a Slack-ready section."""
    if not brief.has_content:
        return "*Executive Learning Brief:* _No new learning this cycle._"

    lines = ["*:books: EXECUTIVE LEARNING BRIEF*", ""]

    # What the ship learned
    lines.append("*What the ship learned:*")
    if brief.lesson_candidates_pending:
        lines.append(
            f"  {brief.lesson_candidates_pending} lesson candidate(s) generated "
            f"({brief.lessons_generated} high-confidence) — pending Knowledge review."
        )
    else:
        lines.append("  No new lessons captured this cycle.")

    # Patterns identified
    if brief.patterns:
        lines.append("\n*Patterns identified:*")
        for p in brief.patterns[:4]:
            lines.append(f"  [{p.severity}] {p.label}: {p.occurrences}× / {p.window_days}d")

    # Cross-domain findings / emerging opportunities
    if brief.cross_domain_opportunities:
        lines.append("\n*Emerging cross-domain opportunities:*")
        for o in brief.cross_domain_opportunities[:3]:
            lines.append(f"  [{o.confidence_label}] {o.title} ({' + '.join(o.domains)})")

    # Knowledge quality / gaps
    if brief.knowledge_quality:
        kq = brief.knowledge_quality
        lines.append(f"\n*Knowledge health:* {kq.grade} ({kq.composite:.0%})")
        # Surface the weakest dimension as a "gap"
        dims = {
            "ADR coverage": kq.adr_coverage,
            "Decision rationale": kq.decision_rationale_coverage,
            "Lesson coverage": kq.lesson_coverage,
            "Mission outcomes": kq.mission_outcome_coverage,
            "Knowledge reuse": kq.knowledge_reuse_rate,
            "Doc freshness": kq.documentation_freshness,
        }
        weakest = min(dims, key=dims.get)
        lines.append(f"  Largest gap: {weakest} ({dims[weakest]:.0%})")

    # Decision-quality insight
    if brief.decision_quality_note:
        lines.append(f"\n*Decision-quality insight:* {brief.decision_quality_note}")

    return "\n".join(lines)


__all__ = [
    "LearningBrief",
    "assemble_learning_brief",
    "format_learning_brief",
]
