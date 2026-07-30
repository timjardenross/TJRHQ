#!/usr/bin/env python3
"""Compatibility wrapper for the risk and challenge officer workflow."""

from __future__ import annotations

import logging
from typing import Any, Optional
from pathlib import Path
import sys

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "supabase"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from challenge_review import run_challenge_review
from specialist_executor import SpecialistOutput

log = logging.getLogger(__name__)


def call_risk_challenge_officer(
    topic: str,
    research_type: str,
    confidence: float,
    recommendation: str,
    synthesis: str,
) -> Optional[dict[str, Any]]:
    """Return a challenge review package or None on failure."""
    try:
        primary = SpecialistOutput(
            specialist="Chief of Staff",
            routing_reason="challenge review",
            perspective=synthesis or "",
            recommendation=recommendation or "",
            sources=[],
            confidence=int(confidence * 100),
            latency_ms=0.0,
            retrieval_mode="keyword",
        )
        review = run_challenge_review(
            question=topic,
            reviewer="Chief of Staff",
            reviewer_reason=f"Research type: {research_type}",
            primary=primary,
            supporting=[],
            context={"source_paths": []},
        )
        return {
            "status": "success",
            "review": review.as_dict(),
            "agent_output": "Risk & Challenge Officer",
        }
    except Exception as exc:
        log.warning("[risk-challenge-officer] challenge review failed: %s", exc)
        return None
