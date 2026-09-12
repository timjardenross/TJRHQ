# Knowledge Record — memory_graph.py's first real caller, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (OSS-Gap-Solutions GAP 3 follow-up) |
| Title | The audit's "unexecuted" item was already executed — the real gap was one caller short |
| Date | 2026-09-12 |
| Lesson | LL-147 |

## Outcome

Tasked with "wiring Graphiti (memory_graph.py), then mem0, per GAP 3
Option B" — the audit doc (2026-08-23) and this task's own framing both
assumed both were unbuilt. Investigation found the opposite: mem0 was
already fully wired into `core/platform/unified_memory.py`'s SEMANTIC/
FACTUAL recall paths (commit `124978d1`) and Graphiti's `memory_graph.py`
already existed as real, working code (commit `895423af`) — both merged to
`main` well before this task started. The audit's stated goal ("give
temporal_entities/facts/episodes a real read/write path") was also
impossible as written: those Supabase tables were dropped outright in
migration `0183_drop_retired_dead_tables.sql` (2026-09-01) — memory_graph.py
never touched them anyway (it's FalkorDB-backed, a separate store).

The one real, narrow gap: `memory_graph.py` had zero callers anywhere in the
repo. Its own docstring names the fix — "a unified_memory.py route... none
of that is built here." Wired exactly that: `unified_memory.recall()`'s
RELATIONSHIPS branch now tries `memory_graph.search()` (Graphiti's temporal
fact graph) when a `query` kwarg is given, falling through to the existing
`knowledge_edges` table on no query or any Graphiti/GEMINI_API_KEY failure —
same non-blocking degrade pattern every other path in that module already
uses. Verified live against the real FalkorDB store (0 results for a query
with no matching backfilled facts — a correct empty result, not an error).

Also fixed `episodic_memory.py`'s docstring, which stated the Option B
deferral as a still-current fact; updated to point at where it's now
resolved. Pinned `mem0ai>=2.0.18` in `platform-runtime/requirements.txt` —
installed and load-bearing since 124978d1, never declared.

## Lesson

A gap-closure audit document is a snapshot, not a live index. Three weeks
is enough time for the two items an audit called "unexecuted" to become
fully executed and merged, while a third fact the same audit relied on
(the temporal tables existing at all) becomes false in the other
direction. Re-deriving a plan from an audit doc without first grepping for
whether its premises still hold risks either redoing already-shipped work
or building toward a target that no longer exists.

## Future Guidance

Before executing any "wire X into Y" instruction sourced from a dated audit
or backlog document, grep for X's actual current caller count and check
recent migration/commit history for whatever Y names as its target — both
took under an hour here and changed the scope of the task from "build two
integrations" to "add one caller and two docstring fixes." The cost of
checking is small relative to the cost of either duplicating merged work or
writing against a schema that's already gone.
