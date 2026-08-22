"""
Daily Digest — 2026-08-22. Combines the OSINT/world-news brief
(intelligence/brief/brief_generator.py) with the platform's own multi-domain
Captain Brief (core/platform/captain_brief_orchestrator.py) into one
LLM-synthesized educational narrative.

Two genuinely different inputs, kept parallel rather than merged into one
pipeline:
- World/OSINT events — intelligence_source_registry-backed, now broadened
  past banking-only (see intelligence/classification/filter.py's 2026-08-22
  _OR_SPECIFIC_MEDIA_CATEGORIES change). Already collected, classified,
  ranked, and narrated by brief_generator.py; this module just reads its
  persisted output.
- The platform's own core_events (health/engineering/learning/opportunities/
  operational_intelligence) — core/platform/event_bus.py's poll_events(),
  the exact same call core/context-assembly/context_service.py's
  /brief/full endpoint makes for the Captain's Brief Workbench. The
  CVE-shaped classify/rank pipeline is the wrong shape for a health or
  engineering event, so these are never forced through it — instead
  reused verbatim via assemble_captain_brief_document(), the same
  domain-grouping engine System B already runs.

Persists nothing itself — brief_generator.py already persists its own
OSINT ResilienceBrief row (auto-published, see
intelligence/persistence/intelligence_store.py:save_brief()). This
module's only job is the combined narrative text used for delivery
(Telegram — see intelligence/captains_brief.py's generate_morning_brief()).
Never raises — degrades to None on any failure so a caller's existing
per-domain formatting still works.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
from core.platform.event_bus import poll_events
from intelligence.brief.llm_provider import LLMProvider

log = logging.getLogger(__name__)

_llm = LLMProvider()

_DOMAIN_SECTIONS = (
    ("Health", "health"),
    ("Engineering", "engineering"),
    ("Learning", "learning"),
    ("Opportunities", "opportunities"),
    ("Operational Intelligence (platform)", "operational_intelligence"),
)


def _format_domain_events(doc) -> str:
    """Plain-text rollup of the platform's own multi-domain events, grouped
    by section, for the LLM prompt. Only non-empty sections are included —
    an all-empty digest is a real, common state (see BriefView.tsx's own
    "No New Signals" handling), not something to pad with invented content."""
    blocks = []
    for label, attr in _DOMAIN_SECTIONS:
        items = getattr(doc, attr, None) or []
        if not items:
            continue
        lines = "\n".join(f"- {i.reason}" for i in items[:10])
        blocks.append(f"{label}:\n{lines}")
    return "\n\n".join(blocks)


def build_daily_digest(osint_brief: Optional[dict], hours: int = 24) -> Optional[str]:
    """
    osint_brief: the latest row from intelligence_briefs (dict with
    executive_snapshot/bottom_line/emerging_themes), or None if unavailable.
    Returns one educational narrative covering every domain actually
    represented, or None if there's nothing to synthesise or the LLM chain
    is unavailable. Never raises.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        events = poll_events(since=since, limit=200)
    except Exception as exc:
        log.warning("[daily_digest] poll_events failed: %s", exc)
        events = []

    doc = None
    if events:
        try:
            doc = assemble_captain_brief_document(events)
        except Exception as exc:
            log.warning("[daily_digest] assemble_captain_brief_document failed: %s", exc)

    domain_text = _format_domain_events(doc) if doc else ""

    osint_text = ""
    if osint_brief:
        snap = osint_brief.get("executive_snapshot") or osint_brief.get("bottom_line") or ""
        themes = osint_brief.get("emerging_themes") or []
        if snap:
            osint_text = f"World/OSINT summary: {snap}"
            if themes:
                osint_text += f"\nThemes: {', '.join(str(t) for t in themes[:5])}"

    if not domain_text and not osint_text:
        return None

    prompt = (
        "Write today's educational daily digest for Captain TJR, combining the inputs "
        "below into one cohesive narrative — a few short paragraphs, plain language, "
        "explain why things matter, not just what happened. Cover every domain actually "
        "present below; don't force a section for a domain with no input.\n\n"
        f"{osint_text}\n\n{domain_text}".strip()
    )

    try:
        text, provider = _llm.generate(prompt)
    except Exception as exc:
        log.warning("[daily_digest] LLM synthesis failed: %s", exc)
        return None

    if text:
        log.info("[daily_digest] narrative generated via %s", provider)
    return text
