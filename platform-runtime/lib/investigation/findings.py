"""Findings & Recommendation Engine (EXEC-004 WP5).

Separates observed facts from inferences and recommendations.

Principle: evidence first, recommendation second. Never recommend action
before establishing what the evidence actually shows.

Pattern detection categories:
  operational  — blockages, failures, delays, overdue items
  knowledge    — unknown, undocumented, missing, gap
  systematic   — recurring, patterns, consistent trends
  risk         — risk signals, safety concerns, vulnerabilities
  improvement  — waste, inefficiency, automation opportunities

Findings are stored in the decisions table:
  statement : "[FINDING] {inv_id}: {observation[:80]}"
  owner     : "investigation_finding:{inv_id}"
  rationale : "CONFIDENCE: {x} | IS_FACT: {bool} | BASIS: {basis[:120]} |
               RECOMMENDATION: {action_type}"

Public API:
    generate_findings(inv_id, evidence, question) -> FindingsReport
    get_findings(inv_id)                          -> FindingsReport | None
    format_findings_report(report)                -> str
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import (
    EvidencePackage, Finding, FindingsReport, Recommendation,
    FINDING_OWNER_PREFIX,
)


# ── Pattern signal tables ─────────────────────────────────────────────────────

_PATTERNS: dict[str, frozenset[str]] = {
    "operational":  frozenset({"blocked", "stale", "failed", "overdue", "delayed", "outstanding", "error", "stuck"}),
    "knowledge":    frozenset({"unknown", "unclear", "undocumented", "missing", "gap", "undefined", "no record"}),
    "systematic":   frozenset({"recurring", "repeated", "pattern", "consistent", "frequent", "chronic", "always", "never"}),
    "risk":         frozenset({"risk", "concern", "critical", "urgent", "safety", "danger", "vulnerability", "red"}),
    "improvement":  frozenset({"waste", "inefficient", "manual", "tedious", "automate", "improve", "slow", "bottleneck"}),
}

_PATTERN_TO_ACTION: dict[str, str] = {
    "operational":  "mission",
    "knowledge":    "knowledge_update",
    "systematic":   "improvement",
    "risk":         "monitoring",
    "improvement":  "improvement",
}

_PATTERN_TO_FINDING_TEMPLATE: dict[str, str] = {
    "operational":  "Evidence indicates operational issues (blockages, failures, or delays) in this domain.",
    "knowledge":    "Evidence indicates knowledge or documentation gaps in this domain.",
    "systematic":   "Evidence indicates a recurring or systemic pattern rather than isolated incidents.",
    "risk":         "Evidence indicates risk signals that warrant ongoing monitoring.",
    "improvement":  "Evidence indicates efficiency or automation opportunities in this domain.",
}


# ── Analysis ──────────────────────────────────────────────────────────────────

def _score_patterns(evidence: EvidencePackage) -> dict[str, float]:
    """Score each pattern category based on evidence signal density.

    Score = (matching_items / total_items) × avg_confidence_of_matching_items
    Returns a dict of {pattern_name: score} for patterns with score > 0.
    """
    all_text = [
        (f"{i.summary} {i.data}").lower()
        for i in evidence.items
    ]
    total = max(len(all_text), 1)

    scores: dict[str, float] = {}
    for category, signals in _PATTERNS.items():
        matching_items = [
            evidence.items[idx]
            for idx, text in enumerate(all_text)
            if any(sig in text for sig in signals)
        ]
        if not matching_items:
            continue
        avg_conf = sum(i.confidence for i in matching_items) / len(matching_items)
        scores[category] = round((len(matching_items) / total) * avg_conf, 3)

    return scores


def _generate_findings_from_patterns(
    scores: dict[str, float],
    evidence: EvidencePackage,
) -> list[Finding]:
    """Convert pattern scores into structured findings."""
    findings: list[Finding] = []

    # Sort patterns by score descending
    for category, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if score < 0.1:
            continue

        sources = list({i.source.value for i in evidence.items})
        basis = (
            f"{len(evidence.items)} evidence item(s) from {', '.join(sources[:3])} "
            f"(avg confidence: {evidence.avg_confidence})"
        )

        findings.append(Finding(
            observation=_PATTERN_TO_FINDING_TEMPLATE.get(category, f"Pattern detected: {category}."),
            evidence_basis=basis,
            confidence=min(score * 1.5, 0.95),  # scale but cap at 0.95
            is_fact=(score >= 0.5),  # high-signal patterns are treated as facts
        ))

    if not findings and evidence.items:
        # Inconclusive — still surface a finding
        findings.append(Finding(
            observation="Evidence collected but no strong pattern detected. Further investigation may be required.",
            evidence_basis=f"{len(evidence.items)} evidence item(s) reviewed.",
            confidence=0.4,
            is_fact=False,
        ))

    return findings


def _generate_recommendations(
    findings: list[Finding],
    question: str,
    scores: dict[str, float],
) -> list[Recommendation]:
    """Generate recommendations based on findings and evidence patterns."""
    if not findings:
        return [Recommendation(
            action_type="no_action",
            description="No significant findings warrant action at this time.",
            rationale="Insufficient evidence to recommend action.",
            confidence=0.3,
        )]

    recommendations: list[Recommendation] = []

    for category, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if score < 0.1:
            continue
        action_type = _PATTERN_TO_ACTION.get(category, "further_investigation")

        desc_map = {
            "mission":              "Create a mission to address the identified operational issue.",
            "knowledge_update":     "Update the knowledge base to close identified gaps.",
            "improvement":          "Create an improvement mission to address efficiency or systematic issues.",
            "monitoring":           "Add to risk monitoring to track the identified risk signals.",
            "further_investigation":"Gather more evidence before determining a course of action.",
        }

        recommendations.append(Recommendation(
            action_type=action_type,
            description=desc_map.get(action_type, f"Take action: {action_type}"),
            rationale=f"Pattern '{category}' detected with score {score:.2f} from evidence analysis.",
            confidence=min(score * 1.5, 0.90),
        ))

    if not recommendations:
        recommendations.append(Recommendation(
            action_type="no_action",
            description="Evidence does not point to a required action at this time.",
            rationale="Pattern analysis shows insufficient signal strength for actionable recommendation.",
            confidence=0.4,
        ))

    return recommendations[:3]  # cap to top 3 recommendations


def _summarize_findings(report: FindingsReport, question: str) -> str:
    """Produce a one-paragraph summary of findings."""
    if not report.findings:
        return f"Investigation of '{question[:80]}' yielded no significant findings."

    high = report.high_confidence_findings
    lead = report.lead_recommendation

    parts: list[str] = []
    if high:
        parts.append(f"{len(high)} high-confidence finding(s).")
    else:
        parts.append(f"{len(report.findings)} finding(s) at medium-low confidence.")

    if lead:
        parts.append(f"Lead recommendation: {lead.action_type} ({lead.confidence:.0%} confidence).")

    return " ".join(parts)


def _store_findings(report: FindingsReport) -> None:
    """Persist findings summary to Command Memory (non-blocking)."""
    if not report.findings:
        return
    try:
        from command_memory_integration import log_decision_to_command_memory

        lead = report.lead_recommendation
        for finding in report.findings[:3]:
            log_decision_to_command_memory(
                statement=f"[FINDING] {report.investigation_id}: {finding.observation[:80]}",
                rationale=(
                    f"CONFIDENCE: {round(finding.confidence, 2)} | "
                    f"IS_FACT: {finding.is_fact} | "
                    f"BASIS: {finding.evidence_basis[:120]} | "
                    f"RECOMMENDATION: {lead.action_type if lead else 'none'}"
                ),
                owner=f"{FINDING_OWNER_PREFIX}{report.investigation_id}",
            )
    except Exception as exc:
        log.debug("[investigation.findings] Store findings failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_findings(
    investigation_id: str,
    evidence: EvidencePackage,
    question: str,
) -> FindingsReport:
    """Generate a structured findings report from an evidence package.

    Principle: evidence first, recommendation second.

    Args:
        investigation_id: Investigation being analysed
        evidence:         Collected EvidencePackage
        question:         Original investigation question

    Returns:
        FindingsReport with findings, recommendations, and summary.
    """
    report = FindingsReport(investigation_id=investigation_id)

    if not evidence.items:
        report.summary = f"No evidence collected for investigation '{question[:60]}'. Cannot generate findings."
        report.recommendations.append(Recommendation(
            action_type="further_investigation",
            description="Insufficient evidence. Collect more data before drawing conclusions.",
            rationale="No evidence items available.",
            confidence=0.2,
        ))
        return report

    scores = _score_patterns(evidence)
    report.findings      = _generate_findings_from_patterns(scores, evidence)
    report.recommendations = _generate_recommendations(report.findings, question, scores)
    report.summary       = _summarize_findings(report, question)

    _store_findings(report)

    log.info(
        "[investigation.findings] %s: %d finding(s), lead=%s (%.0f%%)",
        investigation_id,
        len(report.findings),
        report.lead_recommendation.action_type if report.lead_recommendation else "none",
        (report.lead_recommendation.confidence * 100) if report.lead_recommendation else 0,
    )
    return report


def get_findings(investigation_id: str) -> FindingsReport | None:
    """Retrieve findings stored for an investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,created_at")
            .eq("owner", f"{FINDING_OWNER_PREFIX}{investigation_id}")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return None

        report = FindingsReport(investigation_id=investigation_id)
        for row in rows:
            stmt = str(row.get("statement") or "")
            rat  = str(row.get("rationale") or "")
            obs  = stmt.replace(f"[FINDING] {investigation_id}: ", "")

            parts: dict[str, str] = {}
            for seg in rat.split(" | "):
                if ": " in seg:
                    k, v = seg.split(": ", 1)
                    parts[k.strip()] = v.strip()

            try:
                conf = float(parts.get("CONFIDENCE", "0.5"))
            except ValueError:
                conf = 0.5

            report.findings.append(Finding(
                observation=obs[:200],
                evidence_basis=parts.get("BASIS", ""),
                confidence=conf,
                is_fact=parts.get("IS_FACT", "True").lower() == "true",
            ))

        return report

    except Exception as exc:
        log.debug("[investigation.findings] get_findings failed: %s", exc)
        return None


def format_findings_report(report: FindingsReport) -> str:
    """Format findings report as Slack-ready text."""
    lines: list[str] = [f"*Investigation Findings ({report.investigation_id}):*"]

    if not report.findings:
        lines.append("_No findings generated._")
        return "\n".join(lines)

    lines.append(f"_Summary: {report.summary}_\n")

    lines.append("*Findings:*")
    for i, f in enumerate(report.findings, 1):
        label = "FACT" if f.is_fact else "INFERENCE"
        lines.append(
            f"  {i}. [{f.confidence_label}/{label}] {f.observation}"
        )

    if report.recommendations:
        lines.append("\n*Recommendations:*")
        for rec in report.recommendations:
            lines.append(
                f"  → `{rec.action_type}` ({rec.confidence:.0%}): {rec.description}"
            )

    return "\n".join(lines)


__all__ = [
    "generate_findings",
    "get_findings",
    "format_findings_report",
]
