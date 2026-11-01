---
status: "Reconstructed — low confidence"
date: 2026-09-12
decision-makers: {unknown}
consulted: {unknown}
informed: {unknown}
---

# ADR-031 — "Agent Orchestration Standardisation" (title only, no real decision content found)

## Context and Problem Statement

ADR-031 is cited in exactly one piece of real, non-fixture, non-ghost-table
content anywhere in the repository:
`docs/runbooks/graphify-query-templates.md`, an example query block under an
"ADR Traceability (once governance indexed)" heading:

```
$GRAPHIFY query "ADR-031 agent orchestration" --graph $GRAPH
```

This is an **aspirational example command** for a knowledge-graph tool
(`graphify`), written as sample usage for *after* governance content has been
indexed — not a citation of an actual, already-made decision. It does confirm
a topic guess ("agent orchestration"), matching the orphaned
`temporal_entities` ghost-table dump's title for ADR-031,
"Agent-Orchestration-Standardisation" (status `UNKNOWN`, zero owning
application code, filename `ADR-031-Agent-Orchestration-Standardisation.md`
that does not exist anywhere in the tracked repo). No production code module
anywhere in the repo actually cites `ADR-031` as governing its own behaviour
— unlike ADR-013/022/024/030, there is no docstring, comment, or test that
says "this module does X because of ADR-031."

## Decision Outcome

**No decision reconstructed.** The evidence is limited to two
non-authoritative sources agreeing on a plausible topic name
("agent orchestration standardisation") with zero substantive content about
what was standardised, why, what alternatives were considered, or what it
explicitly does not cover. Per this mission's instruction, that is too thin
to write a confident MADR body, so this file records the gap honestly instead
of inventing content.

### Confirmation

If a genuine ADR-031 decision surfaces (e.g. in a future mission that
actually designs agent-orchestration standardisation — the multiple parallel
scheduler instances documented in
`knowledge/missions/USS-TJR-MSN-0368-knowledge-record.md` Stream 6
("6 independent scheduler instances... not consolidated") are a plausible
candidate for what such a decision would eventually need to cover), this file
should be replaced with the real content rather than merged with speculation.

## More Information

Full evidence list found by `grep -rn "ADR-031"` repo-wide (2026-09-12,
USS-TJR-MSN-0369 Stream 3): `docs/runbooks/graphify-query-templates.md`,
`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`
(ghost table, title-only), 11 `data/self-improvement/runs/*/evidence.json`
retrieval-fixture path lists (candidate document paths for a retrieval
evaluation, several referencing files that never existed on disk — not
independent evidence, likely all sourced from the same original fixture
data), and `knowledge/missions/USS-TJR-MSN-0368-knowledge-record.md` (lists
ADR-031 among the "genuinely real, code-referenced... still an unverified
list, not confirmed one by one" — the prior mission also did not find
enough to formalize this one).
