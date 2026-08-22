-- 0151_capacity_interventions.sql
-- MY CAPACITY TODAY V02 — Regulate. Work Package 02: intervention data
-- model. See MY_CAPACITY_TODAY_V02_Mission_and_Scope.md §23.
--
-- Additive only — capacity_checkins (0148) is untouched, no rename/migrate.
-- Existing Command Centre dashboards reading capacity_checkins directly
-- keep working unmodified.
--
-- Four new tables:
--   capacity_interventions        catalogue (seeded from the existing
--                                  30-code MASTER_ACTIONS table in
--                                  capacity_today.py — same intervention_id
--                                  values, so /capacity Q9's existing
--                                  selected_action text stays meaningful
--                                  once WP06 routes it through this table).
--   capacity_intervention_events  every accept/reassess cycle — the actual
--                                  outcome-learning data (spec §11).
--   capacity_rescue_protocols /
--   capacity_protocol_steps       the 3 default named protocols (§18),
--                                  structured for future custom protocols.
--
-- capacitybot connects via SUPABASE_KEY (service_role, bypasses RLS) —
-- unlike XO's xo_bot scoped role, there is no scoped Postgres role for
-- capacitybot yet, so no role-specific GRANT/POLICY pair is needed for it
-- to function. RLS + an authenticated-select policy are still added on
-- every table for future LCARS Portal dashboard reads, matching 0148's
-- pattern.

-- ── capacity_interventions ───────────────────────────────────────────────────

create table if not exists public.capacity_interventions (
  id bigint generated always as identity primary key,
  intervention_id text unique not null,
  title text not null,
  full_description text,
  button_label text not null,
  management_lever text not null check (management_lever in ('reduce_load', 'regulate', 'recover', 'redesign')),
  target_states text[] not null default '{}',
  capacity_allowed text[] not null default '{green,orange,red}',
  stimulation_effect text check (stimulation_effect in ('increase', 'decrease', 'neutral')),
  pain_compatible boolean not null default true,
  executive_effort text not null default 'low' check (executive_effort in ('low', 'moderate', 'high')),
  estimated_minutes integer,
  environment text[] not null default '{anywhere}',
  requires_followup boolean not null default true,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists capacity_interventions_target_states_idx
  on public.capacity_interventions using gin (target_states);
create index if not exists capacity_interventions_capacity_allowed_idx
  on public.capacity_interventions using gin (capacity_allowed);
create index if not exists capacity_interventions_enabled_idx
  on public.capacity_interventions (enabled) where enabled;

alter table public.capacity_interventions enable row level security;
grant select on public.capacity_interventions to authenticated;
drop policy if exists authenticated_select on public.capacity_interventions;
create policy authenticated_select on public.capacity_interventions for select to authenticated using (true);

-- ── capacity_intervention_events ─────────────────────────────────────────────
-- One row per accepted intervention. checkin_id links back to the
-- originating capacity_checkins row when source='capacity_q9'; null for
-- helpme/guide/manual entries with no quick-check-in parent.

create table if not exists public.capacity_intervention_events (
  id bigint generated always as identity primary key,
  source text not null check (source in ('capacity_q9', 'helpme', 'guide', 'manual')),
  help_state text,
  intervention_id text not null references public.capacity_interventions (intervention_id),
  checkin_id bigint references public.capacity_checkins (id),

  capacity_before text check (capacity_before in ('green', 'orange', 'red')),
  stimulation_before text check (stimulation_before in ('low', 'balanced', 'high')),
  pain_before text check (pain_before in ('low', 'baseline', 'elevated', 'high')),
  pain_score_before smallint check (pain_score_before between 0 and 10),
  regulation_before text check (regulation_before in ('settled', 'manageable', 'activated', 'overloaded')),
  executive_before text check (executive_before in ('good', 'strained', 'difficult', 'very_difficult')),
  compensation_before text check (compensation_before in ('low', 'moderate', 'high', 'extreme')),
  context_loads text[],

  started_at timestamptz not null default now(),
  reassessment_due_at timestamptz,
  reassessment_completed_at timestamptz,

  outcome text check (outcome in ('better', 'same', 'worse', 'not_completed', 'unknown')),
  capacity_after text check (capacity_after in ('green', 'orange', 'red')),
  would_use_again text check (would_use_again in ('yes', 'maybe', 'no')),
  optional_note text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists capacity_intervention_events_intervention_idx
  on public.capacity_intervention_events (intervention_id);
create index if not exists capacity_intervention_events_source_idx
  on public.capacity_intervention_events (source);
create index if not exists capacity_intervention_events_started_at_idx
  on public.capacity_intervention_events (started_at);
-- Pending reassessment lookups (JobQueue reminder fires, or a future
-- reconciliation sweep) — partial index keeps it small since most rows
-- settle to a non-null reassessment_completed_at quickly.
create index if not exists capacity_intervention_events_pending_idx
  on public.capacity_intervention_events (reassessment_due_at)
  where reassessment_completed_at is null and reassessment_due_at is not null;

alter table public.capacity_intervention_events enable row level security;
grant select on public.capacity_intervention_events to authenticated;
drop policy if exists authenticated_select on public.capacity_intervention_events;
create policy authenticated_select on public.capacity_intervention_events for select to authenticated using (true);

-- ── capacity_rescue_protocols / capacity_protocol_steps ─────────────────────

create table if not exists public.capacity_rescue_protocols (
  id bigint generated always as identity primary key,
  protocol_key text unique not null,
  title text not null,
  description text,
  target_states text[] not null default '{}',
  enabled boolean not null default true,
  is_default boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.capacity_protocol_steps (
  id bigint generated always as identity primary key,
  protocol_id bigint not null references public.capacity_rescue_protocols (id) on delete cascade,
  step_order smallint not null,
  instruction text not null,
  unique (protocol_id, step_order)
);

alter table public.capacity_rescue_protocols enable row level security;
alter table public.capacity_protocol_steps enable row level security;
grant select on public.capacity_rescue_protocols, public.capacity_protocol_steps to authenticated;
drop policy if exists authenticated_select on public.capacity_rescue_protocols;
create policy authenticated_select on public.capacity_rescue_protocols for select to authenticated using (true);
drop policy if exists authenticated_select on public.capacity_protocol_steps;
create policy authenticated_select on public.capacity_protocol_steps for select to authenticated using (true);

-- ── capacity_preferences ─────────────────────────────────────────────────────
-- Stub for future personal configuration (spec §23) — unused by V02, no
-- reads/writes yet. Key-value shape so future settings don't need a schema
-- change to add.

create table if not exists public.capacity_preferences (
  id bigint generated always as identity primary key,
  key text unique not null,
  value jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

alter table public.capacity_preferences enable row level security;
grant select on public.capacity_preferences to authenticated;
drop policy if exists authenticated_select on public.capacity_preferences;
create policy authenticated_select on public.capacity_preferences for select to authenticated using (true);

-- ── Seed: existing 30-code MASTER_ACTIONS catalogue ─────────────────────────
-- title/button_label text matches capacity_today.py's MASTER_ACTIONS /
-- MASTER_ACTIONS_SHORT dicts verbatim. target_states map each action onto
-- the /helpme §8 pathways it fits (product judgement, not in the original
-- spec — the 30 codes predate the 9-state helpme model); capacity_allowed
-- follows §10 (no productivity optimisation in red, basic-needs/low-effort
-- actions allowed everywhere).

insert into public.capacity_interventions
  (intervention_id, title, full_description, button_label, management_lever,
   target_states, capacity_allowed, stimulation_effect, pain_compatible,
   executive_effort, estimated_minutes, environment, requires_followup)
values
  ('reduce_input', 'Reduce sensory input', 'Reduce sensory input', 'Reduce input', 'reduce_load',
   '{overwhelmed,sensory_overload}', '{orange,red}', 'decrease', true, 'low', 10, '{anywhere}', true),
  ('postpone', 'Stop or postpone one non-essential demand', 'Stop or postpone one non-essential demand', 'Postpone task', 'reduce_load',
   '{overwhelmed}', '{orange,red}', 'neutral', true, 'low', 5, '{work,anywhere}', true),
  ('quieter_place', 'Move somewhere quieter', 'Move to a quieter environment and reduce unnecessary sensory input for 10 minutes.', 'Quieter space', 'reduce_load',
   '{overwhelmed,sensory_overload}', '{orange,red}', 'decrease', true, 'low', 10, '{anywhere}', true),
  ('rest_20', 'Rest for 20-30 minutes', 'Rest for 20-30 minutes', 'Rest 20 min', 'recover',
   '{overwhelmed,flat}', '{orange,red}', 'decrease', true, 'low', 25, '{home,anywhere}', true),
  ('pain_strategy', 'Use your normal pain/regulation strategy', 'Use your normal pain/regulation strategy', 'Pain strategy', 'recover',
   '{pain_dominant}', '{green,orange,red}', 'neutral', true, 'low', 15, '{anywhere}', true),
  ('move_5', 'Move for 5-10 minutes', 'Move for 5-10 minutes', 'Move 5 min', 'regulate',
   '{flat,understimulated}', '{green,orange}', 'increase', true, 'low', 8, '{anywhere}', true),
  ('music_on', 'Put music on', 'Put music on', 'Music on', 'regulate',
   '{flat,understimulated,anxiety}', '{green,orange,red}', 'increase', true, 'low', 10, '{anywhere}', true),
  ('bounded_task', 'Choose one interesting bounded task', 'Choose one interesting bounded task', 'Bounded task', 'regulate',
   '{flat,understimulated}', '{green,orange}', 'increase', true, 'moderate', 15, '{work,home}', true),
  ('change_env', 'Change environment', 'Change environment', 'Change env.', 'regulate',
   '{flat,overwhelmed,sensory_overload}', '{green,orange,red}', 'neutral', true, 'low', 10, '{anywhere}', true),
  ('talk_briefly', 'Talk to someone briefly', 'Talk to someone briefly', 'Talk briefly', 'regulate',
   '{flat,anxiety,understimulated}', '{green,orange}', 'neutral', true, 'low', 10, '{anywhere}', true),
  ('reduce_physical', 'Reduce physical demand', 'Reduce physical demand', 'Reduce physical', 'reduce_load',
   '{pain_dominant}', '{orange,red}', 'neutral', true, 'low', 15, '{anywhere}', true),
  ('pain_mgmt', 'Use agreed pain-management strategies', 'Use agreed pain-management strategies', 'Pain mgmt', 'recover',
   '{pain_dominant}', '{green,orange,red}', 'neutral', true, 'low', 15, '{anywhere}', true),
  ('change_posture', 'Change posture / position', 'Change posture / position', 'Change posture', 'regulate',
   '{pain_dominant}', '{green,orange,red}', 'neutral', true, 'low', 5, '{anywhere}', true),
  ('pace_not_push', 'Pace rather than push', 'Pace rather than push', 'Pace, don''t push', 'redesign',
   '{pain_dominant,overwhelmed}', '{orange,red}', 'neutral', true, 'low', null, '{anywhere}', false),
  ('protect_recovery', 'Protect recovery time', 'Protect recovery time', 'Protect recovery', 'recover',
   '{pain_dominant,overwhelmed}', '{orange,red}', 'neutral', true, 'low', 30, '{anywhere}', true),
  ('one_task', 'Pick one task only', 'Pick one task only', 'One task only', 'reduce_load',
   '{cannot_start,overwhelmed}', '{orange,red}', 'neutral', true, 'low', 10, '{work,home}', true),
  ('first_action', 'Break it into the first physical action', 'Break it into the first physical action', 'First action', 'reduce_load',
   '{cannot_start}', '{green,orange,red}', 'neutral', true, 'low', 5, '{work,home}', true),
  ('remove_optional', 'Remove optional decisions', 'Remove optional decisions', 'Remove optional', 'reduce_load',
   '{overwhelmed,cannot_start}', '{orange,red}', 'neutral', true, 'low', 5, '{anywhere}', true),
  ('use_timer', 'Use a timer', 'Use a timer', 'Use timer', 'regulate',
   '{cannot_start}', '{green,orange}', 'neutral', true, 'low', 10, '{anywhere}', true),
  ('defer_admin', 'Defer low-value admin', 'Defer low-value admin', 'Defer admin', 'reduce_load',
   '{overwhelmed}', '{orange,red}', 'neutral', true, 'low', null, '{work,home}', false),
  ('stop_performing', 'Where can you stop performing today?', 'Where can you stop performing today?', 'Stop performing?', 'redesign',
   '{overwhelmed,anxiety}', '{orange,red}', 'neutral', true, 'moderate', null, '{anywhere}', false),
  ('cancel_unnecessary', 'Cancel something unnecessary', 'Cancel something unnecessary', 'Cancel task', 'reduce_load',
   '{overwhelmed}', '{orange,red}', 'neutral', true, 'low', null, '{anywhere}', false),
  ('reduce_social', 'Reduce social interaction', 'Reduce social interaction', 'Reduce social', 'reduce_load',
   '{overwhelmed,sensory_overload}', '{orange,red}', 'decrease', true, 'low', null, '{anywhere}', true),
  ('work_directly', 'Work more directly', 'Work more directly', 'Work directly', 'redesign',
   '{anxiety}', '{green,orange}', 'neutral', true, 'moderate', null, '{work}', false),
  ('drop_eye_contact', 'Stop forcing eye contact or conversation where safe', 'Stop forcing eye contact or conversation where safe', 'Drop eye contact', 'reduce_load',
   '{overwhelmed,sensory_overload}', '{orange,red}', 'decrease', true, 'low', null, '{anywhere}', false),
  ('ask_dont_guess', 'Ask for clarity instead of guessing', 'Ask for clarity instead of guessing', 'Ask, don''t guess', 'redesign',
   '{anxiety,cannot_start}', '{green,orange}', 'neutral', true, 'moderate', null, '{work}', false),
  ('simplify_expect', 'Simplify expectations', 'Simplify expectations', 'Simplify expect.', 'redesign',
   '{overwhelmed,anxiety}', '{orange,red}', 'neutral', true, 'low', null, '{anywhere}', false),
  ('take_recovery', 'Take recovery time', 'Take recovery time', 'Take recovery', 'recover',
   '{overwhelmed,flat}', '{orange,red}', 'decrease', true, 'low', 30, '{anywhere}', true),
  ('maintain', 'Maintain', 'Maintain — no need to add load just because capacity is available', 'Maintain', 'redesign',
   '{unknown}', '{green}', 'neutral', true, 'low', null, '{anywhere}', false),
  ('early_reduce', 'Reduce, regulate, or change before this becomes red', 'What can you reduce, regulate, or change before this becomes red?', 'Reduce early?', 'reduce_load',
   '{unknown}', '{orange}', 'neutral', true, 'moderate', null, '{anywhere}', false)
on conflict (intervention_id) do nothing;

-- ── Seed: 3 default rescue protocols (spec §18) ──────────────────────────────

insert into public.capacity_rescue_protocols (protocol_key, title, description, target_states)
values
  ('office_overload', 'OFFICE OVERLOAD', 'Overload while at work/in an office environment.', '{overwhelmed,sensory_overload}'),
  ('flat_cant_start', 'FLAT + CAN''T START', 'Flat/understimulated and struggling to initiate.', '{flat,cannot_start}'),
  ('racing_brain', 'RACING BRAIN', 'Thoughts racing, hard to settle or focus.', '{racing}')
on conflict (protocol_key) do nothing;

insert into public.capacity_protocol_steps (protocol_id, step_order, instruction)
select p.id, s.step_order, s.instruction
from public.capacity_rescue_protocols p
join (values
  ('office_overload', 1, 'Reduce sound/input.'),
  ('office_overload', 2, 'Leave the immediate workspace if possible.'),
  ('office_overload', 3, 'Find a quieter location.'),
  ('office_overload', 4, 'Avoid unnecessary conversation for 10 minutes.'),
  ('office_overload', 5, 'Hydrate.'),
  ('office_overload', 6, 'Reassess capacity.'),
  ('office_overload', 7, 'Decide whether returning to the same load is sustainable.'),
  ('flat_cant_start', 1, 'Stand up.'),
  ('flat_cant_start', 2, 'Add music if appropriate.'),
  ('flat_cant_start', 3, 'Drink water.'),
  ('flat_cant_start', 4, 'Select one bounded task.'),
  ('flat_cant_start', 5, 'Reduce it to the first action.'),
  ('flat_cant_start', 6, 'Ten-minute attempt.'),
  ('flat_cant_start', 7, 'Reassess.'),
  ('racing_brain', 1, 'Brain dump.'),
  ('racing_brain', 2, 'Reduce incoming information.'),
  ('racing_brain', 3, 'Separate tasks/worries/ideas only if useful.'),
  ('racing_brain', 4, 'Pick one bounded activity.'),
  ('racing_brain', 5, 'Park everything else.'),
  ('racing_brain', 6, 'Reassess.')
) as s(protocol_key, step_order, instruction) on s.protocol_key = p.protocol_key
on conflict (protocol_id, step_order) do nothing;
