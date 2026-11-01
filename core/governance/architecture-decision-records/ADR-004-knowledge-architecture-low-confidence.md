---
status: "Reconstructed — low confidence"
date: 2026-09-12
decision-makers: {unknown}
consulted: {unknown}
informed: {unknown}
---

# ADR-004 — "Knowledge Architecture" (title corroborated, decision content not found)

## Context and Problem Statement

ADR-004 is cited in two real, non-fixture code locations as a "knowledge
architecture" decision, paired with ADR-006's "Supabase memory layer"
pattern, in the context of the Number One advisory-memory adapter's
file-based retrieval fallback:

* `core/coordination/number_one_memory_adapter.py`'s `_retrieve_from_files()`
  maps an `"adr"` query type to two expected file paths:
  `core/governance/architecture-decision-records/ADR-004-Knowledge-Architecture.txt`
  and `.../ADR-006-Supabase-Memory-Layer-Architecture.txt`. **Neither file
  exists anywhere in the tracked repo** — this is a fallback lookup table for
  content that was apparently never actually written as a file, only
  referenced by name.
* `platform-runtime/test_decision.py`'s
  `test_number_one_memory_summary_is_compact` uses `"ADR-004: knowledge
  architecture"` as example/expected input to a summary-formatting function —
  confirming the title but not the substance of what was decided.

This title is independently corroborated (for whatever that is worth) by the
orphaned `temporal_entities` ghost-table dump
(`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`),
which names ADR-004 "USS TJR Knowledge Architecture" — the two sources agree
on the topic, unlike the ADR-003 situation. But agreement on a title is not
the same as evidence of what the decision actually was, what alternatives
were rejected, or what it explicitly excludes — none of that content exists
anywhere in the live repository.

## Decision Outcome

**No confident decision reconstructed.** What can honestly be said: ADR-004
is understood, by convention across at least two independent code paths, to
be the platform's "Knowledge Architecture" decision — likely establishing how
knowledge/documentation is organized such that it can be retrieved as
advisory context (the adapter that cites it exists specifically to surface
ADR/decision/capability content to Number One's advisory memory). It is
explicitly paired with ADR-006 (a Supabase-backed memory pattern this module's
own docstring says it "reuses... without changing governance or assignment
authority"). Beyond that pairing and the bare title, no decision drivers,
considered options, or consequences could be reconstructed from real
evidence — inventing them would misrepresent a past decision, which this
mission's brief explicitly warns against.

### Confirmation

If a real `ADR-004` decision document is ever found (e.g. in an external
knowledge system, a deleted commit, or Notion), it should replace this file's
content rather than being merged with invented material. Until then, this
file should be treated as a placeholder confirming the number is claimed
and roughly what topic it claims, not as an authoritative record of the
decision itself.

## More Information

Evidence: `core/coordination/number_one_memory_adapter.py`,
`platform-runtime/test_decision.py`,
`knowledge/missions/USS-TJR-MSN-0368-knowledge-record.md` (lists ADR-004
among the "genuinely real, code-referenced... still an unverified list, not
confirmed one by one"). Title-only corroboration (non-authoritative, not used
as sourcing beyond confirming the topic name):
`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`
("USS TJR Knowledge Architecture", status `UNKNOWN`, zero owning application
code) and the stale `ArchitectureIndex.tsx`/`captainReview.ts` UI mock, which
disagrees with everything else and names ADR-004 "SQLite for local mission
state (missions.db)" — that specific UI-mock title is treated as unreliable
per its own in-repo disclaimer and MSN-0368's finding that the mock should be
retired.
