# Knowledge Record — Python CI pipeline added (pytest matrix + actionlint); found a test suite that can't fail, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream F) |
| Title | First Python pytest/lint CI for this repo; also surfaced a pre-existing test file whose assertions can never fail |
| Date | 2026-09-12 |
| Lesson | LL-154 |

## Outcome

`.github/workflows/` had only `lcars-portal-ci.yml` (Node/npm-focused for
the frontend, plus standalone `python3 tools/check_*.py` gate jobs) —
confirmed there was no Python pytest/lint CI at all before this. PR #174
(https://github.com/timjardenross/TJRHQ/pull/174, merged) added
`.github/workflows/python-ci.yml` only; `lcars-portal-ci.yml` untouched.

- `changes` job (`dorny/paths-filter@v3`) detects which of
  `platform-runtime/`, `core/` (excluding its infrastructure subsystems),
  each `core/infrastructure/*` subsystem individually, `intelligence/`,
  each `telegram-bots/*` subdir, and each `services/*` subdir changed, then
  builds a matrix containing only the directories that actually changed.
- `test` matrix job: one `pytest` invocation per changed directory, each
  with its own `requirements.txt`-hash-keyed `actions/cache` entry.
- `actionlint` job lints every `.github/workflows/*.yml` present (globbed,
  not hardcoded) — also covers Stream E's `scorecard.yml`.

**Real repo-layout decisions, not assumed:**
`core/infrastructure/{mac-collector,vm-processing,vm-transfer}` each ship
an identically-named `config.py`; that subtree's own `conftest.py`
documents that running them combined in one `pytest core/` process lets
whichever subsystem's `config.py` imports first silently win for every
other subsystem's `from config import ...`. So each gets its own separate
matrix entry/process/requirements install, and the main `core` entry
explicitly `--ignore`s all three. `intelligence/` has no `requirements.txt`
of its own and falls back to `platform-runtime`'s. Every `pytest` step
treats exit code 5 ("no tests collected") as a pass, not a failure —
`telegram-bots/recovery_officer` and `telegram-bots/wellness_officer` have
neither requirements nor tests today; `services/transcription` and
`intelligence/analysis/test_shadow_mode_scoring.py` are script-style files
with no real `def test_*`, confirmed collecting 0 pytest items.

**Evidence — a real break-then-revert, not simulated:** changed
`core/health/capacity_score.py`'s `CAPACITY_THRESHOLDS["Green"]` from `80`
to `50`, re-ran `pytest core/health/test_capacity_score.py -q` →
`AssertionError: 68 not less than 50`, 1 failed / 17 passed, real exit code
1. Reverted (confirmed `git diff` empty), re-ran → 18 passed, exit code 0.
Also ran `pytest telegram-bots/xo -q` with its real `requirements.txt`
installed in a venv → 14 passed, and `actionlint` against all three
`.github/workflows/*.yml` files → clean, exit 0.

### Pre-existing bug found, not fixed (out of scope for this stream)

While looking for a test to break, `telegram-bots/xo/test_voice_capture.py`
was found to use a `check()` helper that only prints pass/fail and never
raises — so pytest reports those tests as "passed" regardless of actual
correctness. This is why `core/health/test_capacity_score.py` (real
`unittest.TestCase` assertions) was used for the break-then-revert proof
instead. Not fixed here; flagged for whoever picks it up next.

## Lesson

A CI pipeline that runs `pytest` isn't automatically a gate — if the
underlying test file can't fail, the pipeline will report green forever
regardless of what breaks. Proving the new gate "gates" (the break-then-
revert exercise the mission brief required) is what caught this, not code
review of the workflow YAML itself.

## Future Guidance

`telegram-bots/xo/test_voice_capture.py`'s `check()` pattern should be
converted to real assertions before anyone relies on that specific test
file's pass/fail signal from this new CI pipeline — as written, it cannot
currently report a regression. More broadly: any test file using a
print-based "check" helper instead of `assert`/`self.assertX` anywhere else
in this repo carries the same risk and is worth a targeted audit now that
CI will actually run and report on all of them.
