"""Strategic & Opportunity Intelligence — USS-TJR-MSN-0098 WP4 + WP6.

Strategic (WP4): advisor trends, confidence changes, mission delays, portfolio
health, recurring risks, operational themes — answering what should concern the
Captain, what is changing, and where opportunities exist.

Opportunity (WP6): stalled work, unused/under-used capabilities, reusable
solutions, emerging themes, strategic opportunities.

Reuse-only: signals, patterns, advisory_health, opportunities, timeline. No new
store. Advisory, non-authoritative.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import signals as _signals
import patterns as _patterns
import advisory_health as _advisory_health
import opportunities as _opportunities
import timeline as _timeline


def _portfolio_health() -> dict[str, Any]:
    """Reuse mission-outcome events as a portfolio-health proxy."""
    closures = _timeline.load_events(kinds=["mission_outcome"])
    scored = [e.score for e in closures if e.score is not None]
    avg = round(sum(scored) / len(scored), 3) if scored else None
    return {
        "closed_missions_scored": len(scored),
        "average_outcome_score": avg,
        "status": (
            "unknown" if avg is None
            else "strong" if avg >= 0.7
            else "mixed" if avg >= 0.5 else "weak"
        ),
    }


def strategic_intelligence() -> dict[str, Any]:
    sigs = _signals.emerging_signals()
    pats = _patterns.detect_patterns()
    health = _advisory_health.advisory_health()
    portfolio = _portfolio_health()

    concerns = [s.to_dict() for s in sigs if s.severity == "concern"]
    changing = [s.to_dict() for s in sigs if s.direction in ("improving", "worsening", "increasing")]
    recurring = [p.to_dict() for p in pats if p.pattern_type == "recurring_risk"]
    themes = [p.to_dict() for p in pats if p.pattern_type in ("advisor_outcome", "confidence_trend")]

    return {
        "should_concern": concerns,
        "what_is_changing": changing,
        "recurring_risks": recurring,
        "operational_themes": themes,
        "portfolio_health": portfolio,
        "advisory_health": {"status": health.get("status"), "score": health.get("score")},
        "opportunities": opportunity_intelligence()["opportunities"],
        "headline": _headline(concerns, changing, portfolio),
        "note": "Strategic intelligence — advisory only; the Captain decides.",
    }


def opportunity_intelligence() -> dict[str, Any]:
    """WP6 — opportunities as first-class intelligence (reuses opportunities.py)."""
    opps = _opportunities.detect_opportunities()
    return {
        "opportunities": [o.to_dict() for o in opps],
        "count": len(opps),
        "narrative": (
            f"{len(opps)} opportunity(ies) surfaced — stalled work, reusable solutions and "
            "emerging themes worth attention."
            if opps else "No opportunities surfaced yet (insufficient history)."
        ),
    }


def _headline(concerns, changing, portfolio) -> str:
    bits = []
    if concerns:
        bits.append(f"{len(concerns)} concern(s)")
    if changing:
        bits.append(f"{len(changing)} trend(s) changing")
    if portfolio["status"] != "unknown":
        bits.append(f"portfolio {portfolio['status']}")
    return "Strategic picture — " + ("; ".join(bits) if bits else "quiet; insufficient signal") + "."


def to_markdown() -> str:
    s = strategic_intelligence()
    L = ["# Strategic Intelligence", "", s["headline"], ""]
    if s["should_concern"]:
        L.append("## Should Concern the Captain")
        for c in s["should_concern"]:
            L.append(f"- {c['name']}: {c['detail']}")
    if s["what_is_changing"]:
        L.append("\n## What Is Changing")
        for c in s["what_is_changing"]:
            L.append(f"- {c['name']}: {c['direction']}")
    L.append(f"\n## Portfolio Health\n- {s['portfolio_health']['status']} "
             f"(avg {s['portfolio_health']['average_outcome_score']}, "
             f"n={s['portfolio_health']['closed_missions_scored']})")
    if s["opportunities"]:
        L.append("\n## Opportunities")
        for o in s["opportunities"]:
            L.append(f"- 💡 {o['opportunity_type']}: {o['message']}")
    L.append(f"\n_{s['note']}_")
    return "\n".join(L)
