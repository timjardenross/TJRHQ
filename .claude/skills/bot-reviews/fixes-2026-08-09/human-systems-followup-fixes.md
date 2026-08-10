# Human Systems Workbench — Follow-up Fixes 2026-08-10

USS TJR · Chief Engineer persona · Registry USS-TJR-003, Engineering Division, Advisory authority
Follow-up to: `.claude/skills/bot-reviews/fixes-2026-08-09/human-systems-fixes.md`
(that mission's Finding 1 explicitly flagged both gaps below and deliberately left them unfixed,
pending a dedicated pass — this is that pass)
Project: `cjvrpjwewsrumnbdydgg` (Supabase, USSTJR)

## Gap 1 — `physical_readiness_profiles` and `weight_logs` RLS drift

**Re-verified live first, rather than trusting the brief's framing.** Queried `pg_policies`,
`pg_class.relrowsecurity`, and `information_schema.role_table_grants` fresh for both tables before
touching anything.

**`physical_readiness_profiles` — confirmed permissive, fixed.** All three live policies
(`_select`/`_insert`/`_update`) were still `{public}`-role with `USING (true)`/`WITH CHECK (true)`,
byte-identical to how `0068_physical_readiness.sql` created them in the original MVP (that file's own
header documents the permissive `true` checks as a deliberate single-user shortcut at the time).
`anon` held table-level SELECT/INSERT/UPDATE grants with no policy restricting it — this table was
genuinely read/write-able by unauthenticated API callers. Its siblings
(`physical_readiness_checkins`, `physical_workout_sessions`, `physical_workout_exercise_logs`) had
already been tightened to `authenticated`-only live on 2026-07-17 and tracked retroactively last
night in `0106_tighten_physical_readiness_workout_rls.sql` — `physical_readiness_profiles` was the
one sibling that never got the same treatment.

Fix applied **live** via `apply_migration` (`tighten_physical_readiness_profiles_rls`, tracked
locally as `core/infrastructure/supabase/migrations/0133_tighten_physical_readiness_profiles_rls.sql`):
same three policy names, same operations (SELECT/INSERT/UPDATE — still no DELETE policy, matching
0068's original, which never had one), same `USING (true)`/`WITH CHECK (true)` semantics, only the
role scope narrows from unrestricted/public to `authenticated` — identical pattern to 0106's sibling
fix. This is a real live state change, confirmed via `pg_policies` after apply and via a direct
role-scoped access test:

```
SET ROLE authenticated; SELECT count(*) FROM physical_readiness_profiles;  -- 1 row (legitimate access preserved)
SET ROLE anon;          SELECT count(*) FROM physical_readiness_profiles;  -- 0 rows (anon now blocked)
```

**`weight_logs` — re-verification found the brief's assumption was wrong; not permissive live.**
`pg_policies` shows exactly one live policy, `"Authenticated users can manage weight_logs"`
(`FOR ALL TO authenticated USING (true) WITH CHECK (true)`) — already correctly locked down, matching
`activity_logs`' pattern exactly. RLS is enabled (`relrowsecurity = true`). No live change was needed
or made. What *was* a real gap: this policy, like the table itself (see Gap 2), was never tracked in
any committed migration — grepped all tracked files, the only mention of `weight_logs` anywhere is a
comment in last night's `0110_tighten_recovery_pulses_and_activity_logs_rls.sql` explicitly noting it
was left out of that fix. Tracked now (no live change) as part of the Gap 2 migration below, since
that's the same migration that first creates the table in tracked history.

## Gap 2 — Four tables with no tracked `CREATE TABLE`

`health_daily_logs`, `activity_logs`, `health_insights`, `weight_logs` exist live but predate this
repo's migrations directory — confirmed via `list_migrations` (live entries `health_data_foundation`,
`create_activity_logs`, `create_weight_logs`, 2026-06-12/19, with no matching committed file) and a
repo-wide grep for `CREATE TABLE` of any of the four names (zero hits across all 132 tracked
migrations; several files reference/alter these tables but none creates them).

**Wrote `core/infrastructure/supabase/migrations/0134_track_health_foundation_tables.sql`** —
`CREATE TABLE IF NOT EXISTS` for all four tables, reproducing every column (name, type, precision/
scale, nullability, default), every named `CHECK`/`PRIMARY KEY`/`UNIQUE` constraint, and every index
(including the partial index `idx_health_insights_reviewed` and the two-index-on-one-column pattern
on `weight_logs.log_date`), plus the two table comments (`health_daily_logs`, `health_insights`) and
RLS + policies for all four tables.

**Verification method:** built the exact same DDL in a throwaway `verify_scratch` schema against the
live database, then ran three separate diff queries — `information_schema.columns`,
`pg_constraint` (via `pg_get_constraintdef`), and `pg_indexes` — comparing `public.*` (live) against
`verify_scratch.*` (freshly created from the drafted DDL) for all four tables. Zero differences other
than the expected schema-qualified sequence name on the two `bigserial` `id` columns
(`activity_logs`, `weight_logs`) — an artifact of the scratch schema not being on the default search
path, not a real discrepancy. Scratch schema dropped after verification (`DROP SCHEMA verify_scratch
CASCADE`); no live table was touched by the check itself.

**Why RLS is included and unconditional (not `to_regclass`-guarded like 0105/0110/0111):** those
three catch-up migrations run *before* 0134 in migration order and guard with
`IF to_regclass(...) IS NOT NULL` so they safely no-op on a from-scratch replay where the table
doesn't exist yet. On a truly fresh clone, 0134 is what first brings these tables into existence — if
its own RLS setup were skipped or guarded the same way, a fresh replay would create the tables with
RLS *disabled*, open to `anon` via the standard Supabase schema grants. 0134 applies
`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and the same policies unconditionally, so the end state is
correct regardless of migration run order.

**Not applied live** — `CREATE TABLE IF NOT EXISTS` is a no-op against production (tables already
exist) and the policy statements reproduce what's already live exactly; running `apply_migration`
would add nothing beyond what the scratch-schema diff already proved, so — matching last night's
precedent for the RLS catch-up migrations — this was verified by structural comparison rather than
executed against production. This does not change live state; it makes the four tables reproducible
from a fresh clone of this repo, closing the second-level "foundation schema untracked" gap flagged
in Finding 1 of last night's mission.

## Numbering / concurrency note

Heavy concurrent migration activity was confirmed throughout this task (per the standing memory note
on this repo). Mid-task, a separate concurrent session landed
`ac2eaffe — Renumber 11 duplicate migration filenames in core/infrastructure/supabase/migrations/`,
claiming `0122`–`0132` for renamed (not new) files, while this task's own `0133`/`0134` were still
being drafted at what was originally going to be `0122`/`0123`. Caught this via a `git status`
re-check before writing files (showed the other session's renames staged-uncommitted in the working
tree), waited for it to land, re-verified the directory max after, and used `0133`/`0134` instead —
no collision. `git status --short` was re-checked immediately before staging to confirm `HEAD` was in
sync with `origin/main` and to identify unrelated in-flight changes from other sessions
(`intelligence/classification/classifier.py` modified, two unrelated `.md` review files untracked) —
none of these were staged or committed by this task; explicit pathspecs were used throughout.

## Commits

- `0133_tighten_physical_readiness_profiles_rls.sql` + `0134_track_health_foundation_tables.sql` +
  this report — committed with explicit pathspecs, no unrelated files swept in.

## Summary

Both tables named in the follow-up brief were investigated fresh rather than trusting the "both
permissive" framing: `physical_readiness_profiles` was genuinely permissive live and is now fixed
(role tightened public→authenticated, live change applied and verified — authenticated access
preserved, anon access now blocked); `weight_logs` turned out to already be correctly locked down
live (the brief's assumption was wrong on this one table), so only its missing tracked-history gap
was closed, with no live change. All four untracked foundation tables
(`health_daily_logs`, `activity_logs`, `health_insights`, `weight_logs`) now have a `CREATE TABLE IF
NOT EXISTS` migration verified column-by-column, constraint-by-constraint, and index-by-index against
live via a scratch-schema diff — a fresh clone of this repo can now reproduce all four tables exactly,
closing the deeper gap Finding 1 flagged but didn't attempt.
