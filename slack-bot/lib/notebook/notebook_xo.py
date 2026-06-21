"""XO Intelligence Synthesis (EXEC-010B WP7).

When notes reach READY_FOR_ROUTING, XO synthesises them into the daily brief.
Routes notebook intelligence through the existing xo_orchestrator.py synthesis
layer — notebook does not create a parallel reporting channel.

Public API:
    synthesise_notebook_items(supabase_client) -> NotebookSynthesis
    format_notebook_synthesis(synthesis: NotebookSynthesis) -> str
    inject_into_xo_brief(synthesis: NotebookSynthesis, xo_signals: list) -> list
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class NotebookSynthesis:
    ready_count: int = 0
    captain_items: list[dict[str, Any]] = field(default_factory=list)
    xo_items: list[dict[str, Any]] = field(default_factory=list)
    number_one_items: list[dict[str, Any]] = field(default_factory=list)
    officer_items: list[dict[str, Any]] = field(default_factory=list)
    knowledge_items: list[dict[str, Any]] = field(default_factory=list)
    synthesised_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def has_captain_items(self) -> bool:
        return len(self.captain_items) > 0

    @property
    def action_required(self) -> bool:
        return len(self.captain_items) > 0 or len(self.xo_items) > 0

    @property
    def summary_line(self) -> str:
        if not self.ready_count:
            return "No notebook items ready for routing."
        parts = []
        if self.captain_items:
            parts.append(f"{len(self.captain_items)} Captain")
        if self.xo_items:
            parts.append(f"{len(self.xo_items)} XO")
        if self.number_one_items:
            parts.append(f"{len(self.number_one_items)} Number One")
        return f"{self.ready_count} notebook item(s) ready: " + ", ".join(parts) + "."


def synthesise_notebook_items(supabase_client: Any) -> NotebookSynthesis:
    """Fetch READY_FOR_ROUTING notes and organise into routing buckets."""
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, classification, recommended_route, "
        "strategic_alignment_score, value_score, urgency_score, confidence_score, triage_summary"
    ).eq("status", "READY_FOR_ROUTING").order("strategic_alignment_score", desc=True).execute()

    notes: list[dict[str, Any]] = result.data or []

    synthesis = NotebookSynthesis(ready_count=len(notes))
    route_map: dict[str, list[dict[str, Any]]] = {
        "captain":    synthesis.captain_items,
        "xo":         synthesis.xo_items,
        "number_one": synthesis.number_one_items,
        "officer":    synthesis.officer_items,
        "knowledge":  synthesis.knowledge_items,
    }

    for note in notes:
        route = note.get("recommended_route") or "xo"
        bucket = route_map.get(route, synthesis.xo_items)
        bucket.append({
            "id":           note["id"],
            "title":        note.get("title") or note["raw_content"][:60],
            "classification": note.get("classification"),
            "strategic_score": note.get("strategic_alignment_score"),
            "triage_summary":  note.get("triage_summary"),
        })

    log.info("[notebook-xo] Synthesised %d notebook items for routing", len(notes))
    return synthesis


def format_notebook_synthesis(synthesis: NotebookSynthesis) -> str:
    """Format notebook synthesis as a Slack-ready section for the XO brief."""
    if not synthesis.ready_count:
        return ""

    lines = [
        "*Captain's Notebook — Routing Queue*",
        f"_{synthesis.ready_count} item(s) ready for routing_",
        "",
    ]

    if synthesis.captain_items:
        lines.append(f"*Captain Decision Required ({len(synthesis.captain_items)}):*")
        for item in synthesis.captain_items[:5]:
            lines.append(f"  :white_square_button: {item['title']}")
        lines.append("")

    if synthesis.xo_items:
        lines.append(f"*XO Action ({len(synthesis.xo_items)}):*")
        for item in synthesis.xo_items[:3]:
            lines.append(f"  :arrow_right: {item['title']}")
        lines.append("")

    if synthesis.number_one_items:
        lines.append(f"*Number One ({len(synthesis.number_one_items)}):*")
        for item in synthesis.number_one_items[:3]:
            lines.append(f"  :arrow_right: {item['title']}")
        lines.append("")

    if synthesis.knowledge_items:
        lines.append(f"_Knowledge capture: {len(synthesis.knowledge_items)} item(s)_")

    return "\n".join(lines)


def inject_into_xo_brief(
    synthesis: NotebookSynthesis,
    xo_signals: list[dict[str, Any]],
    supabase_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Inject notebook items as XO signals for xo_orchestrator.py consumption.

    Notebook items surface through the existing XO synthesis layer — not as a
    parallel channel. Call this before xo_orchestrator.synthesise_officer_outputs().
    Optionally includes pattern signals (emerging themes, stalled ideas) when
    supabase_client is provided (EXEC-010C WP8).
    """
    injected = list(xo_signals)

    for item in synthesis.captain_items:
        injected.append({
            "type":        "officer_action_required",
            "source":      "notebook",
            "title":       f"[Notebook] {item['title']}",
            "priority":    "P1",
            "mission_id":  item["id"],
            "description": item.get("triage_summary", ""),
        })

    for item in synthesis.xo_items[:5]:
        injected.append({
            "type":        "decision_package_ready",
            "source":      "notebook",
            "title":       f"[Notebook] {item['title']}",
            "priority":    "P2",
            "mission_id":  item["id"],
        })

    # Pattern signals (WP8 extension — non-blocking)
    if supabase_client is not None:
        try:
            from .notebook_patterns import detect_patterns
            patterns = detect_patterns(supabase_client, lookback_days=14)
            if patterns.emerging_themes:
                top = patterns.emerging_themes[0]
                injected.append({
                    "type":        "pattern_signal",
                    "source":      "notebook",
                    "title":       f"[Notebook Pattern] {top.theme.replace('_', ' ').title()} theme — {top.count} notes",
                    "priority":    "P3",
                    "mission_id":  None,
                    "description": f"Emerging theme across {top.count} notes in the last 14 days.",
                })
            if patterns.abandoned_ideas:
                stalled = len(patterns.abandoned_ideas)
                injected.append({
                    "type":        "pattern_signal",
                    "source":      "notebook",
                    "title":       f"[Notebook Pattern] {stalled} stalled idea(s) in triage",
                    "priority":    "P3",
                    "mission_id":  None,
                    "description": f"{stalled} note(s) in CAPTURED/OFFICER_REVIEW for >7 days without advancement.",
                })
            if patterns.opportunity_clusters:
                top_opp = patterns.opportunity_clusters[0]
                injected.append({
                    "type":        "pattern_signal",
                    "source":      "notebook",
                    "title":       f"[Notebook Opportunity] {top_opp.label} — {top_opp.count} high-value notes",
                    "priority":    "P2",
                    "mission_id":  None,
                    "description": f"Opportunity cluster: avg strategic score {top_opp.avg_strategic_score:.0%}, {top_opp.count} notes.",
                })
        except Exception as exc:
            log.warning("[notebook-xo] Pattern injection failed (non-blocking): %s", exc)

    return injected


__all__ = [
    "NotebookSynthesis",
    "synthesise_notebook_items",
    "format_notebook_synthesis",
    "inject_into_xo_brief",
]
