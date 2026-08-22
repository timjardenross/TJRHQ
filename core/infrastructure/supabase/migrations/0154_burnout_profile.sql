-- 0154_burnout_profile.sql
--
-- TJR Human Systems Workbench V3, Mission 1 Part A — the longitudinal
-- TRAJECTORY signal itself (V3 doc §2/§5/§6/§23). One row per computation
-- run of core/health/burnout_trajectory.py's compute_burnout_trajectory()
-- (a deterministic rules engine, no ML/LLM — V3 doc §22/§35), not one row
-- per check-in: capacity_checkins (0148, extended 0153) stays the raw
-- per-check-in NOW data; this table is the derived, cautious, longitudinal
-- read of that data over a window. The two must never be collapsed into
-- one row/one score (V3 doc §2: "These must never be collapsed into one
-- score").
--
-- Append-only history, not an upsert-in-place single row: keeping every
-- computation run lets the workbench show how the trajectory read has
-- itself changed over time, and lets a bad/miscalibrated run be
-- superseded by a corrected one without deleting evidence. Consumers
-- (lcars-portal/src/app/api/human-systems/route.ts) read the latest row
-- by computed_at desc.
--
-- system_trajectory / trajectory_confidence / strategic_posture /
-- strategic_posture_message are NOT NULL — compute_burnout_trajectory()
-- always returns a value for these (falling back to 'insufficient_data' /
-- 'low' / a NOW-derived posture per V3 Rule F, never omitting them
-- outright), so a row that exists always has an opinion, even if that
-- opinion is "not enough data". exhaustion_level / tolerance_change /
-- recovery_trajectory / current_recovery_stage are nullable — the V3 doc's
-- Burnout Profile domains (§6) that the deterministic engine may not yet
-- have enough signal to populate independently of the overall trajectory
-- bucket.
--
-- contributing_signals (jsonb) — the raw counts/thresholds that produced
-- this row's classification (e.g. {"orange_red_pct": 0.71,
-- "evening_debt_yes_count": 3, "window_checkin_count": 9}), so the
-- workbench's "Confidence" line (V3 doc §18 example: "Moderate — 12
-- relevant check-ins across 18 days") and any future audit of a
-- classification never has to re-derive them from scratch, and so V3 Rule
-- F ("do not fabricate a trajectory") is checkable after the fact, not
-- just asserted by the code.
--
-- No FK to capacity_checkins — a computation run reads a WINDOW of rows,
-- not one row, and capacity_checkins rows are never deleted, so there is
-- nothing to cascade.

create table if not exists public.burnout_profile (
  id bigint generated always as identity primary key,
  computed_at timestamptz not null default now(),
  window_days integer not null,

  system_trajectory text not null check (system_trajectory in (
    'insufficient_data', 'stable', 'accumulating_strain', 'sustained_high_strain',
    'burnout_like_depletion', 'recovery_signals_emerging', 'rebuilding')),
  trajectory_confidence text not null check (trajectory_confidence in ('low', 'moderate', 'high')),
  relevant_checkin_count integer not null,

  -- V3 doc §6 Burnout Profile domains — populated once the deterministic
  -- engine has enough signal for each independently; free text rather
  -- than a fixed enum for exhaustion_level/tolerance_change since V3 §6.1/
  -- §6.3 deliberately don't prescribe a closed vocabulary for these two
  -- (unlike recovery_trajectory/current_recovery_stage below, which do).
  exhaustion_level text,
  tolerance_change text,
  recovery_trajectory text check (recovery_trajectory in
    ('improving', 'stable', 'volatile', 'deteriorating', 'insufficient_data')),
  current_recovery_stage text check (current_recovery_stage in
    ('protect', 'stabilise', 'recover', 're_engage', 'rebuild', 'redesign')),

  -- Strategic Posture (V3 doc §7) — the TRAJECTORY-aware posture,
  -- deliberately a separate field/table from Today's Posture
  -- (deriveSystemPosture() in api/human-systems/route.ts, which stays
  -- NOW-only and unchanged by this migration). engage/steady/protect/
  -- recover are shared with Today's Posture's vocabulary (lowercased) so
  -- Rule A ("today's capacity improves but sustained strain remains high
  -- -> strategic posture must stay protect/recover, never jump to
  -- engage") is a same-vocabulary comparison, not a translation; stabilise/
  -- re_engage/rebuild/redesign are the additional Burnout Recovery Stage
  -- postures (V3 doc §8) Today's Posture has no equivalent for.
  strategic_posture text not null check (strategic_posture in (
    'engage', 'steady', 'protect', 'recover', 'stabilise', 're_engage', 'rebuild', 'redesign')),
  strategic_posture_message text not null,

  contributing_signals jsonb,

  created_at timestamptz not null default now()
);

create index if not exists burnout_profile_computed_at_idx on public.burnout_profile (computed_at desc);

alter table public.burnout_profile enable row level security;

-- Written by a cron/scheduled computation job (xo_bot scoped role,
-- migration 0135), not by a chat handler reacting to a single user tap —
-- select + insert only, no update/delete: a bad run is superseded by a
-- newer row (see append-only rationale above), never corrected in place.
grant select, insert on public.burnout_profile to xo_bot;

drop policy if exists xo_bot_select on public.burnout_profile;
create policy xo_bot_select on public.burnout_profile for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.burnout_profile;
create policy xo_bot_insert on public.burnout_profile for insert to xo_bot with check (true);

-- authenticated — SELECT only, same pattern as every other capacity_*
-- table (0148/0151): the LCARS Portal's Human Systems Workbench reads
-- this table directly, no web write path.
grant select on public.burnout_profile to authenticated;

drop policy if exists authenticated_select on public.burnout_profile;
create policy authenticated_select on public.burnout_profile for select to authenticated using (true);
