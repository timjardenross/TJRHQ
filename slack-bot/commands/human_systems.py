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
except Exception:  # pragma: no cover - fallback for alternate sys.path layouts
    from slack_bot.lib.human_systems import framework, push, safety, memory  # type: ignore


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


# ── Help ──────────────────────────────────────────────────────────────────────

_HELP = (
    "*Human Systems* — your operating-system support across movement, nutrition, "
    "sleep, mind, performance, and resilience.\n\n"
    "*Ask for support:*\n"
    "• `/hs today` — read today's capacity and what fits\n"
    "• `/hs plan low-capacity` — a protected low-capacity day plan\n"
    "• `/hs plan recovery` — a recovery plan for the next few days\n"
    "• `/hs plan movement` — a capacity-based, pain-aware movement plan\n"
    "• `/hs plan nutrition` — practical nutrition anchors\n"
    "• `/hs plan mind` — manage cognitive load / overwhelm\n"
    "• `/hs explain` — interpret today's signal\n"
    "• `/hs review` — weekly Human Systems review\n"
    "• `/hs log <note>` — log a reflection or trigger event\n"
    "• `/hs feedback useful|not <note>` — tell the system if guidance helped\n\n"
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
    if any(p in t for p in ("week", "trend", "review")):
        return "review"
    if any(p in t for p in ("prioritise", "prioritize", "what should i", "today")):
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
    _verbs = ("today", "status", "plan", "explain", "review", "log", "feedback", "domains")
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


def _feedback(rest: str, user_id: str | None) -> str:
    parts = rest.split(maxsplit=1)
    verdict = parts[0].lower() if parts else ""
    note = parts[1] if len(parts) > 1 else None
    if verdict in ("useful", "helpful", "yes", "good"):
        useful = True
    elif verdict in ("not", "unhelpful", "no", "bad"):
        useful = False
    else:
        return (
            "Was the last guidance useful? Try `/hs feedback useful` or "
            "`/hs feedback not <what didn't land>`."
        )
    memory.record_feedback(summary=note or verdict, useful=useful, note=note, user_id=user_id)
    msg = (
        "Noted — I'll favour that kind of guidance."
        if useful
        else "Noted — I'll steer away from that. Thanks for the steer."
    )
    return safety.frame(f"*Feedback recorded.* {msg}", with_footer=False)
