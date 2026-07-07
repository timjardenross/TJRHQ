"""Decision Package Generation (EXEC-004 WP6).

Converts investigation findings into structured executive decisions when the
evidence warrants a choice between options. Not all investigations produce a
decision package — many resolve to "no action" or directly to a mission draft.

Decision packages route through XO before reaching the Captain.

Storage (decisions table):
  statement : "[DECISION_PACKAGE] {inv_id}: {problem[:80]}"
  owner     : "investigation_decision:{inv_id}"
  rationale : "PROBLEM: {stmt} | OPTIONS: {n} | RECOMMENDED: {opt} |
               CONFIDENCE: {conf} | APPROVALS: {approvals}"

Public API:
    generate_decision_package(inv_id, findings, question) -> DecisionPackage | None
    get_decision_package(inv_id)                          -> DecisionPackage | None
    get_pending_decision_packages(limit)                  -> list[DecisionPackage]
    format_decision_package(package)                      -> str
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import (
    DecisionOption, DecisionPackage, FindingsReport, DECISION_OWNER_PREFIX,
)

_ACTION_REQUIRES_DECISION = {"mission", "improvement", "decision"}

_OPTION_TEMPLATES: dict[str, tuple[str, list[str], list[str]]] = {
    "mission": (
        "Create a mission to address the identified issue",
        ["Issue addressed through structured delivery", "Clear owner and timeline"],
        ["Consumes mission capacity", "Requires XO approval"],
    ),
    "improvement": (
        "Create an improvement mission via the D-057 pipeline",
        ["Structured improvement lifecycle with scorecard", "Budget-gated to protect capacity"],
        ["Slower than direct mission", "Subject to improvement budget"],
    ),
    "monitoring": (
        "Add to risk register and monitor",
        ["Low effort", "Non-disruptive"],
        ["No active remediation", "Risk may escalate"],
    ),
    "knowledge_update": (
        "Update knowledge base and close the gap",
        ["Improves institutional memory", "Prevents recurrence"],
        ["Time investment for documentation"],
    ),
    "no_action": (
        "Take no action at this time",
        ["Preserves capacity", "Avoids premature action"],
        ["Issue may persist or escalate"],
    ),
    "further_investigation": (
        "Conduct further investigation before deciding",
        ["Ensures decision is evidence-based"],
        ["Delays action", "Issue may worsen during investigation"],
    ),
}


def _build_options(lead_action: str) -> list[DecisionOption]:
    """Build a decision options list with the lead recommendation first."""
    ordered_actions = [lead_action]
    # Always offer no_action as an alternative
    if lead_action != "no_action":
        ordered_actions.append("no_action")
    if lead_action not in ("monitoring",):
        ordered_actions.append("monitoring")

    options: list[DecisionOption] = []
    seen: set[str] = set()
    for action in ordered_actions:
        if action in seen:
            continue
        seen.add(action)
        if action in _OPTION_TEMPLATES:
            desc, benefits, risks = _OPTION_TEMPLATES[action]
            options.append(DecisionOption(
                label=action.replace("_", " ").title(),
                description=desc,
                benefits=benefits,
                risks=risks,
            ))

    return options[:4]


def _store_decision_package(package: DecisionPackage) -> None:
    """Persist decision package to Command Memory (non-blocking)."""
    try:
        from command_memory_integration import log_decision_to_command_memory

        approvals_str = ", ".join(package.required_approvals) if package.required_approvals else "xo"

        log_decision_to_command_memory(
            statement=f"[DECISION_PACKAGE] {package.investigation_id}: {package.problem_statement[:80]}",
            rationale=(
                f"PROBLEM: {package.problem_statement[:100]} | "
                f"OPTIONS: {len(package.options)} | "
                f"RECOMMENDED: {package.recommended_option} | "
                f"CONFIDENCE: {package.confidence_assessment} | "
                f"APPROVALS: {approvals_str} | "
                f"EVIDENCE: {package.evidence_summary[:120]}"
            ),
            owner=f"{DECISION_OWNER_PREFIX}{package.investigation_id}",
        )
    except Exception as exc:
        log.debug("[investigation.decision_package] Store failed: %s", exc)


def generate_decision_package(
    investigation_id: str,
    findings: FindingsReport,
    question: str,
) -> DecisionPackage | None:
    """Generate a decision package from investigation findings.

    Only generates a package if the lead recommendation requires an active
    decision (mission / improvement / decision). Monitoring and no-action
    outcomes do not require a formal decision package.

    Args:
        investigation_id: The investigation being concluded
        findings:         FindingsReport from generate_findings()
        question:         The original investigation question

    Returns:
        DecisionPackage if a decision is required, None otherwise.
    """
    lead = findings.lead_recommendation
    if not lead:
        log.debug("[investigation.decision_package] No recommendation — no package needed")
        return None

    if lead.action_type not in _ACTION_REQUIRES_DECISION:
        log.debug(
            "[investigation.decision_package] Action '%s' does not require decision package",
            lead.action_type,
        )
        return None

    high_findings = findings.high_confidence_findings
    conf_label = (
        "HIGH" if lead.confidence >= 0.75 else
        "MEDIUM" if lead.confidence >= 0.5 else
        "LOW"
    )

    evidence_summary = (
        findings.summary or
        f"{len(findings.findings)} findings from investigation '{question[:60]}'"
    )

    options = _build_options(lead.action_type)

    required_approvals = ["xo"]
    if lead.action_type == "mission" and lead.confidence >= 0.75:
        required_approvals = ["xo"]  # XO approves missions; Captain for large/strategic
    elif lead.action_type == "improvement":
        required_approvals = ["xo"]

    package = DecisionPackage(
        investigation_id=investigation_id,
        problem_statement=question[:200],
        evidence_summary=evidence_summary,
        options=options,
        recommended_option=options[0].label if options else lead.action_type,
        confidence_assessment=f"{conf_label} ({lead.confidence:.0%}) — {len(high_findings)} high-confidence finding(s)",
        required_approvals=required_approvals,
    )

    _store_decision_package(package)

    log.info(
        "[investigation.decision_package] Package generated: %s (lead=%s, confidence=%s)",
        investigation_id, lead.action_type, conf_label,
    )
    return package


def get_decision_package(investigation_id: str) -> DecisionPackage | None:
    """Retrieve a stored decision package for an investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,created_at")
            .eq("owner", f"{DECISION_OWNER_PREFIX}{investigation_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return None

        stmt = str(rows[0].get("statement") or "")
        rat  = str(rows[0].get("rationale") or "")

        parts: dict[str, str] = {}
        for seg in rat.split(" | "):
            if ": " in seg:
                k, v = seg.split(": ", 1)
                parts[k.strip()] = v.strip()

        problem = parts.get("PROBLEM", stmt.replace(f"[DECISION_PACKAGE] {investigation_id}: ", ""))
        recommended = parts.get("RECOMMENDED", "")
        options = [
            DecisionOption(
                label=recommended or "Review findings",
                description=_OPTION_TEMPLATES.get(recommended, ("See findings report", [], []))[0],
            )
        ] if recommended else []

        return DecisionPackage(
            investigation_id=investigation_id,
            problem_statement=problem[:200],
            evidence_summary=parts.get("EVIDENCE", ""),
            options=options,
            recommended_option=recommended,
            confidence_assessment=parts.get("CONFIDENCE", ""),
            required_approvals=parts.get("APPROVALS", "xo").split(", "),
        )

    except Exception as exc:
        log.debug("[investigation.decision_package] get_decision_package failed: %s", exc)
        return None


def get_pending_decision_packages(limit: int = 10) -> list[DecisionPackage]:
    """Return decision packages awaiting XO review."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{DECISION_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        packages: list[DecisionPackage] = []
        for row in res.data or []:
            owner  = str(row.get("owner") or "")
            inv_id = owner[len(DECISION_OWNER_PREFIX):]
            pkg    = get_decision_package(inv_id)
            if pkg:
                packages.append(pkg)

        return packages

    except Exception as exc:
        log.debug("[investigation.decision_package] get_pending failed: %s", exc)
        return []


def format_decision_package(package: DecisionPackage) -> str:
    """Format a decision package as Slack-ready executive brief."""
    lines: list[str] = [
        f"*Decision Package ({package.investigation_id})*",
        f"*Problem:* {package.problem_statement}",
        f"*Evidence:* {package.evidence_summary}",
        f"*Confidence:* {package.confidence_assessment}",
        "",
        "*Options:*",
    ]

    for i, opt in enumerate(package.options, 1):
        marker = ":white_check_mark:" if opt.label == package.recommended_option else ":white_square_button:"
        lines.append(f"  {marker} *{opt.label}:* {opt.description}")
        if opt.benefits:
            lines.append(f"    Benefits: {'; '.join(opt.benefits[:2])}")
        if opt.risks:
            lines.append(f"    Risks: {'; '.join(opt.risks[:2])}")

    lines.append("")
    lines.append(f"*Recommended:* {package.recommended_option}")
    approvals_str = ", ".join(package.required_approvals) if package.required_approvals else "XO"
    lines.append(f"*Requires approval from:* {approvals_str.upper()}")

    return "\n".join(lines)


__all__ = [
    "generate_decision_package",
    "get_decision_package",
    "get_pending_decision_packages",
    "format_decision_package",
]
