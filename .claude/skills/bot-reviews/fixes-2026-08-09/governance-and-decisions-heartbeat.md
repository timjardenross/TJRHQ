# governance_records Retirement + decisions Heartbeat Wiring

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/monitoring-fixes.md` — two items explicitly left as "needs a real decision, not a guess."

## Item 1 — `governance_records`: RETIRED, verified live

**Independent verification (before touching anything):** fresh repo-wide grep for `governance_records` across `.py`/`.ts`/`.tsx`/`.sql`/`.md` found exactly one hit outside the two prior review docs: the `domain_registry` seed row itself in migration `0071_domain_heartbeats.sql`. No Python or TypeScript code, no other migration, references it anywhere. Confirms the prior finding independently — this domain has never had a write path.

**Fix:** `domain_registry` had no soft-delete/status column, so a hard `DELETE` was the only alternative to adding one. I found precedent for the right pattern instead: `intelligence_source_registry` (migration `0004_intelligence_platform.sql`) already uses `active boolean not null default true` with an `idx_isr_active` index for exactly this "retire without losing history" purpose — `domain_registry`'s own migration comment says it "generalizes the intelligence_source_health pattern," so extending that same convention is the coherent choice, not a hard delete.

Migration `0112_domain_registry_active_flag_retire_governance_records.sql`:
- Adds `active boolean not null default true` + index to `domain_registry` (every other domain defaults to `true`, so no other domain's behavior changes).
- Sets `governance_records.active = false` and appends a dated retirement note to its existing `notes` column (audit trail preserved, not overwritten).
- Recreates `domain_heartbeat_latest` (from migration 0073) scoped to `where r.active`, so `run_verification_pass()` and `infra_narrative.py` — both of which read this view, not `domain_registry` directly — automatically stop reporting retired domains without any Python code change.
- Also patched `core/command-centre/backend/api/verification.js`'s `total_domains` count query to filter `active=eq.true`, so the UI's domain count stays consistent with the degraded-list scope.

Applied directly to the live database via `mcp__supabase__apply_migration` (matches the committed migration file).

**Verification:** ran a fresh `run_verification_pass()` (`core/platform/verification_engine.py`) before and after. Baseline included `governance_records` in `degraded_domains` (part of the 22-domain baseline from the prior report). After the migration: `governance_records` no longer appears anywhere in `run_verification_pass()`'s output — confirmed live, not just by inspecting the view.

**Not done, and why:** did not hard-delete the row, and did not invent a fake writer for it — both were explicitly out of scope per the task's framing and the prior review's own conclusion ("Manual, mission-close-out driven" was never backed by real automation).

## Item 2 — `decisions` (backs `decision_records`): three real writers identified and wired, one confirmed dead

### Investigation

Grepped the whole repo for `decision_records`. The earlier review counted "11 files"; a closer read (distinguishing reads from writes) narrows this considerably. Files that only `select`/read from `decision_records` are not candidates for a *write*-side heartbeat and were excluded:

| File | Access | Verdict |
|---|---|---|
| `core/intelligence/operating_patterns.py` | Not even a table reference — a variable named `n_decision_records` | Excluded |
| `core/coordination/governance_service.py` | `_retrieve_relevant_decisions()` — read-only | Excluded |
| `core/coordination/decision_registry_memory_adapter.py` | `_load_decisions()` — read-only (`.select("*")`) | Excluded |
| `core/coordination/number_one_memory_adapter.py` | `.select("*").limit(10)` — read-only | Excluded |
| `core/platform/unified_memory.py` | `_recall_table(...)` — read-only | Excluded |
| `platform-runtime/commands/decision_log.py` (`handle_decision_log`/`handle_save_decision`, the `/decision-log`-style commands) | Writes **markdown files** to `knowledge/decisions/`, never touches the `decision_records` table at all — a separate "decisions" store entirely | Excluded (but noted below — real fragmentation) |

That leaves four genuine write call sites, all inserting into `decision_records`:

1. **`platform-runtime/lib/build_learning_loop.py::record_build_lifecycle_event()`** — writes on every `/build` engineering-handoff lifecycle event (called from `platform-runtime/commands/mission_brief.py`).
2. **`platform-runtime/lib/learning_loop_service.py::LearningLoopService.log_decision()`** — a class method on a service instantiated in `platform-runtime/app.py::_init_learning_loop()`.
3. **`platform-runtime/lib/research_learning_loop.py::record_research_lifecycle_event()`** — writes on research-mission decisions (called from `platform-runtime/commands/research_command.py::handle_research_request_with_slack`).
4. **`platform-runtime/lib/comms/comms_learning_loop.py::record_comms_approval_event()`** — writes on Captain-only comms pipeline transitions (called from `platform-runtime/lib/comms/pipeline.py::advance()`, gated on `CAPTAIN_ONLY_TRIGGERS`).

### Which of the four is real, via live DB evidence

Queried `decision_records` directly (31 rows total, matches the prior review's count). Grouped by `metadata->>'source'`:

| Source | Count | Date range | Matches which code path? |
|---|---|---|---|
| `build-learning-loop` | 16 | 2026-06-11 (23:13–23:14, one batch) | `build_learning_loop.py` — id format `DEC-REC-<ts>-<hex6>` matches `generate_build_decision_id()` **exactly** |
| `or-intelligence` | 10 | 2026-06-14 | No matching code anywhere in the current repo (grepped for the literal string and the `OR-INTEL-` id prefix — zero hits outside these historical rows). Almost certainly a deleted/retired script; not one of the four live candidates. |
| `NULL` (no source) | 5 | 2026-06-10 (14:30–14:34, sequential MSN-0055…0059) | id format `DEC-REC-YYYYMMDD-HHMMSS` matches `LearningLoopService._generate_decision_id()` exactly, and no other writer omits `metadata.source`. The tight 4-second cadence across synthetic-looking decision-makers ("Chief Operations", "Captain TJR", "XO-Operations", "U98765432") looks like a one-off manual/demo script run, not organic usage. |

`research-learning-loop` and `comms-learning-loop` have **zero rows ever**, despite both being real, reachable call sites.

### Deciding what to wire

- **`build_learning_loop.py` — confirmed canonical for the build/handoff event type.** 16 of 31 real rows, ID format match is exact, and it's wired into a well-established, actively-referenced feature (`/build` handoff lifecycle via `mission_brief.py`). **Wired.**
- **`learning_loop_service.py::log_decision()` — confirmed dead code, deliberately NOT wired.** Grepped the whole repo for `.log_decision(` — the only site that creates a `LearningLoopService` instance is `app.py::_init_learning_loop()`, which assigns it to a local variable `ll` that is never read again anywhere (not stored on a module global, no other call site references `ll.log_decision(...)`). The 5 historical rows almost certainly came from someone exercising the class directly (a REPL/manual script), not from any reachable production code path. Heartbeating this would do exactly what the source review warned against: "heartbeating a rarely-used code path while the real production writer stays silent." Left alone; flagging as a dead-code cleanup candidate for a separate ticket.
- **`research_learning_loop.py` and `comms_learning_loop.py` — real, live-wired, but never yet fired.** Both are called inline (not just imported-and-discarded) from real feature code (`research_command.py`, `comms/pipeline.py`). They represent genuinely different business events feeding the same `decisions` ledger (a research-mission decision vs. a Captain's comms approval vs. an engineering handoff decision) — this is the "two paths are both real, wire both" case the task anticipated, not an either/or choice between competing implementations of the same thing. **Both wired.**

All three wirings follow the exact pattern already established by the `insight_outcomes` fix in the prior pass (`core/platform/insight_outcomes.py`): call `record_heartbeat("decisions", status="ok", detail=...)` immediately after a confirmed-successful insert (checking `SupabaseWriteResult.ok`), wrapped in `try/except Exception: pass` so a heartbeat failure can never break the write it's attached to.

### Why `decisions` will stay degraded for now — and that's expected, not a new bug

All three wired call sites are reachable only through `platform-runtime/app.py` — the Starfleet Slack Commander Bot. Independently confirmed via `systemctl status starfleet-slack-bot.service`: `disabled`/`inactive (dead)`. This is the exact same root cause the prior review already escalated for 13 other domains (missions, human_systems, morning_brief, etc.) — `decisions` simply wasn't in that list before because it had *zero* heartbeat call sites at all, rather than call sites blocked on a dead process. It now belongs in that same bucket: code-complete, will self-clear once the bot runs a `/build`, research, or comms-approval event a few times, blocked on the same Captain decision already flagged (re-enable `starfleet-slack-bot.service` or formally retire/re-home its jobs).

### A fragmentation finding worth flagging separately

`platform-runtime/commands/decision_log.py` (`/decision-log`, `/save-decision`-style handlers) writes **markdown files** to `knowledge/decisions/*.md` — a completely separate "decisions" store from the `decision_records` Postgres table, with its own ID scheme (`DEC-YYYYMMDD-HHMM-<slug>.md`) and its own reader (`decision_registry_memory_adapter.py::_load_from_files()` falls back to this directory when Supabase is unavailable). This wasn't in scope to fix, but it means "decisions" is fragmented across two genuinely different storage mechanisms, not just multiple writers into one table — worth a Captain/Chief-of-Staff decision on whether these should ever be unified, separate from the heartbeat question this mission answered.

## Files changed

| File | Change |
|---|---|
| `core/infrastructure/supabase/migrations/0112_domain_registry_active_flag_retire_governance_records.sql` | New migration: `active` flag on `domain_registry`, retires `governance_records`, scopes `domain_heartbeat_latest` to active domains |
| `core/command-centre/backend/api/verification.js` | `total_domains` count now filters `active=eq.true` |
| `platform-runtime/lib/build_learning_loop.py` | Heartbeat on confirmed `decision_records` insert (canonical build-event writer) |
| `platform-runtime/lib/research_learning_loop.py` | Heartbeat on confirmed `decision_records` insert (research-event writer) |
| `platform-runtime/lib/comms/comms_learning_loop.py` | Heartbeat on confirmed `decision_records` insert (comms-approval writer) |

## Commits

1. `82daa8ba` — fix: retire governance_records from monitored-domains (no write path exists) — pushed directly to `main`.
2. The three `decisions`-heartbeat Python changes were captured correctly but landed inside a **concurrent session's** commit `dfb15898` ("feat: add TypeScript port of Python heartbeat helper for domain_heartbeats") due to a `git add`/commit race in this shared repo — that session's broad-scope commit picked up my already-staged files before I could commit them separately. Verified after the fact: `dfb15898`'s diff includes exactly my three intended diffs to `build_learning_loop.py`, `research_learning_loop.py`, and `comms/comms_learning_loop.py`, byte-for-byte, and is already pushed to `origin/main`. No content was lost; the only casualty is that the commit message doesn't describe the Python-side change, which this document now records. Not re-committing separately to avoid a duplicate/conflicting diff.

## Verification (fresh, post-fix)

- `run_verification_pass()` re-run live: `governance_records` absent from `degraded_domains` (confirmed both immediately after the migration and again after the concurrent session's later commits).
- `decisions` still appears in `degraded_domains` — expected per the root-cause analysis above (blocked on the disabled Starfleet Slack bot, not a wiring gap).
- `python3 -m py_compile` clean on all three modified Python files.
- No `.log_decision(` call sites exist anywhere in the repo — confirms `learning_loop_service.py` was correctly left un-instrumented.

## Mission Status

Advisory implementation complete for both items. `governance_records` fully resolved and live-verified. `decisions` is code-complete on all three confidently-identified real writers; it remains degraded until either (a) `starfleet-slack-bot.service` is re-enabled (same Captain decision already pending from the prior report), or (b) one of the three event types fires through some other path. No new Captain decision required beyond the one already on the table from the prior mission.
