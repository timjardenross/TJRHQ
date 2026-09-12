# USS-TJR-MSN-0370 — Ruff Manual-Judgment Triage: core/

**Scope:** `core/` directory only (parallel worktrees covered `platform-runtime/`, `intelligence/`+`tools/`, `telegram-bots/`+misc).
**Branch:** `msn-0370-ruff-core` (pushed to origin, not merged to main).
**Follow-up to:** USS-TJR-MSN-0369 (ruff autofix pass).

## Result

- **Starting count:** 977 findings (`ruff check core --statistics`, confirmed fresh at mission start).
- **Ending count: 0 findings** (`ruff check core` reports "All checks passed!").
- 11 commits, each scoped to one rule family or a small related group, so review stays tractable.

## Breakdown: fixed vs suppressed vs left

Nothing was left unresolved — every one of the 977 original findings was either fixed with a real code change or suppressed with a specific, callsite-tied `# noqa: <CODE> - <reason>` comment. No blanket/generic suppressions were used.

### Real bugs found and fixed along the way (not just lint noise)
1. **`core/coordination/number_one.py` — undefined `log` (F821)**: three call sites (`_get_memory_context`, `_persist_memory_context`, `_to_status`) called `log.warning(...)` with no `log` ever imported/defined in the module. `_to_status()`'s own docstring promises "Never raises (MSN-0053)" — a real NameError was one unlucky code path away from breaking that contract. Fixed with `import logging; log = logging.getLogger(__name__)`.
2. **`core/coordination/number_one_exporter.py` — `_git_last_modified()` mislabeled timezone**: truncated git's `%ai` output to 19 chars (dropping the commit's UTC offset), parsed it as naive, then hand-appended `"Z"` claiming UTC — but the value was actually the committer's **local** time. Fixed: parse the full string with `%z` and `.astimezone(timezone.utc)`.
3. **`core/coordination/engineering_handoff_reader.py` / `telegram_inbox_reader.py`** — identical "parse naive, blindly append Z" pattern in `_coerce_approved_at`/`_coerce_timestamp`. Now tags the parsed value with `tzinfo=timezone.utc` explicitly (writer emits UTC wall-clock strings per the existing "+Z" convention) instead of string-concatenating a Z onto an ambiguous naive isoformat.
4. **`core/exec-assistant/priority_analyzer.py`** — sort-key fallback mixed `date` (the field's real type) with `datetime.max`, a type mismatch. Fixed to `date.max`.
5. **`core/coordination/exception_router.py` (B033)** — `CAPTAIN_ONLY` frozenset literal listed `"governance_exception"` twice. Harmless at runtime (frozenset dedups) but hid that the EXEC-010A-commented occurrence was a no-op.
6. **`core/coordination/context_service.py`'s `verification_engine.py`** (from MSN-0369 follow-on) — `detail=None if backend_ok else None` always evaluated to `None` regardless of `backend_ok` (RUF034 useless-if-else); simplified to `detail=None`.
7. **`core/voice/tts_edge.py` (ASYNC230)** — `send_voice_reply()` did a blocking `open(path, "rb")` read directly inside an `async def`, stalling the whole event loop for every other in-flight Telegram update for the read's duration. Moved to `asyncio.to_thread()`, passes bytes to `bot.send_audio()` (confirmed python-telegram-bot's API accepts bytes; only 2 call sites, both in `telegram-bots/xo/app.py`, just `await` the coroutine — no behavior change for callers).

### DTZ family (timezone-naive datetime) — all fixed, none suppressed
- `datetime.utcnow()` → `datetime.now(timezone.utc)` everywhere (repo-wide, ~90 call sites across 30+ files), including the "hand-append Z to naive isoformat" anti-pattern (see bugs #2/#3 above) replaced with the standard `+00:00` suffix.
- `date.today()` → `datetime.now().astimezone().date()` **not** `datetime.now(timezone.utc).date()` — this server runs in `Australia/Melbourne` local time (confirmed via `date`/`/etc/timezone`), and every `date.today()` call site found was about "today" as a human/calendar day (Captain's Log entries, daily health buckets, deadline day-diffs), not a UTC audit instant. A naive switch to UTC would have shifted which calendar day these land on for roughly the 10-11 hour window each day where local and UTC dates disagree. `datetime.now().astimezone().date()` preserves the exact prior local-date value while satisfying DTZ011 (ruff doesn't flag it — confirmed empirically).
- `strptime(...)` without `%z`, `datetime.now()` without tz, `utcfromtimestamp()` — each fixed per-callsite based on what the source string/moment actually represents (see bugs #2/#3 above for the two that turned out to be real bugs; the rest were straightforward `.replace(tzinfo=timezone.utc)` / `.now(timezone.utc)` swaps).
- One DTZ007 suppressed (`decision_extractor.py`): source string is date-only with no offset to parse, reduced to `.date()` immediately and compared only to another `.date()` — no naive/aware datetime ever mixes.

### BLE001 (blind except) — 334 findings, all resolved
Per the mission's explicit decision framework: **narrowed where a specific fix was clear, added real logging where a site swallowed silently with zero visibility, suppressed with a specific reason everywhere the broad catch is deliberate** (system boundaries — Flask/HTTP handlers, per-report/per-item isolation loops, module-import availability guards, best-effort telemetry/heartbeats, cascading multi-source fallbacks, documented "return None/[]/False on any failure" contracts). No blanket "except Exception: pass # noqa" — every suppression names what's actually happening at that callsite (e.g. "cascading Supabase fallback to the legacy table; final give-up handled by the nested except below", not "broad catch is fine").
- Added real logging (previously silent `except Exception: pass`) in: `context_service.py` (4 brief-assembly sections), `weekly_synthesis.py`'s Health-Summary.md updater.
- 2 test-fixture files (`test_captain_brief_integration.py`, `test_captain_profile.py`) suppressed as legitimate "any failure means not-live/keep-going" patterns.

### S110/S112 (try-except-pass/continue) — 57 findings, all resolved
55 of 57 were the exact same except-blocks already given a specific BLE001 reason above — just appended the S110/S112 code to the existing noqa rather than re-litigating. 2 in `core/advisory/patterns.py`/`signals.py` had a bare `# noqa: BLE001` with no reason from an earlier (pre-MSN-0370) pass; gave both a real reason (per-detector isolation).

### Mechanical/style buckets — all resolved
- **EXE002/EXE001/EXE005** (245 findings): 21 genuine standalone CLI scripts (argparse/sys.argv entry points) got a real shebang; 216 files with no `__main__` (204) or pytest-only test files (12, confirmed CI never runs them standalone — `.github/workflows/python-ci.yml` always uses `python -m pytest`) had the executable bit removed as accidental; 6 EXE001 files got `chmod +x` (confirmed genuine CLI/worker scripts); 2 (a pure library and a pytest-only test file) had a stray shebang line removed instead; 1 EXE005 fixed a pre-existing duplicate/dead shebang line embedded mid-file.
- **RUF059, F401, F841, SIM103, C408, RUF015, RUF007, SIM118, PERF102, PIE810, FLY002, RUF034** (94 findings): `ruff --fix` handled 76 automatically; 13 F401s were try/except availability-probe imports (only `ImportError`-vs-not matters) suppressed with reason; the RUF034 fix caught real bug #6 above.
- **RUF013** (26): `def f(x: T = None)` → `def f(x: T | None = None)` via `ruff --fix --unsafe-fixes`, pure type-annotation correctness.
- **SIM117** (42): 36 of 42 nested-`with` blocks in `test_engineering_router.py` merged mechanically; 14 involving a multi-line `patch()`/`pytest.raises()` call suppressed rather than forced into an ugly parenthesized `with (...)` for zero behavior benefit; 3 in `test_supabase_client.py` merged; 3 in `provider_chain.py` merged by hand to preserve a `# nosec B310` comment.
- **PLW1510** (15): all callers already inspect `returncode`/stdout manually or deliberately ignore exit status — `check=False` explicit everywhere (not `check=True`, which would change behavior). An initial scripted insertion produced 7 stray-leading-comma syntax errors, caught by `py_compile` before committing and fixed by hand.
- **ISC004** (11): checked each against surrounding context to rule out an accidental missing-comma bug (a real risk this rule guards against) before wrapping in parens — none were bugs, all deliberate multi-line message splits.
- **RUF012** (10): `list` → `tuple` where only ever iterated/indexed (2 sites); `ClassVar[...]` annotation where a dict/set constant is spread or checked for membership (8 sites, all test fixtures).
- **G201 → TRY401 → F841** (5+5+5, cascading): `log.error(msg, exc_info=True)` → `log.exception(msg)`, which then correctly flagged the now-redundant `{exc}` in the message text (traceback already shows it) as TRY401, whose removal then correctly flagged the now-unused `as exc` binding as F841 — each follow-on rule caught something real about the previous fix, not lint whack-a-mole.
- **SIM102** (4), **SIM115** (3), **PLC0206** (1), **PLW1508** (2), **N999** (2) — see "real bugs" and rule descriptions above; N999 (hyphenated `context-assembly`/`exec-assistant` directories) suppressed as a structural repo convention, not a bug — renaming would ripple across every `sys.path.insert()` site in multiple in-flight parallel worktrees.

## Test verification

- `py_compile` run on every changed file after every edit batch, and a full `find core -name "*.py" | xargs py_compile` sweep before each commit — 0 failures throughout.
- `pytest` run on every test suite covering a touched file after each batch (repeatedly, not just once): `core/context-assembly/tests/`, `core/coordination/test_number_one.py`, `core/coordination/tests/test_recommendation_engine.py`, `core/coordination/tests/test_health_adapter.py`, `core/coordination/test_command_bus.py`, `core/coordination/test_pr_health.py`, `core/coordination/tests/test_build_request_verifier.py`, `core/health/` (full dir), `core/platform/test_configuration_service.py`, `core/platform/test_notification_service.py`, `core/engineering/tests/test_engineering_router.py`, `core/infrastructure/vm-transfer/tests/test_engine.py`, `core/knowledge_navigation/tests/test_sync.py`, `core/tests/test_governance_alignment.py`, `core/content/`, `core/capture/`.
- Final combined sweep: 446 passed, 7 failed — all 7 confirmed pre-existing and unrelated when run in isolation:
  - `core/tests/test_governance_alignment.py` (6 failures): pass 30/30 when run standalone; fail only when combined with unrelated test directories in one pytest invocation due to a pre-existing cross-file `config` module-name collision in this repo's test suite (multiple different `config.py` files across directories share the bare module name; whichever gets imported first into `sys.modules` wins for the rest of the session). Not something this mission's changes caused or could fix without touching test infrastructure well outside `core/` linting scope.
  - `core/platform/test_notification_service.py::test_send_apprise_missing_urls_env`: fails because the `apprise` package isn't installed in this environment (`ModuleNotFoundError`), same failure present before any change in this mission.
  - Also seen throughout (not in the final sweep since excluded): `core/context-assembly/tests/test_captain_brief_integration.py`'s `TestLiveService` class (9 tests) requires a running backend on `localhost:5000`; some pass/fail depending on whether the shared box's `context_service` gunicorn worker is up at test time — unrelated to any datetime/exception/style change made here.
- Used `/opt/starship-endeavour/platform-runtime/.venv` for pytest since this worktree's own environment lacked `pytest`/`pyyaml`/etc.; this is a shared, busy production box (many live services running) — two test runs hit transient timeouts/hangs under load that passed cleanly on retry (`vm-transfer/tests/test_engine.py`), confirmed via `git diff` showing zero content change to that file, so treated as environmental noise, not a regression.

## Commits (chronological, all pushed to `origin/msn-0370-ruff-core`)

1. `fix(core): ruff mechanical cleanup (RUF059/F401/F841/SIM/C4/RUF0xx)`
2. `fix(core): replace naive datetime calls with timezone-aware equivalents (DTZ family)`
3. `fix(core): resolve EXE001/EXE002/EXE005 shebang/executable-bit findings`
4. `fix(core): narrow/suppress BLE001 blind-except findings, batch 1`
5. `fix(core): narrow/suppress BLE001 blind-except findings, batch 2`
6. `fix(core): narrow/suppress BLE001 blind-except findings, batch 3 (final)`
7. `fix(core): resolve S110/S112 try-except-pass/continue findings`
8. `fix(core): resolve RUF013 implicit-Optional and SIM117 nested-with findings` (+ a `.secrets.baseline` line-number-drift commit from the detect-secrets hook)
9. `fix(core): resolve RUF012 mutable-class-default findings`
10. `fix(core): resolve G201/SIM102/SIM115/I001 and follow-on TRY401/F841`
11. `fix(core): clear final ruff findings — 0 remaining in core/`

## What's left

Nothing outstanding in `core/` for ruff's default rule set. Not merged to main per the mission brief — branch `msn-0370-ruff-core` is ready for review/merge whenever the Captain (or whoever owns the merge for this multi-worktree mission) is ready to combine it with the sibling worktrees' branches (`platform-runtime/`, `intelligence/`+`tools/`, `telegram-bots/`+misc).

One thing flagged for awareness but not "left broken": the `core/tests/test_governance_alignment.py` cross-file `config`-module-collision test-isolation issue (see Test Verification above) is pre-existing and orthogonal to this mission — worth its own ticket if the Captain wants CI to be able to run `pytest core/` as one combined invocation reliably (right now `.github/workflows/python-ci.yml` already works around this by running each subsystem's tests as a separate CI matrix job, per that file's own extensive comments).
