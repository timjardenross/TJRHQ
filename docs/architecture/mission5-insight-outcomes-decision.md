# Mission 5 — `insight_outcomes` architecture decision

## The gap this closes

`insight_outcomes` (migration `core/infrastructure/supabase/migrations/0062_insight_outcomes.sql`,
read/write module `core/platform/insight_outcomes.py`) was write-only in
production. `captain_brief_evolution.py:75-83` (`assemble_evolved_captain_brief()`)
calls `record_insight()` on every real Captain Brief assembly, but
`fetch_outcome_history()` — the table's only read function — had zero
call sites anywhere in the repo before this mission. Number One
(`reasoning_engine.build_recommendation()`, `insight_engine.py`) never
read its own outcome history to adjust anything it produced.

## What was wired (this mission)

- `core/platform/insight_outcomes.py`: added `fetch_similar_outcomes(source_kind, source_domains, limit=200)`
  — a thin filter over the existing `fetch_outcome_history()`, not a new
  query shape. Returns rows sharing `source_kind` and at least one
  `source_domains` entry, restricted to rows with a real recorded
  `outcome` (`useful`/`not_useful`/`incorrect` — `pending` carries no
  evidence yet).
- `core/platform/reasoning_engine.py:build_recommendation()` now calls
  `_apply_outcome_evidence()` on every recommendation it builds, which:
  - below `_MIN_OUTCOMES_FOR_ADJUSTMENT = 3` recorded outcomes, makes
    **zero** changes (no confidence shift, no note, no error) — mirrors
    `core/coordination/mission_knowledge_store.py`'s own
    `_MIN_OUTCOMES_FOR_SCORE = 3` floor exactly, so this platform has one
    consistent "not enough evidence to say anything" threshold, not two.
  - at or above the floor, applies a coarse, tiered confidence
    adjustment (`+0.08` / `+0.04` / `0.0` / `-0.08`, clamped to
    `±0.15` — reusing `mission_knowledge_store.get_intelligence_evidence()`'s
    own clamp value, `core/coordination/mission_knowledge_store.py:328`,
    rather than inventing a new bound for the same category of
    adjustment).
  - appends a plain-language, evidence-grounded sentence to
    `Recommendation.supporting_context` naming the exact sample size and
    useful/not_useful split, framed the same causality-guarded way
    `telegram-bots/capacitybot/intervention_engine.py:423-427` already
    frames its own outcome surfacing ("was followed by improvement in N
    of M") — an association, never a claim that a past outcome caused
    this new insight to be correct.

No new confidence-scoring model, no second evidence engine: this is one
additional consumer of the one existing table, using thresholds and a
clamp this codebase already established elsewhere.

## Is the current data sufficient in practice?

Not yet, and the wiring is deliberately built to say so honestly rather
than force a conclusion. This sandbox has no live Supabase access to
confirm today's exact row count, but the discovery grep hit ("insight_outcomes
sat at 3 rows") and MSN-0329's own Phase 4 gate (tune only once
`insight_outcomes` reaches ≥20 rows) both point the same direction: real
accumulated history here is still thin. `_apply_outcome_evidence()`'s
floor of 3 means it will mostly no-op today, by design — a correctly
built consumer with an empty inbox, not a bug. It will start
contributing real adjustments as `record_insight()`'s write path (already
live and unconditional) keeps accumulating rows, and as `record_outcome()`
gets more real calls (today: an engineer reviewing results; eventually,
per the table's own migration comment, the Captain via a real UI).

## Decision: keep `insight_outcomes` as its own narrow evidence source — do not merge or retire it

Reasoned recommendation, as required by this mission's brief:

**Keep.** `insight_outcomes` is architecturally distinct from the
capacity/Ready Room evidence model this same mission generalises
elsewhere (`capacity_interventions` / `capacity_intervention_events`,
migration `0218_mission5_evidence_domain_generalisation.sql`,
`docs/architecture/mission5-preferences-contract.md`):

1. **Different unit of evidence.** The capacity/Ready Room model tracks
   evidence for a fixed, named catalogue of *interventions* — "was
   `rr_unstick_me` followed by improvement" — a small, enumerable set of
   things a human can choose to offer again. `insight_outcomes` tracks
   evidence for *individual, LLM-synthesized Insights/Recommendations* —
   free-text observations about relationships/conflicts the Understanding
   Engine found, which are never the same insight twice (each has its own
   `observation`/`why_it_matters` text and `evidence_chain` of real
   event IDs). There is no shared catalogue to unify these onto without
   inventing a canonical "insight type" taxonomy that does not exist
   today and that Mission 5's own discovery for the capacity/Ready Room
   side explicitly avoided building a second version of.
2. **Different domain.** Capacity/Ready Room evidence is about *execution
   support* — did a specific intervention offered to help the Captain do
   a task actually help. `insight_outcomes` is about *relationship/
   conflict intelligence* — was a cross-domain pattern Number One
   surfaced actually meaningful. These are genuinely different questions
   answered by genuinely different upstream systems (`intervention_engine.py`
   / capacitybot vs. `understanding_engine.py` / `insight_engine.py` /
   `reasoning_engine.py`). Merging the tables would not reduce evidence
   engines from two to one; it would produce one table serving two
   unrelated read patterns with a `nullable`-everything schema, which is
   the outcome Mission 5's own capacity-generalisation migration
   explicitly rejected doing for a second time ("Mission 5 generalises
   this ONE model across domains rather than building a second evidence
   engine" — `0218_mission5_evidence_domain_generalisation.sql:9`).
3. **Already-correct schema for its actual job.** `insight_outcomes`
   (`0062_insight_outcomes.sql`) already has the right shape for what it
   evidences: `source_kind`/`source_domains`/`evidence_chain` describing
   an insight's own provenance, plus the same non-punitive
   `pending`-default `outcome` vocabulary
   (`useful`/`not_useful`/`incorrect`/`pending`) the capacity model uses.
   It was never architecturally broken — it was unread. This mission
   fixes that; it does not need a schema change or a merge to become
   useful.

**What would change this recommendation:** if a future mission
introduces a genuinely shared "was this suggestion good" taxonomy that
both execution-support interventions and cross-domain insights map onto
cleanly (not merely "both have an outcome enum"), a unification would be
worth another explicit decision at that point. Nothing in this mission's
scope motivates that now, and forcing it prematurely would cost real
regression risk to the now-generalised capacity/Ready Room model for no
present benefit.

## Files referenced (file:line)

- `core/platform/insight_outcomes.py:30` — `record_insight()`, the
  existing write path (already live, called from
  `captain_brief_evolution.py:83`).
- `core/platform/insight_outcomes.py:111` — `fetch_outcome_history()`,
  the pre-existing read function with zero callers before this mission.
- `core/platform/insight_outcomes.py` (new) — `fetch_similar_outcomes()`,
  added this mission, the first real caller.
- `core/platform/reasoning_engine.py` — `_MIN_OUTCOMES_FOR_ADJUSTMENT`,
  `_MAX_CONFIDENCE_ADJUSTMENT`, `_outcome_evidence()`,
  `_apply_outcome_evidence()`, `build_recommendation()` (now calls
  `_apply_outcome_evidence()` before returning).
- `core/coordination/mission_knowledge_store.py:29` —
  `_MIN_OUTCOMES_FOR_SCORE = 3`, the floor this mission's
  `_MIN_OUTCOMES_FOR_ADJUSTMENT` mirrors.
- `core/coordination/mission_knowledge_store.py:328` — the `±0.15`
  clamp this mission's `_MAX_CONFIDENCE_ADJUSTMENT` reuses.
- `telegram-bots/capacitybot/intervention_engine.py:423-427` — the
  causality-guarded ("was followed by improvement in") framing this
  mission's evidence note reuses.
- `core/infrastructure/supabase/migrations/0218_mission5_evidence_domain_generalisation.sql:9`
  — the sibling Mission 5 workstream's own "generalise, don't duplicate"
  decision for the capacity/Ready Room evidence model, cited above as
  the reasoning this decision does not extend to `insight_outcomes`.
- `tests/test_reasoning_engine_outcome_evidence.py` — new test coverage
  for the floor/clamp/no-op-below-floor/mixed-evidence behaviour added
  this mission.
