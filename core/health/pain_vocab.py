"""Shared pain vocabulary (TJR Life R2 alignment, Phase 2 step 1 — readers).

Pain is captured as *pain compared with your usual baseline* (pain_state:
low / baseline / elevated / high). Older rows carry a numeric 0-10
pain_score; those stay readable but are labelled as history, never converted.

Rules for readers:
  * A missing value (None) is unknown. It must never read as 0 or "no pain".
  * A numeric value is shown only as an older (history) record.
"""
from __future__ import annotations

PAIN_STATE_LABELS = {
    "low": "Lower than usual",
    "baseline": "Around usual",
    "elevated": "Higher than usual",
    "high": "Much higher than usual",
}


def pain_state_label(state: str | None) -> str | None:
    """Label for a stored pain_state; unknown/missing -> None (not a default)."""
    if not state:
        return None
    return PAIN_STATE_LABELS.get(str(state).strip().lower())


def describe_pain(pain_state: str | None, pain_score: float | int | None = None) -> str | None:
    """One display phrase for a reading, or None when nothing was recorded.

    New data: "Pain vs usual: Higher than usual". Old numeric-only data:
    "Pain (older 0-10 record): 6/10". If both exist the state wins and the
    number is appended as history. Neither -> None.
    """
    label = pain_state_label(pain_state)
    if label:
        text = f"Pain vs usual: {label}"
        if pain_score is not None:
            text += f" (older 0-10 record: {_fmt(pain_score)}/10)"
        return text
    if pain_score is not None:
        return f"Pain (older 0-10 record): {_fmt(pain_score)}/10"
    return None


def _fmt(value: float | int) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f == int(f) else f"{f:.1f}"
