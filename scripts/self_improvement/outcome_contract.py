"""
Outcome Contract construction (V2 sections 5-9): built once, at approval
time, BEFORE implementation — "what is expected to improve, how would we
know, what is the baseline, when should we check, what would count as
regression". Deterministic and category-driven, matching the spec's own
worked examples per change_class; never requires a numeric measurement
where none can be honestly grounded (section 8: "if no valid baseline
exists, record that explicitly — do not fabricate one").
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import evidence_sources

log = logging.getLogger("outcome_contract")

# V2 section 7: measurement type per change_class. Deliberately coarse and
# honest — a specific opportunity's provenance/measurement_hint can still
# ground a real quantitative baseline (see _capture_baseline) even where
# the change_class default is "deterministic" or "mixed".
_MEASUREMENT_TYPE_BY_CLASS = {
    "maintenance": "deterministic",
    "configuration": "deterministic",
    "reliability": "quantitative",
    "cost_optimisation": "quantitative",
    "capability": "mixed",
    "product_improvement": "mixed",
    "architecture": "mixed",
}

# V2 section 9: observation window per change_class, event/cycle-based
# rather than elapsed-days where that's more meaningful. "cycles" here
# means completed HQ Evolution overnight cycles (the unit run_cycle()
# itself advances once per real invocation), which is honest and
# available everywhere, unlike a domain-specific job cadence this generic
# contract-builder has no way to know per-opportunity.
_OBSERVATION_WINDOW_BY_CLASS = {
    "maintenance": {"type": "immediate", "count": 1},
    "configuration": {"type": "immediate", "count": 1},
    "reliability": {"type": "cycles", "count": 5},
    "cost_optimisation": {"type": "cycles", "count": 7},
    "capability": {"type": "cycles", "count": 7},
    "product_improvement": {"type": "cycles", "count": 7},
    "architecture": {"type": "cycles", "count": 14},
}

_EVIDENCE_SOURCES_BY_CLASS = {
    "maintenance": ["internal_evidence_snapshot"],
    "configuration": ["internal_evidence_snapshot"],
    "reliability": ["domain_heartbeats", "internal_evidence_snapshot"],
    "cost_optimisation": ["model_router_call_log", "internal_evidence_snapshot"],
    "capability": ["internal_evidence_snapshot"],
    "product_improvement": ["internal_evidence_snapshot"],
    "architecture": ["internal_evidence_snapshot"],
}

_REGRESSION_SIGNAL_BY_CLASS = {
    # V2 section 30: guardrails so an opportunity can never define success
    # solely by a counter it can itself suppress to move.
    "maintenance": "The removed/changed file or config is referenced elsewhere and something now fails to load.",
    "configuration": "A consumer of the changed configuration now fails or behaves unexpectedly.",
    "reliability": "The affected job's failure rate increases, or it stops running/heartbeating entirely.",
    "cost_optimisation": "Any dependent output (e.g. a Brief) starts failing, coming back empty, or is materially degraded — a call-count drop caused by suppressing real work is a regression, not a saving.",
    "capability": "The new capability introduces a new failure mode, security gap, or measurably worse behaviour in what it touches.",
    "product_improvement": "The targeted surface's assessed behaviour gets measurably worse, not just different.",
    "architecture": "The replaced/restructured subsystem's dependents fail, regress in latency/reliability, or lose a capability they relied on.",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_baseline(opportunity: dict[str, Any], measurement_type: str, repo_root: Path) -> dict[str, Any]:
    """Section 8: capture a real baseline where one can be honestly
    grounded; otherwise say so explicitly rather than guessing."""
    hint = opportunity.get("measurement_hint")
    if hint:
        reading = evidence_sources.read_measurement(hint, repo_root)
        if reading.get("available"):
            return {
                "available": True,
                "value": reading.get("value", reading),
                "description": reading.get("description") or f"Measured via {hint.get('type')}",
                "provenance": f"evidence_sources.read_measurement({hint})",
                "captured_at": _now_iso(),
            }
        return {"available": False, "reason": reading.get("reason", "Measurement unavailable"), "captured_at": _now_iso()}

    if measurement_type == "deterministic":
        # The candidate's own discovery-time provenance IS the baseline
        # state description — no separate re-read needed.
        provenance = opportunity.get("provenance") or []
        if provenance:
            first = provenance[0]
            return {
                "available": True,
                "value": first.get("detail"),
                "description": f"State observed at discovery: {first.get('detail')}",
                "provenance": f"{first.get('source')} @ {first.get('location')}",
                "captured_at": _now_iso(),
            }
        return {"available": False, "reason": "No discovery-time evidence captured for this candidate", "captured_at": _now_iso()}

    if measurement_type in ("mixed", "qualitative"):
        return {
            "available": False,
            "reason": "Qualitative/mixed measurement — comparison will be evidence-based at observation "
                      "time rather than against a single numeric baseline.",
            "captured_at": _now_iso(),
        }

    # quantitative with no measurement_hint — honest gap, not a guess
    # (section 11's Model Router observability finding is exactly why this
    # can't always be grounded yet: no per-opportunity task_type tagging).
    return {
        "available": False,
        "reason": "No specific measurable signal (measurement_hint) was identified for this candidate at discovery time.",
        "captured_at": _now_iso(),
    }


def build_outcome_contract(opportunity: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Section 5-6: the pre-implementation contract. Called once, at
    approval time (dashboard.py's approve_improvement/create_mission
    decisions) — never re-built afterward, so it stays a fixed target to
    evaluate against, not a moving one."""
    change_class = opportunity.get("change_class", "maintenance")
    investigation = opportunity.get("investigation") or {}

    expected_benefit = (
        (investigation.get("potential_benefits") or [None])[0]
        or opportunity.get("why_relevant")
        or opportunity.get("summary")
        or "Not specified"
    )

    measurement_type = _MEASUREMENT_TYPE_BY_CLASS.get(change_class, "unknown")
    baseline = _capture_baseline(opportunity, measurement_type, repo_root)

    return {
        "expected_benefit": expected_benefit,
        "measurement_type": measurement_type,
        "baseline": baseline,
        "success_signal": investigation.get("why_hq_is_looking_at_this") or expected_benefit,
        "regression_signal": _REGRESSION_SIGNAL_BY_CLASS.get(change_class, "Any material degradation of what this change touched."),
        "observation_window": dict(_OBSERVATION_WINDOW_BY_CLASS.get(change_class, {"type": "cycles", "count": 7})),
        "evidence_sources": list(_EVIDENCE_SOURCES_BY_CLASS.get(change_class, ["internal_evidence_snapshot"])),
        "evaluation_status": "pending_implementation",
        "observation_started_at": None,
        "created_at": _now_iso(),
    }
