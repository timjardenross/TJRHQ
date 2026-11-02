-- Rollback for 0247_capacity_checkins_evening_good_day.sql (drops the two evening columns and their data).
alter table public.capacity_checkins
  drop column if exists day_compensation_load,
  drop column if exists good_day;
