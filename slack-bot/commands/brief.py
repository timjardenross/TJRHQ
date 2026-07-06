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
    from lib.strategy import objectives as _strategy, alignment as _alignment
    from lib.comms import opportunities as _comms
except Exception:  # pragma: no cover
    from slack_bot.lib import daily_brief  # type: ignore
    from slack_bot.lib.human_systems import framework, decision, mission_load as ml, safety, memory, learning  # type: ignore
    from slack_bot.lib.delivery import forecast, data as ddata, lifecycle as dlife, analysis as danalysis  # type: ignore
    from slack_bot.lib.intel import ori as _ori, knowledge as _knowledge  # type: ignore
    from slack_bot.lib.strategy import objectives as _strategy, alignment as _alignment  # type: ignore
    from slack_bot.lib.comms import opportunities as _comms  # type: ignore

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

    # MSN-SPC-001 WP4/WP6: strategic snapshot + gentle prioritisation signal.
    strat_snapshot = None
    strat_signal = None
    try:
        strat_snapshot = _strategy.fetch_snapshot()
        if strat_snapshot and strat_snapshot.data_available:
            f = _alignment.to_signal(strat_snapshot)
            strat_signal = decision.StrategicSignal(
                active_objectives=f.active_objectives, top_objective=f.top_objective,
                top_domain=f.top_domain, alignment_weight=f.alignment_weight,
            )
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] strategic snapshot unavailable: %s", exc)

    # Pass today's notes so a red flag escalates; ORI risk feeds the decision (WP4).
    notes = (today or {}).get("notes")
    pkg = decision.recommendation_package(
        snapshot, load, frictions, notes=notes, delivery=delivery, learned=learned,
        ori_risk=(ori_signal.overall_risk if ori_signal else None),
        ori_headline=(ori_signal.top_risk if ori_signal else None),
        strategic=strat_signal,
    )

    # MSN-0328 Wave 3: this is the one genuinely duplicate piece of
    # briefing-assembly logic in this module — a "what matters most today"
    # recommendation, the exact purpose the canonical Attention/Priority
    # Engine pipeline exists for. Not replaced (its capacity-aware scoring
    # has no equivalent in the generic event-stream pipeline — swapping it
    # for doc.priorities[0] would be a real regression, not a convergence),
    # but now also emitted, so the canonical pipeline's own priorities list
    # includes it rather than staying blind to Slack's richest signal.
    try:
        from core.platform.event_bus import publish_event
        publish_event(
            "human_systems.recommendation_computed", domain="health-intelligence",
            source="slack-bot:brief", importance=round(pkg.confidence * 100),
            confidence=round(pkg.confidence * 100),
            recommended_action=pkg.primary,
            metrics={
                "expected_impact": pkg.expected_impact,
                "opportunity_cost": pkg.opportunity_cost,
                "recommended_deferral": pkg.recommended_deferral,
                "strategic_alignment": pkg.strategic_alignment,
                "secondary": pkg.secondary,
                "escalation": pkg.escalation,
            },
        )
    except Exception:
        pass

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

    # COMMS-001 WP5: surface the top publishable opportunity (reused engine).
    comms_opps = None
    try:
        comms_opps = _comms.gather_opportunities()
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] comms opportunities unavailable: %s", exc)

    # MSN-0328 Wave 3: snapshot-on-read emission for the remaining aggregate
    # values this brief already computes (mission load, delivery risk,
    # strategic focus) — these are live counts/derivations, not tied to any
    # single write event, so there's no "choke point" to hook the way
    # Wave 2's missions/delivery/strategy emitters were. Emitting them here,
    # at the one moment they're already gathered, makes them visible to the
    # canonical pipeline for other consumers without duplicating the read
    # logic itself (still owned by mission_load.py/forecast.py/objectives.py).
    try:
        from core.platform.event_bus import publish_event
        if load.data_available:
            publish_event(
                "mission.load_snapshot", domain="mission-lifecycle",
                source="slack-bot:brief", metrics={"open_count": load.open_count},
            )
        if tower:
            publish_event(
                "delivery.risk_snapshot", domain="engineering-delivery",
                source="slack-bot:brief",
                metrics={
                    "high_risk_count": tower.get("high_risk_count", 0),
                    "open_count": tower.get("open_count", 0),
                    "constraint": (tower.get("bottleneck") or {}).get("constraint"),
                    "constraint_count": (tower.get("bottleneck") or {}).get("constraint_count", 0),
                },
            )
        if strat_snapshot and strat_snapshot.data_available:
            publish_event(
                "strategy.focus_snapshot", domain="strategic-planning",
                source="slack-bot:brief",
                metrics={
                    "active_count": len(strat_snapshot.active),
                    "active_domains": len(strat_snapshot.active_domains),
                    "orphan_count": strat_snapshot.orphan_count,
                },
            )
    except Exception:
        pass

    # MSN-0328 Wave 3: poll the canonical pipeline back so this brief's own
    # just-emitted event (above) is available for compose_daily_brief() to
    # render from. None on any failure (Supabase disabled, etc.) — the
    # renderer's own per-field fallback handles that identically to before
    # this change existed.
    canonical_doc = None
    try:
        from core.platform.event_bus import poll_events
        from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
        canonical_doc = assemble_captain_brief_document(poll_events(limit=50))
    except Exception:
        pass

    body = daily_brief.compose_daily_brief(
        capacity=snapshot, recommendation=pkg, load=load,
        delivery=delivery, control_tower=tower, ori=ori_signal, knowledge=knowledge_hits,
        strategy=strat_snapshot, comms=comms_opps, brief_doc=canonical_doc,
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
    if raw in ("strategy", "objectives", "strategic"):
        return safety.frame(_strategy_view())
    return safety.frame(build_brief())


def _strategy_view() -> str:
    """`/brief strategy` — what objectives are currently active (SPC-001 WP4)."""
    try:
        snap = _strategy.fetch_snapshot()
    except Exception as exc:  # pragma: no cover
        log.warning("[brief] strategy view unavailable: %s", exc)
        snap = None

    if snap is None or not snap.data_available:
        return (
            "*Strategic Focus*\n_No active objectives recorded yet._\n\n"
            "The strategic layer sits above missions: Vision → Domain → Objective "
            "→ Mission. Once objectives are registered, this shows what's active, "
            "their progress, and any unaligned missions. See "
            "`governance/STRATEGIC-PLANNING-DOCTRINE.md`."
        )

    active = snap.active
    lines = [
        "*Strategic Focus — active objectives*",
        f"_{len(active)} active across {len(snap.active_domains)} domain(s)_",
        "",
    ]
    for o in active:
        lines.append(f"• [{o.priority}] *{o.title}* — _{o.domain}_")
        lines.append(f"    ↳ {o.progress_label()}")
    if snap.orphan_count:
        lines += ["", f"⚠️ {snap.orphan_count} open mission(s) not yet aligned to an "
                  "objective — review at the fortnightly objective check."]
    lines += ["", "_Strategy advises the daily decision; capacity stays first (D-055)._"]
    return "\n".join(lines)


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
