-- 0247_capacity_checkins_evening_good_day.sql
--
-- Evening reflection gains two optional, skippable answers so "a good day" can be defined
-- from the Captain's own words and a whole-day compensation reading, not from a morning snapshot:
--
--   day_compensation_load  How much pushing / masking / compensating the whole day took
--                          (same low / moderate / high / extreme scale as compensation_load).
--                          Kept separate from compensation_load on purpose: that column is the
--                          start-of-day reading on checkin_type='capacity' rows, and several
--                          readers (trends, posture) merge it across all rows for a day.
--   good_day               The Captain's own answer to "Was today a good day?".
--
-- Both nullable: a skipped question stores nothing, and a missing value is "unknown", never "bad".
-- Additive only; existing rows and readers are untouched.

alter table public.capacity_checkins
  add column if not exists day_compensation_load text
    check (day_compensation_load in ('low', 'moderate', 'high', 'extreme')),
  add column if not exists good_day text
    check (good_day in ('yes', 'kind_of', 'no'));

comment on column public.capacity_checkins.day_compensation_load is
  'Whole-day compensation (low|moderate|high|extreme), asked in the evening reflection only. '
  'Distinct from compensation_load, the start-of-day reading on checkin_type=capacity rows.';
comment on column public.capacity_checkins.good_day is
  'Captain''s own answer to "Was today a good day?" (yes|kind_of|no), evening reflection only.';
