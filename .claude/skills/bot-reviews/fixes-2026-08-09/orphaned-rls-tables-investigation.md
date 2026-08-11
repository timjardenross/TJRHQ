# Orphaned RLS Tables Investigation (2026-08-10)

**Author:** Chief Engineer (Advisory authority)
**Trigger:** follow-up to `platform-rls-audit.md` (2026-08-09), which flagged 5
tables as "needs manual review" — no discoverable owner anywhere in the
tracked codebase, not even in schema/migration files:
`daily_health_snapshot`, `research_input`, and the temporal-knowledge cluster
`temporal_entities`/`temporal_episodes`/`temporal_facts`.
**Project:** `cjvrpjwewsrumnbdydgg`.

Method: fresh row counts/samples/schema via Supabase MCP for all 5 tables;
an independent, from-scratch repo-wide grep (Python/TS/TSX/SQL/MD, plus
RPC-call search) re-run tonight rather than trusting the prior audit's
"zero hits" claim; `cron.job`/`cron.job_run_details` for pg_cron ownership;
`pg_constraint`/`pg_depend` for FK and view dependents; `list_migrations`
against the live project (not just the repo's tracked `.sql` files) to catch
migrations applied directly to the DB that never landed in git.

---

## Verdict summary

| Table | Verdict | Action taken |
|---|---|---|
| `daily_health_snapshot` | **Owner found — live, not orphaned** | Documented via `COMMENT ON TABLE`. No RLS policy added (correctly not needed). |
| `research_input` | **Confirmed orphaned, 0 rows** | Archived — renamed to `research_input_archived_2026`, documented. |
| `temporal_entities` | **Confirmed orphaned prototype** | Archived — renamed to `temporal_entities_archived_2026`, documented. |
| `temporal_episodes` | **Confirmed orphaned prototype (same cluster)** | Archived — renamed to `temporal_episodes_archived_2026`. |
| `temporal_facts` | **Confirmed orphaned prototype (same cluster)** | Archived — renamed to `temporal_facts_archived_2026`. |

All actions were applied via one migration:
`archive_orphaned_temporal_and_research_input_tables`. Nothing was dropped —
every rename is reversible with a plain `ALTER TABLE/VIEW/FUNCTION ... RENAME`
back to the original name.

---

## 1. `daily_health_snapshot` — live, not orphaned

**Rows:** 61. `snapshot_date` runs 2026-06-10 → 2026-08-09 (yesterday),
one row per day, no gaps. `created_at` is `07:00:00` UTC on every row, to
the second.

That exact daily 07:00 UTC cadence was the tell. Querying `cron.job`
directly (not just grepping the repo) found:

```
jobid=2  jobname=uss_tjr_daily_snapshot  schedule='0 7 * * *'  active=true
  command: insert into public.daily_health_snapshot (missions_count,
  decisions_count, working_memory_count, knowledge_documents_count,
  document_chunks_count) select counts from public.missions/decisions/
  working_memory/knowledge_documents/document_chunks;
```

`cron.job_run_details` confirms it has run successfully every day through
`2026-08-09 07:00:00` (`INSERT 0 1`, `status=succeeded`). This is the exact
same pattern already correctly identified and accepted in the prior audit
for `system_heartbeat` (`jobid=1`, `uss_tjr_daily_heartbeat`, `0 8 * * *`) —
a table written entirely inside Postgres by a `pg_cron` job, never through
an external client/key. `pg_cron` jobs execute as the job owner and bypass
RLS regardless of policy state, so `daily_health_snapshot`'s current
deny-all-except-service-role state is already correct — no client ever
needs to see it, and no policy would change what `pg_cron` can do.

No matching migration exists in the repo's tracked `.sql` files (this cron
job — like `uss_tjr_daily_heartbeat` — appears to have been created by a
direct `cron.schedule()` call rather than a committed migration), but the
live `cron.job` definition is unambiguous ground truth.

**Action:** added a `COMMENT ON TABLE daily_health_snapshot` recording the
owning cron job and explaining why no RLS policy is needed, so this doesn't
get re-flagged as "unexplained" on a future advisor pass. No RLS change, no
application-code change — this table was never actually a bug.

---

## 2. `research_input` — confirmed orphaned, archived

**Rows:** 0. Schema: `id uuid`, `mission_id`, `source`, `source_user`,
`source_url`, `source_channel`, `raw_text`, `extracted_data jsonb`,
`task_type`, `priority`, `repo`, `batch_id`, `status default 'extracted'`,
`created_at`/`updated_at`.

Fresh repo-wide grep (Python/TS/TSX/SQL/MD, case-sensitive and
case-insensitive, word-boundary and substring) found **zero** hits anywhere
in the tracked repo — same result as the prior audit, reconfirmed
independently rather than trusted. No migration named for it exists in
`list_migrations` either; like the temporal cluster below, it was applied
directly to the database outside the tracked migration history.

One real clue: `pg_constraint` shows `research_input_batch_id_fkey`
pointing at `batch_jobs` — a table that **is** live (per tonight's earlier
RLS fix pass, `batch_jobs` backs the Engineering dashboard's "Batch Jobs"
panel). Combined with the column shape (`repo`, `task_type`, `priority`,
`batch_id`, a `status` funnel starting at `'extracted'`), this reads as an
early scaffold for a research-intake-into-batch-build pipeline — capture a
research item, extract structured data from it, queue it into a
`batch_jobs` run. The live equivalent that exists today and is actually
wired up end-to-end is `build_request_inbox`
(`lcars-portal/src/lib/engineering-queue.ts`,
`core/coordination/telegram_build_executor.py`,
`lcars-portal/src/app/api/build-request/[id]/approve-action/route.ts`, and
~15 more call sites) — a more mature design (`title`/`summary`/`rationale`/
`risks`/`suggested_next_step`/`action_type`/`action_payload`) covering the
same conceptual ground. `research_input` most plausibly predates it and was
abandoned in favour of it, or of `research_memory` (migration `0014`,
already a documented live table per prior session memory).

Zero rows means zero data-loss risk either way. No FK points *into*
`research_input` from any other table, so renaming it breaks nothing live.

**Action:** renamed to `research_input_archived_2026`, `COMMENT ON TABLE`
added recording the reasoning above. Reversible via a plain rename back.

---

## 3–5. `temporal_entities` / `temporal_episodes` / `temporal_facts` — resolved, not just re-flagged

This is the cluster prior session memory already knew about
(`ghost-temporal-knowledge-tables.md`: "have data but ZERO owning code;
blocks temporal-knowledge design"). Tonight's brief asked to actually
resolve it, not just repeat the finding — here's what changed.

**Rows:** 88 / 78 / 118. Schema is a clean bitemporal knowledge-graph
design: `temporal_entities` (`entity_id`, `entity_type`, `name`, `summary`,
`first_seen_at`, `last_updated_at`, `metadata jsonb`), `temporal_episodes`
(`episode_id`, `source_type`, `source_id`, `content`, `valid_at`,
`created_at`), `temporal_facts` (`fact_id`, `subject_entity_id`,
`predicate`, `object_entity_id`/`object_value`, `fact_text`,
`valid_start`/`valid_end` for bitemporal validity, `source_episode_id`).
Two supporting views (`temporal_fact_chain`, `temporal_facts_current`) and
two `SECURITY DEFINER` full-text-search RPCs
(`temporal_search_episodes`, `temporal_search_facts`, using
`to_tsvector`/`plainto_tsquery`) sit on top. This is competent, deliberate
schema design — not test junk.

**Timestamps pin down the actual history, independent of any code search:**

- `temporal_entities.first_seen_at`/`last_updated_at` cluster tightly
  around **2026-06-06** and **2026-06-21**.
- `temporal_episodes.created_at` and `temporal_facts.created_at` are all
  inside a single **five-minute window on 2026-06-21, 05:56–06:01 UTC** —
  a one-time bulk backfill, not an ongoing ingestion pipeline. `valid_at`/
  `valid_start` on the rows themselves range back to 2026-06-06, meaning
  the backfill script back-dated the *validity* of facts to when the
  underlying decisions/ADRs/missions actually happened, then wrote them
  all at once on 2026-06-21.
- Content confirms what was ingested: 9 ADRs (`ADR-001`…`ADR-009` +
  `ADR-INDEX`), `decisions` rows (e.g. `DEC-20260606-062950-...`), and a
  handful of `missions`/`capabilities`/`specialists` rows — i.e. someone
  pointed a backfill script at the *existing* `decisions`/`missions`/ADR
  data and loaded it into this new graph schema as a proof of concept.

**`list_migrations` against the live project (not just the repo's tracked
`.sql` files) supplies the rest of the timeline, and explains why grepping
the repo alone comes up empty:**

| When | Migration (live DB history) | What it means |
|---|---|---|
| 2026-06-21 05:33 | `0028_temporal_memory` | Created the 3 tables + supporting objects. **No matching file exists anywhere in the tracked repo** — applied directly to the database, never committed. |
| 2026-06-22 11:36 | `0028_knowledge_hierarchy` | A *second* migration independently numbered `0028` (a mission-ID/migration-numbering collision, consistent with the already-known "Mission ID minting drift" pattern) — this is the ancestor of the Hierarchical Knowledge Navigation Layer that **is** live today (`core/knowledge_navigation/*`, ADR-022). Landed the very next day. |
| 2026-06-23 23:21 | `enable_rls_on_temporal_and_knowledge_tables` | RLS turned on for the temporal tables, but no policies were ever added — this is the exact state tonight's audit flagged. It has been deny-all for **7 weeks**, unrelated to tonight's mission. |
| 2026-07-17 20:12 | `live_ops_audit_20260717_temporal_search_lockdown` | The two `SECURITY DEFINER` search RPCs had their `EXECUTE` grants revoked from `public`/`anon`/`authenticated` — a defensive security pass on functions that, per the search below, nothing was ever calling anyway. |

**Reading:** this was a real, competing prototype for "knowledge as a
strategic capability" (ADR-008), built and seeded the same week the
Hierarchical Knowledge Navigation Layer's own migration landed under the
same accidental "0028" number. The hierarchical approach is the one that
won and is live today; this bitemporal-graph approach appears to have been
abandoned mid-build — schema, backfill, and search API all exist, but the
consuming layer (whatever would have called `temporal_search_episodes`/
`temporal_search_facts`, or read `temporal_fact_chain`/
`temporal_facts_current`) was never built, or was built outside the
tracked repo and lost. It was never run again after the one 2026-06-21
backfill.

**Independent re-verification (not trusting the prior audit's "zero hits"
claim), run fresh tonight:**
- `grep -rn` across every tracked `.py`/`.ts`/`.tsx`/`.sql`/`.md` file for
  `temporal_entities`, `temporal_episodes`, `temporal_facts`,
  `temporal_knowledge`, `entity_id`/`episode_id`/`fact_id` as code
  identifiers, `ent-`/`ep-`/`fact-` ID-prefix generation, `graphiti`
  (case-insensitive) — all zero hits, except a namespace collision:
  `entity_id` is also used, unrelated, by the Hierarchical Knowledge
  Navigation Layer's own node model (`core/knowledge_navigation/models.py`).
- `grep -rln` for `hermes` (case-insensitive) — the only real hits are
  MSN-0210H/0210I, a documented **task-execution-engine** build-vs-borrow
  pilot (`knowledge/SUOC-Platform-Registry.md`), unrelated to a
  temporal-knowledge-graph. That pilot's own registry entry states no
  `execution_engines` table was ever created — ruling Hermes out as the
  origin of these tables.
- `grep` for `.rpc('temporal_search_episodes'`/`'temporal_search_facts'`
  and for `temporal_fact_chain`/`temporal_facts_current` — zero hits
  anywhere.
- `pg_depend` — the only dependents of `temporal_facts`/`temporal_entities`/
  `temporal_episodes` are the two views already accounted for above; no
  other table, function, trigger, or foreign key outside this cluster
  touches it in either direction.
- `git log --all` in the 2026-06-15→06-25 window shows real, heavy commit
  activity (Mistral research-pipeline/orchestrator work, ADR-022
  Hierarchical Knowledge Navigation Layer, mission-ID fixes) but **no**
  commit message anywhere mentions temporal/entities/episodes/facts/
  hermes/graphiti.

No external system, cron job, or edge function was found writing to these
tables either (checked `cron.job` — only the two heartbeat/snapshot jobs
exist platform-wide). This is as close to "confirmed orphaned" as this kind
of investigation can get without being able to interview whoever ran the
2026-06-21 backfill by hand.

**Action:** renamed all 3 tables, both views, and both functions to
`*_archived_2026` (functions were recreated under the new name with bodies
updated to reference the renamed tables, then re-locked to no grants — not
just left to silently break). `COMMENT ON TABLE` added to all 3 tables
recording this investigation. Nothing dropped, no rows lost. RLS was
already deny-all with zero policies since 2026-06-23, so this rename
changes no live behaviour for any consumer, real or hypothetical — if
anything outside the tracked repo were still trying to reach these tables
by name, it has already been broken by that RLS lockdown for 7 weeks with
no reported incident.

Reversal, if the Captain wants these back under their original names:

```sql
alter table temporal_entities_archived_2026 rename to temporal_entities;
alter table temporal_episodes_archived_2026 rename to temporal_episodes;
alter table temporal_facts_archived_2026 rename to temporal_facts;
alter table research_input_archived_2026 rename to research_input;
alter view temporal_fact_chain_archived_2026 rename to temporal_fact_chain;
alter view temporal_facts_current_archived_2026 rename to temporal_facts_current;
-- + recreate temporal_search_episodes/temporal_search_facts from the
--   original definitions quoted in this doc's investigation history.
```

---

## Verification performed

1. Row counts, full column schemas, and sample rows pulled fresh for all 5
   tables via `execute_sql` (not assumed from the prior audit).
2. `pg_class`/`obj_description` checked for pre-existing table comments —
   none existed on any of the 5 before tonight.
3. `cron.job` + `cron.job_run_details` queried directly — found the real
   owner of `daily_health_snapshot`, which no repo grep could have found
   since it's not application code.
4. `list_migrations` against the live project (not the repo's `.sql`
   files) — found `0028_temporal_memory`, `enable_rls_on_temporal_and_
   knowledge_tables`, and `live_ops_audit_20260717_temporal_search_
   lockdown`, none of which have a corresponding file in the tracked repo.
5. `pg_constraint`/`pg_depend` — found the `research_input → batch_jobs`
   FK and the two temporal views, confirmed no other dependents anywhere.
6. Independent, fresh repo-wide grep (not reusing or trusting the prior
   audit's search) across Python/TS/TSX/SQL/MD for all 5 table names, the
   two RPC names, both view names, and thematic terms (`graphiti`,
   `hermes`, `temporal_knowledge`, `entity_id`/`episode_id` as code
   identifiers) — zero real hits for any of the 5 orphaned objects.
7. Migration `archive_orphaned_temporal_and_research_input_tables` applied;
   `information_schema.tables` re-queried post-migration to confirm the
   4 renames landed; `get_advisors(type: "security")` re-run — the
   archived tables still appear under `rls_enabled_no_policy` (expected
   and harmless, since RLS state is unchanged by a rename) and
   `daily_health_snapshot` still appears too (also expected — it's
   correctly left at deny-all, same as `system_heartbeat`). No new,
   unexpected advisory findings appeared.

## Mission status

All 5 tables resolved: 1 genuine live-but-not-application-code owner found
and documented (`daily_health_snapshot`), 4 confirmed orphaned and archived
via reversible rename (`research_input` + the 3-table temporal-knowledge
cluster, plus its 2 views and 2 functions). No guessed RLS policy was added
to any table. Nothing was dropped. Migration:
`archive_orphaned_temporal_and_research_input_tables` on project
`cjvrpjwewsrumnbdydgg`.
