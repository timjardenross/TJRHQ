"""Proactive Advisory Orchestrator — USS-TJR-MSN-0096.

"Today the Captain asks; tomorrow the system notices." This is the single
entrypoint that lets advisory intelligence run unprompted — it aggregates
triggers, opportunities, a notification plan, emerging signals and advisory
self-health into one scan.

It NOTICES; it does not ACT. Everything is informational; human approval
remains mandatory. No officers, no autonomy, no approvals, no assignments.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import triggers as _triggers
from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_opportunities = _import_sibling("opportunities")
import notifications as _notifications
import advisory_health as _advisory_health
import signals as _signals


def proactive_scan() -> dict[str, Any]:
    trigs = _triggers.evaluate_triggers()
    opps = _opportunities.detect_opportunities()
    plan = _notifications.route(trigs, opps)
    health = _advisory_health.advisory_health()
    sigs = _signals.emerging_signals()

    interrupts = plan["summary"]["interrupt"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attention_required": interrupts > 0,
        "triggers": [t.to_dict() for t in trigs],
        "opportunities": [o.to_dict() for o in opps],
        "emerging_signals": [s.to_dict() for s in sigs],
        "notification_plan": plan,
        "advisory_health": health,
        "headline": _headline(trigs, opps, interrupts, health),
        "note": "Informational scan only — Captain decides; nothing was actioned.",
    }


def _headline(trigs, opps, interrupts, health) -> str:
    if interrupts:
        return f"⚠ {interrupts} item(s) warrant attention now; {len(trigs)} trigger(s) total."
    if trigs or opps:
        return f"{len(trigs)} trigger(s) and {len(opps)} opportunity(ies) for the daily brief."
    if health.get("status") == "degraded":
        return "No triggers, but advisory health is degraded — review recommendation quality."
    return "Nothing notable — advisory intelligence is quiet."


def to_markdown(scan: dict[str, Any] | None = None) -> str:
    s = scan or proactive_scan()
    L = [f"# Proactive Advisory Scan", "", s["headline"], ""]
    if s["triggers"]:
        L.append("## Triggers")
        icon = {"escalation": "🔴", "concern": "🟠", "warning": "🟡", "observation": "⚪"}
        for t in s["triggers"]:
            L.append(f"- {icon.get(t['level'], '•')} {t['trigger_type']} ({t['level']}): {t['message']}")
        L.append("")
    if s["opportunities"]:
        L.append("## Opportunities")
        for o in s["opportunities"]:
            L.append(f"- 💡 {o['opportunity_type']}: {o['message']}")
        L.append("")
    plan = s["notification_plan"]["summary"]
    L.append(f"## Routing: interrupt={plan['interrupt']} · daily brief={plan['daily_brief']} · wait={plan['wait']}")
    L.append("")
    L.append(s["advisory_health"]["narrative"])
    L.append("")
    L.append("_" + s["note"] + "_")
    return "\n".join(L)
