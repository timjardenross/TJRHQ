"""
Deterministic relevance gate + dedup for HQ Evolution (spec sections 16-17).

An LLM may assist by proposing value/cost/complexity/fit judgments, but
whether a candidate is even eligible to be surfaced is decided here, by
rules, not by model judgment — "Use deterministic/configurable rules where
practical... LLM judgment may assist evaluation but must not control
permission."
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from opportunity_store import OpportunityStore, new_fingerprint

log = logging.getLogger("relevance")

_FIT_SCORE = {"strong": 1.0, "moderate": 0.6, "weak": 0.2, None: 0.4}
_VALUE_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.3, None: 0.4}
_COMPLEXITY_PENALTY = {"low": 0.0, "moderate": 0.15, "high": 0.3, None: 0.15}
_EVIDENCE_SCORE = {"conclusive": 1.0, "strong": 0.8, "moderate": 0.5, "weak": 0.2}


@dataclass
class RelevanceVerdict:
    passes_investigate: bool
    passes_surface: bool
    score: float
    reasons: list[str]
    is_duplicate: bool
    duplicate_of: Optional[str] = None
    duplicate_disposition: Optional[str] = None  # decision recorded on the prior record


class RelevanceGate:
    """Deterministic scoring + dedup against opportunity history."""

    def __init__(self, evolution_config: dict[str, Any], store: OpportunityStore):
        self.config = evolution_config
        self.store = store

    def score_candidate(self, candidate: dict[str, Any]) -> float:
        """Weighted, bounded [0, 1] score from fit/value/complexity/evidence.
        Deliberately simple and inspectable — no hidden model weighting."""
        fit = _FIT_SCORE.get(candidate.get("fit"), _FIT_SCORE[None])
        value = _VALUE_SCORE.get(candidate.get("value"), _VALUE_SCORE[None])
        complexity_penalty = _COMPLEXITY_PENALTY.get(candidate.get("complexity"), _COMPLEXITY_PENALTY[None])
        evidence = _EVIDENCE_SCORE.get(candidate.get("evidence_strength", "weak"), 0.2)

        score = (0.35 * fit) + (0.35 * value) + (0.30 * evidence) - complexity_penalty
        return max(0.0, min(1.0, round(score, 3)))

    def check_duplicate(self, candidate: dict[str, Any]) -> tuple[bool, Optional[dict[str, Any]]]:
        """Section 17: don't resurface the same repo/concept/idea unless
        meaningful new evidence changes the assessment (a higher score than
        last time, after the reconsideration window)."""
        fingerprint = candidate.get("fingerprint") or new_fingerprint(
            candidate.get("title", ""), candidate.get("source", ""), candidate.get("discovery_source", "internal")
        )
        existing = self.store.find_by_fingerprint(fingerprint)
        if not existing:
            return False, None

        state = existing.get("lifecycle_state")
        if state not in ("watching", "rejected"):
            # Already discovered/investigating/proposed/approved/implementing/
            # verifying/learned — it's already tracked, never resurface as a
            # brand-new discovery. Only "watching" (premature) and
            # "rejected" (not useful, at the time) get reconsidered below.
            return True, existing

        reconsider_days = self.config.get("dedup_reconsideration_days", 21)
        updated_at = existing.get("updated_at")
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)).days if updated_at else 0
        except ValueError:
            age_days = 0

        prior_score = existing.get("relevance_score") or 0.0
        new_score = self.score_candidate(candidate)
        meaningfully_better = new_score > prior_score + 0.1

        if state == "rejected" and not meaningfully_better:
            return True, existing
        if state == "watching" and age_days < reconsider_days and not meaningfully_better:
            return True, existing

        return False, existing

    def evaluate(self, candidate: dict[str, Any]) -> RelevanceVerdict:
        reasons: list[str] = []
        is_dup, existing = self.check_duplicate(candidate)
        if is_dup:
            return RelevanceVerdict(
                passes_investigate=False,
                passes_surface=False,
                score=existing.get("relevance_score") or 0.0,
                reasons=[f"Duplicate of {existing.get('opportunity_id')} "
                         f"(state={existing.get('lifecycle_state')}) — no meaningful new evidence"],
                is_duplicate=True,
                duplicate_of=existing.get("opportunity_id"),
                duplicate_disposition=existing.get("lifecycle_state"),
            )

        score = self.score_candidate(candidate)
        min_investigate = self.config.get("min_relevance_score_to_investigate", 0.5)
        min_surface = self.config.get("min_relevance_score_to_surface", 0.65)

        if not candidate.get("why_relevant"):
            reasons.append("No why_relevant evidence — cannot pass relevance gate on popularity/novelty alone")
            return RelevanceVerdict(False, False, score, reasons, False)

        passes_investigate = score >= min_investigate
        passes_surface = score >= min_surface
        reasons.append(f"score={score} (investigate>={min_investigate}, surface>={min_surface})")
        return RelevanceVerdict(passes_investigate, passes_surface, score, reasons, False)


def shortlist(candidates: list[dict[str, Any]], gate: RelevanceGate, max_shortlist: int) -> list[tuple[dict[str, Any], RelevanceVerdict]]:
    """Cheap filter -> dedup -> shortlist (section 42). Only the top N
    investigate-eligible, non-duplicate candidates proceed to the expensive
    investigation step."""
    scored = []
    for c in candidates:
        verdict = gate.evaluate(c)
        if verdict.passes_investigate and not verdict.is_duplicate:
            scored.append((c, verdict))
    scored.sort(key=lambda pair: pair[1].score, reverse=True)
    return scored[:max_shortlist]
