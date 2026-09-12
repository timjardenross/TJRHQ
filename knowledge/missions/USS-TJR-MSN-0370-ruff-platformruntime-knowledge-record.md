# Knowledge Record — USS-TJR-MSN-0370 (ruff manual-judgment triage, platform-runtime/)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0370 |
| Title | ruff manual-judgment triage — `platform-runtime/` scope only |
| Follows | USS-TJR-MSN-0369 (ruff autofix pass) |
| Branch | `msn-0370-ruff-platformruntime` |
| Date | 2026-09-12 |
| Scope | `platform-runtime/` only — `core/`, `intelligence/`+`tools/`, `telegram-bots/`+misc handled by concurrent sessions in separate worktrees |

## Outcome

**Starting count: 1295 findings** (`ruff check platform-runtime --statistics`, confirmed at
mission start).

**Ending count: 0 findings.** `platform-runtime/` is fully clean.

## What was fixed, by commit

1. **`fix(ruff): resolve DTZ timezone-naive datetime findings`** (208 findings — DTZ003/005/007/011/001)
   Real correctness fixes across 75 files:
   - `datetime.utcnow()` → `datetime.now(timezone.utc)` (same instant, now tz-aware).
   - `date.today()` → `datetime.now(timezone.utc).date()` — standardizes on UTC wall-clock,
     matching the convention already used elsewhere in the codebase (`core/coordination/*`).
     This is a deliberate judgment call: assumes the server/DB clock is effectively UTC, which
     is consistent with every other `datetime.now(timezone.utc)` call already present. Flagged
     here in case that assumption is ever wrong for a specific deployment.
   - Bare `datetime.now()` → `datetime.now(timezone.utc)`.
   - `strptime()` results that later get compared against tz-aware `now(timezone.utc)` values
     got `.replace(tzinfo=timezone.utc)` — verified in each case that the source string was
     itself produced by a UTC-based writer (e.g. `mission_registry.py`/`mission_logger.py`'s own
     timestamp-writing code, already using `datetime.now(timezone.utc)`).
   - **Real bug found and fixed**: `captain_notifications._mission_last_activity()` was
     truncating `git log --format=%ci` output to 19 characters before `strptime`, silently
     dropping the commit's UTC offset and producing a naive datetime compared against an aware
     `now`. Fixed to parse the full string with `%z` instead of assuming UTC.
   - **Real bug found and fixed**: `commands/mission_lifecycle.py` had a redundant
     function-local `from datetime import datetime` that shadowed the module-level import,
     causing an `UnboundLocalError` (F823) the first time an earlier line in the same function
     used the module-level name. Removed the redundant import.

2. **`fix(ruff): resolve EXE002 and RUF059`** (223 findings)
   - EXE002 (211): 31 files with a real `__main__` entry point got a `#!/usr/bin/env python3`
     shebang; 181 import-only modules had the executable bit removed (verified via repo-wide
     grep that none are invoked directly by path in any `.service`/`.sh`/`.yml`/Makefile — a
     few hits were prose comments, not real invocations).
   - RUF059 (12): ruff's own `--unsafe-fixes` autofix (prefix unused unpacked names with `_`).

3. **`fix(ruff): resolve S110/S112/E722`** (77 findings)
   77 try/except/pass or try/except/continue sites across 45 files were silently swallowing
   exceptions with zero observability. Fixed by adding real `log.debug(...)` calls (capturing
   the exception) before the pass/continue, which resolves the rule directly rather than
   suppressing it — these are legitimate best-effort/isolated-failure patterns (a pipeline
   sub-step that shouldn't crash the whole run), they just weren't being logged. Also narrowed
   2 bare `except:` (E722) in `lib/research_delegator.py` to `except ValueError:` (parsing a
   regex-matched digit string). Two files (`collaboration_log_consumer.py`, `prompt_loader.py`)
   had no logger at all — added `import logging` + `log = logging.getLogger(__name__)`.

4. **`fix(ruff): resolve remaining small-bucket findings`** (~117 findings across ISC004, F841,
   PLW0602, RUF013, SIM117-partial, G201, RUF012, SIM102, PIE810, FLY002, PERF102, F811,
   PLW1510, RUF046, F401, TRY201, SIM103, SIM201, F821, C408, C401, PIE790, TRY401, F404, I001)
   Mostly `ruff --fix`/`--unsafe-fixes`, plus by-hand fixes for the ones needing real judgment:
   - **Real bug found and fixed** (F821): `commands/mission_lifecycle.py`'s flat-file registry
     fallback in `handle_mission_status()` called an undefined `_parse_registry()` — guaranteed
     `NameError` any time Supabase is unavailable or the mission isn't found there. Wired to the
     real `mission_registry.load_registry_entries()` helper and fixed the row-key lookup.
   - **Dead code found and removed** (F811): `llm.py` had three function definitions
     (`get_gemini_model`/`is_gemini_available`/`generate_with_gemini`) fully shadowed by a
     second, more complete definition later in the same file (checks `GOOGLE_API_KEY` too,
     REST-based instead of SDK-based) — the earlier ones were unreachable dead code.
   - `commands/research_command.py` (PLW0602): trimmed 5 `global` statements to only the names
     actually reassigned in each function.
   - `commands/resilience_brief.py`, `lib/briefing_officer.py`, `lib/learning_loop_service.py`
     (G201 + TRY401): `log.error(msg, exc_info=True)` → `log.exception(msg)`, with the
     now-redundant exception-object reference dropped from the message.
   - 6 test files (RUF012): annotated shared class-level test constants with `typing.ClassVar`.

5. **`fix(ruff): resolve all 658 BLE001 findings`** — the largest bucket, ~50% of the mission's
   total findings. Split into 6 file-disjoint batches (~110 findings each) reviewed in parallel
   by subagents following the mission's explicit per-callsite policy:
   - **~600 sites**: legitimate "best-effort isolated pipeline step" pattern (daily ops cycle,
     learning loops, strategy scorers, notebook/investigation pipelines, comms/officer
     workflows) — a sub-step wrapped in `except Exception` so one failure doesn't crash the
     whole run. Where already logged: `# noqa: BLE001 - <specific reason>` added to the
     `except` line, reason text tailored per-site, not boilerplate.
   - **~40 sites**: had no logging at all — added `log.debug`/`log.warning` referencing the
     exception first (preserving the original fallback behavior), then the noqa. `llm.py`,
     `lib/tz.py`, `lib/mistral_agent_client.py` had no logger configured at all — added one.
   - **~12 sites narrowed to specific exception types** instead of suppressed (only where the
     failure mode is genuinely enumerable): ISO-date/`datetime.fromisoformat` parsing →
     `(ValueError, TypeError)` (`escalation_manager.py`, `lib/delivery/forecast.py`,
     `lib/notebook/notebook_patterns.py`, `lib/research_memory_retrieval.py`,
     `lib/delivery/analysis.py`, `commands/resilience_brief.py`); JSON decode → `ValueError`
     (`commands/github_issue_draft.py`); zoneinfo lookup → `(ImportError, KeyError)`
     (`human_systems_scheduler.py` — `ZoneInfoNotFoundError` is a `KeyError` subclass); file
     read → `(OSError, UnicodeDecodeError)` (`lib/human_systems/mission_load.py`).
   - **1 test-file site** (`test_semantic_routing.py`, interactive REPL loop) noqa'd under the
     test/fixture policy.
   - No narrow-exception guesses were made anywhere confidence was lacking — per the mission's
     explicit instruction, uncertain sites default to logged+noqa.

6. **`fix(ruff): resolve SIM117`** (10 findings, all in test files) — combined nested
   `with A: with B:` context managers into `with A, B:`. Purely mechanical, no behavior change.

## Verification

- Every commit: full `python3 -c "import ast; ast.parse(...)"` syntax check on every touched
  file before committing (zero syntax errors introduced across the whole mission).
- Every commit: full `pytest platform-runtime` run. Result was **byte-identical throughout the
  entire mission**: 577 passed / 19 failed, always the *same* 19 pre-existing, unrelated
  failures (in `test_build_router_alignment.py`, `test_mission_lifecycle_wp2_wp3.py`,
  `test_wp1_wp2_wp3.py`) present before this mission started. Confirmed via a clean-HEAD
  baseline run early in the mission. These 19 failures are pre-existing test/implementation
  drift unrelated to ruff and out of scope for this mission — a concurrent session
  (`msn-0368-stage-2b-existing-capability-fixes`) appears to already have WIP addressing them
  (found live in the shared stash stack, see incident note below; not applied here since it's
  someone else's in-flight work).
- pytest environment note: system `pytest` was broken (`ModuleNotFoundError: _pytest`); used
  the working venv at `/opt/starship-endeavour/platform-runtime/.venv` for all test runs instead.

## Incident: shared git-stash collision across concurrent worktrees (recovered cleanly)

Git worktrees share a single `refs/stash` stack even with separate working directories. Mid-mission,
a routine `git stash && <baseline test> && git stash pop` (done to get a clean-HEAD pytest
baseline for regression comparison) collided with a stash simultaneously held/pushed by the
concurrent `msn-0368` session working in a different worktree of the same repo. The pop grabbed
whatever was on top of the shared stack at that moment, partially applied an unrelated stash
(`msn-0368`'s "platform-runtime test fixes"), and appeared to drop it.

**Recovery**: the dropped stash commit was still reachable as a dangling commit
(`git fsck --no-reflog`); found it by grep-matching its commit message, restored it to the stash
list with `git stash store`, then recovered my own WIP by diffing my stash commit against its
parent (`git diff <parent> <stash-sha> > patch; git apply patch`) rather than touching the shared
stash mechanism again. No work was lost — my own or the other session's.

**Lesson for future missions in this repo**: **never use `git stash` in a shared-worktree
repo** (multiple worktrees of the same git dir share one stash stack — this is the same class of
issue as the previously-recorded "git shared-worktree collision" lesson, now confirmed to extend
to `git stash`, not just `git checkout`). For a "compare against clean HEAD" need, prefer
`git diff` + `git apply -R`/`git apply` round-trips (which touch only the working tree, never a
shared ref) over `git stash`.

## Not attempted / left for a future pass

Nothing — `platform-runtime/` reached 0 ruff findings in this pass, ahead of the mission's own
"fine to not reach zero" allowance.

## Pre-commit hook notes

`ruff-check` and `bandit` are configured as hard-blocking local pre-commit hooks (unlike CI,
which keeps `ruff-check` informational for now per the repo's own `.pre-commit-config.yaml`
comment). Every commit in this mission except the last two legitimately hit this wall (the
commit's own diff was clean, but the *file* still carried findings from a rule family not yet
addressed by that commit) and used the documented `SKIP=ruff-check,bandit` escape hatch, per the
mission brief's explicit instruction. `gitleaks` and `detect-secrets` were never skipped. The
final SIM117 commit only needed `SKIP=bandit` (ruff-check passed clean) — bandit flagged
pre-existing findings in the same test files unrelated to the SIM117 diff itself.

## Branch state

Branch `msn-0370-ruff-platformruntime` pushed to origin after every commit (7 commits total).
Not merged to `main` — per mission instructions.
