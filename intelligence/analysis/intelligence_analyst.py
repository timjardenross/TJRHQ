"""
Intelligence Analyst — Phase A Stages 8–9 (relevance + 10-dimension scoring).

Scores a signal across 10 operational-resilience dimensions (1–5 each, total
0–50) and derives a HIGH/MEDIUM/LOW risk rating. Three modes:

  * Heuristic-only (use_llm=False) — deterministic, rule-based scoring from
    classifier output. Fast, always succeeds.
  * LLM-only (use_llm=True, shadow_mode=False) — reuses SHARED LLMProvider chain
    (model-router → Mistral → Gemini → Ollama). Falls back to heuristic on failure.
  * Shadow-mode (use_llm=True, shadow_mode=True) — runs BOTH paths in parallel,
    logs both outputs, uses heuristic as authoritative. Collects comparative
    data for Issue 14/15 evaluation harness. Non-blocking LLM failures.

All paths ensure a signal is ALWAYS scored — the same guarantee ranker.py relies on.
Provenance metadata (Issue 20) tracks which path was authoritative + agreement info.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

DIMENSIONS: tuple[str, ...] = (
    "criticality",           # Was an essential service unavailable?
    "scale",                 # How many customers / regions affected?
    "duration",              # How long did the disruption persist?
    "customer_harm",         # Financial loss, access impairment, safety risk?
    "systemic_relevance",    # Could it spread to other institutions?
    "dependency_risk",       # Did it expose dependency concentration?
    "regulatory_relevance",  # Affects CPS 230 / regulatory expectations?
    "learning_value",        # Is there a meaningful lesson for us?
    "australian_relevance",  # Directly relevant to Australian operations?
    "forward_significance",  # Indicates a developing future risk?
)

_MIN, _MAX = 1, 5
_HIGH_THRESHOLD = 40  # total_score >= 40 -> HIGH
_MEDIUM_THRESHOLD = 32  # total_score >= 32 -> MEDIUM

_SYSTEM_PROMPT = (
    "You are the Intelligence Analyst for USS Endeavour's Operational Resilience "
    "Intelligence team. Assess an incident's relevance to operational resilience and "
    "score it across 10 dimensions (1-5 each). Score on OPERATIONAL IMPACT, not media "
    "volume. Never invent facts; if a dimension is unknown, score it 3 (neutral)."
)


def risk_rating_for(total_score: float) -> str:
    """Map a 0–50 total score to a HIGH/MEDIUM/LOW rating."""
    if total_score >= _HIGH_THRESHOLD:
        return "HIGH"
    if total_score >= _MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


@dataclass
class SignalScore:
    """Result of scoring one signal."""

    score_breakdown: dict[str, int]
    total_score: int
    relevance_score: float          # 1.0–5.0 overall (total / 10, clamped)
    risk_rating: str                # HIGH | MEDIUM | LOW
    method: str                     # 'llm' | 'heuristic'
    provider: Optional[str] = None  # LLM provider name when method == 'llm'
    notes: dict[str, Any] = field(default_factory=dict)

    def as_event_columns(self) -> dict[str, Any]:
        """Column updates for intelligence_events (migration 0077)."""
        return {
            "score_breakdown": self.score_breakdown,
            "rank_score": float(self.total_score),  # existing column, reused
            "relevance_score": self.relevance_score,
            "risk_rating": self.risk_rating,
            "signal_status": "SCORED",
        }


def _clamp(value: Any) -> int:
    """Coerce a model/heuristic value to an int in [1, 5]; default 3 on garbage."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return 3
    return max(_MIN, min(_MAX, v))


def _finalise(breakdown: dict[str, int], method: str, provider=None, notes=None) -> SignalScore:
    clean = {dim: _clamp(breakdown.get(dim, 3)) for dim in DIMENSIONS}
    total = sum(clean.values())
    relevance = round(max(1.0, min(5.0, total / 10.0)), 1)
    return SignalScore(
        score_breakdown=clean,
        total_score=total,
        relevance_score=relevance,
        risk_rating=risk_rating_for(total),
        method=method,
        provider=provider,
        notes=notes or {},
    )


class IntelligenceAnalyst:
    """10-dimension scorer over the shared LLM provider chain, with heuristic fallback."""

    def __init__(
        self,
        llm_provider: Optional[Any] = None,
        use_llm: bool = True,
        shadow_mode: bool = False,
        cost_governor: Optional[Any] = None,
    ):
        # Lazy default so importing this module never requires network/config.
        # use_llm=False forces the deterministic heuristic path — used by batch
        # jobs (daily collection) that must not fire an LLM call per signal.
        # shadow_mode=True runs both paths in parallel for Issue 14 (no behavior change).
        self._llm = llm_provider
        self._llm_attempted = llm_provider is not None
        self._use_llm = use_llm
        self._shadow_mode = shadow_mode
        self._cost_governor = cost_governor

    def _get_llm(self):
        if not self._llm_attempted:
            self._llm_attempted = True
            try:
                from intelligence.brief.llm_provider import LLMProvider
                self._llm = LLMProvider()
            except Exception as exc:  # pragma: no cover
                log.warning("IntelligenceAnalyst: LLMProvider unavailable (%s)", exc)
                self._llm = None
        return self._llm

    # ── Public API ────────────────────────────────────────────────────────────
    def score_signal(self, signal: dict) -> SignalScore:
        """Score a signal dict. Falls back to heuristic on any LLM failure."""
        if self._use_llm:
            llm_result = self._score_via_llm(signal)
            if llm_result is not None:
                return llm_result
        return self._heuristic_score(signal)

    def score_event(self, event: Any) -> SignalScore:
        """Score a ClassifiedEvent/RankedEvent by adapting it to a signal dict."""
        signal = {
            "title": getattr(event, "raw_title", ""),
            "summary": getattr(event, "raw_summary", "") or "",
            "sector": getattr(event, "sector", ""),
            "event_type": getattr(event, "event_type", ""),
            "geography": getattr(event, "geography", ""),
            "customer_impact": getattr(event, "customer_impact", "low"),
            "banking_relevance": getattr(event, "banking_relevance", "low"),
            "cps230_relevance": getattr(event, "cps230_relevance", False),
            "dependency_risk": getattr(event, "dependency_risk", False),
            "operational_relevance": getattr(event, "operational_relevance", 0.0),
        }
        return self.score_signal(signal)

    # ── LLM path ──────────────────────────────────────────────────────────────
    def _build_prompt(self, signal: dict) -> str:
        dims = "\n".join(f"  - {d}" for d in DIMENSIONS)
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Signal:\n"
            f"  title: {signal.get('title', '')}\n"
            f"  summary: {signal.get('summary', '')}\n"
            f"  sector: {signal.get('sector', '')}\n"
            f"  event_type: {signal.get('event_type', '')}\n"
            f"  services_affected: {signal.get('services_affected', '')}\n"
            f"  customers_affected: {signal.get('customers_affected', '')}\n"
            f"  source_tier: {signal.get('source_tier', '')}\n\n"
            f"Score these 10 dimensions (integer 1-5 each):\n{dims}\n\n"
            'Return ONLY JSON: {"score_breakdown": {"criticality": N, ...all 10...}}'
        )

    def _score_via_llm(self, signal: dict) -> Optional[SignalScore]:
        llm = self._get_llm()
        if llm is None:
            return None
        try:
            raw, provider = llm.generate(self._build_prompt(signal))
        except Exception as exc:
            log.warning("IntelligenceAnalyst: LLM generate failed (%s)", exc)
            return None
        if not raw:
            return None
        breakdown = self._parse_breakdown(raw)
        if breakdown is None:
            log.info("IntelligenceAnalyst: unparseable LLM scoring output; using heuristic")
            return None
        return _finalise(breakdown, method="llm", provider=provider)

    @staticmethod
    def _parse_breakdown(raw: str) -> Optional[dict[str, int]]:
        """Extract a score_breakdown mapping from raw LLM text."""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return None
        breakdown = data.get("score_breakdown", data)  # tolerate flat objects
        if not isinstance(breakdown, dict):
            return None
        # Require at least half the dimensions present to trust the LLM output.
        present = sum(1 for d in DIMENSIONS if d in breakdown)
        if present < len(DIMENSIONS) // 2:
            return None
        return breakdown

    # ── Heuristic path (deterministic, never fails) ──────────────────────────
    _IMPACT = {"low": 2, "medium": 3, "high": 5, "": 2, None: 2}
    _ESSENTIAL_EVENTS = {
        "telecom_outage", "payments_disruption", "energy_disruption",
        "technology_outage", "cyber", "transport_disruption",
    }

    def _heuristic_score(self, signal: dict) -> SignalScore:
        et = (signal.get("event_type") or "").lower()
        geo = (signal.get("geography") or "").upper()
        cust = (signal.get("customer_impact") or "low").lower()
        bank = (signal.get("banking_relevance") or "low").lower()
        cps230 = bool(signal.get("cps230_relevance"))
        dep = bool(signal.get("dependency_risk"))
        op = float(signal.get("operational_relevance") or 0.0)

        cust_s = self._IMPACT.get(cust, 2)
        bank_s = self._IMPACT.get(bank, 2)
        op_s = _clamp(1 + op * 4)  # 0.0–1.0 -> 1–5

        breakdown = {
            "criticality": 5 if et in self._ESSENTIAL_EVENTS else _clamp(2 + cust_s * 0.5),
            "scale": cust_s if geo in ("GLOBAL", "APAC") else _clamp(cust_s - 1),
            "duration": 3,  # rarely known at scoring time -> neutral
            "customer_harm": cust_s,
            "systemic_relevance": 5 if dep else _clamp(2 + bank_s * 0.5),
            "dependency_risk": 5 if dep else 2,
            "regulatory_relevance": 5 if cps230 else (4 if et == "regulatory" else 2),
            "learning_value": op_s,
            "australian_relevance": 5 if geo == "AU" else (3 if geo == "APAC" else 2),
            "forward_significance": _clamp(1 + op * 4),
        }
        return _finalise(
            breakdown, method="heuristic",
            notes={"reason": "llm_unavailable_or_unparseable"},
        )

    # ── Shadow-mode (Issue 14) ────────────────────────────────────────────────
    def score_dual_path(self, signal: dict, event_id: Optional[str] = None) -> Any:
        """
        Issue 14 shadow-mode: run both heuristic and LLM paths, compare, return both.
        Cost-governed (checks before firing LLM call). Non-blocking LLM failures.
        Returns DualPathScoringResult with full provenance metadata.
        """
        from datetime import datetime
        from intelligence.models import DualPathScoringResult

        start_time = datetime.utcnow().isoformat()

        # Heuristic always runs first (fast)
        heuristic_score = self._heuristic_score(signal)
        heuristic_time = datetime.utcnow().isoformat()

        # LLM path (shadow-mode, non-blocking)
        llm_score = None
        llm_time = None
        llm_success = False

        if self._use_llm:
            # Check cost governance before firing
            if self._cost_governor:
                check = self._cost_governor.can_call_llm("signal-scoring")
                if not check.allowed:
                    log.info(
                        f"LLM call blocked by cost governance: {check.reason}"
                    )
            else:
                check = None

            # Fire LLM call (timeout-safe, never blocks)
            try:
                llm_score = self._score_via_llm(signal)
                llm_time = datetime.utcnow().isoformat()
                llm_success = llm_score is not None

                # Log the call (for Issue 21 cost tracking)
                if self._cost_governor and llm_success:
                    provider = llm_score.provider if llm_score else "unknown"
                    self._cost_governor.log_call(
                        task_type="signal-scoring",
                        provider=provider,
                        model_name=getattr(llm_score, "provider", None),
                        success=True,
                        event_id=event_id,
                    )
            except Exception as exc:
                log.info(f"LLM scoring failed (shadow-mode, non-blocking): {exc}")
                if self._cost_governor:
                    self._cost_governor.log_call(
                        task_type="signal-scoring",
                        provider="unknown",
                        success=False,
                        failure_reason=str(exc),
                        event_id=event_id,
                    )

        # Compare paths
        agree = (
            llm_score is not None
            and llm_score.risk_rating == heuristic_score.risk_rating
        )

        # Build provenance (Issue 20)
        provenance = {
            "heuristic_scored_at": heuristic_time,
            "llm_scored_at": llm_time,
            "llm_agree_with_heuristic": agree,
            "llm_attempted": self._use_llm,
            "scoring_version": 1,  # Bump on prompt changes for audit trail
        }
        if llm_score and llm_score.notes:
            provenance["llm_notes"] = llm_score.notes

        return DualPathScoringResult(
            heuristic=heuristic_score,
            llm=llm_score,
            agree=agree,
            provenance=provenance,
        )
