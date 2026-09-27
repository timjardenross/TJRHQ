-- core/platform/heartbeat.py now writes a repeated healthy ('ok'/'skipped')
-- heartbeat at most every 20 min per domain (Supabase usage review
-- 2026-09-27: 5-min jobs reporting "ok" all day were ~2k PostgREST writes a
-- day). Failures and status changes are still written immediately.
--
-- domain_heartbeat_latest.is_stale fires once the last ok is older than
-- expected_cadence_minutes + grace_period_minutes. For a 5-min job the next
-- recorded ok can now be up to 20 + 5 min after the previous one, so every
-- active domain with a window under 40 min is widened to 40 (grace 35).
--
-- verification_engine is deliberately NOT widened: heartbeat.py exempts it
-- from throttling, and core/platform/deadmans_switch.py uses this row's
-- window as its alarm threshold for verification_state.
update domain_registry
   set grace_period_minutes = 40 - expected_cadence_minutes
 where active
   and domain_key <> 'verification_engine'
   and expected_cadence_minutes + grace_period_minutes < 40;
