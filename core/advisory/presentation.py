"""Presentation Layer — USS-TJR-MSN-0099 WP6 + WP7.

The mission's job is delivery, not compute: show the Captain *meaning, not
machinery*, and respect that attention is scarce. This module provides the
primitives every intelligence PRODUCT uses:

    WP7 — Information visibility:
        VISIBLE  → implications, evidence, recommendations, trends, opportunities
        HIDDEN   → internal scoring, confidence numbers, thresholds, rankings
    WP6 — Signal & noise:
        curate to a few items; interruption is exceptional (escalation only).

No engine, no store, no compute — pure presentation. Confidence is shown as
plain words, never numbers; ranks/scores/thresholds are stripped.
"""

from __future__ import annotations

from typing import Any, Iterable

# Machinery the Captain should never see (WP7 — hide internal mechanics).
HIDDEN_KEYS = {
    "score", "confidence_value", "rank_score", "rank", "threshold", "frequency",
    "sample_size", "samples", "accuracy", "outcome_score", "success_rate",
    "officer_ranking", "advisor_ranking", "confidence_distribution",
    "advisor_utilisation", "outcome_coverage", "relevance", "relevance_score",
    "confidence_adjustment", "severity_rank",
}


# ---------------------------------------------------------------------------
# Confidence → words (never numbers)
# ---------------------------------------------------------------------------

def humanize_confidence(value: float | None = None, band: str | None = None) -> str:
    if band:
        return {
            "High": "well-supported",
            "Medium": "reasonably supported",
            "Low": "tentative",
        }.get(band, "tentative")
    if value is None:
        return "not yet established"
    if value >= 0.75:
        return "well-supported"
    if value >= 0.5:
        return "reasonably supported"
    if value >= 0.3:
        return "tentative"
    return "unproven"


def humanize_severity(sev: str) -> str:
    return {
        "concern": "needs attention",
        "watch": "worth watching",
        "info": "for awareness",
        "escalation": "needs attention now",
        "warning": "worth watching",
        "observation": "for awareness",
    }.get((sev or "").lower(), "for awareness")


# ---------------------------------------------------------------------------
# Signal & noise (WP6)
# ---------------------------------------------------------------------------

def curate(items: Iterable[Any], limit: int) -> dict[str, Any]:
    """Keep the top ``limit`` items; report how many were suppressed."""
    items = list(items)
    shown = items[:limit]
    suppressed = max(0, len(items) - limit)
    return {"shown": shown, "suppressed": suppressed, "total": len(items)}


def interruption_class(level: str) -> str:
    """How an item should reach the Captain. Interruption is exceptional."""
    lvl = (level or "").lower()
    if lvl in ("escalation", "critical"):
        return "interrupt"      # rare — only genuine escalations
    if lvl in ("concern", "warning"):
        return "brief"          # belongs in a briefing, not an interruption
    return "silent"             # visible on demand only


def deserves_interruption(level: str) -> bool:
    return interruption_class(level) == "interrupt"


# ---------------------------------------------------------------------------
# Strip machinery (WP7)
# ---------------------------------------------------------------------------

def strip_machinery(obj: Any) -> Any:
    """Recursively remove hidden/mechanical keys so only meaning remains."""
    if isinstance(obj, dict):
        return {k: strip_machinery(v) for k, v in obj.items() if k not in HIDDEN_KEYS}
    if isinstance(obj, list):
        return [strip_machinery(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Product envelope
# ---------------------------------------------------------------------------

def product(title: str, cadence: str, sections: list[dict[str, Any]], *,
            bottom_line: str = "", note: str = "") -> dict[str, Any]:
    """Standard Captain-facing product envelope — meaning-first, machinery-free."""
    return {
        "product": title,
        "cadence": cadence,
        "sections": [s for s in sections if s.get("items") or s.get("text")],
        "bottom_line": bottom_line,
        "note": note or "Advisory only — the Captain decides. Nothing here was actioned.",
    }


def to_markdown(prod: dict[str, Any]) -> str:
    L = [f"# {prod.get('product', 'Intelligence Product')}"]
    if prod.get("bottom_line"):
        L.append("")
        L.append(f"**{prod['bottom_line']}**")
    for s in prod.get("sections", []):
        L.append("")
        L.append(f"## {s['heading']}")
        if s.get("text"):
            L.append(s["text"])
        for it in s.get("items", []):
            L.append(f"- {it}")
        if s.get("suppressed"):
            L.append(f"_(+{s['suppressed']} more held back to protect attention)_")
    L.append("")
    L.append(f"_{prod.get('note', '')}_")
    return "\n".join(L)
