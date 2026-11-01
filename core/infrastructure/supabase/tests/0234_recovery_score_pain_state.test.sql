-- Test for migration 0234 (compute_recovery_score reads pain_state) and its
-- rollback. Run ONLY against a throwaway database whose name contains "test":
--   createdb recovery_test && psql -d recovery_test -v ON_ERROR_STOP=1 \
--     -f core/infrastructure/supabase/tests/0234_recovery_score_pain_state.test.sql
-- It builds minimal fixture tables (it drops/recreates them), applies the
-- ROLLBACK definition (= the live pre-change function), records old scores,
-- applies migration 0234, and asserts the new scores. Any failure raises.
\set ON_ERROR_STOP on

do $$ begin
  if current_database() !~ 'test' then
    raise exception 'refusing to run: database name must contain "test" (got %)', current_database();
  end if;
end $$;

drop function if exists public.compute_recovery_score(date);
drop function if exists public.compute_life_participation(text, text, text, int, text, text);
drop table if exists public.analytics_health_daily cascade;
drop table if exists public.capacity_checkins cascade;

create table public.analytics_health_daily (
  log_date date primary key, sleep_hours numeric, sleep_quality text, cpap_hours numeric, cpap_status text,
  nervous_system_state text, energy text, captain_capacity_rating text, pulse_readiness text,
  movement_notes text, pleasure_creativity_marker text, what_happened text,
  sitting_tolerance_minutes int, workload_constraint text, pulse_day_win text
);
create table public.capacity_checkins (
  id bigserial primary key, log_date date not null, checkin_type text not null default 'capacity',
  captured_at timestamptz not null default now(), capacity_state text, regulation_state text,
  pain_score smallint, pain_state text check (pain_state in ('low','baseline','elevated','high'))
);
-- Constant life-participation stub so the test isolates the pain term.
create function public.compute_life_participation(text, text, text, int, text, text)
returns numeric language sql immutable as $$ select 50::numeric $$;

-- One fixture day per case; identical everywhere except the pain inputs.
-- sleep 7.5h/good, calm, green  => raw = 83.00, ns_modifier 1.00
--   (settled regulation; dysregulated cases use 'overloaded' => 0.85)
create temp table cases (d date primary key, label text, pain_state text, pain_score smallint, reg text);
insert into cases values
  ('2026-01-01','no_checkin_pain',   null,       null, 'settled'),
  ('2026-01-02','low',               'low',      null, 'settled'),
  ('2026-01-03','baseline',          'baseline', null, 'settled'),
  ('2026-01-04','elevated',          'elevated', null, 'settled'),
  ('2026-01-05','high',              'high',     null, 'settled'),
  ('2026-01-06','number_only_9',     null,       9,    'settled'),   -- retired number alone: ignored
  ('2026-01-07','baseline_with_10',  'baseline', 10,   'settled'),   -- number ignored when a state exists
  ('2026-01-08','high_overloaded',   'high',     null, 'overloaded'),-- 0.85 - 0.15 = 0.70 (the floor)
  ('2026-01-09','none_overloaded',   null,       null, 'overloaded'),
  ('2026-01-10','elevated_overloaded','elevated',null, 'overloaded');

insert into public.analytics_health_daily (log_date, sleep_hours, sleep_quality)
  select d, 7.5, 'good' from cases;
insert into public.capacity_checkins (log_date, capacity_state, regulation_state, pain_state, pain_score)
  select d, 'green', reg, pain_state, pain_score from cases;

-- 1) Apply the ROLLBACK definition (= live, pre-change) and record old scores.
\i core/infrastructure/supabase/rollbacks/0234_recovery_score_pain_state.rollback.sql
create temp table old_scores as
  select d, label, public.compute_recovery_score(d) s from cases;

do $$ declare v numeric; begin
  select s into v from old_scores where label='number_only_9';
  -- old rule: pain 9/10 -> 9/40 = 0.225 capped at 0.15 -> 83 * 0.85 = 70.55
  if v <> 70.55 then raise exception 'old/number_only_9 expected 70.55 got %', v; end if;
end $$;

-- 2) Apply migration 0234 and assert the new scores.
\i core/infrastructure/supabase/migrations/0234_recovery_score_pain_state.sql
create temp table new_scores as
  select d, label, public.compute_recovery_score(d) s from cases;

create or replace function pg_temp.expect(p_label text, p_expected numeric) returns void language plpgsql as $$
declare v numeric;
begin
  select s into v from new_scores where label = p_label;
  if v is distinct from p_expected then
    raise exception 'new/% expected % got %', p_label, p_expected, v;
  end if;
end $$;

-- calm/green base: raw 83.00 x modifier
select pg_temp.expect('no_checkin_pain',  83.00);  -- missing state: NO adjustment (unknown, not zero-pain evidence)
select pg_temp.expect('low',              83.00);  -- lower than usual  = 0
select pg_temp.expect('baseline',         83.00);  -- around usual      = 0
select pg_temp.expect('elevated',         76.78);  -- higher than usual = half weight: 83 x 0.925 = 76.775
select pg_temp.expect('high',             70.55);  -- much higher       = full weight: 83 x 0.85
select pg_temp.expect('number_only_9',    83.00);  -- retired number alone no longer penalises
select pg_temp.expect('baseline_with_10', 83.00);  -- number ignored when a state exists

-- dysregulated/overloaded: ns score 20 and modifier 0.85
do $$
declare none_s numeric; high_s numeric; elev_s numeric;
begin
  select s into none_s from new_scores where label='none_overloaded';
  select s into high_s from new_scores where label='high_overloaded';
  select s into elev_s from new_scores where label='elevated_overloaded';
  -- modifier none 0.85, elevated 0.775, high 0.70 (floor) => ratios
  if abs(high_s / none_s - 0.70/0.85) > 0.001 then raise exception 'floor ratio wrong: % / %', high_s, none_s; end if;
  if abs(elev_s / none_s - 0.775/0.85) > 0.001 then raise exception 'elevated ratio wrong: % / %', elev_s, none_s; end if;
end $$;

-- 3) "Much higher than usual" is not loosened vs the old 9/10 worst case.
do $$ declare o numeric; n numeric; begin
  select s into o from old_scores where label='number_only_9';
  select s into n from new_scores where label='high';
  if o <> n then raise exception 'high vs old 9/10 should match (cap = full weight): old % new %', o, n; end if;
end $$;

-- 4) Rollback restores the exact old behaviour.
\i core/infrastructure/supabase/rollbacks/0234_recovery_score_pain_state.rollback.sql
do $$ declare v numeric; begin
  select public.compute_recovery_score(d) into v from cases where label='number_only_9';
  if v <> 70.55 then raise exception 'rollback did not restore old behaviour: %', v; end if;
end $$;

select 'OK: 0234 recovery score tests passed' as result;
