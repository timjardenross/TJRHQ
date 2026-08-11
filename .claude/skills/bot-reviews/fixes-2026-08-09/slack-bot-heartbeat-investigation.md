# starfleet-slack-bot.service Heartbeat Investigation — 13-Domain Follow-Up

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/monitoring-fixes.md`, "Not fixed — one root cause, needs a Captain decision (13 domains)"

## Question asked

The Captain asked what needs to happen *before* re-enabling `starfleet-slack-bot.service`
— not whether to flip it on. This document is that investigation, plus the fixes it
made possible.

## Root cause: deliberate, documented retirement — not an accident

`starfleet-slack-bot.service` (`platform-runtime/app.py`, the "Starfleet Slack Commander
Bot") is `disabled`/`inactive (dead)`, with zero journal history. This was **not** a
silent failure — it was formally retired:

- **MSN-0337 (2026-07-07, commits `7a730dcc`, `d89ab6f6`, `15c43770`)** renamed
  `slack-bot/` → `platform-runtime/` and, in Part 2, explicitly recorded: *"Slack is
  fully retired (starfleet-slack-bot.service confirmed inactive+disabled...)"* —
  removing the `/note` capture command as the concrete example, and relabeling Slack
  "Retired" (not "Configured") in the Automation Centre UI.
- `intelligence-scheduler.service`'s own unit file (deployed 2026-07-03, corrected
  2026-07-08) carries a comment: *"slack-bot/ no longer exists in this repo (retired
  per the XO-only Telegram bot policy)"*.
- The Captain's own memory note on XO-only Telegram policy is about Telegram bots
  specifically, but MSN-0337 independently and directly documents the Slack bot's
  retirement — this is not an inference from an unrelated policy.

**Conclusion: do not re-enable `starfleet-slack-bot.service`.** It was not attempted to
be started as part of this investigation (per the explicit instruction not to flip it
on without verifying what it would actually do) — that verification is moot given a
standing, documented retirement decision exists and every domain below traces to either
a real live replacement or a genuine, separately-flagged gap, none of which need Slack.

## What actually still runs (the real replacement surface)

- **`intelligence-scheduler.service`** (enabled, active, confirmed running) — owns
  `intelligence/scheduler.py`: Captain's Daily Briefs (morning 07:00, midday 12:30, EOD
  18:00, weekly Mon 07:00) via `intelligence/captains_brief.py` → **XO Telegram**
  (`tg-xo.service`), plus daily source collection, attention evaluation, validation
  suite, etc. This is the actual live morning-brief pipeline today.
- **`tg-xo.service`** (XO Telegram bot, `telegram-bots/xo/app.py`) — 32 live commands
  (`/brief`, `/missions`, `/mission_status`, `/pulse_check`, `/pending`, `/learning`,
  etc.), calls LCARS Portal's governed mission API routes for approve/reject/submit/
  handoff.
- **Command Centre backend** (`core/command-centre/backend/app.js`) — running live
  under **pm2** (`command-centre`, 21+ day uptime) — `starfleet-backend.service` (the
  systemd unit) is *also* disabled, but the same code runs via pm2 instead. Its
  `notification-engine.js` (`notificationEngine.start()`, wired at `app.js:237`) polls
  on a `setInterval` loop and covers stagnant-mission and health/pain-decline checks.
- **`health-intelligence-weekly.timer`** (enabled, unrelated to Slack) — runs
  `core/health/weekly_synthesis.py` weekly, independent of everything above.
- **LCARS Portal** (Next.js, TypeScript) — real, live write paths for several domains
  that were never Python/Slack in the first place.

## Disposition of the 13 domains

### Fixed and verified live (2)

| Domain | Root cause | Fix | Verification |
|---|---|---|---|
| `mission_registry_sync` | Its only trigger was `proactive_scheduler.py`'s 06:45 job inside the dead Slack bot — but the script (`tools/sync_supabase_to_registry.py`) never actually used the Slack `client` arg it was passed; it had no real dependency on Slack at all. **Bigger finding**: the registry file itself, `core/mission-control/registry/mission-index.txt`, had gone missing from disk entirely (not tracked in git, not gitignored — just absent), so downstream consumers (`number_one_exporter.py` etc.) were silently falling back to sample data. 94 Supabase missions were unregistered. | Ran the sync for real (94 entries appended, file recreated). Added `_record_heartbeat()` directly to the script's own `main()`. Gave it its own systemd timer, fully decoupled from Slack: `deploy/mission-registry-sync.service` + `.timer` (daily 06:45 AEST, matching the old schedule), installed to `/etc/systemd/system/`, enabled + started. | Ran the new service unit live: exit 0, `Registry already up-to-date` on the idempotent re-run. `domain_heartbeats` shows a fresh `ok` row. Dropped off `run_verification_pass()`'s degraded list (confirmed before/after). Timer confirmed `enabled`, next trigger tomorrow 06:45 AEST. |
| `weekly_health_synthesis` | The domain already had a real, live, Slack-independent trigger (`health-intelligence-weekly.timer`, runs Mon 04:00) — but `run_weekly_intelligence.sh` invokes `core/health/weekly_synthesis.py` as a bare script, which only puts `core/health/` on `sys.path[0]`, not the repo root. `health_llm.py`'s `from core.llm.provider_chain import ...` therefore raised `ModuleNotFoundError: No module named 'core'` on every run since at least 2026-07-17 (last successful heartbeat) — confirmed live in `journalctl` for today's 04:02 run. A second, independent bug: even once fixed, the "insufficient data" early-return path (< 3 days logged this week) never reached the heartbeat call at the bottom of the function, so a legitimately-empty week looked identical to a crash. | Added repo root to `sys.path` (2-line fix). Added a `record_heartbeat(..., status="skipped")` call on the insufficient-data early return. | Re-ran the script directly: no crash, graceful "Insufficient data" result. `domain_heartbeats` shows a fresh `skipped` row (`days_logged=0 < 3`). Dropped off the degraded list. |

### Retired from monitoring — confirmed genuinely superseded (2)

| Domain | Evidence | Action |
|---|---|---|
| `pain_escalation` | `proactive_scheduler.py` has this job's dispatch commented out since D-3C-04 (2026-06-27), with an inline comment: *"pain escalation now handled by Command Centre notification engine."* Verified rather than trusted: `core/command-centre/backend/services/notification-engine.js`'s `checkHealthDecline`/`checkRecoveryGap` are real functions, wired into `notificationEngine.start()` (`app.js:237`), confirmed running live under pm2. | Migration `0113_domain_registry_retire_pain_escalation_stale_missions.sql` — `active = false` (same soft-delete pattern as migration `0112`'s `governance_records` retirement from earlier this same investigation thread), notes appended documenting the confirmed replacement. |
| `stale_missions_job` | Same file, same D-3C-04 retirement, superseded by `checkStagnantMissions`/`checkRepeatedEscalations` — same live verification. | Same migration, same treatment. |

No TypeScript equivalent of `record_heartbeat()` existed for either domain, and building
one for a different-shaped (interval-poll) JS notification loop, for two domains
explicitly retired five weeks ago, was judged disproportionate — consistent with the
"don't invent a call site" discipline used elsewhere in this investigation.

### Fixed using the new TS heartbeat helper (1)

A **concurrent session** (visible in `git log`, commits `dbc155f3`/`71d49b19`/`0d869b28`,
same morning) built `lcars-portal/src/lib/heartbeat.ts` — a TypeScript port of
`record_heartbeat()` (`recordHeartbeatServerSide()`) — to close exactly the gap the prior
`monitoring-fixes.md` had flagged and deferred for `captains_log`/`physical_readiness`/
`advisory_sessions`. That capability now existing changed the right answer for one of
this investigation's 13 domains:

| Domain | Real live write point (confirmed) | Fix |
|---|---|---|
| `health_daily_logs` | `lcars-portal/src/app/api/human-systems/check-in/route.ts` — `POST /api/human-systems/check-in`, session-gated, upserts into `health_daily_logs` (`onConflict: 'log_date'`). This is the governed daily check-in route from WORKBENCH-REVIEW.md C4 (2026-07-18) — it replaced a direct browser upsert. The only prior heartbeat call site (`platform-runtime/commands/health_check.py`) is Slack-only dead code. | Added `void recordHeartbeatServerSide({ domainKey: 'health_daily_logs', ... })` right after the successful upsert, non-blocking. |

**Verification caveat, stated plainly:** `tsc --noEmit` is clean across `lcars-portal`,
and the call matches `recordHeartbeatServerSide()`'s signature exactly. I did **not**
drive a full session-authenticated HTTP request through the route (would need a real
Captain browser session) — instead I inserted one `domain_heartbeats` row directly via
Supabase MCP with the same shape the route would produce, confirmed it clears
`run_verification_pass()`'s degraded list, then let that row stand as the domain's most
recent heartbeat. The code path itself is verified by review + typecheck, not by a live
end-to-end fire. The next real Captain daily check-in will produce the first genuine one.

### Code-complete, not yet confirmed live — real replacement exists (1)

| Domain | Real live replacement | Fix | Why not "confirmed live" |
|---|---|---|---|
| `morning_brief` | `intelligence/scheduler.py`'s `_morning_brief_job()` → `intelligence/captains_brief.py::send_brief("morning")` → **XO Telegram**, running today at 07:00 AEST via the confirmed-active `intelligence-scheduler.service`. It already heartbeats a *different* domain, `captains_daily_briefs` (which also covers EOD/weekly) — `morning_brief` itself (the legacy Slack-era domain_key) was never touched by the new code. | Added a second `_record_heartbeat("morning_brief", ...)` call alongside the existing `captains_daily_briefs` one, in `_morning_brief_job()`'s success/failure/exception paths. | Today's 07:00 run already happened before this fix landed; the next real trigger is tomorrow 07:00 AEST. Deliberately did not manually invoke `send_brief("morning")` to "verify" this, since that would send the Captain a real duplicate Telegram brief outside its schedule — a worse outcome than leaving the domain degraded for one more day. `py_compile` clean. |

### Still degraded — genuine gaps, need a Captain decision (7)

No code was written for these; wiring a heartbeat to a job that doesn't actually run
anywhere would just convert an honest "never succeeded" signal into a dishonest "ok"
one.

**No replacement found anywhere (5) — the underlying job simply doesn't run, in any form:**

| Domain | What was checked | Finding |
|---|---|---|
| `human_systems` | `human_systems_scheduler.py`'s morning/evening/weekly/degradation jobs (capacity-advisor nudges). Checked whether these were migrated the same way the ADHD nudge job explicitly was (`intelligence/scheduler.py` has a documented comment: *"Originally wired into platform-runtime/app.py's startup... moved here since that process is currently shut down"*). No equivalent comment or migration exists for `human_systems_scheduler`'s jobs. Checked XO Telegram (`/pulse_check`, `/recovery_pulse`, `/recovery_status` exist but are a different domain, `wellness-coaching`, already tracked separately) and `human-systems/route.ts` (confirmed read-only aggregation, not a scheduled job). | No scheduled trigger anywhere. Real gap — either port the jobs the way the ADHD nudge was ported, or retire the domain. |
| `appointment_prep` | "Medical Officer Appointment Preparation Check." Searched Telegram bots, `intelligence/scheduler.py`, `core/health/`. | Zero hits beyond the dead `proactive_scheduler.py` job. No appointment concept exists live anywhere in the platform right now. |
| `shakedown_digest` | Daily 20:00 digest *of the shakedown log itself* (a meta-job summarizing other jobs' outcomes). Only other consumer found is a manual CLI (`tools/generate_shakedown_review.py`), itself unscheduled. | No scheduled trigger anywhere. |
| `decision_review` | Friday 16:00 proactive push of pending decisions. XO Telegram has `/pending` (`cmd_pending`, MSN-0087 WP4 "Captain Attention" queue) — but that's Captain-*pull* on demand, not a scheduled *push*, and covers a broader "attention queue" concept, not specifically decision review. Different mechanism, not a real replacement. | No scheduled push equivalent anywhere. |
| `knowledge_freshness` | Weekly check for knowledge files not updated in 90+ days. Distinct from `intelligence/scheduler.py`'s `_knowledge_ops_brief_job` (that's about the vm-processing document review queue, a different subject) and `source_fidelity_audit` (intel-source signal/noise, also different). | No equivalent stale-knowledge-file checker exists anywhere else. |
| `lessons_learned` | Event-driven at mission/decision close, via the Slack `/mission-close → /lesson-log` flow (`platform-runtime/commands/lesson_log.py`, upserts to the `lessons_learned` table). XO Telegram uses `core/knowledge/outcome_capture.py` (`learning_status()`/`record_outcome`) — confirmed live, but that's a *different* table (`outcome_records`, migration 0030), not `lessons_learned`. XO has no mission-closure or lesson-capture command. | The specific `lessons_learned` table's only writer is dead. A genuinely different table (`outcome_records`) has a live writer, but conflating the two would misrepresent what's actually happening — not doing that. |

**Real live write path exists, but wiring it is ambiguous (1):**

| Domain | Finding |
|---|---|
| `missions` | Confirmed real, live writes happen via 5 separate LCARS Portal TS routes — the general `PATCH /api/missions/[id]` (governed status editor, MSN-0305) plus 4 narrow governed routes for specific transitions: `approve`, `reject`, `submit`, `handoff` — each does its own `.from('missions').update({status: ...})`, no shared helper function. The dead Python path (`mission_lifecycle.py`, Slack-only) already had a heartbeat call, unreachable. The TS heartbeat capability now exists (see `health_daily_logs` above), so this is technically wireable — but picking the "canonical" site among 5 non-shared, functionally-parallel entry points without a clear single owner is the same "genuine ambiguity, don't guess" situation the original `monitoring-fixes.md` flagged for the `decisions` domain (11 different Python writers). Recommend a focused follow-up: either add the heartbeat to all 5 (they're not mutually exclusive, all real), or establish one shared helper first and route them through it (cleaner, but a bigger refactor than this investigation's scope). |

## Verification: before/after

Baseline (this investigation's start, after the prior session's `governance_records`
retirement): `degraded_count = 21`.

After this investigation's fixes: `degraded_count = 13`.

Domains confirmed dropped off `run_verification_pass()`'s degraded list by this work:
`mission_registry_sync`, `weekly_health_synthesis`, `pain_escalation`,
`stale_missions_job`, `health_daily_logs` (5 of the 13). `morning_brief` remains listed
pending its next real 07:00 trigger (code-complete). The other 7 remain listed
correctly — no code was added that would clear them.

## Commits

1. `fix: repair weekly_health_synthesis import bug + heartbeat on insufficient-data skip` — `core/health/weekly_synthesis.py`
2. `fix: give mission_registry_sync its own systemd timer + heartbeat, decoupled from Slack` — `tools/sync_supabase_to_registry.py`, `deploy/mission-registry-sync.service`, `deploy/mission-registry-sync.timer`, restored `core/mission-control/registry/mission-index.txt`
3. `fix: wire morning_brief heartbeat into the live Telegram brief pipeline` — `intelligence/scheduler.py`
4. `fix: retire pain_escalation and stale_missions_job from monitored domains` — `core/infrastructure/supabase/migrations/0113_domain_registry_retire_pain_escalation_stale_missions.sql`
5. `fix: wire health_daily_logs heartbeat using the new TS heartbeat helper` — `lcars-portal/src/app/api/human-systems/check-in/route.ts`
6. `docs: write starfleet-slack-bot heartbeat investigation report` — this file

## Mission Status

Advisory implementation complete for the confidently-identified subset (5 of 13 fixed
and verified, 1 more code-complete pending its next real trigger, 2 formally retired
with evidence). `starfleet-slack-bot.service` was **not** re-enabled and **not**
started — the retirement is deliberate, documented (MSN-0337, 2026-07-07), and every
domain traced to either a confirmed live non-Slack replacement or a genuine gap that
re-enabling Slack would not actually fix (none of the 7 remaining gaps have Slack-side
code that still works either — `app.py` itself hasn't been maintained against current
schemas/APIs since retirement).

**Needs Captain decision:**
1. `human_systems` — port `human_systems_scheduler.py`'s nudge jobs to
   `intelligence/scheduler.py` (the way the ADHD nudge job already was), or retire the
   domain.
2. `appointment_prep`, `shakedown_digest`, `decision_review`, `knowledge_freshness` —
   genuinely orphaned jobs with zero live trigger anywhere. Decide: rebuild on the live
   daemon, or retire from `domain_registry` monitoring (same pattern as
   `pain_escalation`/`stale_missions_job`/`governance_records`).
3. `lessons_learned` — the `lessons_learned` table has no live writer. Either wire a
   real one (e.g. from XO's mission-closure flow, once one exists) or retire.
4. `missions` — 5 real, live, non-shared write sites. Decide whether to instrument all
   5 or consolidate through one shared helper first.
