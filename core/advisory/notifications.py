"""Notification Intelligence — USS-TJR-MSN-0096 WP4.

Decides, for each trigger/opportunity:

    * What deserves interruption?   → escalation-level items (push now)
    * What belongs in the daily briefing? → warning/concern + opportunities
    * What should wait?             → observations (portal only, on demand)

…and suggests the right channel(s): Telegram/Slack push, XO briefing,
Number One briefing, or the Portal. Routing only — nothing is sent here, and
nothing is actioned. Human approval remains mandatory.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_escalation = _import_sibling("escalation")

# disposition → channels
_ROUTING = {
    "interrupt": ["Telegram", "Slack", "XO briefing"],
    "daily_brief": ["Slack daily brief", "Number One briefing", "Portal"],
    "wait": ["Portal (on demand)"],
}


def _disposition(level: str) -> str:
    r = _escalation.rank(level)
    if r >= _escalation.rank("escalation"):
        return "interrupt"
    if r >= _escalation.rank("warning"):
        return "daily_brief"
    return "wait"


def route(triggers: list[Any], opportunities: list[Any] | None = None) -> dict[str, Any]:
    """Group triggers/opportunities by disposition with suggested channels."""
    opportunities = opportunities or []
    plan: dict[str, list[dict[str, Any]]] = {"interrupt": [], "daily_brief": [], "wait": []}

    for t in triggers:
        d = t.to_dict() if hasattr(t, "to_dict") else dict(t)
        disp = _disposition(d.get("level", "observation"))
        plan[disp].append({
            "type": d.get("trigger_type"),
            "level": d.get("level"),
            "message": d.get("message"),
            "channels": _ROUTING[disp],
        })

    # Opportunities are never interruptions — they belong in the daily brief.
    for o in opportunities:
        d = o.to_dict() if hasattr(o, "to_dict") else dict(o)
        plan["daily_brief"].append({
            "type": d.get("opportunity_type"),
            "level": "opportunity",
            "message": d.get("message"),
            "channels": _ROUTING["daily_brief"],
        })

    return {
        "interrupt": plan["interrupt"],
        "daily_brief": plan["daily_brief"],
        "wait": plan["wait"],
        "summary": {
            "interrupt": len(plan["interrupt"]),
            "daily_brief": len(plan["daily_brief"]),
            "wait": len(plan["wait"]),
        },
        "note": "Routing recommendation only — no notification is sent and no action is taken.",
    }


def to_markdown(plan: dict[str, Any]) -> str:
    L = ["# Notification Plan", ""]
    titles = {"interrupt": "🔔 Interrupt now", "daily_brief": "📋 Daily briefing", "wait": "🕓 Can wait"}
    for disp in ("interrupt", "daily_brief", "wait"):
        items = plan.get(disp, [])
        L.append(f"## {titles[disp]} ({len(items)})")
        if items:
            for it in items:
                L.append(f"- [{it['level']}] {it['type']}: {it['message']}")
        else:
            L.append("- (none)")
        L.append("")
    L.append("_" + plan.get("note", "") + "_")
    return "\n".join(L)
