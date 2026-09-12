# knip dead-code scan — lcars-portal — 2026-09-12

Real run, real output. `lcars-portal/` had zero dead-code tooling before this
(confirmed by reading `lcars-portal/package.json`: `lint`/`typecheck`/`test`
only). knip 5.88.1, added as a devDependency (`npm install --save-dev knip`)
plus an `npm run deadcode` script; run with:

```
cd lcars-portal && npx knip
```

(knip auto-detects the Next.js 14 App Router — `page.tsx`/`layout.tsx`/
`route.ts`/etc. under `src/app/` — as entry points via its built-in Next.js
plugin, so those aren't reported as unused even though most aren't reached
by import statements from other app code.)

`knip-2026-09-12-full-output.txt` is the full output after adding
`lcars-portal/knip.json` (see below) to remove three confirmed false
positives. Before that config existed the run reported 34 unused files;
after, 31.

## Findings: 313 total (with `knip.json` in place)

| Category | Count |
|---|---|
| Unused files | 31 |
| Unused devDependencies | 1 |
| Unused exports | 104 |
| Unused exported types | 173 |
| Duplicate exports | 1 |

### Confirmed true positives (spot-checked, not assumed)

- **`src/app/knowledge-workbench/_components/{LibraryView,LibraryKpis,BatchTriageBar,DocumentDetail,badges,types}.{ts,tsx}`**
  (6 of the 31 unused files) — genuinely dead. `src/app/knowledge-workbench/page.tsx`
  itself is live (a real route) but its own comment explains why: "Library
  (document cataloguing/review, MSN-0331) pulled back to draft 2026-08-22,
  Captain directive — mid-setup, not fully operational, hidden from view
  until it's ready." The page only renders `MemoryView`; the whole
  `LibraryView` branch and its supporting components are orphaned. This is
  the same shape of finding as the `commander_runtime.py`/`router.py`
  cluster on the Python side — internally-cross-referencing files with zero
  external caller — except here **knip did catch the whole cluster**,
  because it does real whole-file reachability analysis from Next.js's
  known route entry points, not just per-symbol usage counting. See the
  knowledge record for the direct comparison with Vulture's narrower catch.
- **`src/components/home/HomeScreen.tsx`** — confirmed dead by checking
  every hit for the string "HomeScreen" in the repo: every other occurrence
  (`LCARSHeader.tsx`, `LCARSNav.tsx`, `LCARSPanel.tsx`,
  `captains-chair/page.tsx`, `lib/recommendations.ts`) is a code *comment*
  referencing the file by name for historical context ("matching
  HomeScreen.tsx's earlier redesign"), not an actual import. No file
  imports the module.
- **`axe-core` unused devDependency** — confirmed by checking where
  "axe-core" appears in `src/`: only inside a test's `describe(...)` label
  string (`src/components/ui/__tests__/a11y.test.tsx:84`), never as an
  `import`. `vitest-axe` (already a devDependency) bundles its own axe-core
  internally, so the direct `axe-core` entry in `package.json` is
  redundant.

### Confirmed false positives (handled via `lcars-portal/knip.json`)

Three files knip initially flagged as "unused" are real, intentionally
non-imported entry points — verified by reading each and its surrounding
docs before touching config, not preemptively:

- **`deploy-phase-1b.js`** — a standalone Node deployment script
  (`#!/usr/bin/env node`, run directly, not imported by app code). Added to
  `knip.json`'s `entry` list.
- **`scripts/gen-icons.mjs`** — a standalone, "zero-dependency", manually
  re-run PWA icon generator (`// Run: node scripts/gen-icons.mjs`). Added
  to `entry`.
- **`public/sw.js`** — the PWA service worker, registered at runtime by URL
  (`ServiceWorkerRegister`, per `docs/MOBILE-MVP.md`) rather than imported
  as an ES module; lives in `public/` specifically because it's a static
  asset, not part of the webpack/Next module graph. Added to `ignore`.

### Not hand-triaged: the 104 unused exports / 173 unused exported types

These are almost entirely `export`-ed helpers/types that are only used
within their own file or route and don't need to be exported at all (a
very common, low-risk Next.js pattern: components/lib files export more
than their actual external call sites need). We did not hand-verify all
277 of these individually — that's real, ongoing triage work for the
teams that own each workbench, which is exactly why this step is advisory
(`continue-on-error: true`) rather than a merge gate. `Duplicate exports (1)`
(`GOOGLE_OAUTH_SCOPES`/`GOOGLE_CALENDAR_SCOPE` in `src/lib/google-calendar.ts`,
both exporting the same value under two names) is a one-line, low-risk
cleanup a maintainer can pick up separately.
