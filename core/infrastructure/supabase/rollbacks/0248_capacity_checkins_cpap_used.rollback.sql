-- Rollback for 0248_capacity_checkins_cpap_used.sql (drops the column and its data).
alter table public.capacity_checkins drop column if exists cpap_used;
