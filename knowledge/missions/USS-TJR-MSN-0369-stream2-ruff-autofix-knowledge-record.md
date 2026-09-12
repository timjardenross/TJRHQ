# USS-TJR-MSN-0369 Stream 2: Ruff Auto-Fix — Knowledge Record

**Date:** 2026-09-12
**Branch:** `msn-0369-stream2-ruff-autofix`
**Status:** Complete — not merged to main (per mission brief; lands as its own
reviewed PR, not blind-merged), branch pushed to origin.

## Scope

Mechanically-pure `ruff check --fix` autofix pass over the whole repo, using
the exact rule set CI/pre-commit already runs (`ruff-check` via
`ruff-pre-commit` rev `v0.16.7` in `.pre-commit-config.yaml`). No `pyproject.toml`
or `ruff.toml` exists in this repo — the pre-commit hook and this pass both
run Ruff's stock default rule selection, so "same rule set as CI" is
automatic (nothing to configure or diverge on).

No logic changes, no hand-edits, no unrelated files touched. Manual-judgment
findings (the ~3,400 non-autofixable ones) are explicitly out of scope here
per the mission brief — that's separate future triage work.

## What was run

```
ruff check --fix .
```

Repo-wide, from the repo root, no extra excludes needed: `.gitignore` already
excludes every `.venv`/`venv`/`*-venv` pattern in this repo (confirmed via
`grep -n venv .gitignore`), Ruff respects `.gitignore` by default, and this
checkout has no real venv directories present anyway. Only the default (safe)
fix set was applied — `--unsafe-fixes` was never passed, so the 347-348
unsafe-only fixes Ruff reports as available were deliberately left alone.

## Results

- **Baseline:** `ruff check . --statistics` → **6,912 errors**, **3,427
  fixable** with `--fix` (matches the mission brief's ~6,861 / ~3,420 figures;
  small variance is just normal count drift since that estimate was taken).
- **After `ruff check --fix .`:** **3,740 findings fixed**, **3,396 remaining**
  (unfixable / manual-judgment — out of scope for this stream). The "fixed"
  count (3,740) is slightly higher than the initial 3,427 "fixable" estimate
  because some fixes cascade — e.g. removing an import can surface a second,
  previously-shadowed finding in the same pass; this is normal, expected Ruff
  behavior, not evidence of anything applied beyond straight autofix.
- **Idempotency check:** re-running `ruff check --fix . --diff` afterwards
  reports "No errors would be fixed" (only the 348 unsafe-only fixes remain
  available) — confirms the autofix pass is complete and stable, and that the
  working tree is exactly Ruff's fixed-point output for `--fix` (no manual
  edits layered on top).
- **Files touched:** 696 files, all `.py` — confirmed via
  `git diff --name-only | grep -v '\.py$'` returning nothing. No config files,
  no docs, no unrelated file types in the diff.
- **Diff shape:** 3,924 insertions / 3,742 deletions across those 696 files.

### Rule categories eliminated entirely by this pass (before/after stats diff)

`F541` (f-string missing placeholders), `FURB122/129/167/188`, **`I001`
(unsorted-imports — the main import-reordering category)**, `PIE790/807/808`,
`PLR0402`, `PYI041`, `RUF010/023/100`, `SIM114/905`, `UP006/024/035/037/045`
(typing modernization: `List`→`list`, `Optional[X]`→`X | None`, etc.). No
category outside Ruff's own known auto-fixable set appears in the diff.

## Behavior-risk review (import reordering)

The mission brief specifically flagged import reordering interacting with
import-time side effects (logging setup, env loading, monkeypatching,
import-time registration) as the main real risk on a 930-file monorepo. This
was checked, not just diff-skimmed:

- Searched the full diff for any hunk that touches (adds/removes/moves) a
  `sys.path.insert(...)` or `logging.basicConfig(...)` line itself — **zero
  hits**. Ruff's isort-equivalent only reorders *within* a contiguous import
  block; it never merges import blocks across an intervening non-import
  statement, so a `sys.path.insert()` sitting between two import blocks (a
  very common pattern in this repo, e.g. `core/health/weekly_synthesis.py`,
  `core/model-router/app.py`) is never crossed by a reorder.
- Spot-checked the highest-churn / most side-effect-prone files by hand,
  including:
  - `core/health/weekly_synthesis.py` (237-line diff, biggest in the repo) —
    reordered `from supabase_client import ...` / `from capacity_score
    import ...` / `from trend_utils import ...` / `from health_llm import
    ...`. All four sibling modules were read and confirmed to only define
    constants/functions at module scope — no import-time side effects that
    depend on relative ordering.
  - `core/model-router/app.py` — reordered `from opentelemetry import trace`
    and `from platform_runtime.lib.telemetry import configure_tracing`
    inside the same `try/except` block, ahead of the `_configure_tracing(...)`
    call. Confirmed downstream code only ever touches the tracer via the
    `_ROUTER_TRACING_AVAILABLE` flag set at the end of that same block, so
    both "both imports succeed" and "either import fails" behave identically
    regardless of which import ran first.
  - `telegram-bots/xo/app.py`, `telegram-bots/capacitybot/app.py`,
    `telegram-bots/revs/app.py` — isort moved first-party imports
    (`core.platform.telegram_access`, `telegram_bots.*`) to after third-party
    imports (`telegram`, `telegram.ext`), matching standard isort section
    ordering. Read `core/platform/telegram_access.py`,
    `telegram-bots/llm.py`, `telegram-bots/recovery_officer/
    engagement_dispatcher.py`, and `telegram-bots/wellness_officer/
    intelligence.py` — none do anything at import time beyond
    `log = logging.getLogger(__name__)` (idempotent, order-independent).
  - `intelligence/scheduler.py` — reordered several function-local (not
    module-level) `from x import y` statements inside job functions; these
    execute only when the function runs, at which point both modules are
    already fully initialized regardless of import order.
- No hunk was found that changed observable behavior. **No hunks were
  hand-reverted** — the entire diff is Ruff's raw `--fix` output, unmodified.

## Test suite: 0 new failures vs main

No `pytest`/lint config exists in a single root `pyproject.toml`; the real
invocation is `.github/workflows/python-ci.yml`'s per-directory matrix
(`python -m pytest <dir> -q`, tolerating pytest exit code 5 as "no tests
collected"). Ran the matrix entries covering the directories this stream
actually touched, each isolated in its own venv per that workflow's own
documented reasoning (mixed `config.py` collisions, per-bot dependency pins):

| Matrix entry | Before (main / stashed) | After (this branch) | New failures |
|---|---|---|---|
| `core` (3 infra dirs ignored, per CI) | 17 failed, 521 passed, 9 skipped | 17 failed, 521 passed, 9 skipped | **0** — identical failing test names both runs |
| `platform-runtime` | 1 collection error (`test_health_event.py`, pre-existing `ImportError` unrelated to this diff — file untouched) | same 1 collection error | **0** |
| `intelligence` | 0 tests collected (documented in the CI workflow's own header: its one `test_*.py` file collects 0 real `def test_*` items) | same | **0** |
| `telegram-bots/capacitybot` (own venv, own pinned deps) | 128 passed, 1 failed (with required env vars stubbed — `TELEGRAM_BOT_TOKEN` etc. are read at import time) | 128 passed, 1 failed | **0** — same failing test |
| `services/revs-content-agents/tests` (own venv, own `pytest.ini`) | 8 passed, 3 failed, 10 errors | 8 passed, 3 failed, 10 errors | **0** — identical failure/error set |

Evidence method for each row: ran the suite on this branch, then
`git stash` (confirmed `git status --short` back to 0 changes / 696 files
restored via `git stash pop` before proceeding each time) to get the
unmodified-`main`-equivalent tree, re-ran the identical command, diffed the
`FAILED`/`ERROR`/summary lines — not just pass/fail counts, but the actual
test node IDs, to rule out one failure silently swapping for a different one
at the same count.

`telegram-bots/xo` and `telegram-bots/revs` could not be installed in this
sandbox — both pin `supabase==2.3.4` + `gotrue==2.12.4` together with
`python-telegram-bot`, which pip's resolver here reports as a genuine
`ResolutionImpossible` (conflicting `httpx` version constraints). This is a
pre-existing dependency-pinning issue in those bots' own `requirements.txt`
files (neither file is touched by this diff — only `.py` files changed
anywhere in this branch), not something this stream introduced or could fix
without touching out-of-scope files. Not run; flagged here for whoever picks
up those bots' own dependency hygiene.

## Excluded hunks

**None.** The entire diff is exactly `ruff check --fix .`'s output — no hunk
was judged behaviorally risky enough to hand-revert. See the behavior-risk
review above for what was checked before reaching that conclusion.

## Verification that the diff is pure autofix output

1. `git diff --name-only | grep -v '\.py$'` → empty (only `.py` files).
2. `ruff check --fix . --diff` on the already-fixed tree → "No errors would
   be fixed" (fixed point reached, nothing layered on top by hand).
3. `git status --short` shows only `M` (modified) entries — no added,
   deleted, or renamed files; 696 files, matching `git diff --stat`'s file
   count exactly.
4. Before/after `ruff check . --statistics` category diff shows only Ruff's
   own known-fixable rule codes (`I001`, `UP006/024/035/037/045`, `F541`,
   `FURB1xx`, `PIE7xx/8xx`, `SIM1xx/9xx`, `RUF0xx`, `PLR0402`, `PYI041`)
   disappearing — nothing outside that set.
