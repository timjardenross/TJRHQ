# Knowledge Record — USS-TJR-MSN-0369 Stream 3 (ADR Formalization)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0369 |
| Title | Real Backlog Closeout (Bandit/Ruff/ADR/Dependabot) — Stream 3 only |
| Scope | ADR formalization / governance docs only, no code changes |
| Date | 2026-09-12 |
| Branch | msn-0369-stream3-adr-filing |
| Follows | USS-TJR-MSN-0368 Stream 7 (filed ADR-020, ADR-027; identified the ~9-number real-citation scope) |

## Outcome

Filed all 7 remaining real-cited ADR numbers into
`core/governance/architecture-decision-records/` in MADR 4.0.0 format, per
`docs/decisions/TEMPLATE-madr.md`. Method: `grep -rn "ADR-0NN"` across the
whole repo for each number (not just the obvious files), reading enough
citing context in each real hit to reconstruct what was decided, why, and
what it excludes — treated as reconstruction from evidence, not invention.
Two non-authoritative sources recur across almost every number and were
explicitly **not** used as primary sourcing, only as weak title
corroboration where they happened to agree with real code:

1. `lcars-portal/src/app/knowledge-workbench/_components/ArchitectureIndex.tsx`
   / `lcars-portal/src/lib/investigations/captainReview.ts` — a
   hand-maintained UI mock explicitly commented as "not guaranteed complete
   or current," which the code's own comment says MSN-0353 §4 recommended
   retiring. Its titles for ADR-003/004/013/022/024 directly **contradict**
   the real code evidence in several cases.
2. `core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`
   — a pre-drop dump of the orphaned `temporal_entities_archived_2026` ghost
   table (confirmed elsewhere in this repo's own knowledge base to have zero
   owning application code). All its ADR entries carry status `UNKNOWN` and
   reference `.txt`/`.md` files that never existed on disk.

## Per-ADR results

| ADR | File | Confidence | Real (non-fixture) citation count / key locations |
|---|---|---|---|
| ADR-013 | `ADR-013-advisory-only-recommendation-is-not-a-decision.md` | **High** — accepted | 6 real citations: `core/coordination/lifecycle_reconciler.py`, `engineering_prep.py`, `lifecycle_advancer.py`, `lifecycle_coverage.py`, `triage_package.py`, `review_package.py`. Consistent, load-bearing governance rule ("Number One recommends, XO decides") repeated verbatim across the mission-lifecycle pipeline. |
| ADR-022 | `ADR-022-hierarchical-knowledge-navigation-graph.md` | **High** — accepted | Real citations in `core/knowledge_navigation/__init__.py`, `core/advisory/episodic.py`, `core/platform/relationship_model.py`, migrations `0057_relationship_model_extension.sql` and `0126_knowledge_hierarchy.sql` (multiple `COMMENT ON TABLE`/view citations), `knowledge/SUOC-Platform-Registry.md` (2 capability entries), and `.claude/skills/bot-reviews/fixes-2026-08-09/orphaned-rls-tables-investigation.md`. |
| ADR-024 | `ADR-024-resilience-intelligence-convergence.md` | **High** — accepted | 15+ real citations: `core/platform/operational_state_model.py`, `core/platform/infra_narrative.py`, `core/llm/provider_chain.py`, `core/health/health_llm.py`, `intelligence/proactive_cadences.py`, `intelligence/ingestion/collection_engine.py`, `intelligence/captains_brief.py`, `platform-runtime/human_systems_scheduler.py`, `platform-runtime/commands/{health_check,recovery_pulse,mission_lifecycle}.py`, `deploy/mission-registry-sync.{service,timer}`, migration `0083_domain_registry_wellness_and_registry_sync.sql`. |
| ADR-030 | `ADR-030-engineering-router-execution-model.md` | **Medium** — Reconstructed, partially unimplemented | Real citations in `core/engineering/providers/gemini.py` (governance boundary: plan/review-only, no auto-apply) and `platform-runtime/test_build_router_alignment.py` (expects an "Engineering Router Metadata" / `ADR-030` handoff section that `mission_brief.py`'s current `save_engineering_handoff_from_build_record()` does **not** implement — flagged as an open gap, not fixed, since this stream is docs-only). |
| ADR-004 | `ADR-004-knowledge-architecture-low-confidence.md` | **Low** — Reconstructed | Real but thin: `core/coordination/number_one_memory_adapter.py` (`_retrieve_from_files()` maps `"adr"` queries to `ADR-004-Knowledge-Architecture.txt`, which does not exist on disk) and `platform-runtime/test_decision.py` (uses "ADR-004: knowledge architecture" as fixture text). Title corroborated by the ghost-table dump but no real decision content found anywhere. |
| ADR-003 | `ADR-003-unresolved-low-confidence.md` | **Low** — Reconstructed, contradictory | Only real citation is boilerplate placeholder text in an MSN-0013C demo script (`tools/supabase/event_listeners.py`, "Link to related ADR-003 if introducing new services" — same function also invents fake "ADR-001"/"DEC-015" filler). The UI mock and the ghost table **disagree** with each other on subject matter (FastAPI backend vs. Tailscale networking). Filed as an honest "no decision reconstructed" record. |
| ADR-031 | `ADR-031-agent-orchestration-standardisation-low-confidence.md` | **Low** — Reconstructed | Only real citation is an aspirational example query in `docs/runbooks/graphify-query-templates.md` ("ADR-031 agent orchestration"), not an actual usage citation. Ghost table agrees on topic name only. No module in the repo cites ADR-031 as governing its own behaviour. Filed as an honest "no decision reconstructed" record. |

Previously filed (not touched this stream): **ADR-020** (Capability Reuse
Before Capability Creation), **ADR-027** (Whole-of-System Principle) — both
`status: accepted`, both high confidence per MSN-0368 Stream 7.

## Acceptance check

Ran `grep -rn "ADR-0[0-9][0-9]"` repo-wide after filing and extracted the
distinct numbers cited: `000–031` (32 distinct numbers appear somewhere in
the tree). Of these, only **9** (`003, 004, 013, 020, 022, 024, 027, 030,
031`) now have canonical files in `core/governance/architecture-decision-records/`
— this matches the full scope MSN-0368 Stream 7 identified as "genuinely
real, code-referenced" citations, and this mission's brief explicitly scoped
only the 7 not yet filed.

**Flag for the record — numbers NOT resolved to a canonical file, and why
that's expected, not a miss:** ADR-000–002, 005–012, 014–019, 021, 023,
025–029 all still appear somewhere in the repo (mostly inside
`core/context-assembly/enrichment_poc/` sample/fixture data, and the same
stale `ArchitectureIndex.tsx`/`captainReview.ts` UI mock, per MSN-0368
Stream 7's own finding: "18 hits (roughly ADR-001 through ADR-011) turned
out to be inside `core/context-assembly/enrichment_poc/` sample/fixture
data, not real governance citations"). This mission's brief explicitly
scoped work to the 7 remaining numbers from that already-vetted 9-number
list and explicitly said not to re-litigate the "4 scattered registries"
premise — re-auditing all 32 raw numbers for real-vs-fixture status was out
of scope for Stream 3 and was not attempted here. A future stream that wants
full closure on the raw `grep` surface would need to re-verify each of those
~23 remaining numbers individually against `enrichment_poc/` and any other
locations before deciding whether any of them also deserve a canonical file
or are confirmed pure fixture noise.

## Process notes / lessons

* The recurring pattern across all 7 numbers: a stale, self-admittedly
  unreliable UI mock and an orphaned ghost-table dump both "cite" every ADR
  number with confident-sounding titles, but neither is real evidence — they
  should be actively distrusted as primary sources for any future ADR
  reconstruction in this repo, and checked against real code/migration
  citations before being trusted even as a title hint (ADR-003's two
  fictional sources directly contradicted each other; ADR-024's fictional
  titles were flatly wrong compared to 15+ pieces of real code evidence).
* Real evidence quality varied enormously by number even within the same
  7-item batch — ADR-013/022/024 had deep, consistent, multi-file governance
  language; ADR-030 had a real but partially-unimplemented feature; ADR-003/
  004/031 had essentially nothing beyond title-guessing. The instruction to
  file low-confidence numbers honestly rather than inventing content was
  necessary and used for 3 of the 7.
* Found (not fixed, out of scope for this docs-only stream): a likely
  pre-existing test/implementation mismatch in
  `platform-runtime/test_build_router_alignment.py` vs.
  `platform-runtime/commands/mission_brief.py`'s
  `save_engineering_handoff_from_build_record()` — the test expects an
  "Engineering Router Metadata" section with an `ADR-030` citation that the
  current implementation does not produce. Worth a follow-up to confirm
  pass/fail and either implement the missing section or update the test.
