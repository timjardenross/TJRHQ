"""
Issue 16: Selective augmentation — route ambiguous signals to LLM path.

Once Issue 15 identifies a confidence band where LLM adds value
(e.g., relevance_score 3.0–3.9), this module routes only those signals
to the LLM path. High/low confidence signals continue using heuristic.

Blocked on Issue 15 providing a threshold recommendation.
This module is ready to activate once Issue 15 data is available.

Public API:
    should_augment_with_llm(signal_score: float, threshold_config: dict) -> bool
    augment_signal(signal: dict, analyst, store) -> dict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class AugmentationThreshold:
    """Configuration for Issue 16 selective routing."""
    score_min: float  # e.g., 3.0
    score_max: float  # e.g., 3.9
    band_name: str  # "AMBIGUOUS (3.0-3.9)"
    expected_llm_improvement_pct: float  # How much does LLM improve QA pass rate vs heuristic?


def should_augment_with_llm(
    heuristic_score: float, threshold: Optional[AugmentationThreshold]
) -> bool:
    """
    Decide whether to route this signal to the LLM path.

    Args:
        heuristic_score: Heuristic relevance_score (1.0–5.0)
        threshold: AugmentationThreshold from Issue 15 analysis

    Returns:
        True if score falls in the ambiguous band (worth LLM augmentation)
    """
    if threshold is None:
        return False  # No threshold recommendation from Issue 15 yet
    return threshold.score_min <= heuristic_score <= threshold.score_max


def augment_signal(
    signal: dict,
    heuristic_score_result,  # SignalScore from heuristic path
    analyst,  # IntelligenceAnalyst
    cost_governor=None,
    threshold: Optional[AugmentationThreshold] = None,
) -> dict:
    """
    Issue 16: Selectively run LLM path on ambiguous signals.

    If heuristic score falls in the ambiguous band AND we're within cost limits,
    run LLM path and blend results. Otherwise use heuristic only.

    Args:
        signal: Raw signal dict
        heuristic_score_result: SignalScore from heuristic path
        analyst: IntelligenceAnalyst with use_llm=True
        cost_governor: LLMCostGovernance (optional)
        threshold: AugmentationThreshold from Issue 15

    Returns:
        dict with fields to persist:
        {
            "score_breakdown": authoritative score breakdown,
            "relevance_score": authoritative score,
            "risk_rating": authoritative rating,
            "score_method": "heuristic" | "llm" | "blended",
            "llm_score_breakdown": LLM result if run,
            "llm_risk_rating": LLM rating if run,
            "llm_provider": model used,
            "score_provenance": full audit trail,
        }
    """
    # Check if this signal is in the ambiguous band
    if not should_augment_with_llm(heuristic_score_result.relevance_score, threshold):
        # Out of band: use heuristic only
        log.debug(
            f"Signal score {heuristic_score_result.relevance_score} outside ambiguous band; "
            f"using heuristic only"
        )
        return {
            "score_breakdown": heuristic_score_result.score_breakdown,
            "relevance_score": heuristic_score_result.relevance_score,
            "risk_rating": heuristic_score_result.risk_rating,
            "score_method": "heuristic",
            "score_provenance": {
                "reason": "outside_ambiguous_band",
                "ambiguous_band": f"{threshold.band_name if threshold else 'none_configured'}",
            },
        }

    # In the ambiguous band: check cost & run LLM
    log.info(
        f"Signal score {heuristic_score_result.relevance_score} in ambiguous band "
        f"({threshold.band_name if threshold else 'unknown'}); attempting LLM augmentation"
    )

    # Cost check
    if cost_governor:
        check = cost_governor.can_call_llm("signal-scoring")
        if not check.allowed:
            log.warning(f"LLM augmentation blocked: {check.reason}; falling back to heuristic")
            return {
                "score_breakdown": heuristic_score_result.score_breakdown,
                "relevance_score": heuristic_score_result.relevance_score,
                "risk_rating": heuristic_score_result.risk_rating,
                "score_method": "heuristic",
                "score_provenance": {
                    "reason": "cost_limit_exceeded",
                    "attempted_augmentation": True,
                },
            }

    # Run LLM path
    try:
        llm_result = analyst._score_via_llm(signal)
        if llm_result:
            log.info(
                f"LLM augmentation succeeded: heuristic={heuristic_score_result.risk_rating}, "
                f"llm={llm_result.risk_rating}"
            )
            # Log the call
            if cost_governor:
                cost_governor.log_call(
                    task_type="signal-scoring",
                    provider=llm_result.provider,
                    success=True,
                )
            # Use LLM as authoritative (Issue 16 decision)
            return {
                "score_breakdown": llm_result.score_breakdown,
                "relevance_score": llm_result.relevance_score,
                "risk_rating": llm_result.risk_rating,
                "score_method": "llm",  # LLM is now authoritative in ambiguous band
                "llm_score_breakdown": llm_result.score_breakdown,
                "llm_relevance_score": llm_result.relevance_score,
                "llm_risk_rating": llm_result.risk_rating,
                "llm_provider": llm_result.provider,
                "score_provenance": {
                    "reason": "selective_augmentation_ambiguous_band",
                    "ambiguous_band": threshold.band_name if threshold else "unknown",
                    "heuristic_would_have_been": heuristic_score_result.risk_rating,
                    "llm_was_used": True,
                    "method": "llm",
                },
            }
        else:
            log.warning("LLM path failed; falling back to heuristic")
            if cost_governor:
                cost_governor.log_call(
                    task_type="signal-scoring",
                    success=False,
                    failure_reason="unparseable_output",
                )
            return {
                "score_breakdown": heuristic_score_result.score_breakdown,
                "relevance_score": heuristic_score_result.relevance_score,
                "risk_rating": heuristic_score_result.risk_rating,
                "score_method": "heuristic",  # Fallback to heuristic
                "score_provenance": {
                    "reason": "llm_path_failed",
                    "attempted_augmentation": True,
                    "ambiguous_band": threshold.band_name if threshold else "unknown",
                },
            }
    except Exception as exc:
        log.error(f"LLM augmentation error: {exc}; using heuristic")
        if cost_governor:
            cost_governor.log_call(
                task_type="signal-scoring",
                success=False,
                failure_reason=str(exc),
            )
        return {
            "score_breakdown": heuristic_score_result.score_breakdown,
            "relevance_score": heuristic_score_result.relevance_score,
            "risk_rating": heuristic_score_result.risk_rating,
            "score_method": "heuristic",
            "score_provenance": {
                "reason": "llm_path_exception",
                "exception": str(exc),
                "attempted_augmentation": True,
            },
        }
