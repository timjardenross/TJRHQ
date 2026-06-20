"""/comms — Communications & Presence Officer (USS-TJR-MSN-COMMS-001 WP5 pull).

The Captain-pulled surface for the ship's external voice. Reuses the Content
Opportunity Engine (live over Command Memory), the thought-leadership pillars, the
draft scaffolder, and the weekly influence brief. Read/scaffold only — the Captain
writes, edits, and publishes.

    handle_comms(text, user_id=None, channel_id=None) -> str

Subcommands: weekly (default) · opportunities · draft <n> [format] · pillars ·
portfolio.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from lib.comms import opportunities as opp, formats, weekly, pillars, portfolio
    from lib.human_systems import safety
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import opportunities as opp, formats, weekly, pillars, portfolio  # type: ignore
    from slack_bot.lib.human_systems import safety  # type: ignore


def handle_comms(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    raw = (text or "").strip()
    parts = raw.split(maxsplit=1)
    cmd = (parts[0].lower() if parts else "")
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("", "weekly", "brief"):
        return safety.frame(_weekly(), with_footer=False)
    if cmd in ("opportunities", "opps", "ideas"):
        return safety.frame(_opportunities(), with_footer=False)
    if cmd in ("draft", "write"):
        return safety.frame(_draft(rest), with_footer=False)
    if cmd in ("pillars", "themes"):
        return safety.frame(_pillars(), with_footer=False)
    if cmd in ("portfolio", "reputation"):
        return safety.frame(_portfolio(), with_footer=False)
    return safety.frame(_help(), with_footer=False)


def _help() -> str:
    return (
        "*Communications & Presence Officer — the ship's external voice.*\n"
        "I turn what the ship already knows into publishable influence. The Captain "
        "always writes, edits, and publishes.\n\n"
        "• `/comms weekly` — \"What should I be talking about this week?\"\n"
        "• `/comms opportunities` — publishable opportunities mined from Command Memory\n"
        "• `/comms draft <n> [format]` — a draft scaffold for opportunity n\n"
        "• `/comms pillars` — the eight thought-leadership themes\n"
        "• `/comms portfolio` — published reputation record + content pipeline\n\n"
        "_Reputation over reach. Intelligence first. Captain-as-publisher._"
    )


def _weekly() -> str:
    items = opp.gather_opportunities()
    return weekly.compose_weekly_brief(items)


def _opportunities() -> str:
    items = opp.gather_opportunities()
    if not items:
        return ("*Content Opportunities*\nNothing surfaced right now — as missions "
                "complete, decisions are recorded, and research lands, opportunities "
                "appear here automatically.")
    lines = ["*Content Opportunities — mined from Command Memory*", ""]
    for i, o in enumerate(items[:12], 1):
        lines.append(f"{i}. *{o.title}* — _{o.pillar_name}_ · {formats.FORMATS_BY_KEY.get(o.suggested_format).label if o.suggested_format in formats.FORMATS_BY_KEY else o.suggested_format} "
                     f"· score {o.score} _(source {o.source_kind})_")
    lines += ["", "_`/comms draft <n>` to scaffold one. Captain publishes._"]
    return "\n".join(lines)


def _draft(rest: str) -> str:
    toks = rest.split()
    if not toks or not toks[0].lstrip("#").isdigit():
        return "Which opportunity? Try `/comms draft 1` (optionally `/comms draft 1 case_study`)."
    idx = int(toks[0].lstrip("#"))
    fmt_key = toks[1] if len(toks) > 1 else None
    items = opp.gather_opportunities()
    if not (1 <= idx <= len(items)):
        return f"Opportunity {idx} isn't in range (1–{len(items)}). Try `/comms opportunities`."
    o = items[idx - 1]
    if fmt_key and fmt_key not in formats.FORMATS_BY_KEY:
        valid = ", ".join(f.key for f in formats.FORMATS)
        return f"Unknown format '{fmt_key}'. Options: {valid}."
    # Record the draft intent in the content lifecycle (non-blocking).
    try:
        portfolio.record_content(
            content_id=f"{o.source_kind}-{o.source_ref}", title=o.title, pillar=o.pillar_key,
            source_kind=o.source_kind, source_ref=o.source_ref, classification=o.classification,
            status="draft", fmt=(fmt_key or o.suggested_format), strategic_domain=o.strategic_domain,
        )
    except Exception:  # pragma: no cover
        pass
    return formats.render_format(o, fmt_key or o.suggested_format)


def _pillars() -> str:
    lines = ["*Thought Leadership Pillars*", ""]
    for p in pillars.PILLARS:
        lines.append(f"• *{p.name}* — {p.audience}")
        lines.append(f"    ↳ _{p.key_message}_ · advances {p.strategic_domain}")
    return "\n".join(lines)


def _portfolio() -> str:
    published = portfolio.fetch_portfolio(status="published")
    pipe = portfolio.pipeline_summary()
    lines = ["*Professional Reputation Portfolio*", ""]
    if published:
        for p in published[:20]:
            tag = f" _({p.pillar})_" if p.pillar else ""
            lines.append(f"• {p.title}{tag}")
    else:
        lines.append("_No published items recorded yet._")
    if pipe:
        order = ["opportunity", "draft", "approved", "published", "archived"]
        summary = " · ".join(f"{s}: {pipe[s]}" for s in order if s in pipe)
        lines += ["", f"*Pipeline:* {summary}"]
    lines += ["", "_The portfolio records what the Captain chose to publish._"]
    return "\n".join(lines)
