---
status: "accepted"
date: 2026-09-12
decision-makers: {unknown — reconstructed from code, not from a governance-log entry}
consulted: {unknown}
informed: {unknown}
---

# Hierarchical Knowledge Navigation Layer (knowledge_nodes / knowledge_edges graph)

## Context and Problem Statement

The platform needed one place where every "navigable" governance/knowledge
entity — principle, objective, initiative, mission, decision, ADR, lesson —
could be related to every other one (a mission implements an objective, a
decision is `governed_by` an ADR, and so on), instead of each domain
inventing its own ad-hoc cross-referencing. ADR-022 is the decision to build
this as a single generalised graph rather than one graph per domain.

## Decision Drivers

* Avoid building a second relationship/graph engine for every new domain
  that needs cross-references (missions, capabilities, officers, tasks…).
* Keep the hierarchy navigable and queryable (not just markdown prose links).
* Support both human-declared edges (confidence 1.0) and auto-extracted ones
  (confidence < 1.0).

## Considered Options

* One shared `knowledge_nodes`/`knowledge_edges` graph, generalised over time
  to new entity types as new domains need it.
* A separate relationship table/schema per domain (governance graph,
  platform-runtime graph, etc.).

## Decision Outcome

Chosen option: "One shared graph, generalised over time", because migration
0126 (`0028_knowledge_hierarchy`, historically also numbered 0028 in a
mission-ID collision) established `knowledge_nodes`/`knowledge_edges` first
for the governance hierarchy (`principle(0) → objective(1) → initiative(2) →
mission(3) → decision(4) → adr(5) → lesson(6)`), and migration 0057
("SUOC Wave 3, Workstream D") deliberately extended — did not replace or
duplicate — that same schema to cover platform-runtime entities
(capability/pattern/officer/task/event/confidence/outcome/learning/memory),
explicitly because "the Wave 3 discovery pass confirmed no other persisted
relationship/graph store exists anywhere in the repo."

### Consequences

* Good, because new domains (platform-runtime relationships, per
  `core/platform/relationship_model.py`) get graph support by extending one
  schema's enums rather than standing up new infrastructure.
* Good, because typed edges (`expresses|pursues|contains|produces|generates|
  governed_by|informed_by|depends_on|supersedes|validates|contradicts|
  references|emits|informs`) give one shared vocabulary for "how X relates to Y"
  across the whole platform.
* Bad, because sync into the graph is manual (`core/knowledge_navigation/sync.py`),
  not event-triggered — per `knowledge/SUOC-Platform-Registry.md`'s own
  Technical Debt note, so the graph can lag reality.
* Bad, because provenance of the parallel, unrelated `temporal_entities`/
  `facts`/`episodes` tables (created the same week under a colliding
  migration number `0028_temporal_memory`) is still unresolved and has been
  mistaken for part of this decision before — they are a *different*,
  orphaned system, not ADR-022's tables.

### Confirmation

`core/knowledge_navigation/sync.py` populates `knowledge_nodes`/`knowledge_edges`
from `knowledge/hierarchy/Objectives.md`, `Initiatives.md`,
`governance/ADR-*.md`, `knowledge/Lessons-Learned.md`, `knowledge/decisions/`,
and `Missions/Active/` (per migration 0126's table comment). The
`knowledge_hierarchy_summary` view gives node counts by type/level/status for
graph-health monitoring; `knowledge_unmapped_missions` surfaces missions with
no initiative parent. `knowledge/SUOC-Platform-Registry.md` reports "88%
engineering confidence... the underlying schema (ADR-022) has years of
correct operation," and as of MSN-0210K, 6 capability/officer nodes and 13
evidence-backed edges exist as real content (not just an empty, live-verified
schema).

## Pros and Cons of the Options

### One shared, generalised graph

* Good, because it was validated by an explicit discovery pass (Wave 3)
  before extending rather than duplicating.
* Good, because `core/platform/relationship_model.py` and
  `core/advisory/episodic.py` both reuse it "opportunistically" rather than
  building their own store.
* Neutral, because generalising an existing schema (adding node types/verbs)
  is itself a maintenance cost every time a new domain needs it.

### Per-domain relationship tables

* Bad, because it was explicitly rejected — the Wave 3 discovery pass found
  "no other persisted relationship/graph store exists anywhere in the repo,"
  meaning nothing was actually built this way, and building one would have
  contradicted the reuse-first principle already in effect for this area
  (see ADR-020).

## More Information

Evidence: `core/knowledge_navigation/__init__.py`, `core/advisory/episodic.py`,
`core/platform/relationship_model.py`, migrations
`core/infrastructure/supabase/migrations/0057_relationship_model_extension.sql`
and `0126_knowledge_hierarchy.sql`, `knowledge/SUOC-Platform-Registry.md`
(lines documenting "Related ADRs: ADR-022" for both the Knowledge and
Platform Relationships capabilities), and
`.claude/skills/bot-reviews/fixes-2026-08-09/orphaned-rls-tables-investigation.md`
(which uses ADR-022 as the known-good reference point while investigating the
unrelated, orphaned `temporal_*` tables created in the same week under a
colliding migration number). Also referenced (title-only, non-authoritative)
in the stale `ArchitectureIndex.tsx`/`captainReview.ts` UI mock and a
`temporal_entities` ghost-table dump — not used as sourcing here, since the
`core/knowledge_navigation` and migration evidence is direct and sufficient.
Related: ADR-020 (Capability Reuse Before Capability Creation) — the same
reuse discipline this decision follows; ADR-027 (Whole-of-System Principle) —
the Platform Relationships graph is how ADR-027's "discoverable/linked"
requirement is satisfied for capabilities that have a graph node.
