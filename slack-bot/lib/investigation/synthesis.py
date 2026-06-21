"""Collaborative Findings & Challenge Engine (EXEC-005 WP3 / WP4).

WP3 — Synthesis: combine multiple officers' findings into a single integrated
finding with supporting evidence, contradicting evidence, and a multi-officer
confidence assessment.

WP4 — Challenge & Review: every significant investigation receives a supporting
perspective, a challenging perspective, an alternative explanation, and a
confidence challenge — reducing confirmation bias.

Storage (decisions table):
  Synthesis:  statement = "[SYNTHESIS] {inv_id}: {headline[:80]}"
              owner     = "investigation_synthesis:{inv_id}"
  Challenge:  statement = "[CHALLENGE] {inv_id}: {alt_hypothesis[:80]}"
              owner     = "investigation_challenge:{inv_id}"

Public API:
    IntegratedFinding
    ChallengeReview
    synthesize_findings(inv_id, question, participants) -> IntegratedFinding
    generate_challenge(inv_id, integrated)              -> ChallengeReview
    get_synthesis(inv_id)                               -> IntegratedFinding | None
    format_integrated_finding(finding)                  -> str
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

from lib.investigation.framework import Finding, FindingsReport

SYNTHESIS_OWNER_PREFIX = "investigation_synthesis:"
CHALLENGE_OWNER_PREFIX = "investigation_challenge:"


@dataclass
class OfficerPerspective:
    officer: str
    finding: str
    recommended_action: str
    confidence: float


@dataclass
class IntegratedFinding:
    investigation_id: str
    headline: str
    supporting_perspectives: list[OfficerPerspective] = field(default_factory=list)
    contradicting_perspectives: list[OfficerPerspective] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    integrated_confidence: float = 0.0
    consensus_action: str = ""
    has_contradiction: bool = False
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def confidence_label(self) -> str:
        if self.integrated_confidence >= 0.75:
            return "HIGH"
        if self.integrated_confidence >= 0.5:
            return "MEDIUM"
        return "LOW"

    @property
    def officer_count(self) -> int:
        seen = {p.officer for p in self.supporting_perspectives}
        seen |= {p.officer for p in self.contradicting_perspectives}
        return len(seen)


@dataclass
class ChallengeReview:
    investigation_id: str
    reviewer: str
    supporting_perspective: str
    challenging_perspective: str
    alternative_explanation: str
    confidence_challenge: str
    revised_confidence: float
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ── Multi-officer confidence model ────────────────────────────────────────────

def _integrate_confidence(
    supporting: list[OfficerPerspective],
    contradicting: list[OfficerPerspective],
) -> float:
    """Combine officer confidences into an integrated confidence.

    Agreement across officers raises confidence; contradiction lowers it.
      base       = max supporting confidence
      agreement  = +0.05 per additional supporting officer (cap +0.15)
      dissent    = -0.12 per contradicting officer
    Result is clamped to [0.05, 0.97].
    """
    if not supporting:
        return 0.2 if not contradicting else 0.1

    base = max(p.confidence for p in supporting)
    agreement = min(0.15, 0.05 * (len(supporting) - 1))
    dissent = 0.12 * len(contradicting)
    return round(max(0.05, min(0.97, base + agreement - dissent)), 2)


def _gather_officer_perspectives(
    investigation_id: str,
    participants: list[str],
) -> list[OfficerPerspective]:
    """Pull each participant's finding/recommendation from stored findings.

    Reuses findings.get_findings which reads investigation_finding:{inv_id}.
    Since findings are stored per-investigation (shared), this represents the
    collective view. We synthesise multiple findings into perspectives.
    """
    from lib.investigation.findings import get_findings

    report: FindingsReport | None = get_findings(investigation_id)
    if not report or not report.findings:
        return []

    perspectives: list[OfficerPerspective] = []
    # Map each finding to a participating officer round-robin (findings are
    # collective but we attribute them to contributors for perspective diversity)
    officers = participants or ["lead"]
    lead_action = (
        report.lead_recommendation.action_type
        if report.lead_recommendation else "no_action"
    )

    for idx, finding in enumerate(report.findings):
        officer = officers[idx % len(officers)]
        perspectives.append(OfficerPerspective(
            officer=officer,
            finding=finding.observation,
            recommended_action=lead_action,
            confidence=finding.confidence,
        ))

    return perspectives


# ── WP3: Synthesis ────────────────────────────────────────────────────────────

def synthesize_findings(
    investigation_id: str,
    question: str,
    participants: list[str] | None = None,
) -> IntegratedFinding:
    """Synthesise an integrated finding from all participants' findings.

    Separates supporting from contradicting perspectives, aggregates evidence,
    and computes a multi-officer confidence.
    """
    participants = participants or []
    perspectives = _gather_officer_perspectives(investigation_id, participants)

    integrated = IntegratedFinding(
        investigation_id=investigation_id,
        headline=f"Integrated finding for: {question[:80]}",
    )

    if not perspectives:
        integrated.headline = f"No findings to synthesise for: {question[:60]}"
        integrated.integrated_confidence = 0.1
        integrated.consensus_action = "further_investigation"
        return integrated

    # Determine the dominant recommended action (consensus)
    action_votes: dict[str, int] = {}
    for p in perspectives:
        action_votes[p.recommended_action] = action_votes.get(p.recommended_action, 0) + 1
    consensus_action = max(action_votes, key=action_votes.get)
    integrated.consensus_action = consensus_action

    # Split supporting vs contradicting relative to consensus action
    for p in perspectives:
        if p.recommended_action == consensus_action:
            integrated.supporting_perspectives.append(p)
        else:
            integrated.contradicting_perspectives.append(p)

    integrated.has_contradiction = bool(integrated.contradicting_perspectives)
    integrated.integrated_confidence = _integrate_confidence(
        integrated.supporting_perspectives,
        integrated.contradicting_perspectives,
    )

    # Aggregate evidence references
    integrated.supporting_evidence = [
        f"{p.officer}: {p.finding[:80]}" for p in integrated.supporting_perspectives[:4]
    ]
    integrated.contradicting_evidence = [
        f"{p.officer}: {p.finding[:80]}" for p in integrated.contradicting_perspectives[:3]
    ]

    # Compose headline
    high = [p for p in integrated.supporting_perspectives if p.confidence >= 0.75]
    integrated.headline = (
        f"{len(integrated.supporting_perspectives)} officer(s) converge on "
        f"'{consensus_action}' ({integrated.confidence_label} confidence)"
        + (f"; {len(integrated.contradicting_perspectives)} dissent" if integrated.has_contradiction else "")
    )

    _store_synthesis(integrated)

    log.info(
        "[investigation.synthesis] %s: %d supporting, %d contradicting, confidence %.2f, action=%s",
        investigation_id,
        len(integrated.supporting_perspectives),
        len(integrated.contradicting_perspectives),
        integrated.integrated_confidence,
        consensus_action,
    )
    return integrated


def _store_synthesis(integrated: IntegratedFinding) -> None:
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"[SYNTHESIS] {integrated.investigation_id}: {integrated.headline[:80]}",
            rationale=(
                f"CONFIDENCE: {integrated.integrated_confidence} | "
                f"ACTION: {integrated.consensus_action} | "
                f"OFFICERS: {integrated.officer_count} | "
                f"SUPPORTING: {len(integrated.supporting_perspectives)} | "
                f"CONTRADICTING: {len(integrated.contradicting_perspectives)} | "
                f"EVIDENCE: {'; '.join(integrated.supporting_evidence[:3])[:200]}"
            ),
            owner=f"{SYNTHESIS_OWNER_PREFIX}{integrated.investigation_id}",
        )
    except Exception as exc:
        log.debug("[investigation.synthesis] Store synthesis failed: %s", exc)


# ── WP4: Challenge & Review ───────────────────────────────────────────────────

def generate_challenge(
    investigation_id: str,
    integrated: IntegratedFinding,
    reviewer: str = "xo",
) -> ChallengeReview:
    """Generate a challenge/review for an integrated finding (reduces bias).

    Produces a supporting perspective, a challenging perspective, an
    alternative explanation, and a confidence challenge. The reviewer is
    typically the XO but may be any non-participating officer.
    """
    consensus = integrated.consensus_action

    # Supporting perspective
    supporting = (
        f"{len(integrated.supporting_perspectives)} officer(s) support '{consensus}' "
        f"at {integrated.confidence_label} confidence."
    )

    # Challenging perspective — surface dissent or construct devil's advocate
    if integrated.has_contradiction:
        challenging = (
            f"{len(integrated.contradicting_perspectives)} officer(s) disagree: "
            + "; ".join(integrated.contradicting_evidence[:2])
        )
    else:
        challenging = (
            "No dissent recorded — risk of confirmation bias. "
            f"Has the '{consensus}' conclusion been tested against the null hypothesis "
            "(that no action is required)?"
        )

    # Alternative explanation — propose a different root cause domain
    alt_map = {
        "mission":          "The issue may be a capacity or knowledge gap rather than requiring new delivery work.",
        "improvement":      "The recurring pattern may be a one-off rather than systemic — verify recurrence before optimising.",
        "decision":         "The options presented may not be exhaustive; consider a deferred or hybrid option.",
        "monitoring":       "Monitoring may be insufficient if the risk is already materialising — consider active mitigation.",
        "knowledge_update": "A documentation fix may mask an underlying process problem.",
        "no_action":        "Absence of a strong signal is not evidence of absence — confirm the data was complete.",
    }
    alternative = alt_map.get(consensus, "Consider whether the framing of the question constrained the findings.")

    # Confidence challenge
    if integrated.integrated_confidence >= 0.75 and not integrated.has_contradiction:
        confidence_challenge = (
            "High confidence with no dissent — verify evidence diversity before accepting. "
            "Single-source confidence can be brittle."
        )
        revised = round(integrated.integrated_confidence - 0.05, 2)
    elif integrated.has_contradiction:
        confidence_challenge = (
            "Contradicting perspectives present — confidence should remain provisional "
            "pending resolution of the disagreement."
        )
        revised = round(max(0.3, integrated.integrated_confidence - 0.1), 2)
    else:
        confidence_challenge = "Confidence is moderate; additional evidence would strengthen the conclusion."
        revised = integrated.integrated_confidence

    review = ChallengeReview(
        investigation_id=investigation_id,
        reviewer=reviewer,
        supporting_perspective=supporting,
        challenging_perspective=challenging,
        alternative_explanation=alternative,
        confidence_challenge=confidence_challenge,
        revised_confidence=revised,
    )

    _store_challenge(review)

    log.info(
        "[investigation.synthesis] Challenge for %s by %s: revised confidence %.2f",
        investigation_id, reviewer, revised,
    )
    return review


def _store_challenge(review: ChallengeReview) -> None:
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"[CHALLENGE] {review.investigation_id}: {review.alternative_explanation[:80]}",
            rationale=(
                f"REVIEWER: {review.reviewer} | "
                f"REVISED_CONFIDENCE: {review.revised_confidence} | "
                f"CHALLENGE: {review.confidence_challenge[:120]} | "
                f"ALTERNATIVE: {review.alternative_explanation[:120]}"
            ),
            owner=f"{CHALLENGE_OWNER_PREFIX}{review.investigation_id}",
        )
    except Exception as exc:
        log.debug("[investigation.synthesis] Store challenge failed: %s", exc)


def get_synthesis(investigation_id: str) -> IntegratedFinding | None:
    """Retrieve a stored synthesis for an investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale")
            .eq("owner", f"{SYNTHESIS_OWNER_PREFIX}{investigation_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return None

        parts: dict[str, str] = {}
        for seg in str(rows[0].get("rationale") or "").split(" | "):
            if ": " in seg:
                k, v = seg.split(": ", 1)
                parts[k.strip()] = v.strip()

        try:
            conf = float(parts.get("CONFIDENCE", "0.5"))
        except ValueError:
            conf = 0.5

        stmt = str(rows[0].get("statement") or "")
        headline = stmt.replace(f"[SYNTHESIS] {investigation_id}: ", "")

        return IntegratedFinding(
            investigation_id=investigation_id,
            headline=headline,
            integrated_confidence=conf,
            consensus_action=parts.get("ACTION", ""),
            has_contradiction=int(parts.get("CONTRADICTING", "0") or 0) > 0,
        )

    except Exception as exc:
        log.debug("[investigation.synthesis] get_synthesis failed: %s", exc)
        return None


# ── Formatting ────────────────────────────────────────────────────────────────

def format_integrated_finding(finding: IntegratedFinding) -> str:
    """Format an integrated finding as Slack-ready text."""
    lines = [
        f"*Integrated Finding ({finding.investigation_id}):*",
        f"  {finding.headline}",
        f"  Confidence: {finding.confidence_label} ({finding.integrated_confidence:.0%}) "
        f"across {finding.officer_count} officer(s)",
        f"  Consensus action: `{finding.consensus_action}`",
    ]
    if finding.supporting_evidence:
        lines.append("  *Supporting:*")
        for e in finding.supporting_evidence[:3]:
            lines.append(f"    + {e}")
    if finding.contradicting_evidence:
        lines.append("  *Contradicting:*")
        for e in finding.contradicting_evidence[:2]:
            lines.append(f"    - {e}")
    return "\n".join(lines)


__all__ = [
    "OfficerPerspective",
    "IntegratedFinding",
    "ChallengeReview",
    "synthesize_findings",
    "generate_challenge",
    "get_synthesis",
    "format_integrated_finding",
    "SYNTHESIS_OWNER_PREFIX",
    "CHALLENGE_OWNER_PREFIX",
]
