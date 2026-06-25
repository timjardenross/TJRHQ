"""Leadership Intelligence Brief (USS-TJR-MSN-0082 WP6/WP7).

Converts the ship's captured learning — leadership- and operational-resilience-
classified outcome candidates plus recent lessons — into an INTERNAL leadership
insight product for the Captain and the ANZ leadership context.

Pure composition (takes already-gathered data, returns the brief string), mirroring
weekly.py — no new store, no network here. INTERNAL ONLY: this is a reflection
product for leadership audiences; it is never published externally and contains no
sensitive personal/health content (those classifications are excluded upstream by
get_content_candidates).
"""

from __future__ import annotations

from collections import Counter
from datetime import date

OFFICER = "Communications & Presence Officer"

# WP5 leadership insight categories the brief can surface (from the content
# classifications + lesson themes the ship actually produces).
LEADERSHIP_CATEGORIES = (
    "operational_resilience", "leadership", "workload", "capacity", "change",
    "communication", "decision_quality", "recovery", "organisational_learning",
)

# Which content_classifications feed the leadership brief (internal leadership lens).
_LEADERSHIP_CLASSES = ("leadership", "operational_resilience")


def _label(cls: str) -> str:
    return (cls or "").replace("_", " ").title()


def compose_leadership_brief(candidates: list, lessons: list, *,
                             date_str: str | None = None, limit: int = 6) -> str:
    """WP6: the recurring Leadership Insight brief. Pure.

    ``candidates`` are outcome content candidates (dicts) already filtered to the
    leadership lens and free of sensitive/not_for_publication items.
    ``lessons`` are recent lessons_learned rows (dicts).
    """
    d = date_str or date.today().strftime("%a %d %b %Y")
    lead = [c for c in (candidates or [])
            if c.get("content_classification") in _LEADERSHIP_CLASSES]

    lines = [
        f"*Weekly Leadership Insight — {d}*  _(internal — for leadership reflection; not published)_",
        f"_{OFFICER} · \"What should leaders know?\"_",
        "",
    ]

    if not lead and not lessons:
        lines += [
            "No leadership insights surfaced yet.",
            "_As outcomes are captured with a leadership / operational-resilience lens, "
            "insights appear here automatically. Capture closes the gap._",
        ]
        return "\n".join(lines)

    if lead:
        lines.append("*Leadership & resilience insights — evidence-backed:*")
        for i, c in enumerate(lead[:limit], 1):
            cls = c.get("content_classification")
            insight = (c.get("reusable_insight") or "").strip()
            lines.append(f"{i}. *{c.get('title', 'Untitled')}* — _{_label(cls)}_")
            if insight:
                lines.append(f"     ↳ {insight[:160]}")
            lines.append(f"     ↳ _(source {c.get('source_type')}:{c.get('source_id')})_")
        themes = Counter(c.get("content_classification") for c in lead)
        lines += ["", "*Themes:* " + " · ".join(f"{_label(k)} ({n})" for k, n in themes.most_common())]

    if lessons:
        lines += ["", "*Reusable leadership lessons:*"]
        for ls in lessons[:limit]:
            title = ls.get("title") or ls.get("lesson_id") or "Lesson"
            guidance = (ls.get("future_guidance") or "").strip()
            lines.append(f"• {title}" + (f" — _{guidance[:120]}_" if guidance else ""))

    lines += [
        "",
        f"_Generate an internal draft with `/comms draft <n>` (executive insight / leadership note / "
        f"resilience observation). {OFFICER} scaffolds; the Captain approves. Internal audiences only._",
    ]
    return "\n".join(lines)
