# Runtime Render Validation Framework

**Mission:** `Missions/Completed/USS-TJR-MSN-0317-Runtime-Render-Validation-Framework-Implementation.md` (Phase 1), `Missions/Active/USS-TJR-MSN-0319-Runtime-Validation-Wave2-Scenario-Coverage.md` (Wave 2, Phase 2A — scenario coverage expansion).
**Status:** Phase 1 complete (Command Centre pilot, 7 default-render scenarios). Phase 2A complete (7 API-driven state scenarios added — loading/empty/populated/error, via route mocking, no live backend required).

A reusable rendered-UI validation capability: it launches a real headless browser, renders a real page, and checks what the browser actually computed — not what source text implies. It sits as a new layer in the validation pipeline, between existing engineering tests and human Design Officer / Visual Design Officer review:

```
Static Guards → Unit / Integration Tests → Runtime Render Validation → Human Design Review → Commissioning
```

It **complements**, and does not replace, any of the layers around it:
- **`tools/css_token_guard.py`** still runs exactly as before — it's fast, cheap, and needs no browser. This framework catches what that guard structurally cannot (JS-runtime-constructed styles, composited/alpha-blended contrast, layout/visual regressions).
- **Existing engineering tests** (`tsc`, `next build`, contract tests) still verify logical/type correctness — this verifies rendered presentation, a different concern entirely.
- **Design Officer / Visual Design Officer review** is unaffected. This tool exists to reduce how much manual contrast arithmetic and hand-hunting for runtime bugs officers need to do, so their time goes to genuine design judgment instead.

This is **not wired into CI, does not gate anything, and does not block a build or a merge.** It is a capability you run and read a report from — nothing more, by design, this phase.

---

## Why it exists

MSN-0315's 5th Joint Review found real accessibility defects hiding in JS-constructed presentation logic (`statusBadge()`, `statusColour()`, `renderCmdQueue()`) — invisible to any tool that only reads source text, because the defect only exists after a browser resolves and renders it. MSN-0316's feasibility spike proved a headless-browser validation pipeline runs in this environment (an assumption 5 review rounds had carried, unverified, as a blocker). This framework is the reusable capability that spike proved technically viable.

---

## Architecture

```
tools/runtime-validation/
├── src/
│   ├── renderer.js        launches Chromium, opens a page in a fresh context
│   ├── accessibility.js   axe-core scan wrapper, severity filtering
│   ├── computedStyle.js   generic runtime-CSS primitives (resolved var() values,
│   │                      computed style extraction for arbitrary selectors) —
│   │                      no Command-Centre-specific knowledge here
│   ├── visualRegression.js  screenshot capture, pixelmatch-based baseline diff
│   ├── report.js          JSON + Markdown report generation
│   ├── validator.js       orchestrator: runs a target's scenarios through the
│   │                      full pipeline (render → scan → screenshot → compare)
│   └── index.js           public API — everything above, re-exported
├── targets/
│   └── command-centre.js  7 default-render tab scenarios (Phase 1) + 7
│                          API-driven state scenarios (Phase 2A)
├── baselines/
│   └── command-centre/    committed baseline screenshots, one per scenario
├── bin/
│   └── validate.js        CLI entry point
└── reports/
    ├── command-centre-pilot-run.md / .json   committed evidence from a clean run
    ├── pilot-run-screenshots/                the screenshots referenced above
    └── runs/                                  gitignored — future ad-hoc run output
```

**`src/` has no application-specific knowledge in it.** Everything Command-Centre-specific — the URL, the 7 tabs, which tokens to check — lives in `targets/command-centre.js`. Adopting this framework for another Captain-facing application means writing a new file in `targets/`, not modifying `src/`.

---

## How to run it

From `tools/runtime-validation/`:

```bash
npm install                          # installs deps + Playwright's bundled Chromium (postinstall)
npm run validate:command-centre      # runs all 7 scenarios, compares against committed baselines
npm run baseline:command-centre      # re-establishes baselines from the current rendered state
```

Or directly:

```bash
node bin/validate.js command-centre [--update-baseline] [--min-severity=serious]
```

Output: a Markdown + JSON report under `reports/`, screenshots under `reports/runs/screenshots/` (gitignored — ad-hoc, not committed), and a non-zero-exit-code-free run regardless of findings (§ "no gates", by design).

---

## Adding a new target (extensibility)

A target is a plain object:

```js
module.exports = {
  name: 'my-app',
  url: 'file://...' /* or 'http://localhost:3000' */,
  viewport: { width: 1280, height: 720 },   // optional, defaults shown
  scenarios: [
    {
      name: 'default-view',
      cssVariables: ['--sf-status-ok'],      // optional — resolved and reported
      axeRules: null,                        // optional — restrict axe-core to specific rules
      async setup(page) {                    // optional — drive the page into the state to check
        await page.click('...');
      },
    },
    // one entry per distinct state worth validating
  ],
};
```

Run it the same way: `node bin/validate.js my-app`. No changes to `src/` required — this is the extensibility MSN-0317 §8 (Constraints: "keep the framework modular and reusable") calls for.

### Exercising API-driven states (Phase 2A)

A scenario can supply `mocks` — an array of `{ url, status?, contentType?, body?, delayMs? }` — registered as `page.route()` handlers *before* navigation, so any target can exercise loading/empty/populated/error states without a live backend:

```js
{
  name: 'widget-populated',
  state: 'populated (successful API response with data)',   // optional, shown in the report
  mocks: [
    { url: '**/api/v1/some/endpoint**', body: { total: 2, items: [...] } },       // empty: body: { total: 0 }
    // { status: 500, body: { error: '...' } }                                     // error state
    // { delayMs: 5000, body: {...} }                                             // loading state — pair with
  ],                                                                               // a short settle time in setup()
  async setup(page) {
    await page.click('...');
    await page.waitForTimeout(300); // long enough for a normal mock to resolve and render
  },
}
```

`url` is a Playwright glob/regex route pattern. For a **loading** state, set `delayMs` longer than the scenario's own settle wait in `setup()` — the scan/screenshot then captures the pre-resolution DOM deliberately, rather than racing real network latency.

---

## What's checked today

**Phase 1 — 7 default-render scenarios**, one per real Command Centre tab, driven via real `.tab-btn` clicks:
- **Accessibility** (`axe-core`, default rule set).
- **Visual regression** — pixel-exact comparison against a committed baseline.
- **CSS variable resolution** — a representative set of ratified state tokens (`--sf-status-ok/warn/crit` and their `-text` variants, `--sf-accent`, `--sf-border-subtle`), confirmed to resolve to a real value at runtime, not silently empty.

**Phase 2A — 7 additional API-driven state scenarios**, added because the Phase 1 scenarios only ever see fetch-failure behaviour (no backend running) — never a real, successful, specific-shaped API response:
- Command Console: blockers widget in **empty** (0 count), **populated** (2 items across severities), and **error** (HTTP 500) states.
- Astrometrics: OR Intelligence Brief in **populated** (`overall_risk: GREEN`), **populated** (`overall_risk: RED`), **error**, and **loading** (delayed response) states.

This directly reproduced 2 real defects an officer review had found but the Phase 1 scenarios couldn't (both `renderORBrief()` branches — RED and GREEN — using a DEFAULT token as text colour instead of `-text`), and found one more, previously-unknown defect no prior round had surfaced: `.blocker-section-title.critical` fails contrast (3.82:1) in the populated-blockers state. None of these 3 findings were remediated by Phase 2A — coverage expansion and remediation are deliberately separate, gated phases (see the mission brief).

## Known limitations (honest, not hidden)

- Visual regression here is pixel-exact (via `pixelmatch`) — no perceptual/anti-aliasing tolerance tuning has been done yet. A 1px font-rendering difference between machines would currently register as a diff. Acceptable for Phase 1's single-environment pilot; would need a tolerance pass before running across heterogeneous machines/CI runners.
- `computedStyle.js`'s CSS-variable check confirms a variable *resolves to a non-empty value* — it does not (yet) assert that value is the *specific* value the caller expects. A target's `setup()`/scenario definition can add that assertion itself using `getComputedStyles()`; the framework provides the primitive, not a hardcoded expectation.
- No perceptual diffing, no cross-browser matrix (Chromium only), no mobile-viewport pass — all explicitly out of Phase 1 scope per the mission brief.
- **Phase 2A's mocked states are illustrative, not exhaustive.** 7 stateful scenarios were added against 2 widgets (Command Console blockers, Astrometrics OR brief) — not every API-driven section of Command Centre. The mocked response shapes are hand-authored to match the real endpoints' documented contract as read from source, not validated against a live backend's actual response (none is running in this sandbox) — a schema drift between the mock and the real API would not be caught by this framework.
