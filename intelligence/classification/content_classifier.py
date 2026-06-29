"""
Content classifier — scores existing intelligence_events for content relevance.

Reads from the intelligence_events + intelligence_source_registry tables,
adds a content-specific interpretation layer:
  - pillar_key / pillar_name   which of the 8 thought-leadership pillars
  - content_relevance          0–1 content strategy fit
  - captain_focus              aligns with active missions / priority keywords
  - suggested_angle            one-line framing angle for the Captain

This is NOT a new ingestion path. It re-interprets events already collected
by the ORI pipeline. No new HTTP calls, no new adapters.

Usage:
    from intelligence.classification.content_classifier import score_for_content
    result = score_for_content(event, active_mission_keywords)
"""

from __future__ import annotations

import re
import sys
import os
from dataclasses import dataclass
from typing import Optional

# Allow running from repository root; slack-bot uses a hyphen in the directory name
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "slack-bot", "lib"))

from comms.pillars import classify_pillar, PILLARS_BY_KEY  # type: ignore


@dataclass
class ContentScore:
    """Output of score_for_content()."""
    event_id_text: str          # intelligence_events.event_id (text PK)
    source_name: str
    pillar_key: str
    pillar_name: str
    content_relevance: float    # 0–1
    captain_focus: bool
    suggested_angle: str
    raw_title: str              # passed through for display without extra join
    raw_summary: Optional[str]
    canonical_url: Optional[str]
    collected_at: str           # ISO string — from the source event
    useful_life_days: int       # from source registry; used by content_ranker


# ── Captain focus keywords ────────────────────────────────────────────────────
# Broad set; mission-specific keywords are passed in at call time.
_CAPTAIN_FOCUS_BASE = [
    "operational resilience", "resilience", "cps 230", "ai", "leadership",
    "decision", "coaching", "performance", "continuity", "governance",
    "endeavour", "ai-augmented", "personal operating", "future of work",
    "thought leadership", "human performance", "wellness",
]


def score_for_content(
    event: dict,
    active_mission_keywords: Optional[list[str]] = None,
    useful_life_days: int = 14,
) -> Optional[ContentScore]:
    """
    Score a single intelligence_events row for content relevance.

    Args:
        event: raw dict from intelligence_events table
        active_mission_keywords: additional keywords from active missions/priorities
        useful_life_days: useful life for recency decay (from source registry)

    Returns:
        ContentScore if the event passes minimum threshold, else None.
    """
    text = f"{event.get('raw_title', '')} {event.get('raw_summary', '') or ''}"

    # ── Pillar classification ──────────────────────────────────────────────────
    pillar, pillar_score = classify_pillar(text)

    # Wellness is for personally-authored content only. External intelligence
    # events should never drive it — too many false positives from tech/ops
    # sources that mention health/recovery tangentially.
    if pillar.key == "wellness_sustainable_performance":
        return None

    # ── Content relevance ──────────────────────────────────────────────────────
    # Base: pillar match strength (0–5 typical, cap at 1.0)
    relevance = min(1.0, pillar_score * 0.20)

    # Boost: source confidence weight reflects editorial quality
    src_weight = float(event.get("source_confidence_weight") or 0.5)
    relevance = min(1.0, relevance + src_weight * 0.30)

    # Boost: high operational relevance events tend to have content value
    op_rel = float(event.get("operational_relevance") or 0.0)
    relevance = min(1.0, relevance + op_rel * 0.15)

    # Boost: cross-source confirmation raises confidence
    rank_score = float(event.get("rank_score") or 0.0)
    if rank_score > 60:
        relevance = min(1.0, relevance + 0.10)
    elif rank_score > 40:
        relevance = min(1.0, relevance + 0.05)

    # Require actual pillar keyword alignment — source weight alone should not
    # qualify an event. Without this, earthquake data and road-name records from
    # non-OR sources can slip through on source confidence weight alone.
    if pillar_score == 0:
        return None

    # ── Captain focus ─────────────────────────────────────────────────────────
    text_lower = text.lower()
    focus_keywords = _CAPTAIN_FOCUS_BASE + (active_mission_keywords or [])
    captain_focus = any(kw.lower() in text_lower for kw in focus_keywords)

    # ── Suggested angle ────────────────────────────────────────────────────────
    suggested_angle = _derive_angle(
        pillar_key=pillar.key,
        pillar_name=pillar.name,
        text=text,
        event_type=event.get("event_type", ""),
        captain_focus=captain_focus,
    )

    return ContentScore(
        event_id_text=event["event_id"],
        source_name=event.get("source_name", ""),
        pillar_key=pillar.key,
        pillar_name=pillar.name,
        content_relevance=round(relevance, 3),
        captain_focus=captain_focus,
        suggested_angle=suggested_angle,
        raw_title=event.get("raw_title", ""),
        raw_summary=event.get("raw_summary"),
        canonical_url=event.get("canonical_url"),
        collected_at=event.get("collected_at", ""),
        useful_life_days=useful_life_days,
    )


# ── Angle derivation ──────────────────────────────────────────────────────────

_ANGLE_TEMPLATES: dict[str, list[tuple[list[str], str]]] = {
    "operational_resilience": [
        (["outage", "disruption", "incident"], "Lessons from this disruption for building resilient operations"),
        (["regulation", "compliance", "apra"], "What this regulatory signal means for resilience practitioners"),
        ([], "Operational resilience: what this signal means for leaders"),
    ],
    "business_continuity": [
        (["cps 230", "cps230", "apra"], "CPS 230 lens: how this regulatory development shapes continuity practice"),
        (["third party", "vendor", "outsourced"], "Third-party resilience: what this signal means for BCPs"),
        ([], "Business continuity insight: what practitioners should notice here"),
    ],
    "human_performance": [
        (["burnout", "stress", "fatigue", "load"], "Human capacity under pressure: the leadership angle"),
        (["performance", "focus", "productivity"], "Performance sustainability: a practitioner's take"),
        ([], "Human performance lens: why this matters for high-performing leaders"),
    ],
    "wellness_sustainable_performance": [
        (["sleep", "recovery", "rest"], "The recovery science behind sustained performance"),
        (["coaching", "wellness", "wellbeing"], "Coaching perspective: applying this in practice"),
        ([], "Sustainable performance: translating this signal into practice"),
    ],
    "ai_augmented_leadership": [
        (["ai", "llm", "agent", "automation"], "AI leadership: what this development means for executives adopting AI"),
        (["risk", "governance"], "AI governance: the accountability angle senior leaders must own"),
        ([], "AI-augmented leadership: what this signal means for the next wave of leaders"),
    ],
    "personal_operating_systems": [
        (["system", "command", "workflow", "governance"], "Personal operating systems: the systems-thinking angle"),
        ([], "Running your work like a well-governed system: a practical angle"),
    ],
    "future_of_work": [
        (["remote", "team", "org", "talent"], "Future of work: the operating model implication"),
        (["automation", "ai", "productivity"], "The automation era: what this means for how we work"),
        ([], "Future of work: what this signal means for the evolving professional landscape"),
    ],
    "decision_quality_governance": [
        (["decision", "judgement", "judgment", "approval"], "Decision quality: the systemic angle leaders miss"),
        (["governance", "board", "review"], "Governance insight: how this shapes better decision architecture"),
        ([], "Decision quality: translating this signal into better leadership practice"),
    ],
}


def _derive_angle(
    pillar_key: str,
    pillar_name: str,
    text: str,
    event_type: str,
    captain_focus: bool,
) -> str:
    text_lower = text.lower()
    templates = _ANGLE_TEMPLATES.get(pillar_key, [])
    for keywords, angle in templates:
        if not keywords or any(kw in text_lower for kw in keywords):
            suffix = " (captain-focus signal)" if captain_focus else ""
            return angle + suffix
    return f"Angle: {pillar_name} — how this connects to what practitioners need to hear"
