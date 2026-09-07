"""
Canonical brief rendering — one intelligence assessment, multiple delivery
formats (Sections 8-10, 26, 29).

Every function here SELECTS and lightly truncates fields already persisted
on an intelligence_briefs row. None of them call an LLM, and none of them
decide posture, what matters, or what changed independently — that
judgment was already made once, by BriefGenerator, and is stored on the
brief. Telegram's morning message and Captain's Chair's excerpt both build
on `build_morning_intelligence_view()` so neither can drift from the other
or from the canonical brief (Section 29's testable guarantee).

`brief` throughout is a plain dict shaped like an intelligence_briefs row
(as returned by Supabase/PostgREST) — brief_id, overall_risk,
executive_snapshot, top_events, forward_watch, comparison, coverage, ...
"""

from __future__ import annotations

from typing import Optional

RISK_LABEL = {"RED": "🔴 RED", "AMBER": "🟡 AMBER", "GREEN": "🟢 GREEN", "UNKNOWN": "⚪ UNKNOWN"}


def build_morning_intelligence_view(brief: Optional[dict], max_items: int = 3) -> dict:
    """The one canonical content selection for morning intelligence
    delivery. Returns a plain dict — no markup — so every channel renders
    it in its own style without re-deciding what belongs in it.
    """
    if not brief:
        return {
            "has_brief": False, "brief_id": None, "generated_at": None,
            "overall_risk": None, "executive_read": None,
            "what_matters": [], "changed": None, "watch": [],
            "coverage_note": None, "coverage_degraded": False,
        }

    top = (brief.get("top_events") or [])[:max_items]
    what_matters = [
        {"title": e.get("title"), "so_what": e.get("so_what"), "risk_rating": e.get("risk_rating")}
        for e in top
    ]

    comparison = brief.get("comparison") or None
    changed = None
    if comparison:
        changed = {
            "new": [i.get("title") for i in (comparison.get("new") or [])[:3]],
            "escalated": [i.get("title") for i in (comparison.get("escalated") or [])[:3]],
            "improved": [i.get("title") for i in (comparison.get("improved") or [])[:3]],
        }
        if not any(changed.values()):
            changed = None

    coverage = brief.get("coverage") or {}
    coverage_degraded = bool(coverage.get("degraded"))
    coverage_note = None
    if coverage_degraded:
        missing = coverage.get("missing_sources") or []
        if len(missing) == 1:
            coverage_note = "One intelligence source was unavailable during this morning collection cycle."
        elif missing:
            coverage_note = f"{len(missing)} intelligence sources were unavailable during this morning collection cycle."
        else:
            coverage_note = coverage.get("reason") or "This morning's collection cycle was degraded."

    return {
        "has_brief": True,
        "brief_id": brief.get("brief_id"),
        "generated_at": brief.get("generated_at"),
        "overall_risk": brief.get("overall_risk") or "UNKNOWN",
        "executive_read": brief.get("executive_snapshot") or brief.get("bottom_line"),
        "what_matters": what_matters,
        "changed": changed,
        "watch": (brief.get("forward_watch") or [])[:5],
        "coverage_note": coverage_note,
        "coverage_degraded": coverage_degraded,
    }


def render_telegram_morning_text(brief: Optional[dict], max_items: int = 3) -> str:
    """Plain-text rendering matching the Section 9 example shape. Callers
    that need channel-specific markup (HTML/MarkdownV2) should build on
    `build_morning_intelligence_view()` directly instead of parsing this."""
    view = build_morning_intelligence_view(brief, max_items=max_items)
    if not view["has_brief"]:
        return "Today's canonical brief has not been generated yet."

    lines = [f"Posture: {RISK_LABEL.get(view['overall_risk'], view['overall_risk'])}", ""]

    if view["what_matters"]:
        word = {1: "One thing", 2: "Two things", 3: "Three things"}.get(len(view["what_matters"]), "Things")
        lines.append(f"{word} matter today:")
        for i, item in enumerate(view["what_matters"], 1):
            line = f"{i}. {item['title']}"
            if item.get("so_what"):
                line += f" — {item['so_what']}"
            lines.append(line)
        lines.append("")

    if view["changed"]:
        lines.append("Changed since yesterday:")
        for label, key in (("New", "new"), ("Escalated", "escalated"), ("Improved", "improved")):
            for title in view["changed"].get(key) or []:
                lines.append(f"- {label}: {title}")
        lines.append("")

    if not view["what_matters"] and not view["changed"]:
        lines.append("Nothing currently requires immediate action.")
        lines.append("")

    if view["coverage_note"]:
        lines.append(view["coverage_note"])
        lines.append("")

    return "\n".join(lines).strip()


def render_captains_excerpt(brief: Optional[dict], max_items: int = 3) -> dict:
    """Structured excerpt for Captain's Chair — the same canonical
    selection as the Telegram morning message (Section 10/29)."""
    return build_morning_intelligence_view(brief, max_items=max_items)
