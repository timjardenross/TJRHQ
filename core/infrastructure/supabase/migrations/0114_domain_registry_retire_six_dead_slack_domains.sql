-- Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
-- slack-bot-heartbeat-investigation.md, "Still degraded — genuine gaps" section),
-- same soft-delete pattern as migrations 0112 (governance_records) and 0113
-- (pain_escalation, stale_missions_job).
--
-- Captain-confirmed retirement (2026-08-10) of 6 of the 7 remaining domains
-- from that investigation's "no replacement found anywhere" cluster. The 7th,
-- `missions`, is explicitly NOT included here — it has 5 real, live,
-- non-shared write paths (LCARS Portal PATCH/approve/reject/submit/handoff
-- routes) and stays monitored pending a follow-up to consolidate/instrument
-- them.
--
-- Each of the 6 below was re-verified fresh at retirement time (not just
-- carried forward from the earlier investigation), via a repo-wide grep for
-- both the domain_key string and its underlying job/table, plus a check of
-- every TypeScript `recordHeartbeatServerSide()` call site added by the
-- concurrent session that shipped lcars-portal/src/lib/heartbeat.ts earlier
-- the same night (advisory_sessions, captains_log, physical_readiness,
-- health_daily_logs) — none of the 6 domain_keys below appear there. No
-- other code touching these domains landed between the investigation and
-- this migration.
--
-- human_systems — human_systems_scheduler.py's morning/evening/weekly/
--   degradation jobs. Only two call paths exist for this scheduler anywhere
--   in the repo: (1) platform-runtime/app.py's startup, gated behind
--   HUMAN_SYSTEMS_SCHEDULER=on, inside starfleet-slack-bot.service
--   (disabled/inactive, confirmed via systemctl); (2) Slack slash-command
--   handlers (commands/human_systems.py, commands/comms.py) that are only
--   ever dispatched by the same dead app.py — no other dispatcher (XO
--   Telegram, intelligence/scheduler.py, LCARS Portal) calls into
--   human_systems_scheduler or its command handlers.
--
-- appointment_prep — platform-runtime/commands/health_appointment_prep.py's
--   check_upcoming_appointments() is only invoked by
--   proactive_scheduler.py's _job_appointment_prep (registered on the
--   scheduler that only starts inside the dead Slack app), plus a manual,
--   unscheduled Slack-only validation CLI (tools/validate_briefing_pipeline.py).
--   No live trigger anywhere.
--
-- shakedown_digest — proactive_scheduler.py's _job_shakedown_digest, same
--   dead scheduler. Only other consumer is the manual, unscheduled
--   tools/generate_shakedown_review.py CLI.
--
-- decision_review — proactive_scheduler.py's _job_decision_review (Friday
--   16:00 proactive push), same dead scheduler. XO Telegram's /pending is a
--   different mechanism (pull, not push) covering a broader attention-queue
--   concept, not a replacement.
--
-- knowledge_freshness — proactive_scheduler.py's _job_knowledge_freshness
--   (weekly stale-knowledge-file check), same dead scheduler. No equivalent
--   exists anywhere else in the repo (distinct from
--   intelligence/scheduler.py's _knowledge_ops_brief_job, a different
--   subject — vm-processing document review queue, not stale-file detection).
--
-- lessons_learned — the table's only direct writer is
--   platform-runtime/commands/lesson_log.py, itself only dispatched by the
--   dead Slack app. A second candidate write path was found and checked at
--   retirement time: platform-runtime/lib/learning/lessons.py's
--   promote_lesson_candidate() does insert into the real `lessons_learned`
--   table (migration 0010) — but it has zero callers anywhere in the repo
--   beyond its own module and docstring; it is unreachable dead code, not a
--   live path. core/knowledge/lesson_capture.py and
--   core/knowledge/outcome_capture.py are confirmed-distinct modules (the
--   former writes knowledge/Lessons-Learned.md, the latter writes the
--   separate `outcome_records` table, migration 0030) — neither writes
--   `lessons_learned`.

update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-10: no live write path anywhere in the repo, re-verified fresh at retirement time (repo-wide grep, not just carried forward from the prior investigation). Sole trigger was platform-runtime/proactive_scheduler.py / human_systems_scheduler.py, both only reachable via starfleet-slack-bot.service (disabled/inactive since MSN-0337, 2026-07-07). Removed from monitored/degraded-domain reporting per Chief Engineer review, Captain-confirmed. Re-activate if a real live writer is built.'
where domain_key in (
  'human_systems',
  'appointment_prep',
  'shakedown_digest',
  'decision_review',
  'knowledge_freshness',
  'lessons_learned'
);
