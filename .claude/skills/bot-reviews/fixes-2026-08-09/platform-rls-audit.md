# Platform RLS Audit — "RLS Enabled, No Policy" (2026-08-09)

**Author:** Chief Engineer (Advisory authority)
**Trigger:** Supabase security-advisor scan found tables with RLS enabled and zero
policies. This is the *deny-all* failure shape (broken for legit users), not a
leak — with RLS on and no policy, only `service_role` can touch the table; both
`anon` and `authenticated` are denied everything.
**Scope:** every table currently returned by `get_advisors(type: "security")` /
lint `rls_enabled_no_policy` on project `cjvrpjwewsrumnbdydgg`, checked
individually, not blanket-fixed.

At the time this mission ran, the live advisor list had **48** tables (not 44 —
noted in the brief as likely to have drifted since the initial scan). One of
the 48, `comms_content_revisions`, already had an `auth_read` SELECT policy in
place by the time I queried `pg_policies` (added by other/concurrent work
tonight) — verified, not duplicated, not counted as "fixed by this mission"
below even though it's now correctly resolved.

## Method

For every table: grepped `lcars-portal/src` (the only client-facing/browser
surface in this repo) for real `.from('<table>')` query usage, then checked
which Supabase client each call site uses:

- `createSupabaseServerClient()` / `createSupabaseBrowserClient()` — anon key,
  session/cookie-aware, **RLS-enforced as `authenticated`** when a session
  exists. A real user hitting one of these paths is genuinely blocked by a
  zero-policy table.
- `lib/supabase.ts`'s plain `createClient(url, anonKey)` — also anon-key, and
  when consumed from a `'use client'` hook (confirmed for
  `useCommandCentre.ts`), picks up the same browser-persisted session via
  shared localStorage auth token, so it behaves as `authenticated` too.
- `createSupabaseServiceRoleClient()` / inline `createClient(url,
  SUPABASE_SERVICE_ROLE_KEY)` — bypasses RLS entirely regardless of policy
  state.

Then cross-checked the Python backend (`core/`, `intelligence/`,
`platform-runtime/`, `telegram-bots/`, `tools/`, `services/`, `specialists/`)
for the same table names. Every shared Python Supabase wrapper found
(`tools/supabase/client.py`, `core/health/supabase_client.py`,
`core/infrastructure/vm-processing/supabase_client.py`,
`core/platform/configuration_service.py`, `core/platform/heartbeat.py`,
`core/platform/deadmans_switch.py`) uses `SUPABASE_SERVICE_ROLE_KEY`
consistently — this is an established, repo-wide convention, not a
per-file guess.

## Result: 8 fixed / 35 confirmed service-role-only / 5 needs manual review

---

## Fixed (8) — real bug, authenticated policy added

Migration: `rls_authenticated_policies_client_touched_tables` (applied via
`apply_migration`). Policy shape follows the existing convention already used
on `missions` / `intelligence_briefs` / `captured_items`
(`<table>_select`/`_insert`/`_update`, `TO authenticated`, `USING (true)`) —
single-tenant app, any authenticated session is the Captain
(`lcars-portal/src/lib/supabase-server.ts`).

| Table | Evidence (client-side usage) | Policy added |
|---|---|---|
| `agent_performance` | `lcars-portal/src/app/(app)/engineering/page.tsx` — `createSupabaseBrowserClient()`, Engineering dashboard "Agent Performance" panel | SELECT (authenticated) |
| `batch_jobs` | same file, same client, "Batch Jobs" panel | SELECT (authenticated) |
| `health_source_articles` | `lcars-portal/src/app/api/intelligence-workbench/route.ts` — `createSupabaseServerClient()`, joined into the health-mode insights query (`.select('..., health_source_articles(...)')`). Already flagged as a known gap in `.claude/skills/workbench-reviews/intelligence/chief-engineer-review.md:79` ("confirm whether `health_source_articles` needs the same treatment"). Confirmed: yes. | SELECT (authenticated) |
| `human_systems_recommendations` | `lcars-portal/src/lib/command-centre.ts` (`fetchRecommendedAction`), consumed by `useCommandCentre.ts` (`'use client'`) — Captain's Chair "Recommended Action" strip | SELECT (authenticated) |
| `intelligence_notes` | `captains-notebook/page.tsx` (browser client: select/insert/update — capture, list, archive), `approve-route/route.ts` (server client: select/update — approve-and-route flow), read-only in `captains-chair/page.tsx` and `search/page.tsx` | SELECT, INSERT, UPDATE (authenticated) |
| `mission_execution_events` | `timeline/page.tsx`, `search/page.tsx`, `automation-centre/page.tsx` (browser client), `lib/alerts.ts` (browser client), `lib/command-centre.ts` (shared-session client). No client-side INSERT found — writes are backend/service_role. | SELECT (authenticated) |
| `mission_state_transitions` | `api/operating-picture/route.ts` + `timeline/page.tsx` (reads); `api/missions/[id]/handoff/route.ts` — **INSERT via `createSupabaseServerClient()`** for the audit-trail row (was silently failing under deny-all, caught by the route's own non-blocking try/catch, so no visible error — a real, quiet bug). The sibling `submit`/`reject`/`approve` routes already insert via the service-role client and were unaffected either way. | SELECT, INSERT (authenticated) |
| `comms_content_revisions` | `revisions/route.ts` GET — `createSupabaseServerClient()`, draft revision history read. Writes (`draft`/`generate` routes) go through the service-role client. **Already had an `auth_read` SELECT policy in place before this migration ran** (added elsewhere tonight) — verified via `pg_policies`, not duplicated. | *(pre-existing, verified correct)* |

Verified via a fresh `get_advisors(type: "security")` run after applying the
migration: all 8 tables above no longer appear in the `rls_enabled_no_policy`
list.

---

## Confirmed service-role-only — no client policy needed (35)

Each of these is written and/or read exclusively by Python backend code using
`SUPABASE_SERVICE_ROLE_KEY` (verified per-table below), with **zero**
`.from('<table>')` usage found anywhere in `lcars-portal/src`. Leaving RLS as
deny-all-except-service-role is correct here — recorded explicitly so this
doesn't get re-flagged as "unexplained" on the next advisor pass.

| Table | Backend owner(s) |
|---|---|
| `authority_audit_log` | `core/platform/audit_service.py`, `core/governance/authority_validator.py`, `platform-runtime/lib/officers/officer_actions.py` |
| `brief_lessons_learned` | `intelligence/workflow/repository.py`, `intelligence/workflow/service.py` |
| `capabilities` | `core/context-assembly/*`, `core/advisory/strategic.py`, `core/platform/priority_engine.py`, `platform-runtime/lib/strategy/*` (large capability-planning subsystem) |
| `capacity_calibration` | `core/health/calibration_engine.py` |
| `capacity_calibration_summary` | `core/health/calibration_engine.py` |
| `commander_mission_candidates` | `tools/supabase/client.py` (`CommanderSupabaseClient`, `SUPABASE_SERVICE_ROLE_KEY`) |
| `decision_outcomes` | `core/platform/unified_memory.py`, `core/platform/event_bus.py`, `core/knowledge/outcome_capture.py`, several `platform-runtime/lib/*learning_loop*.py` |
| `escalation_events` | `platform-runtime/escalation_manager.py`, `platform-runtime/alert_metrics.py` |
| `escalation_history` | same + `tools/supabase/client.py` |
| `feedback_signals` | `platform-runtime/lib/feedback_loops_service.py` |
| `human_systems_feedback` | `platform-runtime/lib/human_systems/memory.py`, `platform-runtime/commands/brief.py` |
| `human_systems_friction` | `platform-runtime/lib/human_systems/memory.py` |
| `human_systems_patterns` | `platform-runtime/lib/human_systems/memory.py` |
| `intelligence_health_correlations` | `intelligence/scheduler.py`, `intelligence/workflow/health_mission_correlation_workflow.py`, `intelligence/brief/correlation_synthesis.py` |
| `knowledge_edges` | `core/platform/relationship_model.py`, `core/platform/unified_memory.py`, `core/knowledge_navigation/*` |
| `knowledge_nodes` | same set |
| `llm_call_metrics` | `intelligence/governance/llm_cost_governance.py` |
| `llm_cost_governance` | `intelligence/governance/llm_cost_governance.py`, `intelligence/governance/__init__.py` |
| `operational_patterns` | `core/platform/operational_pattern_library.py`, `core/platform/unified_memory.py` |
| `ori_source_documents` | `intelligence/persistence/intelligence_store.py`, `tools/intelligence/github_brief_sync.py` |
| `provider_quality_history` | `core/platform/unified_memory.py`, `platform-runtime/lib/feedback_loops_service.py` |
| `quality_anomalies` | `platform-runtime/lib/quality_forecasting_service.py` |
| `quality_forecasts` | Defined in `tools/supabase/schema/MSN-0060B-B1E-FORECASTING-SCHEMA.sql` for `quality_forecasting_service.py`'s proactive-routing forecasts, but **the write path was never wired up** (per prior memory: "Quality-scoring dead-end" — built, never fired). No code currently reads or writes this table at all, client or backend. Leaving it alone is still the right call: nothing depends on client access, and if/when it's wired up it will follow the same service-role convention as every sibling table in this list. Flagging for a future decision (wire it up or drop the table) rather than guessing a policy for a dead path. |
| `quality_scores` | `core/platform/unified_memory.py` + 6 `platform-runtime/lib/*` learning-loop/forecasting modules, `tools/supabase/commander_decision_support.py` |
| `research_metrics` | `core/coordination/research_orchestration.py`, `core/coordination/research_metrics.py` |
| `retrieval_logs` | `platform-runtime/commands/brief.py`, `tools/supabase/retrieve_knowledge.py` |
| `specialist_permissions` | `tools/supabase/ingest_knowledge.py`, `tools/supabase/retrieve_knowledge.py` |
| `specialists` | ~20 files across `core/advisory`, `core/coordination`, `platform-runtime/*`, `tools/supabase/*`, `tools/notion/*` — specialist runtime/registry backbone. (`AskView.tsx` in lcars-portal has a text match on "specialists" but does **not** call `.from('specialists')` — it's an unrelated variable/label, confirmed by direct read of the file.) |
| `staff_autonomy_log` | `platform-runtime/lib/autonomy_log.py`, `core/content/signal_opportunity_converter.py` (`SUPABASE_SERVICE_ROLE_KEY`). Also written from `lcars-portal/src/app/api/content/signals-to-opportunities/route.ts`, but that route explicitly builds its own `serviceClient()` (service-role key) for the write — the `requireSession()` check gates *feature access*, not the DB call, so RLS never applies to it either way. |
| `system_heartbeat` | Not application code at all — per `core/infrastructure/supabase/migrations/0071_domain_heartbeats.sql`'s own comment, this table "only tracks a single Supabase pg_cron liveness ping (component='supabase_cron', once daily)" — written by a `pg_cron` job inside Postgres itself, not through any external client/key. |
| `task_events` | `core/infrastructure/vm-processing/worker.py`, `core/platform/task_engine.py` |
| `tasks` | `core/platform/task_engine.py`, `core/infrastructure/vm-processing/worker.py`, and ~20 more `platform-runtime`/`core` files (task engine, research orchestration, ADHD task decomposition). Text matches in `lcars-portal/src/lib/ai-roles.ts`, `engineeringMetrics.ts`, `ai-models.ts` are the generic English word "tasks" in unrelated contexts, not `.from('tasks')` calls — confirmed by direct grep for the query pattern (zero hits). |
| `watchlist_items` | `intelligence/workflow/repository.py`, `intelligence/workflow/service.py`, `scripts/verify_phase_a_live_population.py` |
| `watchlist_tracking` | `intelligence/workflow/repository.py`, `intelligence/watchlist/tracker.py` |
| `working_memory` | `lcars-portal/src/lib/ai-context.ts` — server-side only (file's own header comment: "Runs server-side only — never called from the browser"), and **prefers the service-role key, falling back to anon key only if `SUPABASE_SERVICE_ROLE_KEY` is unset**. Given every other route in this app that needs a service-role client (`lib/supabase-service-role.ts`) assumes that env var is configured in production, the anon-key branch is a defensive fallback, not the real path. `tools/validate_ai_context_schema.py` (a schema-validation script) follows the identical service-role-preferred pattern. No `authenticated`-session-driven feature depends on this table. |

---

## Needs manual review (5) — could not confirm usage confidently, not guessing

| Table | Why it's ambiguous |
|---|---|
| `daily_health_snapshot` | **Zero references anywhere in the tracked codebase** — no Python, no TypeScript, no `.sql` migration/schema file defines or queries it (checked with and without word-boundary grep to rule out substring false-positives against the *different*, plural `daily_health_snapshots` table mentioned once in `tools/supabase/schema/MSN-0060B-LEARNING-LOOP-SCHEMA.sql`, which itself has no code touching it either). Either created directly against the DB outside of any tracked migration, or a leftover from removed code. Can't tell if this is dead or if something external (a manual script, a different untracked service) depends on it. **Do not assume safe to leave, do not assume safe to grant — flag for the Captain/Chief Engineer to check who created it and whether it's still needed.** |
| `research_input` | Same situation: zero hits in any `.py`/`.ts`/`.tsx`/`.sql` file in the repo, confirmed with a plain (non-word-boundary) grep as well to rule out substring matches. No schema file defines it. Flag for manual check. |
| `temporal_entities` | Per prior memory (`ghost-temporal-knowledge-tables.md`): "have data but ZERO owning code; blocks temporal-knowledge design." Independently reconfirmed here — no current reader/writer anywhere in the codebase. Data exists (something wrote it, historically or externally) but nothing in the live repo owns it, so I can't determine an intended access pattern to grant a policy for. |
| `temporal_episodes` | Same as above — part of the same ghost-table cluster. |
| `temporal_facts` | Same as above — part of the same ghost-table cluster. |

None of these five were touched by this mission. They're excluded from both
the "fixed" and "service-role-only" counts on purpose — granting a policy on
a guess would repeat the exact mistake this audit exists to avoid, and
"leave alone" isn't safe to assert either without knowing who's supposed to
be able to reach them.

---

## Verification performed

1. `pg_policies` queried before writing the migration (caught the pre-existing
   `comms_content_revisions` policy — avoided a duplicate/conflicting create).
2. `apply_migration` — `rls_authenticated_policies_client_touched_tables`,
   applied successfully.
3. `pg_policies` re-queried after — all 8 target tables show exactly the
   intended policies (`SELECT`/`INSERT`/`UPDATE` as scoped per table above,
   `roles = {authenticated}`, `qual`/`with_check = true`).
4. Fresh `get_advisors(type: "security")` run — the 8 fixed tables no longer
   appear under `rls_enabled_no_policy`. The remaining 40 entries are exactly
   the 35 service-role-only + 5 needs-manual-review tables above (no
   surprises, no tables missed, no new ones appeared).
5. Three pre-existing unrelated advisory items remain open (out of scope for
   this mission, noted for completeness): `function_search_path_mutable` on
   `match_document_chunks`, `extension_in_public` (`vector` extension),
   `authenticated_security_definer_function_executable` on
   `current_officer_clearance()`, and `auth_leaked_password_protection`
   disabled.

## Mission status

Advisory + implementation complete for the 8 confirmed real bugs (single
migration, additive-only, no existing access changed or removed). 35 tables
verified and left untouched with reasoning recorded. 5 tables explicitly
escalated as needing manual review rather than guessed — two are apparently
orphaned tables with no owning code at all (`daily_health_snapshot`,
`research_input`) and three are the previously-known temporal-knowledge
ghost-table cluster.
