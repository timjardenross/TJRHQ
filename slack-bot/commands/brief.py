"""/brief — Captain's Daily Operating Picture (MSN-XO-002 WP1/WP2/WP3).

The single primary briefing entry point. Reuses the Human Systems decision engine
and the EDO control tower (no new analytics), composes them via
lib/daily_brief.compose_daily_brief, records the brief for adoption metrics, and
applies the learned feedback loop.

Supporting commands (/hs decide, /delivery forecast, …) remain for deep dives.

    handle_brief(text, user_id=None, channel_id=None) -> str
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
    from lib import daily_brief
    from lib.human_systems import framework, decision, mission_load as ml, safety, memory, learning
    from lib.delivery import forecast, data as ddata, lifecycle as dlife, analysis as danalysis
except Exception:  # pragma: no cover
    from slack_bot.lib import daily_brief  # type: ignore
    from slack_bot.lib.human_systems import framework, decision, mission_load as ml, safety, memory, learning  # type: ignore
    from slack_bot.lib.delivery import forecast, data as ddata, lifecycle as dlife, analysis as danalysis  # type: ignore

# Reuse the Human Systems command's data helpers (single source of fetch logic).
try:
    from commands.human_systems import _fetch_rows, _today_row, _delivery_context
except Exception:  # pragma: no cover
    from slack_bot.commands.human_systems import _fetch_rows, _today_row, _delivery_context  # type: ignore


def build_brief() -> str:
    """Gather from the existing engines and compose the daily operating picture."""
    rows = _fetch_rows(days=7)
    today = _today_row(rows)
    snapshot = framework.interpret_capacity(today)
    load = ml.get_mission_load()
    frictions = decision.detect_friction(rows)
    delivery, _ = _delivery_context()
    learned = learning.learned_adjustments()
    # Pass today's notes so a red flag escalates at the top of the brief.
    notes = (today or {}).get("notes")
    pkg = decision.recommendation_package(snapshot, load, frictions, notes=notes,
                                          delivery=delivery, learned=learned)

    # EDO control tower (reused, not rebuilt).
    tower = None
    try:
        drows = ddata.fetch_delivery_rows()
        if drows:
            tower = forecast.control_tower(drows)
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] control tower unavailable: %s", exc)

    body = daily_brief.compose_daily_brief(
        capacity=snapshot, recommendation=pkg, load=load,
        delivery=delivery, control_tower=tower,
    )

    # WP3 adoption metric: record that a brief was issued (usage signal).
    memory.record_recommendation(
        kind="daily_brief", domain="resilience", output_class="action",
        summary=pkg.primary[:200], source="captain_pull",
    )
    return body


def handle_brief(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    raw = (text or "").strip().lower()
    if raw in ("feedback", "fb"):
        return (
            "Tell the system how today's brief landed: `/hs feedback helpful`, "
            "`/hs feedback neutral`, or `/hs feedback not <note>`."
        )
    if raw in ("adoption", "metrics"):
        return _adoption()
    return safety.frame(build_brief())


def _adoption() -> str:
    """WP3 adoption metrics: brief usage + recommendation effectiveness."""
    issued = 0
    try:
        c = memory._client()  # reuse the graceful client
        if c is not None:
            res = (c.raw_client.table("human_systems_recommendations")
                   .select("id", count="exact").eq("kind", "daily_brief").execute())
            issued = getattr(res, "count", None) or len(res.data or [])
    except Exception:  # pragma: no cover
        issued = 0
    return (
        "*Daily brief — adoption*\n"
        f"• Briefs issued: {issued}\n\n"
        + learning.effectiveness_report()
    )
