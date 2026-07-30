-- Adds the Human Systems Workbench's live source tables to the
-- supabase_realtime publication so the workbench can subscribe to changes
-- over websockets (see lcars-portal/src/lib/realtime/useRealtimeRefresh.ts and
-- lcars-portal/src/app/human-systems-workbench/page.tsx). Mirrors 0080's
-- treatment of intelligence_events.
--
--   recovery_pulses          — the current live health signal (Telegram-fed,
--                              multiple pulses/day). The Recovery + Medical
--                              tabs re-fetch the moment a new pulse lands.
--   physical_workout_sessions — the Readiness tab's last-session / weekly-count
--                              source; re-fetch when a session is logged.
--
-- Publication membership is a SEPARATE gate from RLS: both tables already have
-- SELECT policies (recovery_pulses via its own policies; physical_workout_sessions
-- via the permissive `true` policy in 0068_physical_readiness.sql), which cover
-- normal reads but do NOT make Realtime fire. This only makes an already-landed
-- row visible to subscribed clients immediately instead of on next page load —
-- it does not change how or how often those rows are written.
--
-- Idempotent: skip a table if it is already a member of the publication.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'recovery_pulses'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.recovery_pulses;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'physical_workout_sessions'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.physical_workout_sessions;
  END IF;
END $$;
