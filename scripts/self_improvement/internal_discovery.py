"""
Internal discovery for HQ Evolution (spec section 6): "How could the
existing HQ work better?"

Two sources, both observable-evidence-only (no manufactured evidence):

1. The existing model-analysed, policy-classified findings (the pipeline
   this module sits alongside, unchanged) — mapped into the opportunity
   vocabulary so they appear in Discover/Investigate/Improve rather than a
   second, competing surface (Phase 3).
2. A small set of deterministic candidates derived directly from
   EvidenceCollector facts that the model-analysis prompt does not already
   cover (bounded — this is cheap filtering, not a second full analyzer).
"""

import logging
from typing import Any

log = logging.getLogger("internal_discovery")

# Legacy finding category -> HQ Evolution change_class (section 24).
# Anything not listed falls back to "maintenance" — the lowest-authority
# class — never to a Mission-only class by default.
CATEGORY_TO_CHANGE_CLASS: dict[str, str] = {
    "doc_drift": "maintenance",
    "duplicate_implementation": "maintenance",
    "placeholder_code": "maintenance",
    "dead_code": "maintenance",
    "missing_test": "reliability",
    "config_drift": "configuration",
    "stale_adr": "maintenance",
    "observability_gap": "reliability",
    "security_gap": "reliability",
    "resilience_gap": "reliability",
    "router_bypass": "architecture",
    "route_policy_drift": "configuration",
    "silent_fallback": "reliability",
    "model_catalogue_drift": "configuration",
    "knowledge_health": "maintenance",
    "performance_gap": "cost_optimisation",
    "operational_failure": "reliability",
    "governance_violation": "maintenance",
    "automation_opportunity": "capability",
    # New-in-Evolution categories map onto themselves.
    "cost_optimisation": "cost_optimisation",
    "capability": "capability",
    "product_improvement": "product_improvement",
    "architecture": "architecture",
}


def finding_to_candidate(finding: dict[str, Any]) -> dict[str, Any]:
    """Section 3 of Phase 3: map one already-classified finding into an
    opportunity candidate. Preserves category/severity/confidence/evidence/
    proposed_action rather than re-deriving them."""
    category = finding.get("category", "unknown")
    change_class = CATEGORY_TO_CHANGE_CLASS.get(category, "maintenance")
    evidence = finding.get("evidence") or []

    return {
        "title": finding.get("title", finding.get("finding_id", "Untitled finding")),
        "source": finding.get("finding_id", ""),
        "discovery_source": "internal",
        "category": category,  # original legacy category — kept precise for PolicyEngine, see evolution_orchestrator.py
        "change_class": change_class,
        "summary": finding.get("description", "") or (finding.get("proposed_action") or {}).get("description", ""),
        "why_relevant": finding.get("expected_benefit") or f"Observed directly in HQ's own repository (category: {category}).",
        "evidence_strength": confidence_to_evidence_strength(finding.get("confidence", 0.0)),
        "confidence": finding.get("confidence", 0.0),
        "fit": "strong",  # internal findings are HQ's own state by construction
        "value": _severity_to_value(finding.get("severity", "low")),
        "cost_impact": "lower" if category in ("performance_gap", "cost_optimisation") else "neutral",
        "complexity": "low" if change_class in ("maintenance", "configuration") else "moderate",
        "provenance": [{
            "source": "internal_evidence_collector",
            "location": (evidence[0].get("location") if evidence else None),
            "detail": f"{len(evidence)} evidence item(s) from EvidenceCollector",
        }],
        "source_finding_id": finding.get("finding_id"),
        "risk_level": finding.get("risk_level"),
        "automation_eligibility": finding.get("automation_eligibility"),
        "policy_decision_rationale": finding.get("policy_decision_rationale"),
    }


def confidence_to_evidence_strength(confidence: float) -> str:
    if confidence >= 0.9:
        return "conclusive"
    if confidence >= 0.8:
        return "strong"
    if confidence >= 0.6:
        return "moderate"
    return "weak"


def _severity_to_value(severity: str) -> str:
    return {"critical": "high", "high": "high", "medium": "medium", "low": "low", "info": "low"}.get(severity, "low")


def evidence_derived_candidates(evidence: dict[str, Any], max_candidates: int) -> list[dict[str, Any]]:
    """A small number of deterministic candidates straight from
    EvidenceCollector facts, for gaps the model-analysis prompt doesn't
    target directly (bounded, cheap — section 42)."""
    candidates: list[dict[str, Any]] = []

    router_audit = evidence.get("model_router_audit", {}) or {}
    call_log_mb = router_audit.get("call_log_size_mb")
    if isinstance(call_log_mb, (int, float)) and call_log_mb > 25:
        candidates.append({
            "title": "Model Router call log has no rotation or aggregation",
            "source": "model_router_audit.call_log_size_mb",
            "discovery_source": "internal",
            "change_class": "reliability",
            "summary": f"core/model-router/call_log.jsonl is {call_log_mb:.1f}MB with no rotation or "
                       f"queryable aggregation, observed by EvidenceCollector.",
            "why_relevant": "An unbounded flat log makes routing/latency/cost regressions invisible to "
                            "both operators and this cycle's own discovery evidence, and risks unbounded disk growth.",
            "evidence_strength": "conclusive",
            "confidence": 0.9,
            "fit": "strong",
            "value": "medium",
            "cost_impact": "neutral",
            "complexity": "low",
            "provenance": [{"source": "internal_evidence_collector", "location": "core/model-router/call_log.jsonl",
                             "detail": f"call_log_size_mb={call_log_mb}"}],
            # V2 section 6-8: a concrete, honestly re-checkable quantitative
            # signal — outcome_contract.py uses this for baseline capture,
            # outcome_evaluation.py re-reads the same metric post-window for
            # a real before/after comparison, not a guess.
            "measurement_hint": {"type": "file_size_mb", "path": "core/model-router/call_log.jsonl"},
        })

    fs_audit = evidence.get("filesystem_audit", {}) or {}
    config_files = fs_audit.get("config_files") or []
    if isinstance(config_files, list) and len(config_files) > 40:
        candidates.append({
            "title": "Configuration sprawl across the repository",
            "source": "filesystem_audit.config_files",
            "discovery_source": "internal",
            "change_class": "configuration",
            "summary": f"{len(config_files)} configuration files observed across the repository "
                       f"(yaml/yml/json/config/**), a plausible source of drift between similar settings.",
            "why_relevant": "More config surfaces than any one person tracks by memory increases the chance "
                            "two of them silently disagree — the same failure mode config_drift findings already catch individually.",
            "evidence_strength": "moderate",
            "confidence": 0.6,
            "fit": "moderate",
            "value": "low",
            "cost_impact": "neutral",
            "complexity": "moderate",
            "provenance": [{"source": "internal_evidence_collector", "location": "config/",
                             "detail": f"config_files_count={len(config_files)}"}],
        })

    missing_dirs = fs_audit.get("missing_directories") or []
    for d in missing_dirs:
        candidates.append({
            "title": f"Expected directory missing: {d}",
            "source": f"filesystem_audit.missing_directories:{d}",
            "discovery_source": "internal",
            "change_class": "reliability",
            "summary": f"EvidenceCollector expected '{d}' to exist and it does not.",
            "why_relevant": "A component that depends on this path will fail at the point of use rather than at startup.",
            "evidence_strength": "conclusive",
            "confidence": 0.95,
            "fit": "strong",
            "value": "low",
            "cost_impact": "neutral",
            "complexity": "low",
            "provenance": [{"source": "internal_evidence_collector", "location": d, "detail": "directory absent"}],
        })

    return candidates[:max_candidates]


def discover(
    classified_findings: list[dict[str, Any]],
    evidence: dict[str, Any],
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Bounded internal discovery: existing findings mapped 1:1, plus a
    small number of evidence-derived candidates, capped at max_candidates
    total (section 42's cost bound)."""
    from_findings = [finding_to_candidate(f) for f in classified_findings]
    remaining = max(0, max_candidates - len(from_findings))
    from_evidence = evidence_derived_candidates(evidence, remaining) if remaining else []
    return (from_findings + from_evidence)[:max_candidates]
