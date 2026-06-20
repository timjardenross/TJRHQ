"""HSF-001 — /human-systems (alias /hs) command handler.

The Captain-pulled side of the Human Systems Framework. One command surface for
asking for help, building plans, explaining signals, reviewing trends, and
logging events across the six domains.

Public API:
    handle_human_systems(text, user_id=None, channel_id=None) -> str

The handler is pure with respect to Slack: it returns a mrkdwn string. Data is
read from the Supabase ``analytics_health_daily`` view when available, and
degrades gracefully to a no-data path when it isn't.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Package import works whether invoked as slack-bot.lib or with slack-bot on path.
try:
    from lib.human_systems import framework, push, safety, memory
    from lib.human_systems import decision, mission_load as ml, xo
except Exception:  # pragma: no cover - fallback for alternate sys.path layouts
    from slack_bot.lib.human_systems import framework, push, safety, memory  # type: ignore
    from slack_bot.lib.human_systems import decision, mission_load as ml, xo  # type: ignore


# ── Data access ───────────────────────────────────────────────────────────────

def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[human-systems] Supabase client unavailable: %s", exc)
        return None


def _fetch_rows(days: int = 7) -> list[dict]:
    """Return up to ``days`` of analytics_health_daily rows, newest first."""
    db = _make_supabase()
    if db is None or not db.is_enabled() or db.raw_client is None:
        return []
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        result = (
            db.raw_client.table("analytics_health_daily")
            .select("*")
            .gte("log_date", since)
            .order("log_date", desc=True)
            .execute()
        )
        return list(result.data or [])
    except Exception as exc:
        log.error("[human-systems] data fetch failed: %s", exc)
        return []


def _today_row(rows: list[dict]) -> dict | None:
    today = date.today().isoformat()
    for r in rows:
        if str(r.get("log_date")) == today:
            return r
    return rows[0] if rows else None


def _context(days: int = 7):
    """Shared decision-engine context: (snapshot, mission load, recent rows)."""
    rows = _fetch_rows(days=days)
    snapshot = framework.interpret_capacity(_today_row(rows))
    load = ml.get_mission_load()
    return snapshot, load, rows


# ── Help ──────────────────────────────────────────────────────────────────────

_HELP = (
    "*Human Systems — Capacity & Decision Support Officer.*\n"
    "I assess your available capacity, flag friction and overload, and give you "
    "the single highest-leverage action — so scarce capacity goes where it has the "
    "greatest operational impact, sustainably.\n\n"
    "*Decision support — what should I do about it?*\n"
    "• `/hs decide` — the single highest-leverage action right now\n"
    "• `/hs focus` — recommended focus + what to defer (capacity allocation)\n"
    "• `/hs load` — mission load vs. available capacity\n"
    "• `/hs friction` — recurring causes of capacity loss\n"
    "• `/hs capacity-review` — weekly drivers, drains, one change\n"
    "• `/hs xo <request>` — cross-domain decision (e.g. `xo make progress on coaching`)\n\n"
    "*Ask for support:*\n"
    "• `/hs today` — read today's capacity and what fits\n"
    "• `/hs plan low-capacity|recovery|movement|nutrition|mind` — build a plan\n"
    "• `/hs explain` — interpret today's signal\n"
    "• `/hs review` — weekly Human Systems review\n"
    "• `/hs log <note>` · `/hs feedback helpful|neutral|not <note>`\n"
    "• `/hs push morning|evening|weekly|degradation` — preview a proactive push\n\n"
    "_Evidence-informed and non-diagnostic. For anything medical, clinicians "
    "remain the right call._"
)


def _natural_intent(text: str) -> str | None:
    """Map a natural-language ask to a subcommand (Captain-pulled, free text)."""
    t = text.lower()
    if any(p in t for p in ("low capacity", "low-capacity", "rough day", "bad day", "struggling today")):
        return "plan low-capacity"
    if "recovery" in t or "recover" in t:
        return "plan recovery"
    if any(p in t for p in ("movement", "exercise", "move ", "walk", "workout")):
        return "plan movement"
    if any(p in t for p in ("nutrition", "eat", "food", "meal", "protein")):
        return "plan nutrition"
    if any(p in t for p in ("overwhelm", "focus", "cognitive", "mental load", "can't think")):
        return "plan mind"
    if any(p in t for p in ("what does my", "pattern suggest", "explain", "signal", "interpret")):
        return "explain"
    # Decision-support intents (HSF-002).
    if any(p in t for p in ("overload", "too many missions", "mission load", "how many missions")):
        return "load"
    if any(p in t for p in ("friction", "what is consuming", "what's draining", "draining my", "what's costing")):
        return "friction"
    if any(p in t for p in ("what should i focus", "what should i prioritise", "what should i prioritize",
                            "what to focus", "where should i focus", "what should i stop", "what should i defer")):
        return "focus"
    if any(p in t for p in ("highest leverage", "what should i do", "what should i do today",
                            "highest-value", "best use of", "what matters most")):
        return "decide"
    if any(p in t for p in ("capacity drivers", "capacity review", "what improved", "weekly capacity")):
        return "capacity-review"
    if any(p in t for p in ("week", "trend", "review")):
        return "review"
    if "today" in t:
        return "today"
    return None


# ── Handler ───────────────────────────────────────────────────────────────────

def handle_human_systems(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """Route a /human-systems request and return a mrkdwn response."""
    raw = (text or "").strip()

    # Safety first: scan everything the Captain typed for red flags.
    hits = safety.scan_red_flags(raw)
    banner = safety.escalation_banner(hits)

    if not raw:
        return _HELP

    parts = raw.split(maxsplit=1)
    command = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    # Allow natural-language asks ("help me build a low-capacity day plan").
    _verbs = ("today", "status", "plan", "explain", "review", "log", "feedback", "domains", "push",
              "decide", "focus", "prioritise", "prioritize", "allocate", "load", "friction",
              "capacity-review", "creview", "xo")
    # A bare keyword ("plan", "review") is a direct command. Anything else —
    # including "help me build a…" — is treated as a natural-language ask first.
    is_direct = command in _verbs and not (command == "help")
    if not is_direct:
        mapped = _natural_intent(raw)
        if mapped:
            parts = mapped.split(maxsplit=1)
            command = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
        elif command not in _verbs:
            command = "help"

    if command == "help":
        body = _HELP
    elif command in ("today", "status"):
        body = _today(rest)
    elif command == "domains":
        body = _domains()
    elif command == "plan":
        body = _plan(rest)
    elif command == "explain":
        body = _explain()
    elif command == "review":
        body = _review()
    elif command == "log":
        body = _log(rest, user_id)
    elif command == "feedback":
        body = _feedback(rest, user_id)
    elif command == "push":
        body = _push(rest)
    elif command == "decide":
        body = _decide()
    elif command in ("focus", "prioritise", "prioritize", "allocate"):
        body = _focus()
    elif command == "load":
        body = _load_assessment()
    elif command == "friction":
        body = _friction()
    elif command in ("capacity-review", "creview"):
        body = _capacity_review()
    elif command == "xo":
        body = _xo(rest)
    else:  # pragma: no cover - guarded above
        body = _HELP

    # A red flag in the Captain's text always takes priority (doctrine §6).
    if banner:
        return f"{banner}\n\n———\n\n{body}"
    return body


# ── Subcommand implementations ────────────────────────────────────────────────

def _today(_rest: str) -> str:
    rows = _fetch_rows(days=2)
    snap = framework.interpret_capacity(_today_row(rows))
    lines = [
        "*Human Systems — Today*",
        f"_{snap.headline}_",
        "",
        f"*Daily capacity:* {snap.overall_band} ({round(snap.overall_score)}/100)",
        "",
        "*By domain:*",
    ]
    for d in snap.domains:
        lines.append(f"• *{d.label}:* {d.band} — {d.driver}.")
    lines += [
        "",
        "*What matters most today:* pick one anchor that fits this capacity and "
        "pace the rest around it. A practical next step could be `/hs plan "
        f"{'low-capacity' if snap.overall_band in ('limited', 'depleted') else 'movement'}`.",
    ]
    return safety.frame("\n".join(lines))


# ── HSF-002 decision-support subcommands ──────────────────────────────────────

def _decide() -> str:
    """WP5 — the single highest-leverage action right now."""
    snapshot, load, rows = _context(days=7)
    frictions = decision.detect_friction(rows)
    # notes=None: red-flag scanning is handled at the command boundary.
    rec = decision.highest_leverage(snapshot, load, frictions, notes=None)
    memory.record_recommendation(
        kind="highest_leverage", domain="resilience", output_class="action",
        summary=rec.primary[:200], source="captain_pull",
    )
    return safety.frame(rec.render())


def _focus() -> str:
    """WP1 — recommended focus + what to defer."""
    snapshot, load, _ = _context(days=2)
    alloc = decision.allocate_capacity(snapshot, load)
    lines = [
        "*Recommended Focus*",
        f"_Capacity is {alloc.band}. {alloc.note}_",
        "",
    ]
    for i, item in enumerate(alloc.focus, 1):
        lines.append(f"{i}. {item}")
    lines += ["", "*Defer:*"]
    lines += [f"• {d}" for d in alloc.defer]
    return safety.frame("\n".join(lines))


def _load_assessment() -> str:
    """WP2 — mission load vs. available capacity."""
    snapshot, load, _ = _context(days=2)
    a = decision.assess_mission_load(snapshot, load)
    lines = [
        "*Mission Load vs. Capacity*",
        f"• Current capacity: *{a.band}*",
        f"• Open missions: *{a.open_count if load.data_available else 'unknown'}*",
        f"• Sustainable to progress today: *{a.sustainable_active}*",
        "",
        f"_{a.headline}_",
        "",
        "*Recommendation:* " + a.recommendation,
    ]
    return safety.frame("\n".join(lines))


def _friction() -> str:
    """WP4 — recurring causes of capacity loss."""
    _, _, rows = _context(days=14)
    findings = decision.detect_friction(rows)
    if not findings:
        return safety.frame(
            "*Friction Scan*\nNo recurring capacity drains detected in recent data. "
            "Either the pattern is steady or there isn't enough logged yet to read one.",
            with_footer=False,
        )
    lines = ["*Friction — recurring capacity drains*", ""]
    for f in findings:
        lines.append(f"• *{f.description}*")
        lines.append(f"  ↳ {f.lever}")
        memory.record_friction(  # persist to the register (non-blocking)
            friction_key=f.key, description=f.description, lever=f.lever, confidence=f.confidence,
        )
    lines += ["", "_Patterns are framed as information, not verdicts. Based on the pattern, these may suggest where a small change pays off._"]
    return safety.frame("\n".join(lines))


def _capacity_review() -> str:
    """WP3 — weekly drivers, drains, one recommended change."""
    _, load, rows = _context(days=7)
    body = decision.weekly_capacity_review(rows, load)
    memory.record_recommendation(
        kind="capacity_review", domain="resilience", output_class="trend",
        summary="weekly capacity review issued", source="captain_pull",
    )
    return safety.frame(body)


def _xo(request: str) -> str:
    """WP6 — cross-domain decision support."""
    if not request:
        return (
            "What would you like to weigh against your capacity? e.g. "
            "`/hs xo make progress on the coaching business this week`."
        )
    snapshot, load, _ = _context(days=2)
    # scan=False: the command boundary already scanned the raw text for red flags.
    return xo.xo_decision(request, snapshot, load, scan=False)


def _domains() -> str:
    lines = ["*Human Systems — Six Domains*", ""]
    for key, meta in framework.DOMAINS.items():
        lines.append(f"• *{meta['label']}* — {meta['purpose']}")
    lines += [
        "",
        "*Critical personal services tracked:* "
        + ", ".join(framework.CRITICAL_SERVICES) + ".",
    ]
    return safety.frame("\n".join(lines), with_footer=False)


def _plan(rest: str) -> str:
    plan_type = framework.normalise_plan_type(rest) or framework.normalise_plan_type(rest.split()[0] if rest else "")
    if not plan_type:
        return (
            "Which plan would help? Try `/hs plan low-capacity`, `recovery`, "
            "`movement`, `nutrition`, or `mind`."
        )
    rows = _fetch_rows(days=2)
    snap = framework.interpret_capacity(_today_row(rows))
    body = framework.build_plan(plan_type, snap)

    # Memory: record that this plan was issued (non-blocking).
    domain = {
        "low_capacity": "resilience", "recovery": "medical", "movement": "movement",
        "nutrition": "nutrition", "mind": "mind",
    }.get(plan_type, "resilience")
    memory.record_recommendation(
        kind=f"plan_{plan_type}", domain=domain, output_class="action",
        summary=f"{plan_type} plan at {snap.overall_band} capacity", source="captain_pull",
    )
    return safety.frame(body)


def _explain() -> str:
    rows = _fetch_rows(days=2)
    return safety.frame(framework.explain_signal(_today_row(rows)))


def _review() -> str:
    rows = _fetch_rows(days=7)
    body = framework.weekly_review(rows)
    memory.record_recommendation(
        kind="weekly_review", domain="resilience", output_class="trend",
        summary="weekly human systems review issued", source="captain_pull",
    )
    return safety.frame(body)


def _log(note: str, user_id: str | None) -> str:
    if not note:
        return "Add a note to log, e.g. `/hs log slept badly, neck flared after sitting`."
    memory.record_pattern(
        pattern_type="trigger", description=note, user_id=user_id,
    )
    return safety.frame(
        "*Logged.* Thanks — that's stored as context for spotting patterns over "
        "time. If this connects to a red-flag signal, the system will always "
        "prompt you toward professional support.",
        with_footer=False,
    )


def _push(rest: str) -> str:
    """On-demand preview of a proactive push (dry-run render). Reuses the runner."""
    job = (rest.split()[0].lower() if rest else "")
    valid = ("morning", "evening", "weekly", "degradation")
    if job not in valid:
        return (
            "Which push would you like to preview? Try "
            "`/hs push morning`, `evening`, `weekly`, or `degradation`."
        )
    try:
        from human_systems_scheduler import run_job  # lazy to avoid import cycle
        report = run_job(job, dry_run=True, record=False)
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems] push preview failed: %s", exc)
        return "Couldn't generate that preview right now."
    if report.get("skipped"):
        return (
            f"*{job.capitalize()} push* — no actionable signal right now, so "
            "nothing would be sent. That's the system staying quiet by design."
        )
    return f"_Preview — this is what the {job} push would send:_\n\n{report.get('text', '')}"


def _feedback(rest: str, user_id: str | None) -> str:
    parts = rest.split(maxsplit=1)
    verdict = parts[0].lower() if parts else ""
    note = parts[1] if len(parts) > 1 else None
    # Pilot taxonomy: helpful | neutral | not_helpful (with friendly aliases).
    if verdict in ("helpful", "useful", "yes", "good"):
        category = "helpful"
    elif verdict in ("neutral", "ok", "meh"):
        category = "neutral"
    elif verdict in ("not", "not_helpful", "not-helpful", "unhelpful", "no", "bad"):
        category = "not_helpful"
    else:
        return (
            "How did that guidance land? Try `/hs feedback helpful`, "
            "`/hs feedback neutral`, or `/hs feedback not <what didn't land>`."
        )
    memory.record_feedback(summary=note or category, category=category, note=note, user_id=user_id)
    msg = {
        "helpful": "Noted — I'll favour that kind of guidance.",
        "neutral": "Noted — neither helped nor got in the way. Useful signal.",
        "not_helpful": "Noted — I'll steer away from that. Thanks for the steer.",
    }[category]
    return safety.frame(f"*Feedback recorded.* {msg}", with_footer=False)
