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
    from lib.intel import ori as _ori, knowledge as _knowledge
except Exception:  # pragma: no cover
    from slack_bot.lib import daily_brief  # type: ignore
    from slack_bot.lib.human_systems import framework, decision, mission_load as ml, safety, memory, learning  # type: ignore
    from slack_bot.lib.delivery import forecast, data as ddata, lifecycle as dlife, analysis as danalysis  # type: ignore
    from slack_bot.lib.intel import ori as _ori, knowledge as _knowledge  # type: ignore

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

    # MSN-XO-003 WP2: ORI signal (reused from existing briefs).
    ori_signal = None
    try:
        ori_signal = _ori.fetch_ori_signal()
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] ORI signal unavailable: %s", exc)

    # Pass today's notes so a red flag escalates; ORI risk feeds the decision (WP4).
    notes = (today or {}).get("notes")
    pkg = decision.recommendation_package(
        snapshot, load, frictions, notes=notes, delivery=delivery, learned=learned,
        ori_risk=(ori_signal.overall_risk if ori_signal else None),
        ori_headline=(ori_signal.top_risk if ori_signal else None),
    )

    # EDO control tower (reused, not rebuilt).
    tower = None
    try:
        drows = ddata.fetch_delivery_rows()
        if drows:
            tower = forecast.control_tower(drows)
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] control tower unavailable: %s", exc)

    # MSN-XO-003 WP3: relevant prior knowledge (reused from Command Memory).
    knowledge_hits = None
    try:
        knowledge_hits = _knowledge.relevant_knowledge(f"{pkg.primary} {snapshot.headline}")
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] knowledge unavailable: %s", exc)

    body = daily_brief.compose_daily_brief(
        capacity=snapshot, recommendation=pkg, load=load,
        delivery=delivery, control_tower=tower, ori=ori_signal, knowledge=knowledge_hits,
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


def _count(table: str, **eq) -> int:
    """Reuse the graceful client to count rows (adoption telemetry, no new store)."""
    try:
        c = memory._client()
        if c is None:
            return 0
        q = c.raw_client.table(table).select("*", count="exact")
        for k, v in eq.items():
            q = q.eq(k, v)
        res = q.execute()
        return getattr(res, "count", None) or len(res.data or [])
    except Exception:  # pragma: no cover
        return 0


def _adoption() -> str:
    """WP5 adoption & consumption metrics — reuses existing telemetry tables."""
    briefs = _count("human_systems_recommendations", kind="daily_brief")
    feedback = _count("human_systems_feedback")
    retrievals = _count("retrieval_logs")
    ori_briefs = _count("intelligence_briefs")
    return (
        "*Daily Operating Picture — adoption & consumption*\n"
        f"• Briefs issued: {briefs}\n"
        f"• Feedback responses: {feedback}\n"
        f"• Knowledge retrievals: {retrievals}\n"
        f"• ORI briefs available: {ori_briefs}\n\n"
        + learning.effectiveness_report()
    )
