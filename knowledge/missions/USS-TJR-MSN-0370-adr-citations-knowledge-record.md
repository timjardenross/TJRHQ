# USS-TJR-MSN-0370 — ADR Citation Sweep (follow-up to MSN-0369)

## Mission

MSN-0369 Stream 3 filed 9 canonical ADRs (ADR-003/004/013/020/022/024/027/030/031)
in `core/governance/architecture-decision-records/`. `grep -rn "ADR-0[0-9][0-9]"`
repo-wide still surfaced bare citations to ~23 other numbers
(000–002, 005–012, 014–019, 021, 023, 025–029) that don't resolve to any
canonical file. MSN-0368 Stream 7 *suspected* most of these were
`core/context-assembly/enrichment_poc/` fixture data and the stale
`ArchitectureIndex.tsx`/`captainReview.ts` UI mock, but that was never
verified number-by-number. This mission did that verification.

## Method

For each of the 23 numbers: `grep -rn "ADR-0NN\b"` repo-wide, read every
citing file, and classify. A citation only counted as "real" if it appeared
in live, load-bearing production code or its accompanying tests — not in
the known-stale UI mock, not in `enrichment_poc/` fixture data, not in
template/example boilerplate, not in test fixture literals, and not in the
orphaned `temporal_entities_archived_2026` ghost table alone (established
by MSN-0369's ADR-003 file as insufficient on its own — "zero owning
application code").

## Result summary

- **1 of 23 was a real, evidenced citation** and has been reconstructed:
  **ADR-006** — `core/governance/architecture-decision-records/ADR-006-supabase-memory-layer-architecture-low-confidence.md`
  (status: Reconstructed — low confidence, same honesty tier as ADR-004).
- **22 of 23 are not real architectural citations** — noise from fixture
  data, a stale UI mock, template/example boilerplate, test fixtures, or
  self-improvement pipeline telemetry (ephemeral agent-worktree
  `git status` snapshots that were never committed to this repo). No files
  were written for these; see the table below for evidence per number.
- **0 flagged as "something else" requiring escalation.** A few numbers
  (008, 009, 023) had secondary/forensic corroboration worth noting (see
  table) but none crossed the bar for reconstruction or for a standalone
  flag — they are documented inline instead.

## Classification table

| ADR # | Classification | Citation count (files) | Evidence / notes |
|---|---|---|---|
| 000 | Fixture/meta noise | 1 | Only appears in MSN-0369 Stream 3's own knowledge record, listing the noise-number range itself (self-referential, not a citation of a decision). |
| 001 | Template/example + test-fixture noise | ~24 | `AGENTS.md` and `platform-runtime/adr_conflict_detector.py` point at `docs/decisions/EXAMPLE-ADR-001-...md` (explicitly an example file). `docs/decisions/TEMPLATE-madr.md` uses ADR-001/002 as numbering-convention examples. `tools/supabase/knowledge_packs.py` and `tools/supabase/test_msn_0013bcd.py` use "ADR-001: Kubernetes Migration" as literal `# Example usage` / test-fixture sample data (fictional, unrelated to any real Kubernetes decision). `tools/supabase/event_listeners.py`'s "See ADR-001" is demo filler already flagged by ADR-003's own file as invented example text in the same function. `core/knowledge_navigation/tests/*` use ADR-001 as a generic graph-fixture node ("Use Supabase"). Remainder: `enrichment_poc/`, `ArchitectureIndex.tsx`/`captainReview.ts`, mission-record meta-mentions. |
| 002 | Template/example + test-fixture noise | ~18 | `core/context-assembly/run_validation.py` uses `'ADR-002'` as a hardcoded fallback default string in a report generator, not a citation. `core/context-assembly/tests/test_captain_brief_integration.py`'s `governing_adrs: ["ADR-002"]` is synthetic fixture data for a fictional test mission (`MSN-0009`). `docs/decisions/TEMPLATE-madr.md` uses it as a numbering-convention example. Remainder: `enrichment_poc/`, mock, backups. |
| 005 | Fixture/mock noise | 4 | Only in `enrichment_poc/`, the ghost-table backup, `ArchitectureIndex.tsx`/`captainReview.ts` mock ("Slack as primary push notification channel"), and `TEMPLATE-madr.md`'s numbering example. No production code. |
| **006** | **Real citation — RECONSTRUCTED** | ~10 real + noise | `core/coordination/number_one_memory_adapter.py` (395-line production module, docstring: "reuses the ADR-006 Supabase memory pattern... Retrieval failures are non-blocking"), plus three real `platform-runtime/test_*.py` suites explicitly testing "ADR-006 Phase 1" (research memory), "Phase 2A" (Number One oversight), "Phase 3" (mission registry integration). Already cross-referenced by the existing `ADR-004` file as ADR-004's paired decision. See filed ADR-006 for full evidence list. |
| 007 | Fixture/mock noise | ~12 | Only in `enrichment_poc/` (MSN-0008 demo fixture), the ghost table (`ADR-007-Source-Data-Contract-Validation`, status `UNKNOWN`, auto-generated-looking summary), self-improvement run telemetry (ephemeral uncommitted-file snapshot, never merged), and the stale UI mock. No production code. |
| 008 | Fixture/mock noise (secondary forensic corroboration noted, insufficient) | ~13 | Same pattern as 007, plus `.claude/skills/bot-reviews/fixes-2026-08-09/orphaned-rls-tables-investigation.md` — an independent forensic doc that names ADR-008 "knowledge as a strategic capability" while explaining the ghost table's one-time 2026-06-21 backfill origin. This is real investigative *commentary about* a historical topic, not a citation *in* live code — per the ADR-003 precedent, ghost-table-derived evidence alone (even when corroborated by forensic analysis of the same ghost table) doesn't meet the reconstruction bar. Not flagged separately since the investigation doc itself already treats this as unresolved/historical, not actionable. |
| 009 | Fixture/example noise | ~15 | Cited only as a generic **ID-format example** alongside `OBJ-001`, `INI-002`, `MSN-0053`, `LL-023` in real code comments/docstrings (`core/knowledge_navigation/models.py`, `sync.py`, `platform-runtime/commands/navigate.py`, `core/infrastructure/supabase/migrations/0126_knowledge_hierarchy.sql`, `docs/runbooks/graphify-query-templates.md`) — illustrating the *shape* of an ADR ID, not citing a specific decision's content. Ghost table gives it a placeholder-style summary (`ADR-009-Supabase-as-Operational-Data-Layer`, status `UNKNOWN`) matching the slug verbatim rather than prose — consistent with being an artifact of the same backfill, not a formalized decision. |
| 010 | Fixture/mock noise | ~13 | Only `enrichment_poc/`, ghost table, self-improvement telemetry, UI mock. Zero real code. |
| 011 | Test-fixture noise | ~8 | `platform-runtime/test_decision.py`'s `DecisionRegistryMemoryAdapterTests` uses `"adr_reference": "ADR-011"` as `_FakeSupabase` synthetic test data ("Approve mission registry consolidation" — fictional). Remainder: `enrichment_poc/`, UI mock, mission-record meta-mentions. No entry at all in the ghost table (the only number in the 000–012 range missing from it). |
| 012 | Fixture/mock noise | ~13 | Same pattern as 010. |
| 014 | Fixture/mock noise | 35 | Only `data/self-improvement/runs/*/evidence.json` (10 files, ephemeral worktree snapshot noise) + ghost table + UI mock. |
| 015 | Fixture/mock noise | 35 | Same pattern. |
| 016 | Fixture/mock noise | 35 | Same pattern. |
| 017 | Fixture/mock noise | 35 | Same pattern. |
| 018 | Fixture/mock noise | 35 | Same pattern. |
| 019 | Fixture/mock noise | 35 | Same pattern. |
| 021 | Fixture/mock noise | 35 | Same pattern. |
| 023 | Fixture/mock noise | 35 | Same pattern; one self-improvement snapshot file additionally names a never-committed `governance/ADR-023-Public-Site-as-Canonical-tjrmindbody-com.md` from an ephemeral agent worktree — real filename, but never merged/adopted, and not present anywhere in the tracked repo today. |
| 025 | Fixture/mock noise | 35 | Same pattern. |
| 026 | Fixture/mock noise | 36 | Same pattern, plus `lcars-portal/src/lib/__tests__/captainReview.test.ts` — a unit test *of the stale mock itself*, not an independent citation. |
| 028 | Fixture/mock noise | 21 | Self-improvement telemetry + ghost table only (no UI mock reference for this one). |
| 029 | Fixture/mock noise | 21 | Same pattern as 028. |

## New ADR files filed

- `core/governance/architecture-decision-records/ADR-006-supabase-memory-layer-architecture-low-confidence.md`
  — status "Reconstructed — low confidence". Real decision (a Supabase-backed
  advisory memory layer, phased Research→Number-One→Mission-Registry
  rollout) confirmed by production code and tests; decision drivers/
  alternatives/consequences not recoverable from the live repo, so left
  honestly unresolved rather than invented.

## Notes for future sweeps

- `data/self-improvement/runs/*/evidence.json` is a previously-unlisted
  noise source: it stores `git status`-style "uncommitted_files" snapshots
  from past self-improvement pipeline runs, several of which reference
  ADR-numbered filenames that existed only in ephemeral agent worktrees
  (`.claude/worktrees/agent-*`, `.claude/worktrees/busy-lamarr-*`) and were
  never committed to the tracked repo. Worth adding to the known-noise list
  alongside `enrichment_poc/` and the stale UI mock for any future ADR
  citation sweep.
- The ghost `temporal_entities_archived_2026` table (in
  `core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`)
  gives ADR-001 through ADR-006 distinct, prose-style titles with status
  `APPROVED`, but ADR-007 through ADR-012 only slug-repeat summaries with
  status `UNKNOWN` — a pattern consistent with the 2026-06-21 backfill
  (documented in `.claude/skills/bot-reviews/fixes-2026-08-09/orphaned-rls-tables-investigation.md`)
  having ingested exactly ADR-001 through ADR-009 from whatever real
  decisions/ADR data existed at the time, then a later, less-careful
  process extending placeholder rows up through ADR-031. This is consistent
  with, but does not independently prove, ADR-001/002/005's titles.
