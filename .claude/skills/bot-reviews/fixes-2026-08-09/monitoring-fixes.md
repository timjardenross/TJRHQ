# Monitoring Fixes — EOD Alert Verification Follow-Up

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/eod-alert-verification/chief-engineer-review.md`

## Scope

Two real findings from the EOD alert verification review:
1. 16+ of 22-24 monitored domains never had heartbeat instrumentation wired in, causing false "never recorded" claims.
2. `vm-processing-healthcheck.service` crash-looping every 30 min since 2026-07-12 on a missing log directory, freezing the "47 permanent failures" figure.

## Item 2 — Knowledge Library healthcheck crash-loop: RESOLVED

Two stacked bugs, both fixed:

1. **Missing directory.** `core/infrastructure/vm-processing/logs/` did not exist on disk (lost in the 2026-08-07 resync; it's gitignored so nothing restored it). Created it (`claude:claude`, 0755). This alone stopped the `status=2/INVALIDARGUMENT "Directory nonexistent"` crash that had repeated every 30 minutes since 2026-07-12 (confirmed via `journalctl`).
2. **A second, previously-hidden bug surfaced by fixing #1.** `core/platform/heartbeat.py::_load_dotenv()` unconditionally called `env_path.read_text()` on `/opt/starship-endeavour/.env` (mode 0600, `root:root`) after only checking `.exists()` (which succeeds without read access). Every `vm-processing-*` service runs as `User=claude`, which cannot read that file — even though `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` were already correctly present in the process environment via systemd's `EnvironmentFile=` (read by root pre-setuid). The `PermissionError` crashed the `heartbeat` module's import, which every `record_heartbeat()` call site wraps in `try/except Exception: pass` — so the failure was silent. This meant **no `knowledge_library` heartbeat had ever actually been written by a `claude`-user process**, independent of the crash-loop. Fixed by wrapping the read in `try/except OSError` and falling back to whatever's already in `os.environ`. Verified via `systemd-run --uid=claude` reproduction before and after.

**Verification:**
- `journalctl -u vm-processing-healthcheck.service`: crash-loop entries stop at 07:26 AEST 2026-08-10 (the directory fix); the next run at 07:28 exits 1 by the script's own documented design (`permanently_failed_count(47) > threshold(0)` → `healthy: false`), not a crash. This exit-1-on-unhealthy behavior is intentional per the script's own docstring, not a bug.
- `domain_heartbeats` query confirms a real, fresh row for `knowledge_library` (previously frozen at 2026-07-12) and `knowledge_library` has dropped out of `run_verification_pass()`'s degraded list.
- **Current real count confirmed live:** `processing_documents` has 47 `permanently_failed`, 795 `awaiting_review`, 8 `excluded` — the "47" figure is coincidentally still numerically accurate, but is now a live-reported number again, not a 4-week-old frozen snapshot.
- `vm-processing.service`/`vm-processing.timer` (the actual ingestion worker) was never affected — it was healthy throughout.

## Item 1 — Heartbeat instrumentation gap

**Baseline** (first live `run_verification_pass()`): `degraded_count = 24`.
**After fixes:** `degraded_count = 22` (confirmed by re-running `run_verification_pass()`).

### Fixed and confirmed live (2)

| Domain | Fix | Verification |
|---|---|---|
| `knowledge_library` | logs/ dir + heartbeat.py permission fix (Item 2 above) | Dropped off degraded list; fresh `ok`/`failed` rows in `domain_heartbeats` |
| `engineering_handoff` | `core/coordination/delivery_reconciler.py` (runs every 15 min via `deploy/delivery-reconciler.timer`, confirmed live) had **zero** `record_heartbeat()` calls despite being an actively-scheduled job. Added heartbeat at the CLI's `__main__` success/failure points. | Manually ran `python -m core.coordination.delivery_reconciler report`; new `ok` row (`items=148`) written; domain dropped off degraded list |

### Fixed (code-complete, correctly wired, not yet confirmed live — no real trigger has fired since the fix)

| Domain | Real write point found | Note |
|---|---|---|
| `insight_outcomes` | `core/platform/insight_outcomes.py::record_insight()` — single canonical function, all callers (`context_service.py`, `captain_brief_evolution.py`, `captain_brief_cli.py`) go through it | Will heartbeat on the next real insight generation |
| `captured_items` | Two live insert points, both inside `tg-xo.service` (confirmed running): `telegram-bots/xo/voice_capture.py::save_capture()` and `telegram-bots/xo/app.py::cmd_note()` | Will heartbeat on the next voice-note capture or `/note` |
| `wellness-coaching` | `telegram-bots/recovery_officer/engagement_dispatcher.py::_emit_and_return()` — migration 0083's comment claimed this was already covered via the Event Bus mirror; it wasn't (`event_bus.py` only self-heartbeats its own `core_events` domain, never the caller's). Added the real call. | **Caveat:** `run_dispatch_check()` is currently only invoked by the Telegram `/dispatch` command — there is no scheduled trigger anywhere in the repo. This domain will only clear when someone manually runs `/dispatch`, not continuously. Flagging the missing schedule rather than inventing one without confidence in the intended cadence — worth a Captain decision on whether this should be on a timer. |
| `decision_outcome_reminder` | `platform-runtime/proactive_scheduler.py::_job_decision_outcome_reminder()` was the only job in the file that never called `_shakedown_log()` (every sibling job does) | Blocked on the disabled service below, same as the other `proactive_scheduler` jobs |

### Not fixed — one root cause, needs a Captain decision (13 domains)

**`starfleet-slack-bot.service` (the "Starfleet Slack Commander Bot", `platform-runtime/app.py`) is disabled and has not run at all in the last 10 days of journal history.** It is the sole entrypoint that wires `proactive_scheduler.start_scheduler()`, `human_systems_scheduler`, `mission_lifecycle`, and `health_check` commands. All of the domains below **already have correct, working `record_heartbeat()` call sites** (most from a prior fix pass, commit `db77436`, plus the `decision_outcome_reminder` fix above) — they are degraded purely because the process that would exercise them isn't running, not because of a code gap:

`missions`, `health_daily_logs`, `human_systems`, `morning_brief`, `appointment_prep`, `shakedown_digest`, `decision_review`, `knowledge_freshness`, `mission_registry_sync`, `weekly_health_synthesis`, `lessons_learned`, `pain_escalation`, `stale_missions_job`

Two of these (`pain_escalation`, `stale_missions_job`) are additionally marked `RETIRED D-3C-04` in their own `domain_registry` notes — not currently scheduled even if the bot were running, so they may be legacy monitoring entries worth removing regardless.

**I did not start this service.** Whether it was deliberately retired (superseded by the XO Telegram bot?) or is simply down by accident is not something I can determine from the code or the available journal history — this is a platform-wide decision (which bot is the Captain-facing command surface) that needs the Captain's/relevant owner's sign-off, not something to flip on unilaterally per Chief Engineer escalation discipline.

**Recommendation:** Captain decision needed — (a) re-enable `starfleet-slack-bot.service` if it's meant to be live, which would clear 11 of these 13 domains automatically once its scheduled jobs run a few cycles, or (b) if it's intentionally retired in favor of the XO Telegram bot, formally retire these domains from `domain_registry` (or re-home the jobs onto XO) rather than leaving them permanently "degraded."

### Not fixed — real write points exist, but in TypeScript (LCARS Portal), not Python (3 domains)

`captains_log`, `physical_readiness`, `advisory_sessions` all have real, live write points in `lcars-portal/` (Next.js API routes — e.g. `app/api/advisory-sessions/route.ts`, `app/api/physical-readiness/complete/route.ts`, and the Captain's Log editor). **No TypeScript equivalent of `core/platform/heartbeat.py` exists anywhere in the repo.** Wiring these requires either a small new TS helper that POSTs to the same `domain_heartbeats` REST endpoint, or a Postgres trigger — a genuine (if small) new capability, not a one-line addition to an existing pattern. Flagging for a follow-up rather than improvising a cross-language helper under time pressure.

### Not fixed — no corresponding code found anywhere (1 domain, likely legacy)

`governance_records` — zero references anywhere in the repo (Python or TypeScript) beyond the `domain_registry` seed row itself. Its own registry note says "Manual, mission-close-out driven — low-alert domain," consistent with there never having been an automated write path. **Recommend the Captain/Knowledge Officer decide whether to remove it from monitored domains or define what should actually write to it** — I'm not inventing a fake call site per the task's explicit guidance.

### Skipped — genuine ambiguity, not confident enough to guess (1 domain)

`decisions` (backs `decision_records`, 31 real rows) — found **11 different Python files** that write to `decision_records` (`operating_patterns.py`, `number_one_memory_adapter.py`, `decision_registry_memory_adapter.py`, `governance_service.py`, `unified_memory.py`, and five `platform-runtime/lib/*learning_loop*.py` variants), none of them a single obviously-canonical live path the way `insight_outcomes.record_insight()` was. Picking the wrong one risks heartbeating a rarely-used code path while the real production writer stays silent. Recommend a focused follow-up investigation specifically on which of these 11 is the actual production write path (or whether more than one legitimately is, requiring multiple heartbeat sites).

## Commits (all pushed to `main`)

1. `403625b` — fix: heartbeat.py crashes on import when root-owned .env unreadable
2. `7e562f2` — fix: wire missing heartbeat for engineering_handoff domain
3. `a6142c8` — fix: wire missing heartbeat for insight_outcomes domain
4. `cb59f8e` — fix: wire missing heartbeat for captured_items domain
5. `55b50c4d` — fix: wire missing heartbeat for wellness-coaching domain
6. `2cc8ef10` — fix: wire missing heartbeat for decision_outcome_reminder domain

`core/infrastructure/vm-processing/logs/` was created directly on disk (gitignored, not a git change).

## Mission Status

Advisory implementation complete for the safe, confidently-identified subset. Two structural findings need Captain sign-off before further progress is possible:
1. Is `starfleet-slack-bot.service` meant to be live? (blocks 13 of the remaining 22 degraded domains)
2. Should `governance_records` (and possibly `pain_escalation`/`stale_missions_job`) be retired from `domain_registry` rather than carried as permanently-degraded?
