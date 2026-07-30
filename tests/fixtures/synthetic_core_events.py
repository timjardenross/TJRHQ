"""Synthetic `core_events`-shaped fixtures for MSN-0306 (Captain Intelligence
Platform, Programme B — Runtime Design & Simulation).

Every event dict below is shaped exactly like a real `core_events` row
(`core/infrastructure/supabase/migrations/0055_core_events.sql`) so this
corpus can be swapped for real `event_bus.poll_events()` output later
(Wave 2, Blueprint §14) with no shape changes required.

Domains used match the canonical catalogue in the Captain Intelligence
Blueprint v1.0 (MSN-0304 §6): Personal Health Intelligence, Operational
Resilience Intelligence, Holistic Wellness Coaching, Content Intelligence,
Research & Learning Intelligence, Engineering Intelligence.

This corpus is entirely synthetic and MUST NOT be cited as evidence of
real production behaviour for any domain — per MSN-0306's own "not
allowed: tuning using fake data as if it were real" constraint. It exists
solely to exercise every branch of the Attention/Priority Engines'
routing and scoring logic under controlled, known-answer conditions.
"""

from __future__ import annotations

# --- Single-event category coverage ---------------------------------------

INTERRUPT_NOW_EVENT = {
    "event_id": "evt-001",
    "event_type": "health.capacity.red",
    "domain": "personal_health_intelligence",
    "source": "core.health.capacity_gate",
    "importance": 90,
    "confidence": 85,
    "relevance": 95,
    "linked_entities": ["capacity_gate"],
    "linked_missions": [],
    "linked_documents": [],
    "recommended_action": "Review today's capacity gate action before accepting new missions.",
    "status": "new",
}

NEVER_INTERRUPT_EVENT = {
    "event_id": "evt-002",
    "event_type": "ori.source.health_check_ok",
    "domain": "operational_resilience_intelligence",
    "source": "intelligence.scheduler",
    "importance": 5,
    "confidence": 95,
    "relevance": 10,
    "linked_entities": [],
    "linked_missions": [],
    "linked_documents": [],
    "recommended_action": None,
    "status": "new",
}

CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT = {
    "event_id": "evt-003",
    "event_type": "research.finding.unverified",
    "domain": "research_learning_intelligence",
    "source": "core.coordination.research_orchestration",
    "importance": 80,
    "confidence": 30,
    "relevance": 60,
    "linked_entities": ["research-mission-42"],
    "linked_missions": ["research-mission-42"],
    "linked_documents": [],
    "recommended_action": "High-importance finding but low confidence — verify before acting.",
    "status": "new",
}

CAN_BE_DELAYED_MIDRANGE_EVENT = {
    "event_id": "evt-004",
    "event_type": "engineering.build.delivered",
    "domain": "engineering_intelligence",
    "source": "slack_bot.build_learning_loop",
    "importance": 55,
    "confidence": 80,
    "relevance": 50,
    "linked_entities": ["handoff-107"],
    "linked_missions": ["MSN-0210"],
    "linked_documents": [],
    "recommended_action": "Build delivered — review draft PR when convenient.",
    "status": "new",
}

REMEMBERED_EVENT = {
    "event_id": "evt-005",
    "event_type": "content.opportunity.logged",
    "domain": "content_intelligence",
    "source": "slack_bot.lib.comms.opportunities",
    # 30: strictly between the never-interrupt ceiling (20) and the
    # delayed floor (40) — low-salience but not so low it's filtered as
    # noise. A prior draft of this fixture used 15, which actually falls
    # into NEVER_INTERRUPT — caught by running the harness, not assumed.
    "importance": 30,
    "confidence": 70,
    "relevance": 20,
    "linked_entities": [],
    "linked_missions": [],
    "linked_documents": [],
    "recommended_action": None,
    "status": "new",
}

MISSING_SCORES_EVENT = {
    "event_id": "evt-006",
    "event_type": "wellness.pulse.logged",
    "domain": "holistic_wellness_coaching",
    "source": "telegram_bots.recovery_officer",
    # importance/confidence/relevance deliberately absent — nullable on the
    # real table; an unscored event must not be treated as a scored one.
    "linked_entities": [],
    "linked_missions": [],
    "linked_documents": [],
    "recommended_action": None,
    "status": "new",
}

# --- Batch-only category coverage ------------------------------------------

# 3 events sharing (domain, event_type) -> should aggregate as a count/trend
AGGREGATION_GROUP = [
    {
        "event_id": f"evt-agg-{i}",
        "event_type": "ori.signal.ranked",
        "domain": "operational_resilience_intelligence",
        "source": "intelligence.persistence.intelligence_store",
        "importance": 35,
        "confidence": 60,
        "relevance": 40,
        "linked_entities": [],
        "linked_missions": [],
        "linked_documents": [],
        "recommended_action": None,
        "status": "new",
    }
    for i in range(1, 4)
]

# 2 events related via a Relationship Model edge -> should summarise, not repeat
SUMMARISATION_PAIR = [
    {
        "event_id": "evt-sum-1",
        "event_type": "research.finding.published",
        "domain": "research_learning_intelligence",
        "source": "core.coordination.research_orchestration",
        "importance": 45,
        "confidence": 65,
        "relevance": 55,
        "linked_entities": ["research-mission-88"],
        "linked_missions": ["research-mission-88"],
        "linked_documents": [],
        "recommended_action": None,
        "status": "new",
    },
    {
        "event_id": "evt-sum-2",
        "event_type": "content.opportunity.created",
        "domain": "content_intelligence",
        "source": "slack_bot.lib.comms.opportunities",
        "importance": 40,
        "confidence": 70,
        "relevance": 55,
        "linked_entities": ["research-mission-88"],
        "linked_missions": [],
        "linked_documents": [],
        "recommended_action": None,
        "status": "new",
    },
]

SUMMARISATION_EDGES = {
    "evt-sum-1": ["evt-sum-2"],
    "evt-sum-2": ["evt-sum-1"],
}

# The full corpus, for tests that want "every category present at once"
FULL_MULTI_DOMAIN_CORPUS = (
    [
        INTERRUPT_NOW_EVENT,
        NEVER_INTERRUPT_EVENT,
        CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT,
        CAN_BE_DELAYED_MIDRANGE_EVENT,
        REMEMBERED_EVENT,
        MISSING_SCORES_EVENT,
    ]
    + AGGREGATION_GROUP
    + SUMMARISATION_PAIR
)

# --- Priority Engine synthetic value/opportunity inputs (not core_events
#     columns — Relationship Model edges and Content Intelligence's
#     opportunity score are separate real signals this corpus stands in for) --

SYNTHETIC_VALUE_DIMENSIONS = {
    "evt-001": {"health": 90, "career": 20},
    "evt-003": {"career": 40, "strategic": 70},
    "evt-004": {"strategic": 60},
    "evt-sum-2": {"career": 55, "strategic": 30},
}

SYNTHETIC_OPPORTUNITY_VALUES = {
    "evt-sum-2": 65,
    "evt-004": 20,
}
