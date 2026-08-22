-- 0152_capacity_checkins_sleep_emotional_social.sql
--
-- Closes 3 of the 5 data gaps found in the Human Systems Workbench's
-- Capacity & Recovery Conditions card (2026-08-22 review): Sleep,
-- Emotional, and Social had no live source — human_systems_daily and
-- analytics_health_daily, their intended sources, are both dead (manual
-- daily check-in form retired weeks ago). Physical was dropped instead
-- (no substitute field justifies keeping it); Cognitive already had a
-- substitute (executive_function) and needed no schema change.
--
-- Sleep: asked once per day only (first /capacity check-in), bucketed —
-- no hours/minutes typing, matches every other quick-check-in field.
-- Emotional / Social: dedicated questions, asked on every quick check-in,
-- Captain's explicit choice over the cheaper active_loads-tag-presence
-- proxy (weaker precision, discussed and declined).

alter table public.capacity_checkins
  add column if not exists sleep_state text
    check (sleep_state in ('under_5', '5_6', '6_7', '7_8', '8_plus')),
  add column if not exists emotional_state text
    check (emotional_state in ('light', 'moderate', 'heavy', 'overwhelming')),
  add column if not exists social_state text
    check (social_state in ('plenty', 'some', 'limited', 'none'));
