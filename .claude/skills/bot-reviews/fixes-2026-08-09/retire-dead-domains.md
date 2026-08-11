# Retire 6 Dead Domains from Monitoring — Captain-Confirmed

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/slack-bot-heartbeat-investigation.md`,
"Still degraded — genuine gaps, need a Captain decision (7)" section.

## Mission

The heartbeat investigation flagged 7 domains as having no live replacement for their
dead Slack-bot-era jobs. The Captain reviewed and confirmed: retire 6 of them from
monitoring (`human_systems`, `appointment_prep`, `shakedown_digest`, `decision_review`,
`knowledge_freshness`, `lessons_learned`). The 7th, `missions`, was explicitly excluded
— it has 5 real live write paths (LCARS Portal routes), just no single canonical one
yet, and stays monitored pending a consolidation follow-up.

## Independent re-verification (fresh, not trusted-forward)

A few hours had passed since the original investigation and other work landed
concurrently (a TypeScript heartbeat helper was wired to 4 domains that same night), so
each of the 6 was re-checked from scratch before retiring:

- **`human_systems`** — `platform-runtime/human_systems_scheduler.py`'s
  morning/evening/weekly/degradation jobs. Confirmed only two call paths exist anywhere
  in the repo: `platform-runtime/app.py`'s startup (gated behind
  `HUMAN_SYSTEMS_SCHEDULER=on`, inside `starfleet-slack-bot.service` — confirmed
  `disabled`/`inactive` via `systemctl`), and Slack slash-command handlers
  (`commands/human_systems.py`, `commands/comms.py`) that are only ever dispatched by
  that same dead `app.py`. No other dispatcher (XO Telegram, `intelligence/scheduler.py`,
  LCARS Portal) calls into it.
- **`appointment_prep`** — `platform-runtime/commands/health_appointment_prep.py`'s
  `check_upcoming_appointments()` is only invoked by the dead
  `proactive_scheduler.py`'s `_job_appointment_prep`, plus a manual, unscheduled
  Slack-only validation CLI (`tools/validate_briefing_pipeline.py`, confirmed not in
  any systemd unit or crontab). No live trigger anywhere.
- **`shakedown_digest`** — `proactive_scheduler.py`'s `_job_shakedown_digest`, same dead
  scheduler. Only other consumer is the manual, unscheduled
  `tools/generate_shakedown_review.py` CLI.
- **`decision_review`** — `proactive_scheduler.py`'s `_job_decision_review`, same dead
  scheduler. XO Telegram's `/pending` is pull-on-demand, not the scheduled Friday-16:00
  push, and covers a broader attention-queue concept — not a real replacement.
- **`knowledge_freshness`** — `proactive_scheduler.py`'s `_job_knowledge_freshness`, same
  dead scheduler. No equivalent stale-knowledge-file checker exists anywhere else
  (confirmed distinct from `intelligence/scheduler.py`'s `_knowledge_ops_brief_job`,
  which is about the vm-processing document review queue, a different subject).
- **`lessons_learned`** — the table's only direct writer is
  `platform-runtime/commands/lesson_log.py`, dispatched only by the dead Slack app. A
  second candidate was checked and ruled out: `platform-runtime/lib/learning/lessons.py`'s
  `promote_lesson_candidate()` does insert into the real `lessons_learned` table, but a
  repo-wide grep found zero callers anywhere beyond its own module/docstring — it is
  unreachable dead code, not a live path. `core/knowledge/lesson_capture.py` and
  `core/knowledge/outcome_capture.py` are confirmed-distinct modules (Markdown file and
  the separate `outcome_records` table respectively) — neither writes `lessons_learned`.

**Concurrent-work check:** grepped every `recordHeartbeatServerSide()` call site in
`lcars-portal/src` (the new TS heartbeat helper shipped the same night) — only
`advisory_sessions`, `captains_log`, `physical_readiness`, and `health_daily_logs` are
wired. None of the 6 domains below appear there. No other code touching these domains
landed between the original investigation and this retirement.

**Result: all 6 confirmed still genuinely dead.** None was found to have gained a live
path. All 6 retired as planned; `missions` was left untouched throughout.

## Fix

New migration, following the exact soft-delete pattern established by migration `0112`
(`governance_records`) and `0113` (`pain_escalation`, `stale_missions_job`):

`core/infrastructure/supabase/migrations/0114_domain_registry_retire_six_dead_slack_domains.sql`

Sets `active = false` and appends a dated retirement note (documenting the confirmed
dead path and how to re-activate) on the `domain_registry` rows for all 6 domain_keys,
in a single batched migration. No hard delete — history and re-activation path
preserved.

## Verification

Confirmed via Supabase (`domain_registry` query): all 6 rows now `active = false`,
`missions` still `active = true`, untouched.

Ran `run_verification_pass()` fresh (`core/platform/verification_engine.py`, env
sourced from `platform-runtime/.env`):

- **Before:** `degraded_count = 13` (matching the investigation doc's baseline).
- **After:** `degraded_count = 7` — `missions`, `decisions`, `insight_outcomes`,
  `captured_items`, `morning_brief`, `decision_outcome_reminder`, `wellness-coaching`.

All 6 retired domains (`human_systems`, `appointment_prep`, `shakedown_digest`,
`decision_review`, `knowledge_freshness`, `lessons_learned`) are confirmed gone from the
degraded list. `missions` remains correctly listed (untouched, still monitored per
Captain's instruction). The other 6 domains still in the degraded list are pre-existing,
unrelated gaps this mission did not touch.

## Mission Status

Complete. 6 of 6 flagged domains confirmed genuinely dead on fresh re-verification and
retired via Captain-confirmed decision. `missions` correctly excluded and left
monitored. `degraded_count` dropped from 13 to 7.

**Still open (unchanged from the investigation, not in this mission's scope):**
`missions` — 5 real, live, non-shared write sites; needs a follow-up to instrument all
5 or consolidate through one shared helper first.
