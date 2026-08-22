-- 0159_capacity_experiments.sql
-- TJR Human Systems Workbench V3, Mission 4 — Personal Experiment Engine.
-- See TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §15
-- "Personal Experiment Engine" and §19 "System Learning Upgrade".
--
-- Upgrades "WORTH TESTING" from narrative copy (RecoveryView.tsx's
-- worthTesting() heuristic, still kept as a fallback when no structured
-- experiment exists) into a real, persisted object. Additive only —
-- nothing else in the schema changes.
--
-- One row per experiment, updated in place as it moves through its
-- lifecycle (propose -> active -> completed/stopped) — unlike
-- burnout_profile (0154), which is append-only because it represents a
-- computation run. An experiment is a single ongoing thing the user is
-- trying, not a series of independent observations, so update-in-place is
-- the right shape here: there is exactly one current status/result per
-- experiment, and the V3 doc's own worked example (§15) shows fields like
-- `result` and `status` evolving on the same experiment over its life
-- rather than accumulating a new row per change.
--
-- status includes 'stopped' as a first-class value distinct from
-- 'completed' because V3 §15's own rules for experiments require every
-- experiment to "be reversible where practical" and "be stoppable if
-- worse" — an experiment abandoned because it made things worse is a
-- different, equally legitimate outcome from one that ran its full trial
-- window, and collapsing the two into one 'completed' bucket would lose
-- that distinction. The same §15 rules ("test one meaningful change where
-- possible", "avoid creating excessive change load", "not masquerade as
-- medical treatment") are behavioural/UX constraints on how the bot and
-- workbench present and offer experiments, not something a check
-- constraint can enforce — they're recorded here only as this comment for
-- future readers.
--
-- Written by capacitybot (SUPABASE_KEY, service_role, bypasses RLS — same
-- as capacity_interventions/capacity_intervention_events, 0151) via its new
-- /experiment command. RLS + an authenticated-select policy are still
-- added for the LCARS Portal's Human Systems Workbench read (this route
-- has no POST/PATCH — see api/human-systems/route.ts's header comment;
-- all writes go through the bot, matching the established convention).

create table if not exists public.capacity_experiments (
  id bigint generated always as identity primary key,

  hypothesis text not null,
  target_condition text,
  proposed_change text not null,
  -- Free text description of the observed baseline this experiment is
  -- testing against (V3 §15 example: "4 of 5 office afternoons reached
  -- Stretched or Depleted") — deliberately not a date range or a foreign
  -- key into capacity_checkins. The V3 doc's schema sketch (§15/§23) gives
  -- this as descriptive prose the user/bot writes down once, not a
  -- queryable window; a future mission could compute it, but nothing
  -- reads it programmatically today.
  baseline_window text,
  -- Free text description of how long the trial runs (e.g. "two weeks"),
  -- not a structured duration. capacitybot's /experiment flow offers a
  -- small set of common presets (1/2/3 weeks, 1 month) when marking an
  -- experiment active, purely so it can schedule a reassessment reminder
  -- via the same job_queue.run_once mechanism /helpme already uses — see
  -- experiments.py's header comment. A custom free-text trial_window is
  -- still accepted; it just means no reminder is scheduled.
  trial_window text,
  outcome_measures text[] not null default '{}',

  status text not null default 'proposed'
    check (status in ('proposed', 'active', 'completed', 'stopped')),
  -- Filled once status moves to 'completed' or 'stopped' — the V3 §19
  -- "WHAT CHANGED" layer's source: "After an experiment has enough
  -- observations, show whether the hypothesis appears supported
  -- personally." Deliberately free text, not a boolean
  -- supported/not-supported flag — §15 forbids presenting this as a
  -- medical/diagnostic conclusion, and a plain personal-language summary
  -- is the honest register for that.
  result text,
  confidence text check (confidence in ('low', 'moderate', 'high')),
  notes text,

  started_at timestamptz,
  completed_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists capacity_experiments_status_idx
  on public.capacity_experiments (status);
create index if not exists capacity_experiments_created_at_idx
  on public.capacity_experiments (created_at desc);

alter table public.capacity_experiments enable row level security;

-- xo_bot scoped role (migration 0135), same as burnout_profile (0154) —
-- capacitybot itself connects via SUPABASE_KEY (service_role, bypasses
-- RLS, see 0151's header comment) so this grant is for any future
-- xo_bot-scoped consumer, not a dependency of the bot's own writes.
-- Unlike burnout_profile's select+insert-only (append-only history), this
-- table needs update too — an experiment's status/result/confidence
-- genuinely change in place as it moves proposed -> active ->
-- completed/stopped.
grant select, insert, update on public.capacity_experiments to xo_bot;

drop policy if exists xo_bot_select on public.capacity_experiments;
create policy xo_bot_select on public.capacity_experiments for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.capacity_experiments;
create policy xo_bot_insert on public.capacity_experiments for insert to xo_bot with check (true);

drop policy if exists xo_bot_update on public.capacity_experiments;
create policy xo_bot_update on public.capacity_experiments for update to xo_bot using (true) with check (true);

-- authenticated — SELECT only, same read-only pattern as every other
-- capacity_* table (0148/0151/0154): the LCARS Portal's Human Systems
-- Workbench reads this table directly, no web write path.
grant select on public.capacity_experiments to authenticated;

drop policy if exists authenticated_select on public.capacity_experiments;
create policy authenticated_select on public.capacity_experiments for select to authenticated using (true);
