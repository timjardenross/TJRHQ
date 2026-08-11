# Human Systems Workbench — Fixes 2026-08-09

USS TJR · Chief Engineer persona · Registry USS-TJR-003, Engineering Division, Advisory authority
Source review: `.claude/skills/workbench-reviews/human-systems/chief-engineer-review.md`
(gate-checked, Approve: `.claude/skills/workbench-reviews/human-systems/xo-gate-review.md`)
Project: `cjvrpjwewsrumnbdydgg` (Supabase, USSTJR)

## Finding 1 — Untracked RLS fix migrations

**Fixed.** Live RLS on the Human Systems Workbench's tables was already correctly
locked down (confirmed independently by both the Chief Engineer review and the XO
gate check), but the migrations responsible for that state were applied directly to
production and never committed — a real disaster-recovery gap, not a live
vulnerability.

Wrote 4 new migration files reproducing current live policy state, catching up the
tracked history without touching live state:

- `core/infrastructure/supabase/migrations/0105_tighten_health_daily_logs_and_captains_log_rls.sql`
  — `health_daily_logs`, `captains_log_entries` (the latter had **no RLS at all** in
  its tracked migration, `0005_captains_log_entries.sql`)
- `core/infrastructure/supabase/migrations/0106_tighten_physical_readiness_workout_rls.sql`
  — `physical_readiness_checkins`, `physical_workout_sessions`,
  `physical_workout_exercise_logs` (tracked `0068` still has role-unrestricted
  `USING (true)` policies)
- `core/infrastructure/supabase/migrations/0110_tighten_recovery_pulses_and_activity_logs_rls.sql`
  — `recovery_pulses` (incl. its `service_role` insert policy), `activity_logs`
- `core/infrastructure/supabase/migrations/0111_reconcile_health_insights_rls.sql`
  — `health_insights` (no committed migration touched this table's RLS at all)

**Numbering note:** originally drafted as 0105/0106/0107/0108. Mid-task, a concurrent
session (multiple other agents are actively working in this same shared repo/working
tree tonight — visible via live `git status` churn and a `.claude/skills/bot-reviews/
fixes-2026-08-09/captains-chair-fixes.md` report from a parallel Captain's Chair fix
task) claimed `0107`/`0109` for an unrelated `comms_content_revisions` RLS fix
(commit `a2e728d`). Renumbered mine to `0105`, `0106`, `0110`, `0111` to avoid
collision, and used pathspec-scoped `git add`/`git commit -- <files>` throughout so
neither commit swept up the other session's in-flight uncommitted changes.

**Verification performed:** queried `pg_policies`, `pg_class.relrowsecurity`, and
`information_schema.role_table_grants` live for all target tables, then did a
column-by-column comparison (table, policy name, command, role, `USING`,
`WITH CHECK`) between the live dump and every `CREATE POLICY` statement in the four
new files. All 20 in-scope policies match exactly. I deliberately did **not**
spin up a paid Supabase branch to test-replay the SQL (branch creation requires
cost confirmation the user hasn't given, and wasn't necessary for deterministic
DDL); manual verification against the live policy dump was the check performed.

**Deliberately out of scope (flagged, not fixed):**
- `physical_readiness_profiles` — still `public`-role with `USING (true)` on all 3
  policies, live. Not one of the 9 tables the review scoped this finding to
  (not read/written by this workbench). Left untouched — a real drift, but a
  different finding than the one assigned.
- `weight_logs` — shares `activity_logs`' exact history (`allow_anon_writes_
  activity_weight_logs` touched both) but isn't part of this workbench either.
- **Deeper pre-existing gap, not created or fixed by this task:** `health_daily_logs`,
  `activity_logs`, `health_insights`, and `weight_logs` don't have their own
  `CREATE TABLE` in any tracked migration at all (predates the migrations directory
  — a "foundation" schema applied before version control started). The new RLS
  migrations guard this with `to_regclass(...) IS NOT NULL` checks so a from-scratch
  replay safely no-ops on those tables rather than erroring, but that doesn't make
  the tables reproducible from tracked history — only the RLS-file gap the review
  asked about is closed. Full table-creation tracking for those four tables is a
  separate, larger piece of work outside this task's scope.

## Finding 2 — Stale step 6 in migration 0091

**Confirmed and fixed.** `list_migrations` shows the applied migration is literally
named `0091_intelligence_workbench_phase_b_steps_1_5` — steps 1–5 only; step 6 was
deliberately skipped on original apply. Confirmed live: `analytics_health_daily` has
35 columns (matching `0082_recovery_pulses_daily_view.sql`'s definition, not the
narrow 5-column redefinition step 6 would have created), including every column the
workbench's `GET /api/human-systems` route depends on (`sleep_quality`,
`cpap_status`, `nervous_system_state`, `energy`, `movement_notes`,
`pleasure_creativity_marker`, `what_happened`, `sitting_tolerance_minutes`,
`workload_constraint`, `captain_capacity_rating`).

No live bug exists today. The risk was purely in the tracked file: if step 6 were
ever replayed (a `supabase db push`, a from-scratch rebuild, or a "let's finish 0091"
cleanup), it would silently regress the view to 5 columns with no error — every
Recovery/Medical tab field for the missing columns would go to "Not recorded",
including the entire Life Participation score.

Fix: commented out step 6 in
`core/infrastructure/supabase/migrations/0091_intelligence_workbench_phase_b.sql`
with an explanatory block citing this finding, the live column-count check, and why
it must not be replayed. Left in place rather than deleted, per the review's own
recommendation — migrations are a historical record. No live schema change.

(Minor correction to the original review's own number: it said the live view has 34
columns; a direct `information_schema.columns` count today shows 35. Immaterial to
the finding — still far more than step 6's 5 — but noted for accuracy since I
verified it myself rather than repeating the review's figure.)

## Commits

- `5fde983` — Track missing RLS migrations for Human Systems tables (catch-up, no live change)
- `0325dfb` — Neutralize dead step 6 in 0091 that would regress the Medical tab if replayed

Both pushed to `main` (fast-forward, no conflicts) despite heavy concurrent commit
activity from other sessions in the same working tree during this task.

## Open questions / not done

- `physical_readiness_profiles` and `weight_logs` RLS drift (still public/permissive
  live) — real, but explicitly out of scope for this task; would need its own
  finding/authorization before touching.
- The deeper "several tables' CREATE TABLE predates the migrations directory
  entirely" gap is bigger than this task and not attempted here.
- Did not test-replay the new migrations against a live-clone Supabase branch
  (would require cost confirmation); relied on manual column-by-column comparison
  against `pg_policies` instead. If a rigorous replay test is wanted later, that's a
  cheap follow-up now that branch creation cost is the only blocker.
