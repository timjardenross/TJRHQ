"""MSN-0306 (Captain Intelligence Platform, Programme B): end-to-end
composition test — Attention Engine -> Priority Engine -> Captain Brief
contract, against the synthetic corpus. Proves the three modules wire
together correctly; this is the evidence behind this mission's Integration
Readiness Report, not a claim about live behaviour.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import evaluate_batch, AttentionCategory
from core.platform.priority_engine import PriorityInputs, rank_events
from core.platform.captain_brief_contract import (
    Recommendation,
    assemble_captain_brief,
)
from tests.fixtures.synthetic_core_events import (
    FULL_MULTI_DOMAIN_CORPUS,
    SUMMARISATION_EDGES,
    SYNTHETIC_VALUE_DIMENSIONS,
    SYNTHETIC_OPPORTUNITY_VALUES,
)


def test_full_pipeline_composes_without_error():
    decisions = evaluate_batch(FULL_MULTI_DOMAIN_CORPUS, related_edges=SUMMARISATION_EDGES)

    inputs_list = [
        PriorityInputs(
            event_id=e["event_id"],
            domain=e["domain"],
            event_type=e["event_type"],
            importance=e.get("importance"),
            confidence=e.get("confidence"),
            relevance=e.get("relevance"),
            value_dimensions=SYNTHETIC_VALUE_DIMENSIONS.get(e["event_id"], {}),
            opportunity_value=SYNTHETIC_OPPORTUNITY_VALUES.get(e["event_id"]),
        )
        for e in FULL_MULTI_DOMAIN_CORPUS
    ]
    scores_by_id = {s.event_id: s for s in rank_events(inputs_list)}

    recommendations = {
        "evt-001": Recommendation(
            description="Review today's capacity gate action before accepting new missions.",
            action_type="review",
            confidence=85,
            requires_approval=True,
        )
    }

    brief = assemble_captain_brief(decisions, priority_scores=scores_by_id, recommendations=recommendations)

    # evt-001 (INTERRUPT_NOW) must appear in interrupt_now, ranked, with its recommendation attached
    assert any(item.event_id == "evt-001" for item in brief.interrupt_now)
    interrupt_item = next(item for item in brief.interrupt_now if item.event_id == "evt-001")
    assert interrupt_item.recommendation.action_type == "review"
    assert interrupt_item.priority_score is not None

    # Counts must reconcile: every input event lands in exactly one bucket
    total_surfaced = (
        len(brief.interrupt_now)
        + len(brief.can_be_delayed)
        + len(brief.should_be_summarised)
        + len(brief.should_be_aggregated)
    )
    assert total_surfaced + brief.remembered_count + brief.never_interrupt_count == len(FULL_MULTI_DOMAIN_CORPUS)

    # interrupt_now must be sorted by priority score, highest first
    scores = [item.priority_score or 0 for item in brief.interrupt_now]
    assert scores == sorted(scores, reverse=True)


def test_recommendation_flattens_to_free_text_for_legacy_consumers():
    rec = Recommendation(description="Do the thing.", action_type="review")
    assert rec.as_text() == "Do the thing."


def test_brief_never_surfaces_never_interrupt_events_even_individually():
    decisions = evaluate_batch(FULL_MULTI_DOMAIN_CORPUS, related_edges=SUMMARISATION_EDGES)
    brief = assemble_captain_brief(decisions)
    all_surfaced_ids = {
        item.event_id
        for bucket in (brief.interrupt_now, brief.can_be_delayed, brief.should_be_summarised, brief.should_be_aggregated)
        for item in bucket
    }
    never_interrupt_ids = {d.event_id for d in decisions if d.category == AttentionCategory.NEVER_INTERRUPT}
    assert not (all_surfaced_ids & never_interrupt_ids)
