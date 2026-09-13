# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0375
- **Priority:** P2 — a scoped pilot, not the Wave-4 consolidation itself; safe to sequence after MSN-0374
- **Source:** `knowledge/OSS-Capability-Search-2026-09-12.md`, §5 "Big Bets" and §8 "Next" — pilot `pgqueuer`/`procrastinate` as a Postgres-native durable-execution primitive against the Scheduling capability's disclosed double-fire risk, before committing to a platform-wide Wave-4 consolidation.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -rln "AsyncIOScheduler\|BackgroundScheduler\|BlockingScheduler\|from apscheduler" \
     --include="*.py" . | grep -v test_ | grep -v /tests/
   → 5 files matched: intelligence/scheduler.py, intelligence/proactive_cadences.py,
     platform-runtime/human_systems_scheduler.py,
     telegram-bots/recovery_officer/engagement_dispatcher.py, telegram-bots/revs/scheduler.py.

   grep -rn "task_events\|CREATE TABLE.*tasks" tools/supabase core
   → core/infrastructure/supabase/migrations/0056_task_engine.sql already defines
     tasks/task_events tables (the existing Task Engine capability, separate from
     Scheduling, one real adopter: vm-processing). This pilot does not touch that
     schema or that capability — see Explicitly Not In Scope.
   ```

2. **Premise verification.** The Registry's "5 fragmented APScheduler instances" claim does not survive a direct read of the 5 grep hits — real state is materially different and changes where this pilot should point:
   ```
   Claimed: 5 independent APScheduler instances with a shared double-fire risk.
   -> ACTUALLY: only 3 independent running scheduler processes exist.
      - telegram-bots/recovery_officer/engagement_dispatcher.py: the "apscheduler" hit is a
        comment referencing intelligence/scheduler.py as an example — it does not
        instantiate a scheduler itself. Not a real instance.
      - intelligence/proactive_cadences.py: does not run its own scheduler — its jobs are
        registered INTO intelligence/scheduler.py's single BlockingScheduler via
        `from intelligence.proactive_cadences import register_jobs as _register_proactive`
        (intelligence/scheduler.py:588). One process, not two.
      - So the real 3: intelligence/scheduler.py (BlockingScheduler, ~15+ jobs incl.
        Captain's Brief morning/midday/eod/weekly, source collection,
        mission_registry_sync, content_pipeline, pending_research_sweep — supervised by
        deploy/intelligence-scheduler.service, Restart=always, confirmed live since
        2026-07-08 per that unit's own commit history); platform-runtime/human_systems_
        scheduler.py (BlockingScheduler, 7 cron jobs: morning/midday/eod/evening/weekly/
        degradation/comms_weekly — see below, current live status unconfirmed);
        telegram-bots/revs/scheduler.py (AsyncIOScheduler, 3 interval jobs, ALREADY
        using max_instances=1 + coalesce=True — the one instance with real, if partial,
        overlap protection already built in).

   Claimed (by the source research, as a candidate pilot target): "deadmans-switch" /
   "mission-registry-sync" timers.
   -> mission_registry_sync is not a systemd timer — it's one cron job (06:45 daily)
      inside intelligence/scheduler.py's single BlockingScheduler, per
      proactive_cadences.py's own header comment. deploy/deadmans-switch.timer is a
      genuine standalone systemd timer, unrelated to any of the 3 Python scheduler
      processes above — different mechanism entirely, out of scope for this pilot
      (see Explicitly Not In Scope).

   Verified but NOT resolved by this pre-flight (must be Stream 0 of this mission):
   -> grep found no deploy/*.service, *.timer, or USS-TJR-Control/tmux reference to
      human_systems_scheduler.py anywhere in the repo. Unlike intelligence-scheduler.service
      (which has an explicit, documented, systemd-supervised unit), this scheduler's daemon
      mode may not actually be running in production at all today — or it's invoked by some
      mechanism this repo search didn't find. This mission does not assume either answer;
      Stream 0 below establishes ground truth on the real VM before any code changes.
   ```

3. **Explicitly not in scope.** (see below)

## Explicitly Not In Scope

- **`intelligence/scheduler.py`.** Highest blast radius of the three real instances — it's a `Restart=always` daemon that "never exits under normal operation" and owns the Captain's Brief (morning/midday/eod/weekly) plus daily source collection. Not a first-pilot target under any circumstance; touch it only after this pilot proves the pattern is safe on a smaller surface.
- **`telegram-bots/revs/scheduler.py`.** Already has `max_instances=1, coalesce=True` — the least urgent of the three. Leave as-is; revisit only if the pilot's pattern is adopted platform-wide later.
- **`deploy/deadmans-switch.timer`, `deploy/mission-registry-sync.timer`, and any other systemd `.timer` unit.** These are a different mechanism (systemd OnCalendar) from the in-process APScheduler problem this pilot targets. Not touched here.
- **The Task Engine (`tasks`/`task_events`, migration 0056) and its `vm-processing` adopter.** A separate, existing capability with its own adoption story. This pilot does not merge with, replace, or extend Task Engine — whether Task Engine and a new Postgres-native queue library should eventually converge is a Chief-Engineer-level architecture question outside this pilot's authority.
- **Any Wave-4 "consolidate all scheduling" decision.** This mission produces evidence for that decision; it does not make it. If the pilot succeeds, a separate mission proposes and executes the platform-wide consolidation.
- **Choosing between `pgqueuer` and `procrastinate` in advance.** Stream 2 evaluates both against the real target's actual needs (both are MIT, both are Postgres-native `SKIP LOCKED` queues); this mission picks one during Stream 2, not before.

## Scope / Streams

### Stream 0 — Ground-truth the pilot target before touching it
Confirm, on the actual production host (not this dev sandbox — `human_systems_scheduler.py`'s daemon mode cannot be verified from here any more than `garak_gate.py` could in MSN-0374), whether its `_start_daemon()` path is currently running (`ps`/`systemctl`/`crontab -l`/any process manager in use) or whether its 7 jobs are invoked some other way (e.g., one-shot `--test`/CLI calls from another scheduler or cron entry). Record the real answer — this determines whether Stream 1 is "migrate a live daemon" or "stand up a durable-queue-backed daemon where none currently runs reliably."

### Stream 1 — Wire `human_systems_scheduler.py`'s 7 jobs onto a Postgres-native queue
Replace the `BlockingScheduler`/`CronTrigger` registration in `_start_daemon()` with the chosen library's job scheduling (both `pgqueuer` and `procrastinate` support periodic/cron-style jobs against the existing Supabase Postgres instance — no new infrastructure). Preserve the existing `JOBS`/`_CRON_DEFAULTS`/`_JOB_DOMAIN` structure and env-var-driven cron overrides; only the execution substrate changes. If Stream 0 finds no live daemon today, add a proper `deploy/human-systems-scheduler.service` unit at the same time — the pilot should not leave a genuinely-unsupervised job set unsupervised at the end.

### Stream 2 — Library bake-off
Evaluate `pgqueuer` and `procrastinate` specifically against this target's real shape (7 low-frequency cron-style jobs, not a high-throughput queue) — API ergonomics, migration/schema footprint added to the existing Supabase instance, and how cleanly each expresses `_CRON_DEFAULTS`'s env-var-overridable cron strings. Pick one; document why in the knowledge record, not just "we picked X."

### Stream 3 — Prove the dedup/observability win
Demonstrate, not assert: force a scenario that would have double-fired under plain APScheduler (e.g., a delayed process restart mid-job-window) and show the chosen library's `SKIP LOCKED`-based dedup prevents the double-run, with a queryable job-run record as evidence. This is the actual claim this pilot exists to test — "real dedup + a real job ledger" — and it needs to be shown working, not just wired.

## Acceptance

- Stream 0's ground-truth finding is recorded plainly, including if it contradicts the Registry's "Active" framing for this instance.
- `human_systems_scheduler.py`'s 7 jobs run under the chosen library against the existing Supabase Postgres — zero new infrastructure (no Redis, no second Postgres instance, no new service beyond what Stream 0 determines is needed for supervision).
- The double-fire scenario in Stream 3 is actually demonstrated, with the before/after evidence captured (this is the bar for "pilot succeeded," not "code compiles").
- A clear go/no-go recommendation for Wave-4 (should `intelligence/scheduler.py` and `revs/scheduler.py` eventually migrate to the same library, given what this pilot found) — this mission recommends, a future mission decides and executes.
- SUOC Platform Registry's `Scheduling` capability record updated: correct the "5 fragmented instances" count to the verified 3, note the pilot's outcome, and update Next Planned Evolution.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0375-knowledge-record.md`) covering all four streams — small enough not to need per-stream splitting like MSN-0369/0370/0374. Registry update: yes, required — `Scheduling`'s Current Status, Technical Debt, and Next Planned Evolution fields all change based on this pilot's findings, and the instance-count correction itself belongs in Current Status regardless of the pilot's outcome.
