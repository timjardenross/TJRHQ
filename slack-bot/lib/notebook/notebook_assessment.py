"""Strategic & Portfolio Assessment (EXEC-010B WP6).

Provides scoring functions used by the Number One review (WP5).
Reuses existing strategic planning concept vocabulary — no new planning systems.

Public API:
    assess_strategic_alignment(note: dict) -> float
    compute_content_potential(note: dict) -> float
"""

from __future__ import annotations

from typing import Any

# ── Strategic alignment vocabulary ────────────────────────────────────────────
# Derived from existing strategic objective domains present in the repo.
# Update alongside strategic_objectives table as domains evolve.

_STRATEGIC_DOMAINS: list[tuple[float, list[str]]] = [
    (1.00, ["strategic objective", "okr", "north star", "mission critical", "strategic priority"]),
    (0.85, ["architecture", "capability", "platform", "foundation", "resilience"]),
    (0.75, ["delivery", "mission", "initiative", "programme", "roadmap"]),
    (0.65, ["improvement", "efficiency", "quality", "performance", "reliability"]),
    (0.50, ["operational", "process", "workflow", "coordination", "resource"]),
    (0.40, ["knowledge", "learning", "lesson", "documentation", "communication"]),
    (0.25, ["idea", "suggestion", "thought", "consideration", "explore"]),
]

_HIGH_ALIGNMENT_KEYWORDS: frozenset[str] = frozenset({
    "strategic", "objective", "goal", "priority", "direction", "vision",
    "capability", "architecture", "platform", "resilience", "foundation",
    "okr", "initiative", "programme", "roadmap", "mission",
})

_DEPRIORITISE_KEYWORDS: frozenset[str] = frozenset({
    "admin", "housekeeping", "routine", "minor", "trivial", "small",
})


def assess_strategic_alignment(note: dict[str, Any]) -> float:
    """Score a note's alignment with strategic objectives (0.0–1.0).

    Uses vocabulary matching against strategic domain tiers.
    No LLM call; deterministic and fast for daily cycle use.
    """
    content = " ".join([
        note.get("title") or "",
        note.get("raw_content") or "",
        " ".join(note.get("tags") or []),
    ]).lower()

    # Deprioritise signals
    deprioritise = sum(1 for kw in _DEPRIORITISE_KEYWORDS if kw in content)
    if deprioritise >= 2:
        return 0.10

    # Tier matching — take the best tier score
    best_score = 0.0
    for tier_score, keywords in _STRATEGIC_DOMAINS:
        matches = sum(1 for kw in keywords if kw in content)
        if matches > 0:
            # Weight by number of keyword matches within the tier
            weighted = tier_score * min(1.0, 0.5 + matches * 0.25)
            best_score = max(best_score, weighted)

    # Boost for high-alignment keyword density
    high_matches = sum(1 for kw in _HIGH_ALIGNMENT_KEYWORDS if kw in content)
    if high_matches >= 3:
        best_score = min(1.0, best_score + 0.15)

    return round(max(0.05, best_score), 2)


# ── Content potential scoring ─────────────────────────────────────────────────
# Estimates whether the note could become a communications piece (COMMS-001 reuse).

_COMMS_SIGNALS: frozenset[str] = frozenset({
    "lesson", "insight", "pattern", "principle", "learning", "discovery",
    "breakthrough", "innovation", "result", "outcome", "achievement", "impact",
})


def compute_content_potential(note: dict[str, Any]) -> float:
    """Score the note's potential as a communications/knowledge artefact (0.0–1.0).

    Reuses COMMS-001 content lifecycle signal vocabulary.
    """
    content = " ".join([
        note.get("title") or "",
        note.get("raw_content") or "",
    ]).lower()

    word_count = len(content.split())
    length_score = min(0.5, word_count / 200)

    comms_matches = sum(1 for s in _COMMS_SIGNALS if s in content)
    signal_score = min(0.5, comms_matches * 0.1)

    return round(length_score + signal_score, 2)


__all__ = [
    "assess_strategic_alignment",
    "compute_content_potential",
]
