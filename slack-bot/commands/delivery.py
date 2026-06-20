"""EDO — /delivery command (MSN-EDO-002/008).

The Engineering & Delivery Officer's status surface: where work is stuck,
delivery metrics, data-hygiene lint, and a reuse-first check. Pure with respect
to Slack — returns a mrkdwn string. Reads the delivery views; degrades to a
helpful message when Supabase is unavailable.

    handle_delivery(text, user_id=None, channel_id=None) -> str
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
    from lib.delivery import analysis, data, lifecycle
except Exception:  # pragma: no cover
    from slack_bot.lib.delivery import analysis, data, lifecycle  # type: ignore

_HELP = (
    "*Engineering & Delivery Officer.*\n"
    "I keep delivery visible, measured, and reuse-first.\n\n"
    "• `/delivery status` — open missions by state + age (where work is)\n"
    "• `/delivery bottlenecks` — where work is stuck, ranked\n"
    "• `/delivery metrics` — cycle time, PR rate, outcome rate, rework\n"
    "• `/delivery lint` — mission data-hygiene issues\n"
    "• `/delivery reuse <request>` — what already exists to reuse first\n"
)

_SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪", "info": "ℹ️"}


def handle_delivery(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    raw = (text or "").strip()
    if not raw:
        return _HELP
    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("help", ""):
        return _HELP
    if cmd in ("status", "open"):
        return _status()
    if cmd in ("bottlenecks", "stuck"):
        return _bottlenecks()
    if cmd in ("metrics", "stats"):
        return _metrics()
    if cmd == "lint":
        return _lint()
    if cmd == "reuse":
        return _reuse(rest)
    return _HELP


def _rows():
    return data.fetch_delivery_rows()


def _status() -> str:
    rows = _rows()
    if not rows:
        return "*Delivery status*\nNo mission data available right now."
    open_rows = [r for r in rows if lifecycle.is_open(r.get("delivery_state") or r.get("status"))]
    by_state: dict[str, list[dict]] = {}
    for r in open_rows:
        st = r.get("delivery_state") or lifecycle.canonical_state(r.get("status"))
        by_state.setdefault(st, []).append(r)
    lines = [f"*Delivery status* — {len(open_rows)} open / {len(rows)} total", ""]
    for st in lifecycle.OPEN_STATES:
        bucket = by_state.get(st)
        if not bucket:
            continue
        lines.append(f"*{st.replace('_',' ').title()}* ({len(bucket)})")
        for r in sorted(bucket, key=lambda x: -(x.get("age_days") or 0))[:6]:
            pr = " · PR" if (r.get("pr_url") or "").strip() else ""
            lines.append(f"• {r.get('title','untitled')} — {r.get('age_days',0)}d{pr}")
    return "\n".join(lines)


def _bottlenecks() -> str:
    rows = _rows()
    findings = analysis.detect_bottlenecks(rows)
    if not findings:
        return "*Delivery bottlenecks*\nNothing stuck beyond thresholds. Delivery is flowing."
    lines = ["*Delivery bottlenecks* (ranked)", ""]
    for f in findings[:12]:
        lines.append(f"{_SEV_EMOJI.get(f.severity,'•')} *{f.title}* — {f.detail}")
    return "\n".join(lines)


def _metrics() -> str:
    rows = _rows()
    if not rows:
        return "*Delivery metrics*\nNo mission data available right now."
    m = analysis.summarize_metrics(rows)
    lines = [
        "*Delivery metrics*",
        f"• Total: {m['total']}  ·  Open: {m['open']}  ·  Closed: {m['closed']}",
        f"• Avg open age: {m['avg_open_age_days']}d  ·  Oldest open: {m['oldest_open_age_days']}d",
        f"• Avg cycle time: {m['avg_cycle_days'] if m['avg_cycle_days'] is not None else 'n/a'}d",
        f"• PR rate: {int(m['pr_rate']*100)}%  ·  Outcome captured: {int(m['outcome_rate']*100)}%  ·  Rework: {int(m['rework_rate']*100)}%",
        "",
        "*By state:* " + ", ".join(f"{k} {v}" for k, v in sorted(m["by_state"].items())),
    ]
    if m["pr_rate"] < 0.5 or m["outcome_rate"] < 0.5:
        lines += ["", "_Low PR/outcome capture — delivery is happening off-system. "
                  "Routing work through the instrumented flow will lift these._"]
    return "\n".join(lines)


def _lint() -> str:
    rows = _rows()
    findings = analysis.lint(rows)
    if not findings:
        return "*Mission lint*\nNo data-hygiene issues found."
    lines = ["*Mission lint* — data-hygiene issues", ""]
    for f in findings[:15]:
        lines.append(f"{_SEV_EMOJI.get(f.severity,'•')} {f.title}: {f.detail}")
    return "\n".join(lines)


def _reuse(query: str) -> str:
    if not query:
        return "Usage: `/delivery reuse <what you want to build>` — I'll surface what already exists."
    matches = analysis.reuse_check(query, data.fetch_capabilities(), _rows())
    if not matches:
        return (
            f"*Reuse check — {query}*\nNo strong overlap found in existing "
            "capabilities or missions. If you build, register the capability on close."
        )
    lines = [f"*Reuse-first check — {query}*", "", "Consider reusing/extending:"]
    for m in matches:
        lines.append(f"• [{m['kind']}] *{m['name']}* — {m['detail']}")
    lines += ["", "_Reuse-first: cite what you'll reuse before approving new build._"]
    return "\n".join(lines)
