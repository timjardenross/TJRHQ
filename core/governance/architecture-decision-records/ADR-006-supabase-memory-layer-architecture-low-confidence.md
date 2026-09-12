---
status: "Reconstructed — low confidence"
date: 2026-09-12
decision-makers: {unknown}
consulted: {unknown}
informed: {unknown}
---

# ADR-006 — "Supabase Memory Layer Architecture" (title corroborated, decision content not found)

## Context and Problem Statement

ADR-006 is cited by name, repeatedly, in real, non-fixture, load-bearing
production code and its accompanying tests — not merely in a mock or an
orphaned data dump:

* `core/coordination/number_one_memory_adapter.py` (395 lines, real module)
  opens with the docstring "This reuses the ADR-006 Supabase memory pattern
  without changing governance or assignment authority. Retrieval failures
  are non-blocking." Its `_retrieve_from_files()` fallback also references
  an expected (but non-existent in the tracked repo) file path
  `core/governance/architecture-decision-records/ADR-006-Supabase-Memory-Layer-Architecture.txt`.
* `platform-runtime/test_number_one_memory_phase2a.py` — `"""Tests for
  ADR-006 Phase 2A: Number One memory-aware oversight."""` — exercises the
  real `NumberOneMemoryAdapter`/`MemoryContext` classes.
* `platform-runtime/test_mission.py` — `"""Tests for ADR-006 Phase 3 mission
  registry memory integration."""` — exercises the real
  `MissionRegistryMemoryAdapter` against `MissionRegistry`.
* `platform-runtime/test_research_memory_phase1.py` — `"""Phase 1 tests for
  ADR-006 research memory activation."""` — exercises `research_command`'s
  memory-reuse-before-new-execution path.

Together these describe a real, phased rollout (Phase 1 research memory →
Phase 2A Number One oversight → Phase 3 mission registry) of a
Supabase-backed "memory layer" that supplies advisory historical context
(prior research, prior missions, prior ADR/capability content) to reduce
duplicate work, with retrieval explicitly designed to fail open
(non-blocking) rather than block on Supabase being unavailable.

This is independently, if weakly, corroborated by the orphaned
`temporal_entities_archived_2026` ghost table (documented elsewhere as
having "zero owning application code" and therefore not itself trustworthy
as a citation — see ADR-003's file for why this source alone is
insufficient): it lists `ADR-006` with summary "Supabase Memory Layer
Architecture," status `APPROVED`, matching the docstring's title exactly.
Unlike the placeholder-style summaries the same table gives ADR-007 through
ADR-012 (literally the slug repeated as the summary, status `UNKNOWN`), the
ADR-001–ADR-006 entries carry distinct human-written prose titles and
`APPROVED` status — consistent with (but not proof of) these six having been
real, formalized decisions before this table was populated by a one-time
2026-06-21 backfill script (per the independent forensic timeline in
`.claude/skills/bot-reviews/fixes-2026-08-09/orphaned-rls-tables-investigation.md`,
which found the backfill ingested exactly "9 ADRs (ADR-001…ADR-009 +
ADR-INDEX)" from whatever the *existing* decisions/ADR data was at the time).

None of this reconstructs the decision's actual drivers, considered
alternatives, or explicit exclusions — only that a real "Supabase memory
layer" architecture was decided, named ADR-006, and is actively implemented
and tested in three phases today.

## Decision Outcome

**No confident decision reconstructed.** What can honestly be said: ADR-006
established that Number One (and the research/mission-registry paths built
on top of it) may retrieve advisory historical context from a Supabase-backed
memory layer, with file-based fallback content when Supabase is unavailable,
and that such retrieval must be advisory-only and non-blocking — it must not
change governance or assignment authority (per the adapter's own docstring).
It is the same decision ADR-004 ("Knowledge Architecture") explicitly pairs
itself with. Beyond that scope statement, no documented decision drivers,
considered options, or consequences could be found anywhere in the live
repository — inventing them would misrepresent a past decision.

### Confirmation

If a real `ADR-006` decision document is ever found (e.g. an external
knowledge system, a deleted commit, or Notion), it should replace this
file's content rather than being merged with invented material. Until then,
treat this file as a placeholder confirming the number, its title, and its
real downstream implementation — not as an authoritative record of the
decision's reasoning.

## More Information

Evidence (`grep -rn "ADR-006"` repo-wide, 2026-09-12, USS-TJR-MSN-0370):
`core/coordination/number_one_memory_adapter.py`,
`platform-runtime/test_number_one_memory_phase2a.py`,
`platform-runtime/test_mission.py`,
`platform-runtime/test_research_memory_phase1.py`,
`core/context-assembly/tests/test_captain_brief_integration.py` (synthetic
fixture data only — a `governing_adrs` list in an illustrative test brief,
adds no independent evidence), `core/governance/architecture-decision-records/ADR-004-knowledge-architecture-low-confidence.md`
(already documents the ADR-004/ADR-006 pairing), and title-only corroboration
from `core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`
(ghost `temporal_entities_archived_2026` table, non-authoritative per
ADR-003's file). Also appears in the stale
`ArchitectureIndex.tsx`/`captainReview.ts` UI mock and
`core/context-assembly/enrichment_poc/` fixture data — neither used as
sourcing here.
