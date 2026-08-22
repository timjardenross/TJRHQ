-- 0148_capacity_checkins.sql
-- MY CAPACITY TODAY — replaces Recovery Pulse (recovery_pulses).
--
-- "Track what my system needs today, not what diagnosis explains it."
-- Not a diagnostic tool. Tracks capacity, stimulation, pain, overload,
-- masking/compensation, and what actually helps, across quick check-ins,
-- optional deeper reflections, and evening reviews.
--
-- One flat table, `checkin_type` distinguishes a capacity check-in (quick
-- fields required-ish, deep-check fields optional on the same row, filled
-- via a follow-on UPDATE if "Go deeper" is tapped) from an evening
-- reflection (separate row, evening-only columns filled). No unique
-- constraint on log_date — multiple check-ins per day are expected and are
-- never overwritten (spec: "Allow more than one check-in per day. Do not
-- overwrite previous entries.") — this is the core behavioural difference
-- from the retired recovery_pulses model, which upserted on
-- (log_date, pulse_type).
--
-- recovery_pulses itself is untouched by this migration — it stays as
-- historical, read-only data; nothing in the XO bot writes to it after the
-- companion app.py change lands.
--
-- id is a short bigint identity, not a uuid: the bot's multi-select steps
-- (active_loads, identified_needs) address a row by id in Telegram callback
-- data, which has a hard 64-byte limit — a 36-char uuid combined with even
-- a short index list blows that budget (measured: 103 bytes with a uuid PK
-- and every option selected). A short decimal id keeps every callback well
-- under the limit; this is a single-user table, cardinality is trivial.

create table if not exists public.capacity_checkins (
  id bigint generated always as identity primary key,
  log_date date not null default (now() at time zone 'Australia/Brisbane')::date,
  captured_at timestamptz not null default now(),
  time_of_day text,                 -- descriptive only, no business logic reads this
  checkin_type text not null check (checkin_type in ('capacity', 'evening')),
  source text not null default 'telegram',

  -- quick check-in (spec §1) — all nullable, "Done for now" can save a partial row
  capacity_state text check (capacity_state in ('green', 'orange', 'red')),
  stimulation_state text check (stimulation_state in ('low', 'balanced', 'high')),
  pain_state text check (pain_state in ('low', 'baseline', 'elevated', 'high')),
  pain_score smallint check (pain_score between 0 and 10),
  regulation_state text check (regulation_state in ('settled', 'manageable', 'activated', 'overloaded')),
  executive_function text check (executive_function in ('good', 'strained', 'difficult', 'very_difficult')),
  active_loads text[],
  active_loads_other text,
  compensation_load text check (compensation_load in ('low', 'moderate', 'high', 'extreme')),
  identified_needs text[],
  identified_needs_other text,
  selected_action text,

  -- deep check-in (spec §4) — optional follow-on, same row, filled via
  -- UPDATE if "Go deeper" is tapped after the quick check-in completes
  trigger_note text,
  load_category text check (load_category in ('physical', 'cognitive', 'sensory', 'emotional', 'social', 'environmental')),
  unexpected_change boolean,
  masking_present boolean,
  recovery_factors text[],
  helpful_actions text[],
  unhelpful_actions text[],
  recovery_duration text,
  notes text,

  -- evening reflection (spec §5) — checkin_type = 'evening' rows only
  day_trajectory text check (day_trajectory in ('improved', 'same', 'declined')),
  helpful_factor text,
  capacity_debt text check (capacity_debt in ('no', 'maybe', 'yes')),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists capacity_checkins_log_date_idx on public.capacity_checkins (log_date);
create index if not exists capacity_checkins_checkin_type_idx on public.capacity_checkins (checkin_type);

alter table public.capacity_checkins enable row level security;

-- xo_bot scoped role (migration 0135_xo_bot_scoped_role.sql) — SELECT for
-- status/trend reads, INSERT for new check-ins, UPDATE for the deep-check
-- follow-on write and the partial-row -> action-selected write.
grant select, insert, update on public.capacity_checkins to xo_bot;

drop policy if exists xo_bot_select on public.capacity_checkins;
create policy xo_bot_select on public.capacity_checkins for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.capacity_checkins;
create policy xo_bot_insert on public.capacity_checkins for insert to xo_bot with check (true);

drop policy if exists xo_bot_update on public.capacity_checkins;
create policy xo_bot_update on public.capacity_checkins for update to xo_bot using (true) with check (true);

-- authenticated — SELECT only. No web check-in form ships in this pass, but
-- existing/future portal dashboards (Recovery Brief's "Capacity Today"
-- panel, once repointed by the companion SQL migration) need read access.
grant select on public.capacity_checkins to authenticated;

drop policy if exists authenticated_select on public.capacity_checkins;
create policy authenticated_select on public.capacity_checkins for select to authenticated using (true);
