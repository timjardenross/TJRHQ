-- Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
-- final-4-domains.md), same soft-delete pattern as migrations 0112
-- (governance_records), 0113 (pain_escalation, stale_missions_job), and
-- 0114 (human_systems, appointment_prep, shakedown_digest, decision_review,
-- knowledge_freshness, lessons_learned).
--
-- decision_outcome_reminder — platform-runtime/proactive_scheduler.py's
-- _job_decision_outcome_reminder() (Wed 09:15 weekly push). It IS
-- code-complete: monitoring-fixes.md (2026-08-09) added a real
-- _shakedown_log() call on both its success and skip paths. But the job
-- itself is only ever scheduled on the APScheduler instance that
-- proactive_scheduler.start_scheduler() builds, which is started from
-- exactly one place in the whole repo: platform-runtime/app.py (the
-- Starfleet Slack Commander Bot) — confirmed via
-- `systemctl is-active starfleet-slack-bot.service` = inactive, and via
-- `grep -rl start_scheduler` finding no other caller. Same root cause,
-- same dead trigger, as the 6 domains retired in migration 0114 — this one
-- was simply not re-examined in that earlier pass (its heartbeat call had
-- just been added the same night and looked "code-complete, pending next
-- trigger" rather than "dead scheduler").
--
-- _get_decisions_overdue_outcome() (the job's data source) scans
-- knowledge/decisions/*.md for a `captain_outcome_review` marker — a
-- filesystem-based decisions store, confirmed unrelated to both the
-- decision_records/commander_decisions Postgres tables (the `decisions`
-- domain) and the outcome_records table XO Telegram's /pending command
-- reads (core/knowledge/outcome_capture.py). No live equivalent reminder
-- exists anywhere else in the repo — XO's /pending is a different concept
-- (pull-on-demand attention queue over outcome_records + comms +
-- leadership candidates), not a scheduled push over the markdown decision
-- files, same distinction already drawn for decision_review in migration
-- 0114.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-10: no live trigger anywhere in the repo. Its only schedule was platform-runtime/proactive_scheduler.py (Wed 09:15), reachable only via starfleet-slack-bot.service (disabled/inactive since MSN-0337, 2026-07-07) — same root cause as the 6 domains retired in migration 0114, missed in that pass because a heartbeat call had just been added the same night. Data source (knowledge/decisions/*.md captain_outcome_review markers) has no live consumer elsewhere. Removed from monitored/degraded-domain reporting per Chief Engineer review. Re-activate if a real live writer is built.'
where domain_key = 'decision_outcome_reminder';
