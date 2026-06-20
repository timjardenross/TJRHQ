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
    from lib.comms import opportunities as opp, formats, weekly, pillars, portfolio, drafting
    from lib.human_systems import safety
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import opportunities as opp, formats, weekly, pillars, portfolio, drafting  # type: ignore
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
    if cmd in ("send", "test-send", "push"):
        return safety.frame(_send(), with_footer=False)
    return safety.frame(_help(), with_footer=False)


def _help() -> str:
    return (
        "*Communications & Presence Officer — the ship's external voice.*\n"
        "I turn what the ship already knows into publishable influence. The Captain "
        "always writes, edits, and publishes.\n\n"
        "• `/comms weekly` — \"What should I be talking about this week?\"\n"
        "• `/comms opportunities` — publishable opportunities mined from Command Memory\n"
        "• `/comms draft <n> [format]` — an AI first draft (Gemini) for opportunity n\n"
        "• `/comms send` — deliver the weekly influence brief now (Slack + Telegram)\n"
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
    # Generate a first-draft prose piece via the shared LLM client; degrade to the
    # deterministic scaffold when no LLM is configured (WP8).
    mode, body = drafting.generate_draft(o, fmt_key or o.suggested_format)
    # Record the draft intent in the content lifecycle (non-blocking).
    try:
        portfolio.record_content(
            content_id=f"{o.source_kind}-{o.source_ref}", title=o.title, pillar=o.pillar_key,
            source_kind=o.source_kind, source_ref=o.source_ref, classification=o.classification,
            status="draft", fmt=(fmt_key or o.suggested_format), strategic_domain=o.strategic_domain,
            notes=f"draft_mode={mode}",
        )
    except Exception:  # pragma: no cover
        pass
    return body


def _pillars() -> str:
    lines = ["*Thought Leadership Pillars*", ""]
    for p in pillars.PILLARS:
        lines.append(f"• *{p.name}* — {p.audience}")
        lines.append(f"    ↳ _{p.key_message}_ · advances {p.strategic_domain}")
    return "\n".join(lines)


def _send() -> str:
    """Deliver the Weekly Thought Leadership Brief now to the configured bot(s).

    Reuses the scheduler's comms_weekly job + the shared delivery fan-out, so the
    brief goes to whichever surfaces are set (Slack DM and/or Telegram). On-demand
    equivalent of the Monday cron — for the Captain or the VM operator."""
    try:
        from human_systems_scheduler import run_job
        from lib.human_systems import delivery
    except Exception:  # pragma: no cover
        from slack_bot.human_systems_scheduler import run_job  # type: ignore
        from slack_bot.lib.human_systems import delivery  # type: ignore

    client = delivery.get_slack_client()
    channel = delivery.captain_channel()
    tg_token, tg_chat = delivery.telegram_config()
    if not channel and not (tg_token and tg_chat):
        return ("*Nothing sent* — no delivery surface is configured. Set "
                "`HUMAN_SYSTEMS_CHANNEL` (Slack) and/or `TELEGRAM_BOT_TOKEN` + "
                "`TELEGRAM_CHAT_ID` (Telegram), then try `/comms send` again.")

    report = run_job("comms_weekly", client=client, channel=channel, dry_run=False)
    if report.get("skipped"):
        return ("*Nothing to send* — no publishable opportunities right now. "
                "That's the system staying quiet by design.")
    if report.get("delivered"):
        return f"*Weekly influence brief sent* → {report.get('channel')}."
    return (f"*Couldn't deliver* — {report.get('error') or 'no surface available'}. "
            "Check the bot token(s) and recipient config.")


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
