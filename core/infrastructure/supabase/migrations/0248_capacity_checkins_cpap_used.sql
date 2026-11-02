-- 0248_capacity_checkins_cpap_used.sql
--
-- The once-a-day sleep question ("How much sleep did you get last night?", five hour buckets) is
-- replaced by one yes/no question: "Did you use your CPAP last night?". Stored here. The Captain
-- asked for exactly this one sleep question; sleep_state is kept for history and is simply no
-- longer written by the bot. Nullable: skipped or unasked is unknown, never "no".
-- Additive only.

alter table public.capacity_checkins
  add column if not exists cpap_used boolean;

comment on column public.capacity_checkins.cpap_used is
  'Did the Captain use their CPAP last night (true/false). Asked once a day on the first quick '
  'check-in; replaces the sleep_state hour-bucket question. Null when skipped or not asked.';
