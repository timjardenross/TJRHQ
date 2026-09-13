# USS-TJR-MSN-0374 Stream 1: Storybook a11y CI Enforcement — Knowledge Record

**Date:** 2026-09-13
**Branch:** `msn-0374-stream1-storybook-a11y`
**Status:** Complete — not merged to main (per instructions), branch pushed to origin, PR opened.

## Context

`lcars-portal` already had `@storybook/addon-a11y`, `axe-core`, `vitest-axe`, and
`eslint-plugin-jsx-a11y` installed (confirmed via `grep -n "addon"
lcars-portal/.storybook/main.ts` and `package.json`). Despite that, nothing ran
an a11y check across ALL stories in CI — the addon only surfaces violations in
its interactive Storybook panel, and the handful of existing component tests
that import `vitest-axe` do so ad hoc, one component at a time, not for every
story. This stream closed that gap: a CI job that runs axe-core against every
story in the built Storybook output.

## Method

1. Verified the gap first: `grep -rn "vitest-axe" lcars-portal/src` showed only
   scattered per-component test usage, no story-wide sweep; no CI job invoked
   `storybook` or an a11y tool at all before this change.
2. Tried the "obvious" fix first — `@storybook/test-runner` (Jest + Playwright,
   the classic Storybook a11y-in-CI pattern). It failed outright against this
   project's Storybook 10.5.0 build: every story import throws
   `module.register() is not supported in Jest` (Jest's runtime can't handle
   Storybook 10's ESM module loader). Confirmed by actually running
   `npx test-storybook` against `npm run build-storybook` output — 7/7 test
   suites failed at import time, 0 tests ran.
3. Checked the "modern" alternative, `@storybook/addon-vitest` — its latest
   stable release (9.1.9 on npm) has no version declaring Storybook 10
   support, and installing it alongside `storybook@^10.5.0` would fight the
   existing Vite/Vitest setup rather than fit it.
4. Landed on a hand-rolled script instead:
   `lcars-portal/scripts/storybook-a11y-check.mjs`. It:
   - Builds nothing itself (CI runs `npm run build-storybook` first).
   - Reads `storybook-static/index.json` for every story entry.
   - Serves `storybook-static/` with a ~20-line built-in `http` static
     server (no new static-server dependency — Node's own `http`/`fs` are
     enough for serving a handful of build output files to a local
     Playwright page).
   - Launches headless Chromium via `playwright` (added as a new
     devDependency — needed regardless of approach for any headless
     browser check), navigates to each story's `iframe.html?id=...&viewMode=story`,
     injects `axe-core` (already a devDependency, no new axe-related
     package needed), and runs `axe.run()` scoped to `#storybook-root`.
   - Prints a summary (stories checked / with violations / total
     violations / total passes) plus a per-story violation breakdown, then
     **always exits 0** — report-only by design (see below).
5. Wired it up: `package.json` gained a `test-storybook` script
   (`node scripts/storybook-a11y-check.mjs`); `.github/workflows/lcars-portal-ci.yml`
   gained a `test-storybook` job (`npm ci` → `npx playwright install
   --with-deps chromium` → `npm run build-storybook` → `npm run
   test-storybook`), with the last step marked `continue-on-error: true` at
   the step level — following the same pattern already established by the
   `deadcode` job's `Run knip` step (a job-level `continue-on-error` alone
   doesn't stop the check-run itself from showing red, confirmed by that
   job's own comment referencing PR #180).
6. `@storybook/test-runner` and `axe-playwright` were installed then removed
   once the Jest incompatibility was confirmed (`npm uninstall
   @storybook/test-runner axe-playwright`) — only `playwright` remains as a
   new devDependency.

## Real captured result (not a claim — actual local run)

Ran locally end-to-end: `npm ci` → `npx playwright install --with-deps
chromium` → `npm run build-storybook` → `node scripts/storybook-a11y-check.mjs`
against the real `storybook-static` output, served on `127.0.0.1:6007`.

```
=== Storybook a11y report (axe-core, report-only) ===
Stories checked: 28
Stories with violations: 8
Total violations: 8
Total passing axe checks: 145
```

All 8 violations are the same rule, `color-contrast` (impact: `serious`),
across:
- `TJR Design System/Input` — Text Field, Textarea Field, Select Field, Form
  Layout (1 node each except Form Layout: 3 nodes)
- `TJR Design System/Navigation` — Tab Nav (2 nodes)
- `TJR Design System/Progress` — Bar, Multiple Bars, Steps (1, 3, 1 nodes)

This was **not** run through GitHub Actions CI (no trigger available in this
session to observe a live Actions run before opening the PR) — the number
above is a direct local execution of the exact same command
(`npm run build-storybook && npm run test-storybook`) the new CI job runs,
against the same `storybook-static` build artifact, so it is the real number
CI will report on the next push, not an estimate.

## Outcome

- New file: `lcars-portal/scripts/storybook-a11y-check.mjs`.
- `lcars-portal/package.json`: added `test-storybook` script; added
  `playwright` as a devDependency (only new package — `@storybook/test-runner`
  and `axe-playwright` were tried and removed).
- `.github/workflows/lcars-portal-ci.yml`: new `test-storybook` job,
  report-only via step-level `continue-on-error: true`.
- 8 pre-existing `color-contrast` violations across the design-system Input,
  Navigation, and Progress stories are now visible to CI on every PR, but
  **fixing them is explicitly out of scope for this stream** — that's a
  separate, not-yet-scheduled piece of work.
- All changes committed to `msn-0374-stream1-storybook-a11y` and pushed to
  origin. Not merged to main.
