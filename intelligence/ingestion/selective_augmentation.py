"""
Issue 16: Selective LLM augmentation for ambiguous heuristic scores.

PROVISIONAL — evaluate_shadow_mode_data.py (Issue 15) is explicitly designed
to derive this module's routing threshold empirically: it compares
heuristic-vs-LLM agreement across confidence bands against real QA outcomes
and recommends the band worth routing (its `issue_16_threshold` output). No
real shadow-mode data existed when this shipped (shadow mode activated
2026-07-30); AMBIGUOUS_LOW/HIGH and EXPECTED_IMPROVEMENT_PCT below are a
placeholder, not a measured value. Re-check against evaluate_shadow_mode_data's
recommendation once 2+ weeks of dual-scored data exists, and update or remove
this placeholder accordingly.

Routes only signals whose heuristic relevance_score falls in the "ambiguous"
band to a single extra LLM call — cheaper than shadow-mode's dual-score-every-
signal. Unlike shadow mode (heuristic always stays authoritative), augmentation
REPLACES the heuristic score with the LLM result when the call succeeds —
that's the mechanism by which it's expected to improve borderline cases.
Falls back to the heuristic score on any LLM failure or cost-governance
denial; never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# PROVISIONAL — pending Issue 15's data-derived recommendation.
AMBIGUOUS_LOW = 3.0
AMBIGUOUS_HIGH = 3.9
EXPECTED_IMPROVEMENT_PCT = (5, 10)  # documented target range, unvalidated


def is_ambiguous(relevance_score: float) -> bool:
    """Whether a heuristic relevance_score falls in the ambiguous band."""
    return AMBIGUOUS_LOW <= relevance_score <= AMBIGUOUS_HIGH


def augment_if_ambiguous(
    heuristic_score: Any, signal: dict, analyst: Any,
    task_type: str = "selective-augmentation",
) -> tuple[Any, bool]:
    """
    If heuristic_score.relevance_score is ambiguous, fire one LLM call and
    use it as authoritative on success.

    Returns (final_score, augmented) — augmented=True only when the LLM
    path actually replaced the heuristic result. On any failure (LLM
    unavailable, unparseable, cost-governance denial, non-ambiguous input),
    returns the original heuristic_score unchanged with augmented=False.
    """
    if not is_ambiguous(heuristic_score.relevance_score):
        return heuristic_score, False

    cost_governor = getattr(analyst, "_cost_governor", None)
    if cost_governor is not None:
        check = cost_governor.can_call_llm(task_type)
        if not check.allowed:
            log.info("Selective augmentation skipped (cost governance): %s", check.reason)
            return heuristic_score, False

    llm_score = analyst._score_via_llm(signal)

    if cost_governor is not None:
        cost_governor.log_call(
            task_type=task_type,
            provider=(llm_score.provider if llm_score else "unknown"),
            success=llm_score is not None,
            failure_reason=None if llm_score else "no_llm_result_or_unparseable",
        )

    if llm_score is None:
        return heuristic_score, False
    return llm_score, True
