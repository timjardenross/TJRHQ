"""Weekly Thought Leadership Brief (COMMS-001 WP6) + daily presence line (WP5).

Answers the mission's Definition of Success — *"What should I be talking about
this week?"* — with a prioritised, evidence-backed recommendation composed from
content opportunities (live from Command Memory) and the SPC-001 strategic
objectives the content advances. Pure: takes already-gathered parts, returns the
brief string. Reuses the Daily Operating Picture composition style; no new
briefing engine.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

OFFICER = "Communications & Presence Officer"


def _fmt_label(fmt_key: str) -> str:
    return fmt_key.replace("_", " ").title()


def compose_presence_line(opportunities: list) -> str | None:
    """WP5: a single Daily Operating Picture line. None when nothing to surface."""
    pub = [o for o in opportunities if getattr(o, "is_publishable", True)]
    if not pub:
        return None
    top = pub[0]
    return (f"📡 *Presence ({OFFICER}):* {len(pub)} publishable opportunity(ies) — "
            f"top: {top.title} (_{top.pillar_name}_)")


def compose_weekly_brief(opportunities: list, *, date_str: str | None = None,
                         limit: int = 5) -> str:
    """WP6: the weekly influence brief. Pure."""
    d = date_str or date.today().strftime("%a %d %b %Y")
    pub = [o for o in opportunities if getattr(o, "is_publishable", True)]

    lines = [
        f"*Weekly Thought Leadership Brief — {d}*",
        f"_{OFFICER} · \"What should I be talking about this week?\"_",
        "",
    ]

    if not pub:
        lines += [
            "No publishable opportunities surfaced from Command Memory this week.",
            "_As missions complete, decisions are recorded, and research lands, "
            "opportunities will appear here automatically._",
        ]
        return "\n".join(lines)

    # Recommended topics (prioritised, evidence-backed).
    lines.append("*Recommended this week — prioritised, evidence-backed:*")
    for i, o in enumerate(pub[:limit], 1):
        lines.append(
            f"{i}. *{o.title}* — _{o.pillar_name}_ · suggest a *{_fmt_label(o.suggested_format)}*"
        )
        lines.append(
            f"     ↳ evidence: {o.excerpt[:140] or '(see source)'} "
            f"_(source {o.source_kind}:{o.source_ref})_"
        )
        lines.append(f"     ↳ advances: {o.strategic_domain}")

    # Themes rollup (pillar distribution).
    themes = Counter(o.pillar_name for o in pub)
    theme_str = " · ".join(f"{name} ({n})" for name, n in themes.most_common(4))
    lines += ["", f"*Themes in the pipeline:* {theme_str}"]

    # Strategic tie-in — which long-term domains this week's content advances.
    domains = Counter(o.strategic_domain for o in pub[:limit])
    dom_str = " · ".join(f"{name} ({n})" for name, n in domains.most_common())
    lines += [f"*Strategic alignment:* {dom_str}"]

    lines += [
        "",
        f"_Generate a draft with `/comms draft <n>`. {OFFICER} scaffolds; "
        "the Captain writes, edits, and publishes._",
    ]
    return "\n".join(lines)
