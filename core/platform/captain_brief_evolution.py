"""Captain Brief Evolution (MSN-0329 Phase 2, Step 5).

Wires Steps 1-4 (Operational State Model, Understanding Engine, Insight
Engine, Reasoning Engine) into the canonical `CaptainBriefDocument`,
answering the Step 5 charter's 3 questions: what changed (the existing
document's priorities/warnings, unchanged), why it matters (`insights`,
new), what to do (reasoned `Recommendation`s appended to the existing
`recommendations` list, richer than before via Step 4's
alternatives/trade_offs/expected_outcome).

Deliberately a SEPARATE module from `captain_brief_orchestrator.py`,
not an edit to it: that module's own docstring guarantees "no I/O
beyond `event_bus.poll_events()`" — Steps 2-4 perform real HTTP I/O
(the model router), so composing them here keeps that guarantee intact
for `assemble_captain_brief_document()`'s existing callers (LCARS,
Slack), who are completely unaffected by this module's existence.

Known, disclosed inefficiency: `assemble_captain_brief_document()`
calls `evaluate_batch()` internally; this module calls it again for
`build_understanding()`. Both calls are pure and deterministic — same
events in, same `AttentionDecision`s out — so this is a real but
harmless duplication of computation, not a correctness risk. Left
as-is rather than refactoring the orchestrator's internals, which
would carry more regression risk than the inefficiency it removes.

MSN-0329 Phase 4: every generated Insight/Recommendation pair is now
also persisted via `insight_outcomes.record_insight()` — the durable
history Phase 4's continuous-measurement/evidence-based-tuning/
confidence-scoring objectives all require. Non-blocking, matches this
module's own graceful-degradation guarantee: a failed persist never
affects the returned document.
"""

from __future__ import annotations

from typing import Any, Optional

from core.platform.attention_engine import evaluate_batch
from core.platform.captain_brief_orchestrator import CaptainBriefDocument, assemble_captain_brief_document
from core.platform.insight_engine import generate_insights
from core.platform.insight_outcomes import record_insight
from core.platform.operational_state_model import assemble_operational_state
from core.platform.reasoning_engine import build_recommendation
from core.platform.understanding_engine import build_understanding


def assemble_evolved_captain_brief(
    events: list[dict[str, Any]],
    *,
    priority_weights: Optional[Any] = None,
    top_n_priorities: int = 10,
    min_relationship_strength: float = 0.4,
) -> CaptainBriefDocument:
    """The Step 5 entry point. Falls back gracefully at every new stage:
    if the model router is unreachable, `insights` stays empty and no
    extra recommendations are appended — the returned document is then
    IDENTICAL to calling `assemble_captain_brief_document()` directly,
    never a partially-broken one.
    """
    doc = assemble_captain_brief_document(
        events, priority_weights=priority_weights, top_n_priorities=top_n_priorities,
    )

    decisions = evaluate_batch(events)
    state = assemble_operational_state(events)
    graph = build_understanding(state, events, decisions)
    insights = generate_insights(graph, min_strength=min_relationship_strength)

    for insight in insights:
        recommendation = build_recommendation(insight)
        if recommendation is not None:
            doc.recommendations.append(recommendation)
        # MSN-0329 Phase 5 fix: this call was imported in Phase 4 but
        # never actually invoked — every real insight was silently NOT
        # being persisted, found via re-testing before wiring this into
        # production. Now genuinely wired.
        record_insight(insight, recommendation)

    doc.insights = insights
    return doc


__all__ = ["assemble_evolved_captain_brief"]
