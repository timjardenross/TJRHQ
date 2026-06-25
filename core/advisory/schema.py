"""Advisory Response Standard — USS-TJR-MSN-0092 WP4.

A single, shared response shape for ALL advisory outputs across every officer
and every interface (Slack, Telegram, Portal, XO, Number One). This is the
"common structure" mandated by WP4 so advisory outputs are consistent.

The seven standard sections:

    1. Executive Summary
    2. Recommendation
    3. Historical Evidence
    4. Related Lessons
    5. Risks and Challenges
    6. Confidence Level
    7. Officer Perspectives

Design principles (inherited from the mission guiding principles):
    - Evidence before opinion: evidence/lessons are first-class fields, not prose.
    - Multiple perspectives before single recommendations: officer_perspectives
      is always populated when more than one officer participated.
    - Advisory authority only: every rendered response carries the advisory note
      and never implies autonomous action.

This module is pure data + formatting. It has NO heavy dependencies and is safe
to import anywhere (interfaces, tests, services).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


ADVISORY_AUTHORITY_NOTE = (
    "Advisory only — Captain TJR retains final decision authority. "
    "No autonomous action is taken from this output."
)


# ---------------------------------------------------------------------------
# Sub-structures
# ---------------------------------------------------------------------------

@dataclass
class OfficerPerspective:
    """One officer/specialist viewpoint within an advisory response."""

    officer: str
    recommendation: str
    confidence: int = 0           # 0–100
    stance: str = ""              # e.g. "supports", "challenges", "neutral"
    reasoning: str = ""           # short rationale / retrieved perspective
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceItem:
    """A single piece of historical evidence supporting (or cautioning) advice."""

    kind: str                     # "historical_outcome" | "similar_mission" | "decision"
    reference: str                # mission id, decision id, or metric label
    detail: str                   # human-readable explanation
    outcome_score: Optional[float] = None   # 0.0–1.0 where available

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LessonRef:
    """A reference to a captured lesson relevant to the question."""

    lesson_id: str
    title: str
    guidance: str = ""
    mission_id: str = ""
    relevance: int = 0            # keyword-overlap relevance score

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RelatedDecision:
    """A prior decision related to the current question (institutional recall)."""

    decision_id: str
    question: str
    recommended_action: str = ""
    outcome: str = ""             # "success" | "failure" | "partial" | "pending" | ""
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfidenceLevel:
    """Confidence in the recommendation, with the basis for that confidence."""

    value: float                  # 0.0–1.0
    band: str                     # "High" | "Medium" | "Low"
    basis: str = ""               # why this confidence (evidence quality etc.)

    @staticmethod
    def from_value(value: float, basis: str = "") -> "ConfidenceLevel":
        value = max(0.0, min(1.0, round(value, 3)))
        if value >= 0.75:
            band = "High"
        elif value >= 0.5:
            band = "Medium"
        else:
            band = "Low"
        return ConfidenceLevel(value=value, band=band, basis=basis)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Top-level advisory response
# ---------------------------------------------------------------------------

@dataclass
class AdvisoryResponse:
    """The standard advisory output (WP4). All interfaces render from this."""

    question: str
    executive_summary: str = ""
    recommendation: str = ""
    historical_evidence: list[EvidenceItem] = field(default_factory=list)
    related_lessons: list[LessonRef] = field(default_factory=list)
    risks_and_challenges: list[str] = field(default_factory=list)
    confidence: ConfidenceLevel = field(
        default_factory=lambda: ConfidenceLevel.from_value(0.5)
    )
    officer_perspectives: list[OfficerPerspective] = field(default_factory=list)

    # Metadata (not one of the seven sections, but carried for traceability)
    related_decisions: list[RelatedDecision] = field(default_factory=list)
    decision_mode: str = ""
    reviewer: Optional[str] = None
    escalation_required: bool = False
    disagreement: str = ""        # explicit surfaced disagreement, if any
    sources: list[str] = field(default_factory=list)
    degraded: bool = False        # True when live retrieval/LLM was unavailable
    advisory_note: str = ADVISORY_AUTHORITY_NOTE
    generated_at: str = ""
    raw_synthesis: str = ""       # underlying Commander synthesis (for audit)
    advisory_id: str = ""         # set when the advice is recorded for outcome tracking
    learning_note: str = ""       # closed-loop signal from prior outcomes (MSN-0093)

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "executive_summary": self.executive_summary,
            "recommendation": self.recommendation,
            "historical_evidence": [e.to_dict() for e in self.historical_evidence],
            "related_lessons": [l.to_dict() for l in self.related_lessons],
            "risks_and_challenges": list(self.risks_and_challenges),
            "confidence": self.confidence.to_dict(),
            "officer_perspectives": [o.to_dict() for o in self.officer_perspectives],
            "related_decisions": [d.to_dict() for d in self.related_decisions],
            "decision_mode": self.decision_mode,
            "reviewer": self.reviewer,
            "escalation_required": self.escalation_required,
            "disagreement": self.disagreement,
            "sources": list(self.sources),
            "degraded": self.degraded,
            "advisory_note": self.advisory_note,
            "generated_at": self.generated_at,
            "advisory_id": self.advisory_id,
            "learning_note": self.learning_note,
        }

    # -- rendering ----------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the seven-section standard as plain GitHub-flavoured markdown."""
        L: list[str] = []
        L.append(f"# Advisory — {self.question.strip()}")
        if self.decision_mode:
            L.append(f"_Decision mode: {self.decision_mode}_")
        L.append("")

        L.append("## 1. Executive Summary")
        L.append(self.executive_summary or "_No summary available._")
        L.append("")

        L.append("## 2. Recommendation")
        L.append(self.recommendation or "_No recommendation produced._")
        L.append("")

        L.append("## 3. Historical Evidence")
        if self.historical_evidence:
            for e in self.historical_evidence:
                score = f" ({int(e.outcome_score * 100)}%)" if e.outcome_score is not None else ""
                L.append(f"- **{e.reference}**{score} — {e.detail}")
        else:
            L.append("- No historical evidence matched this question.")
        if self.related_decisions:
            L.append("")
            L.append("**Related decisions:**")
            for d in self.related_decisions:
                tag = f" [{d.outcome}]" if d.outcome else ""
                L.append(f"- `{d.decision_id}`{tag} — {d.question}")
        L.append("")

        L.append("## 4. Related Lessons")
        if self.related_lessons:
            for l in self.related_lessons:
                guidance = f" — {l.guidance}" if l.guidance else ""
                L.append(f"- **{l.lesson_id}: {l.title}**{guidance}")
        else:
            L.append("- No prior lessons matched this question.")
        L.append("")

        L.append("## 5. Risks and Challenges")
        if self.risks_and_challenges:
            for r in self.risks_and_challenges:
                L.append(f"- {r}")
        else:
            L.append("- No specific risks identified.")
        if self.disagreement:
            L.append("")
            L.append(f"**Disagreement surfaced:** {self.disagreement}")
        L.append("")

        L.append("## 6. Confidence Level")
        basis = f" — {self.confidence.basis}" if self.confidence.basis else ""
        L.append(f"**{self.confidence.band}** ({int(self.confidence.value * 100)}%){basis}")
        if self.learning_note:
            L.append(f"_Learning signal: {self.learning_note}_")
        if self.escalation_required:
            L.append("")
            L.append("> ⚠ Escalation recommended — Captain decision advised before proceeding.")
        L.append("")

        L.append("## 7. Officer Perspectives")
        if self.officer_perspectives:
            for o in self.officer_perspectives:
                stance = f" _{o.stance}_" if o.stance else ""
                L.append(f"- **{o.officer}** ({o.confidence}%){stance}: {o.recommendation}")
        else:
            L.append("- Single-officer advisory (no panel).")
        L.append("")

        L.append(f"---\n_{self.advisory_note}_")
        if self.advisory_id:
            L.append(f"_Advisory ref: {self.advisory_id} — close the loop with "
                     f"`/advisory-outcome {self.advisory_id} <success|failure|partial>`._")
        if self.degraded:
            L.append("_Note: produced in degraded mode — live retrieval/LLM was unavailable._")
        return "\n".join(L)

    def to_slack_mrkdwn(self) -> str:
        """Render for Slack (single asterisks for bold, trimmed length)."""
        md = self.to_markdown()
        # Slack uses *bold* not **bold**, and # headings render poorly.
        md = md.replace("**", "*")
        out_lines = []
        for line in md.splitlines():
            if line.startswith("# "):
                out_lines.append(f"*{line[2:]}*")
            elif line.startswith("## "):
                out_lines.append(f"*{line[3:]}*")
            else:
                out_lines.append(line)
        text = "\n".join(out_lines)
        # Slack hard limit safety
        if len(text) > 2900:
            text = text[:2900] + "\n… _(truncated; full response in audit log)_"
        return text
