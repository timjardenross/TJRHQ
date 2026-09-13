# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0378
- **Priority:** P1 — real deadline: grace period ends 2026-10-01, after which the Fair Use Policy applies and requests can start returning 402
- **Source:** Supabase dashboard, Free Plan, current billing cycle (04 Sep–04 Oct 2026): Database Size 0.394/0.5 GB (79%), Egress 3.922/5 GB (78%), already over quota last cycle ("Egress Exceeded")

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -ril "egress|database size|db size|quota" knowledge/ docs/
   → no prior usage-audit or cost-reduction doc exists for Supabase anywhere in the repo.
     This is a genuinely new investigation, not a re-run of something already done.
   ```

2. **Premise verification / real candidate leads found** (grep-based, not assumed — none of these are confirmed root causes yet, they're the starting leads Stream 0 must validate against real usage data):
   ```
   grep -rn "select('\*')|select(\"\*\")" lcars-portal/src --include="*.ts" --include="*.tsx"
   → 17 occurrences across 14 files. Full-row fetches are a classic egress amplifier —
     pulling every column (including ones the UI doesn't render) on every request.

   grep -rln "supabase.*channel|\.subscribe(|createClient" lcars-portal/src
   → 24 files use Realtime channels/subscriptions. Two dedicated realtime publications
     exist (migrations 0080_intelligence_events_realtime.sql, 0081_human_systems_realtime.sql).
     Realtime payload size and REPLICA IDENTITY setting on published tables directly
     drive egress per change event — not yet checked against real traffic volume.

   grep -rn "setInterval|refetchInterval|pollingInterval" lcars-portal/src
   → 11 occurrences. Worth checking whether any of these poll a table ALSO covered by
     a Realtime subscription — double-fetching the same data two ways.

   grep -rli "vector(|pgvector|embedding" core/infrastructure/supabase/migrations/
   → 9 migrations reference embeddings, from at least 3 different embedding sources
     across the platform's history (0002 generic, 0003 Ollama nomic-embed, 0102 Mistral,
     0162 research-memory). pgvector rows are wide (768-1536+ float dims each) — worth
     checking for genuinely redundant/orphaned embedding tables from superseded
     embedding-source migrations, not just active ones.
   ```

3. **What this mission cannot determine from this sandbox alone** — real usage-breakdown data (which specific tables/queries/API routes are actually driving the 3.922 GB of egress and the 0.394 GB of database size) lives in the Supabase dashboard's own Reports (Database → Table sizes, API → Egress by route) and in `pg_stat_statements`/`pg_total_relation_size()` queries against the live database — none of which this sandbox can reach. **Stream 0 is a VM/dashboard-access handoff**, same shape as MSN-0374's garak handoff — this brief scopes the investigation, it doesn't pre-guess the answer.

## Explicitly Not In Scope

- **Upgrading the Supabase plan.** That's a cost/business decision for the Captain, not an engineering fix — this mission is specifically about reducing usage, so a plan upgrade is the fallback if reduction isn't enough, not this mission's deliverable.
- **Any RLS/security policy changes.** Query/column scoping changes in Stream 2 must not touch access control, only which columns/rows get requested.
- **Re-architecting search/memory** (Meilisearch, mem0/Qdrant, Graphiti). Those are separate, already-decided capability choices; this mission only asks whether Supabase-side storage/egress tied to them can be trimmed, not whether the architecture is right.
- **Deleting any embedding/vector table** without first confirming it has zero real callers — an embedding table that looks orphaned by migration history alone (per the pre-flight note above) needs a real caller-check before anything is dropped, same discipline as any other "looks dead" finding in this codebase.

## Scope / Streams

### Stream 0 — Get real usage-breakdown data (VM/dashboard handoff)
Pull the actual numbers: Supabase dashboard's Database → table-size breakdown, API → Egress-by-route (or top queries by `pg_stat_statements` if dashboard granularity isn't enough), and Realtime → messages/connections. Without this, Streams 1-3 are guessing from code inspection alone.

### Stream 1 — Database size (0.394/0.5 GB, 79%)
Using Stream 0's real table-size data: identify the actual largest tables (embeddings are the leading suspect per pre-flight, but confirm rather than assume). For any genuinely oversized/unbounded table, check real growth rate and whether pruning, archiving to cheaper storage, or fixing an actual bug (e.g., an unbounded log table nobody rotates) is the right response — case by case, not a blanket "delete old rows" pass.

### Stream 2 — Egress (3.922/5 GB, 78%)
Using Stream 0's real per-route egress data: convert the 17 `select('*')` call sites (or whichever ones Stream 0's data actually implicates) to explicit column lists. Check the two Realtime publications' `REPLICA IDENTITY` settings and payload width against real traffic. Check for any polling+Realtime double-fetch pattern found in pre-flight.

### Stream 3 — Verify the reduction is real
Don't just ship changes — get a fresh usage reading (Stream 0's same source) after Streams 1-2 land, and show the actual before/after numbers. This mirrors the evidentiary bar MSN-0375's dedup demo held itself to.

## Acceptance

- Stream 0 produces real numbers, not inference from code alone.
- Every fix in Streams 1-2 traces to a real, Stream-0-confirmed top consumer — not a guess from the pre-flight's grep leads alone (those are starting points, not conclusions).
- Stream 3 shows a real before/after usage delta.
- A clear statement of whether the reduction is enough to stay under quota before 2026-10-01, or whether a plan upgrade is genuinely needed as a fallback — that decision goes to the Captain either way, this mission only supplies the real numbers to decide with.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0378-knowledge-record.md`). Given the real deadline, an interim status note after Stream 0 (even before Streams 1-3 land) is worth posting rather than waiting for the full mission to close.
