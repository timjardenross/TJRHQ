"""Daily Intelligence Briefing — USS-TJR-MSN-0098 WP7.

The capstone: composes the existing intelligence engines into one operationally
useful briefing answering:

    * What changed overnight?   * What matters today?
    * What deserves attention?  * What may require action?

…plus the personal operating picture, wellness, strategic read and forecasts.

Reuse-only — this is an *intelligence layer* the existing XO briefing / Captain's
Chair / scheduler can call. It composes; it stores nothing and actions nothing.
Advisory; human approval mandatory.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import temporal as _temporal
import triggers as _triggers
import operating_picture as _operating_picture
import wellness as _wellness
import strategic as _strategic
import forecast as _forecast
import data_quality as _data_quality


def daily_intelligence_brief() -> dict[str, Any]:
    changed = _temporal.what_changed(days=1)
    trigs = _triggers.evaluate_triggers()
    matters_today = [t.to_dict() for t in trigs if t.level in ("warning", "concern", "escalation")]
    may_require_action = [t.to_dict() for t in trigs if t.level == "escalation"]

    picture = _operating_picture.captain_operating_picture()
    wins = _wellness.wellness_intelligence()
    strat = _strategic.strategic_intelligence()
    forecasts = _forecast.all_forecasts()
    gaps = _data_quality.capture_gaps()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "what_changed_overnight": changed.get("narrative", ""),
        "what_matters_today": matters_today,
        "deserves_attention": [t for t in matters_today if t["level"] in ("concern", "escalation")],
        "may_require_action": may_require_action,
        "operating_picture": picture["headline"],
        "wellness": wins.get("narrative", ""),
        "strategic": strat["headline"],
        "opportunities": strat["opportunities"][:3],
        "forecasts": [f for f in forecasts["forecasts"] if f["direction"] != "insufficient_evidence"][:3],
        "capture_prompt": gaps["narrative"],
        "headline": _headline(matters_today, may_require_action),
        "note": "Daily intelligence briefing — advisory only; the Captain decides. Nothing actioned.",
    }


def _headline(matters, action) -> str:
    if action:
        return f"⚠ {len(action)} item(s) may require action today."
    if matters:
        return f"{len(matters)} item(s) matter today; none require immediate action."
    return "Quiet briefing — nothing pressing today."


def to_markdown() -> str:
    b = daily_intelligence_brief()
    L = [f"# Daily Intelligence Briefing", "", b["headline"], ""]
    L.append(f"**Overnight:** {b['what_changed_overnight']}")
    L.append(f"**Operating picture:** {b['operating_picture']}")
    L.append(f"**Wellness:** {b['wellness']}")
    L.append(f"**Strategic:** {b['strategic']}")
    if b["may_require_action"]:
        L.append("\n## May Require Action")
        for t in b["may_require_action"]:
            L.append(f"- [{t['level']}] {t['trigger_type']}: {t['message']}")
    if b["deserves_attention"]:
        L.append("\n## Deserves Attention")
        for t in b["deserves_attention"]:
            L.append(f"- [{t['level']}] {t['trigger_type']}: {t['message']}")
    if b["opportunities"]:
        L.append("\n## Opportunities")
        for o in b["opportunities"]:
            L.append(f"- 💡 {o['opportunity_type']}: {o['message']}")
    if b["forecasts"]:
        L.append("\n## Forecasts")
        for f in b["forecasts"]:
            L.append(f"- {f['metric']}: {f['projection']} ({f['confidence']}, n={f['sample_size']})")
    L.append(f"\n_{b['capture_prompt']}_")
    L.append(f"_{b['note']}_")
    return "\n".join(L)
