-- Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
-- slack-bot-heartbeat-investigation.md), same pattern as migration 0112
-- (governance_records).
--
-- pain_escalation and stale_missions_job were flagged as part of the
-- 13-domain "never succeeded" cluster whose sole real trigger was
-- starfleet-slack-bot.service (disabled since 2026-07-07, MSN-0337).
-- Unlike the other 11 domains in that cluster, these two are NOT simply
-- waiting on a dead scheduler process to come back — their own
-- domain_registry notes already say "RETIRED D-3C-04 (2026-06-27), not
-- currently scheduled", and platform-runtime/proactive_scheduler.py
-- confirms it: the threading.Thread(...) calls that used to fire
-- _job_stale_missions / _job_pain_escalation after the morning brief are
-- commented out (lines 745-748), with an explicit comment "Stale missions
-- and pain escalation now handled by Command Centre notification engine."
--
-- This investigation verified that claim rather than trusting it: the
-- Command Centre backend (core/command-centre/backend/app.js, running
-- live under pm2 as `command-centre`, 21+ day uptime) wires
-- notification-engine.js's checkStagnantMissions/checkRepeatedEscalations
-- (stale-missions equivalent) and checkHealthDecline/checkRecoveryGap
-- (pain-escalation equivalent) into a real setInterval evaluate() loop
-- (notificationEngine.start(), called from app.js:237) -- confirmed
-- running, not dead code.
--
-- No Python or TypeScript heartbeat.py-equivalent call exists for these
-- two domain_keys anywhere in the repo, and building one for a JS
-- notification-poll loop (a different call shape than every other
-- Python domain, and a genuinely new cross-language capability -- see the
-- open TS-heartbeat-helper gap already flagged for captains_log/
-- physical_readiness/advisory_sessions/missions/health_daily_logs) is
-- disproportionate for two domains that were explicitly retired five
-- weeks before that gap was ever the question. Retiring both from
-- monitored/degraded-domain reporting, same soft-delete mechanism as
-- migration 0112.

update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-10: confirmed superseded by core/command-centre/backend/services/notification-engine.js (checkStagnantMissions/checkRepeatedEscalations), running live under pm2 (command-centre, notificationEngine.start()); job itself commented out in proactive_scheduler.py since D-3C-04. Removed from monitored/degraded-domain reporting per Chief Engineer review. Re-activate if a real stale-missions scheduled job is rebuilt.'
where domain_key = 'stale_missions_job';

update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-10: confirmed superseded by core/command-centre/backend/services/notification-engine.js (checkHealthDecline/checkRecoveryGap), running live under pm2 (command-centre, notificationEngine.start()); job itself commented out in proactive_scheduler.py since D-3C-04. Removed from monitored/degraded-domain reporting per Chief Engineer review. Re-activate if a real pain-escalation scheduled job is rebuilt.'
where domain_key = 'pain_escalation';
