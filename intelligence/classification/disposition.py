"""
Canonical cross-pipeline disposition (OSINT Ingestion Quality & Relevance
Mission, Phase 8). ESCALATE / BRIEF / WATCH / REFERENCE / SUPPRESS.

Does NOT replace or change any existing status field's semantics
(suppressed, signal_status, or captains_brief.py's rank_score threshold).
This is a read-only mapping computed from fields that already exist —
per mission §17: "the exact database implementation may use domain-specific
values if existing status machines require it... create a compatible
mapping if necessary." Reuses tools/intelligence/recompute_signal_scores.py's
existing compute_escalation()/impact_from_criticality()/
compute_confidence_level() formulas verbatim rather than reimplementing
them (Phase 1 audit finding: 4 of 5 target dispositions already exist
under different names scattered across `suppressed`, `signal_status`, and
`signal_escalation_history` — this module is the consolidation, not a
rebuild).

Shadow-mode only (mission §33): writing this field never changes what
suppressed/signal_status/rank_score do, so it cannot affect what
captains_brief.py or the workbench currently shows until a human/Phase 12
decision wires disposition into an actual filter.
"""

from __future__ import annotations

from typing import Optional

from tools.intelligence.recompute_signal_scores import (
    compute_confidence_level,
    compute_criticality,
    compute_escalation,
    impact_from_criticality,
)

# Matches intelligence/captains_brief.py's _get_new_signals_since() live
# digest-inclusion bar (rank_score>=50, suppressed=false, signal_status!=
# DUPLICATE) — kept as a named constant here so a Phase 11 tuning pass has
# one place to adjust, not two independently-drifting copies of "50".
BRIEF_RANK_SCORE_FLOOR = 50


def technical_disposition(
    event: dict,
    corroboration_count: int = 0,
) -> tuple[str, str]:
    """
    Compute (disposition, disposition_reason) for one intelligence_events
    row (as a dict of column values). Never raises — falls back to WATCH
    with an explanatory reason on any missing/malformed input, since an
    under-confident default is safer than a mis-suppressed one.

    corroboration_count: number of corroborating sources, if known to the
    caller (e.g. from signal_corroboration) — 0 is a safe default, it only
    makes compute_confidence_level() slightly more conservative.
    """
    try:
        if event.get("suppressed"):
            return "SUPPRESS", event.get("suppression_reason") or "suppressed"

        if event.get("signal_status") == "IN_BRIEF":
            return "BRIEF", "included_in_published_brief"

        if event.get("signal_status") == "DUPLICATE":
            return "REFERENCE", "duplicate_supports_corroboration_only"

        tier = f"TIER_{event['source_tier']}" if event.get("source_tier") else None
        confidence = (
            event.get("confidence_level")
            or event.get("osint_confidence_level")
            or (compute_confidence_level(tier, corroboration_count) if tier else "UNKNOWN")
        )

        criticality = event.get("criticality_score")
        if criticality is None:
            criticality = compute_criticality(
                event.get("risk_rating"),
                event.get("operational_relevance"),
                event.get("banking_relevance"),
                event.get("cps230_relevance", False),
            )
        impact = impact_from_criticality(criticality)

        escalation = compute_escalation(confidence, impact)  # ESCALATE / WATCH / MONITOR

        if escalation == "ESCALATE":
            return "ESCALATE", f"confidence={confidence} impact={impact}"

        if escalation == "WATCH":
            return "WATCH", f"confidence={confidence} impact={impact}"

        # escalation == "MONITOR": still check whether this item actually
        # clears the live captains_brief.py digest bar — if it does, it's
        # already reaching TJR today and should read as BRIEF, not
        # REFERENCE, even though its confidence/impact combo isn't an
        # escalation-worthy pairing.
        rank_score = event.get("rank_score") or 0
        if rank_score >= BRIEF_RANK_SCORE_FLOOR:
            return "BRIEF", f"rank_score={rank_score} clears captains_brief digest floor ({BRIEF_RANK_SCORE_FLOOR})"

        return "REFERENCE", f"confidence={confidence} impact={impact} rank_score={rank_score}"

    except Exception as exc:  # noqa: BLE001 — disposition must never block a save
        return "WATCH", f"disposition_computation_failed: {exc}"


def health_disposition(
    signal: dict,
    curator_decision: Optional[str] = None,
) -> tuple[str, str]:
    """
    Compute (disposition, disposition_reason) for one health_signals row.

    curator_decision, if known (PUBLISH/REJECT/ESCALATE from
    health_signal_curation.py::HealthSignalCurator), is authoritative —
    it already IS the human-facing recommendation/decision. This function
    only maps it (and the auto_ingested/auto_ingest_reviewed/suppressed
    state for rows the curator hasn't reached yet) into the shared
    disposition vocabulary; it does not re-judge relevance itself.
    """
    try:
        if curator_decision == "ESCALATE":
            return "ESCALATE", "curator_escalated"
        if curator_decision == "PUBLISH":
            return "BRIEF", "curator_published"
        if curator_decision == "REJECT":
            return "SUPPRESS", "curator_rejected"

        if signal.get("suppressed"):
            return "SUPPRESS", "suppressed"

        if signal.get("auto_ingested") and not signal.get("auto_ingest_reviewed"):
            return "WATCH", "pending_curation_review"

        # Not auto-ingested (manually captured) and not suppressed: treat
        # as already-accepted background knowledge unless flagged safety.
        if signal.get("safety_relevance"):
            return "ESCALATE", "safety_relevance_flagged"

        return "REFERENCE", "accepted_not_flagged_for_brief"

    except Exception as exc:  # noqa: BLE001
        return "WATCH", f"disposition_computation_failed: {exc}"
