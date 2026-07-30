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
    from lib.comms import opportunities as opp, formats, weekly, pillars, portfolio, drafting, leadership
    from lib.human_systems import safety
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import opportunities as opp, formats, weekly, pillars, portfolio, drafting, leadership  # type: ignore
    from slack_bot.lib.human_systems import safety  # type: ignore

# MSN-0079: sensitive-content approval gate + review/metrics surfaces. Reuses the
# outcome_capture system of record (read-only). Guarded so /comms degrades cleanly.
try:
    import sys as _sys
    _KP = str(_REPO_ROOT / "core" / "knowledge")
    if _KP not in _sys.path:
        _sys.path.insert(0, _KP)
    from outcome_capture import (  # type: ignore
        requires_approval, get_content_candidates, learning_metrics, list_lessons,
        leadership_outcomes, SENSITIVE_APPROVAL_REQUIRED,
    )
except Exception:  # pragma: no cover
    def requires_approval(_c):  # type: ignore
        return False
    def get_content_candidates(*a, **k):  # type: ignore
        return []
    def learning_metrics():  # type: ignore
        return None
    def list_lessons(*a, **k):  # type: ignore
        return []
    def leadership_outcomes(*a, **k):  # type: ignore
        return []
    SENSITIVE_APPROVAL_REQUIRED = ()  # type: ignore


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
    if cmd in ("pending", "approvals", "review"):
        return safety.frame(_pending(), with_footer=False)
    if cmd in ("metrics", "stats"):
        return safety.frame(_metrics(), with_footer=False)
    if cmd in ("leadership", "leaders", "insight"):
        return safety.frame(_leadership(), with_footer=False)
    if cmd in ("resilience", "ori-brief", "resilience-brief"):
        return safety.frame(_resilience(), with_footer=False)
    if cmd in ("patterns", "leadership-themes"):
        return safety.frame(_themes(), with_footer=False)
    return safety.frame(_help(), with_footer=False)


def _send() -> str:
    from lib.human_systems import delivery
    import human_systems_scheduler as hss

    channel = delivery.captain_channel()
    tg_token, _tg_chat = delivery.telegram_config()

    if not channel and not tg_token:
        return "No delivery surface configured. Set SLACK_CHANNEL or TELEGRAM_BOT_TOKEN."

    client = delivery.get_slack_client() if channel else None
    result = hss.run_job("comms_weekly", client=client, channel=channel)

    if result.get("skipped"):
        return "Nothing to send — no publishable opportunities found."
    if result.get("delivered"):
        ch = result.get("channel", "")
        suffix = f" ({ch})" if ch else ""
        return f"Weekly influence brief sent{suffix} — Captain to review and publish."
    return "Weekly influence brief dispatched."


def _help() -> str:
    return (
        "*Communications & Presence Officer — the ship's external voice.*\n"
        "I turn what the ship already knows into publishable influence. The Captain "
        "always writes, edits, and publishes.\n\n"
        "• `/comms weekly` — \"What should I be talking about this week?\"\n"
        "• `/comms opportunities` — publishable opportunities mined from Command Memory\n"
        "• `/comms draft <n> [format]` — a draft scaffold for opportunity n\n"
        "• `/comms pillars` — the eight thought-leadership themes\n"
        "• `/comms portfolio` — published reputation record + content pipeline\n"
        "• `/comms send` — deliver the weekly influence brief now (Slack + Telegram)\n"
        "• `/comms pending` — sensitive content awaiting Captain approval\n"
        "• `/comms metrics` — outcome & learning counts\n"
        "• `/comms leadership` — internal Leadership Insight (evidence-weighted)\n"
        "• `/comms resilience` — internal Operational Resilience brief\n"
        "• `/comms patterns` — recurring leadership themes\n\n"
        "_Reputation over reach. Intelligence first. Captain-as-publisher._"
    )


def _lead_data():
    """Fetch leadership outcomes + recent lessons (read-only, graceful)."""
    try:
        outs = leadership_outcomes(limit=50)
    except Exception:  # pragma: no cover
        outs = []
    try:
        lessons = list_lessons(limit=6)
    except Exception:  # pragma: no cover
        lessons = []
    return outs, lessons


def _leadership() -> str:
    """WP4 (MSN-0085): internal Leadership Insight — what changed / what leaders
    should know / emerging patterns / evidence-weighted recommended actions.
    Internal only; evidence + confidence shown; nothing published."""
    outs, lessons = _lead_data()
    return leadership.compose_leadership_insight(outs, lessons)


def _resilience() -> str:
    """WP3 (MSN-0085): internal Operational Resilience Brief from resilience-classified
    outcomes + operational lessons. Internal only."""
    outs, lessons = _lead_data()
    return leadership.compose_operational_resilience_brief(outs, lessons)


def _themes() -> str:
    """WP6 (MSN-0085): recurring leadership themes, evidence-tracked."""
    outs, _ = _lead_data()
    return leadership.compose_themes(leadership.derive_themes(outs))


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
    # MSN-0079: an explicit confirm/approve token is the Captain's approval for
    # sensitive content. Strip it out before parsing index/format.
    confirmed = any(t.lower() in ("confirm", "approve", "approved") for t in toks)
    toks = [t for t in toks if t.lower() not in ("confirm", "approve", "approved")]
    if not toks or not toks[0].lstrip("#").isdigit():
        return "Which opportunity? Try `/comms draft 1` (optionally `/comms draft 1 case_study`)."
    idx = int(toks[0].lstrip("#"))
    fmt_key = toks[1] if len(toks) > 1 else None
    items = opp.gather_opportunities()
    if not (1 <= idx <= len(items)):
        return f"Opportunity {idx} isn't in range (1–{len(items)}). Try `/comms opportunities`."
    o = items[idx - 1]
    # MSN-0079 WP5: sensitive classifications require explicit Captain approval
    # before a draft is generated. Block (don't generate) until confirmed.
    cls = getattr(o, "content_classification", None)
    if requires_approval(cls) and not confirmed:
        return (
            f"🔒 *Captain approval required* — this draft is classified "
            f"*{cls}* (sensitive: personal / coaching / wellness / internal).\n"
            f"It will not be generated, stored externally, or published. To proceed, "
            f"re-run with confirmation:\n`/comms draft {idx}"
            f"{(' ' + fmt_key) if fmt_key else ''} confirm`"
        )
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
    equivalent of the Monday cron — for the Captain or the VM operator.

    INTERNAL DELIVERY ONLY: targets the Captain's own Slack DM / Telegram via
    HUMAN_SYSTEMS_CHANNEL / TELEGRAM_CHAT_ID. It never posts to any external
    platform — Captain-as-publisher is preserved.
    """
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


def _pending() -> str:
    """WP6: review queue of sensitive content awaiting Captain approval.

    Lists outcome-derived candidates whose classification is sensitive
    (coaching / wellness / personal_story / internal_work). These never appear in
    the default opportunity list and are never auto-published. The Captain may:
      • approve → `/comms draft <n> confirm` (generates an internal draft only)
      • reject  → mark the outcome `not_for_publication` via record_outcome
      • defer   → leave it (it simply stays here)
    """
    try:
        cands = get_content_candidates(include_internal=True, limit=25)
    except Exception:  # pragma: no cover
        cands = []
    sensitive = [c for c in cands if requires_approval(c.get("content_classification"))]
    lines = ["*Sensitive Content — pending Captain approval*", ""]
    if not sensitive:
        lines.append("_Nothing pending. Sensitive outcomes (coaching, wellness, "
                     "personal story, internal) appear here for review before any draft._")
        return "\n".join(lines)
    for i, c in enumerate(sensitive[:25], 1):
        lines.append(f"{i}. *{c.get('title','Untitled')}* — _{c.get('content_classification')}_ "
                     f"_(source {c.get('source_type')}:{c.get('source_id')})_")
    lines += [
        "",
        "_Approve_: `/comms draft <n> confirm` (internal draft only — never published).",
        "_Reject_: mark the outcome `not_for_publication`. _Defer_: leave it here.",
        "_Human approval is mandatory; nothing here is auto-published._",
    ]
    return "\n".join(lines)


def _metrics() -> str:
    """WP7: lightweight learning metrics for the COMMS summary surface."""
    m = learning_metrics() if learning_metrics else None
    if not m or not getattr(m, "data_available", False):
        return ("*Learning Metrics*\n_Unavailable offline — connect Command Memory "
                "to see outcome/lesson counts._")
    d = m.as_dict()
    lines = ["*Learning Metrics*", ""]
    for k, v in d.items():
        lines.append(f"• {k}: *{v}*")
    lines += ["", "_Counts are read-only operational signals; nothing is published._"]
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
