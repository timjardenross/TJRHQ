# USS-TJR-MSN-0375 — Postgres-Native Durable-Execution Pilot (pgqueuer) — Knowledge Record

**Priority:** P2 pilot | **Source:** `knowledge/OSS-Capability-Search-2026-09-12.md` §5/§8 | **Status:** PILOT DELIVERED; ROLLOUT IN PROGRESS (2026-09-13) — see Rollout Update below

## Rollout Update (2026-09-13)

Completed the Go/No-Go's three prerequisites, in order, verifying each
rather than assuming success:

1. **`SUPABASE_DB_URL` provisioned.** User reset the Postgres password and
   provided it directly; DSN built and stored in Infisical `prod`. Verified
   with a real `asyncpg.connect()` — `PostgreSQL 17.6` confirmed, not just
   "secret exists." `pgqueuer`/`asyncpg` were in `requirements.txt` from the
   pilot but had never actually been `pip install`ed on this VM's
   `platform-runtime/.venv` — installed now. `pgq --pg-dsn ... install` run
   for real; `pgq ... verify --expect present` confirms all PgQueuer schema
   objects exist in the live database (not a local Docker Postgres this
   time — the real Supabase instance).
2. **`deploy/human-systems-scheduler.service` installed and enabled.**
   `systemctl status` confirms `active (running)`, the real daemon log line
   `pgqueuer daemon started (jobs=morning, midday, eod, evening, weekly,
   degradation, comms_weekly)` — all 7, matching the pilot's `JOBS`.
3. **Live-day verification: IN PROGRESS, not yet complete.** Queried
   `pgqueuer_schedules` directly: all 7 jobs are registered with the exact
   cron expressions `_CRON_DEFAULTS` specifies, and `next_run` for each
   matches what those expressions predict. **Zero dispatches so far** —
   correctly, since nothing is due yet (checked at 2026-09-13 13:20 AEST /
   03:20 UTC; nearest due job is `morning` at 07:00 UTC, ~3h40m out).
   Today is a Sunday, so `eod` (weekdays only) and `weekly`/`comms_weekly`
   (Mondays only) cannot fire until 2026-09-14 regardless — genuine
   coverage of all 7 needs checking back through Monday, not just today.
   **Do not treat this as "verified live" yet** — that requires observing
   real rows land in `pgqueuer_log`/`pgqueuer_schedules.last_run`, per this
   same mission's own bar (Stream 3 refused to assert dedup without a
   queryable ledger; this update holds itself to the same standard). Next
   check: after `morning`'s 07:00 UTC run, then progressively through
   `midday`/`evening`/`degradation` today and `eod`/`weekly`/`comms_weekly`
   Monday.

## Summary

Piloted `pgqueuer` as a Postgres-native, SKIP-LOCKED-deduplicated replacement for `platform-runtime/human_systems_scheduler.py`'s `BlockingScheduler`/`CronTrigger` daemon mode, against the Scheduling capability's disclosed double-fire risk. The pilot's premise held on inspection but needed one material correction (instance count) and surfaced one genuinely new finding (this daemon has never been supervised in production). The double-fire scenario was demonstrated end to end, not asserted.

## Stream 0 — Ground truth

No reference to `human_systems_scheduler.py` or a daemon supervising it exists anywhere in the repo: no `deploy/*.service`, no `deploy/*.timer`, no `/etc/crontab` entry (the only cron entry found, `*/30 * * * * ... core.content.draft_worker`, is unrelated), no `USS-TJR-Control/tmux` reference. `git log` on the file shows only feature/refactor commits, none adding supervision (contrast with `intelligence-scheduler.service`, which documents its own MSN-0207C provenance in its header comments). One relevant historical commit, `2d2ac609a` (2026-08-23, "document local-scheduler boundaries"), had marked this file as coupled to the Slack bot's `WebClient` and therefore unmigratable — but Slack was retired platform-wide on 2026-09-08 (see the file's own header comment) and that coupling comment has since been removed from the file. The premise that blocked migration seven weeks ago no longer applies.

**Finding:** Stream 1 is "stand up a durable-queue-backed daemon where none currently runs reliably," not "migrate a live daemon." A new `deploy/human-systems-scheduler.service` was added as part of this pilot (see Stream 1) but has **not** been installed/enabled on the production VM — this mission could only reach the repo, not the real host.

## Stream 1 — Wiring

`platform-runtime/human_systems_scheduler.py`'s `_start_daemon()` now delegates to a new `_start_daemon_async()` (see the file). It:
- Reads a direct Postgres DSN from `SUPABASE_DB_URL` (or `HS_SCHEDULER_DB_URL`) — **new**: this repo's Supabase usage has, until now, gone exclusively through the `supabase-py` REST client (`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`); nothing in the codebase previously held a raw `postgresql://` connection string. pgqueuer's `SKIP LOCKED` dequeue needs a real SQL connection (`asyncpg`), so this is a new — but not new-infrastructure — credential: same Postgres instance, different connection surface. Must be added to wherever `run-with-infisical.sh` sources secrets before the new systemd unit is enabled.
- Registers all 7 jobs (`JOBS` unchanged) via `pgqueuer.PgQueuer.schedule(entrypoint, cron_expression)`, one per job, with `_cron_expression()` reading the exact same `_CRON_DEFAULTS` env-var-overridable strings as before (`HS_MORNING_CRON` etc. — unchanged names, unchanged defaults).
- Runs each job's existing synchronous `run_job()` via `asyncio.to_thread()` (pgqueuer is asyncio-native; `run_job()` itself — Supabase/Telegram calls — stays synchronous and untouched).
- `_JOB_DOMAIN`, `_build_message()`, `_publish_core_event()`, heartbeat recording — all untouched.

Added `deploy/human-systems-scheduler.service`, modeled on `deploy/intelligence-scheduler.service` (`Type=simple`, `Restart=always`, same `run-with-infisical.sh` wrapper pattern), documenting in its header that this is the first supervision this daemon has ever had.

Added `pgqueuer>=1.3.2` and `asyncpg>=0.29.0` to `platform-runtime/requirements.txt` (apscheduler left in place — still used by `intelligence/scheduler.py` and `revs/scheduler.py`, both out of scope).

**Live smoke test** (this sandbox, local Postgres via Docker, not the production VM): imported the real `human_systems_scheduler` module (not a copy), monkeypatched only `run_job` (no Supabase/Telegram credentials available here), set `HS_MORNING_CRON="* * * * *"`, and called the real `_start_daemon_async()`. Result: `morning` fired within one cron tick; `pgqueuer_schedules` showed all 7 real jobs registered with their correct env-var-driven cron expressions, and `human_systems_morning`'s row showed `last_run` populated after exactly one dispatch — confirming the wiring is correct end to end, short of the parts (Supabase/Telegram) this sandbox cannot reach.

## Stream 2 — Bake-off: pgqueuer vs. procrastinate

Both installed cleanly from PyPI into a scratch venv (`pgqueuer==1.3.2`, `procrastinate==3.9.0`) — no installability blocker either way.

| | pgqueuer | procrastinate |
|---|---|---|
| Schema footprint | 4 tables (`pgqueuer`, `pgqueuer_log`, `pgqueuer_schedules`, `pgqueuer_statistics`) | 4 tables (`procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`, `procrastinate_workers`) plus triggers/functions for its LISTEN/NOTIFY wakeup |
| Cron API fit | `app.schedule(entrypoint, cron_expression)` — cron string is a plain 5-field crontab string, drops in directly where `_CRON_DEFAULTS` values already are | `@app.periodic(cron=...)` decorator, same idea, but periodic tasks are deferred through the general task-queue machinery (designed primarily for a high-throughput job queue, cron is a secondary feature layered on top) |
| Dedup mechanism | `FOR UPDATE SKIP LOCKED` on both the main queue (`pgqueuer`) and the schedules table (`pgqueuer_schedules`) — confirmed by reading `pgqueuer/adapters/persistence/qb.py` lines 524/546/1054 | Also SKIP-LOCKED-based (documented), not independently verified in this pilot since pgqueuer was selected first |
| CLI/ops surface | `pgq install/upgrade/verify/uninstall`, `pgq run`, a live dashboard (`pgq dashboard`/`pgq web`) — schema migrations are a first-class CLI concern | `procrastinate schema --apply`, `procrastinate worker`, `procrastinate healthchecks` |
| Fit for this target | 7 low-frequency cron jobs, no queue depth to speak of — pgqueuer's schedule-table-native cron support is a closer match; the main job queue isn't even needed here (jobs run directly from the schedule dispatch, not routed through `pgqueuer`'s queue table) | Built for task-queue-first workloads; cron is supported but is architecturally a defer-loop on top of the queue, more machinery than 7 daily/weekly jobs need |

**Chosen: pgqueuer.** Its cron scheduling is a first-class, standalone concept (`SchedulerManager`) with its own SKIP-LOCKED-protected table, not a thin layer over a general task queue — a closer structural match to "7 cron jobs, no queue depth" than procrastinate's queue-first design. Equal on installability, licensing (MIT both), and schema footprint (4 tables each).

## Stream 3 — Dedup proof (the actual bar)

Ran locally against a real Postgres 16 instance (`docker run postgres:16-alpine`, reachable — no Supabase credentials needed for this isolated proof). Script: `msn0375_dedup_demo.py` (kept in this session's scratchpad, not committed — reproducible from the commands in this record).

**Part A — naive claim (the APScheduler-shaped failure mode):** two concurrent workers each run `SELECT ... WHERE due = true` then, after a simulated 50ms of job-body work, `UPDATE ... run_count = run_count + 1` — the same check-then-act race two co-running `BlockingScheduler` processes would hit during a delayed restart. Result: **`run_count = 2`. Double-fire confirmed, reproduced on demand.**

**Part B — pgqueuer's real dequeue path:** one job enqueued; two concurrent `PgQueuer` workers (real library code, not a mock) both attempt `pq.run()` against the same row. `dequeue()`'s `FOR UPDATE SKIP LOCKED` means only one worker acquires the row; the other finds nothing to claim. Result: worker 1 executed (`{'1': 1, '2': 0}`); **`pgqueuer_log` shows exactly one `successful` row** (`id=3, job_id=1, entrypoint=human_systems_morning, status=successful`), preceded by its own `queued`→`picked`→`successful` lifecycle in the same table — a real, queryable ledger, not an assertion.

The Stream 1 smoke test (above) additionally confirmed the same mechanism holds for the *actual* production code path (schedule-table dispatch, not just the raw queue), via `pgqueuer_schedules.last_run` showing a single dispatch per due tick.

## Go/No-Go for Wave-4

**Go, incrementally — not a single platform-wide cutover.**

- `human_systems_scheduler.py`: pilot succeeded. Recommend completing the rollout — provision `SUPABASE_DB_URL`, install/enable `deploy/human-systems-scheduler.service` on the production VM, verify one live day of all 7 jobs before considering it done.
- `intelligence/scheduler.py`: **do not migrate yet.** It is a `Restart=always` daemon that "never exits under normal operation," owns the Captain's Brief (morning/midday/eod/weekly) and daily source collection — the platform's single highest-blast-radius scheduler. This pilot deliberately avoided it per the mission's Explicitly Not In Scope; a future mission should migrate it only after `human_systems_scheduler.py` has run on pgqueuer in production long enough to trust the pattern, and should plan a rollback path given the stakes.
- `telegram-bots/revs/scheduler.py`: lowest priority. It already has `max_instances=1`+`coalesce=True` — real, if partial (in-process only, not cross-process), protection. Revisit only after the other two are settled.

## Explicitly Not In Scope — respected

Not touched: `intelligence/scheduler.py`, `telegram-bots/revs/scheduler.py`, any `deploy/*.timer`, the Task Engine (`tasks`/`task_events`, migration 0056) or its `vm-processing` adopter, and no platform-wide consolidation decision was made — this record recommends, it does not execute Wave-4.

## Files changed

- `platform-runtime/human_systems_scheduler.py` — `_start_daemon()` now delegates to pgqueuer via `_start_daemon_async()`.
- `platform-runtime/requirements.txt` — added `pgqueuer>=1.3.2`, `asyncpg>=0.29.0`.
- `deploy/human-systems-scheduler.service` — new, models `intelligence-scheduler.service`.
- `knowledge/SUOC-Platform-Registry.md` — Scheduling capability's Current Status/Technical Debt/Next Planned Evolution updated; instance count corrected 5→3.
- `knowledge/missions/USS-TJR-MSN-0375-knowledge-record.md` — this record.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M5CxbeqXGEpbTcepT1Gh1W
