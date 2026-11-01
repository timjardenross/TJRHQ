# Style Dictionary + Leonardo — Adopt/Decline Decision

**Context:** UI Primitives Migration mission, Stream 2. The originating survey assumed no real token system existed and proposed adopting Style Dictionary (multi-platform token build pipeline) + Adobe Leonardo (perceptually-uniform color-ramp + contrast-checking tool). On inspection that premise is false: `globals.css` already carries 51 real CSS custom properties, `theme.ts` runs 5 CSS-variable-backed themes, and `PHASE-1A-CONTRAST-MATRIX.md` documents a WCAG contrast-validation methodology. This doc evaluates the three candidate justifications on their merits, not the original premise.

**Overall decision: DECLINE.** No candidate below survives contact with the actual codebase. Adopting either tool now would be administration for its own sake — a second token pipeline sitting next to the one that already works, per this platform's own governing principle.

---

## Candidate 1 — non-web token export (Figma sync / future native app)

**Verdict: DECLINE.**

- No Figma workflow exists anywhere in the org's docs (`grep -rli figma` across the whole repo tree returns zero hits). Style Dictionary's main value-add over hand-written CSS vars is multi-consumer export (Figma Tokens Studio, iOS/Android, web) from one source. With zero non-web consumers, that's pure unused surface area.
- The mobile strategy is explicit and recent: `lcars-portal/docs/MOBILE-MVP.md` states "**Decision: Progressive Web App (PWA) first. Native wrapper only later, only if justified**," and a Capacitor/native wrapper is explicitly deferred, not planned. A Capacitor wrapper would still render the same CSS/web views — it consumes the existing `--wb-*` vars for free, no export pipeline needed. `docs/LifeOS-Wall-Tablet-V1-Component-Scope.md` reaches the same conclusion for the kiosk build (native Android only for a narrow always-listening use case, called out as "a materially bigger architecture commitment... not recommended without a separate, deliberate decision").
- There is no near-term consumer that a build-time export step would serve. Revisit only if a Figma-based design workflow or a genuine native (non-wrapped) app gets commissioned — neither is on record.

## Candidate 2 — automated contrast-checking at build time vs. manual matrix doc

**Verdict: DECLINE, with a smaller real gap noted.**

- The existing method is not "eyeballed" — `PHASE-1A-CONTRAST-MATRIX.md` §2 states ratios were "computed via WCAG 2.2 relative-luminance formula (script-computed, not visual estimate)" and validated against all three live backgrounds. The manual-vs-automated framing in the mission brief overstates the current gap: it's a one-off script, not a spreadsheet guess.
- Real drift does exist: `git log` shows `tailwind.config.ts` (department colors) and `globals.css` (5 adaptive themes, added in the "Adaptive Themes + redesigned Home/Workbench" commit) both received substantive changes *after* the matrix doc was last meaningfully written — the doc's only later touches are merge-noise commits (`"1111"`, `"up"`, a plain merge), not content updates. So the matrix is already stale relative to the 5-theme system it doesn't cover at all.
- But the fix for that drift is "re-run the script when tokens change and update the doc," not "adopt Leonardo." Leonardo's contrast APIs solve the same relative-luminance math the existing one-off script already does correctly — swapping libraries buys nothing. A lightweight `npm run check-contrast` step wrapping the *existing* validated formula (already proven correct in the matrix doc) would close the real gap without a new dependency. That's a follow-up worth filing (a script, not a pipeline), separate from this decision.

## Candidate 3 — Leonardo-generated ramps for the 6 department colors

**Verdict: DECLINE — this candidate rests on a wrong premise about which colors are which.**

- The 6 "department" colors (`command` #FFB81C, `engineering` #FF9800, `operations` #F44336, `medical` #0099FF, `science` #CC88FF, `status` #1B5E20 — `tailwind.config.ts:97-102`) are a Starfleet/LCARS-themed palette, ratified as "Design System v1.0" per MSN-0310, explicitly called out in comments as a **Visual Design Officer call, not an engineering one** — changing their hex values requires design governance sign-off, not a token-tooling upgrade.
- These are a *separate* palette from the brand-accurate `--wb-*` tokens in `globals.css` (the ones actually re-pulled from the live TJR Mind & Body site per the "Re-theme wb- design system to match the real TJR Mind & Body brand" commit). The mission brief's "hex values re-pulled from the live brand site" description applies to `--wb-sage`/`--wb-ink`/etc., not to the department colors — so the brand-fidelity argument against generated ramps applies to the wrong token group, and doesn't even reach the department colors this candidate is about.
- Each department color already ships a 3-step manual ramp (`DEFAULT`/`soft`/`on`), and Phase 1A's own contrast matrix found **all six `DEFAULT` values fail the 3:1 bar against every live background** — a real, documented defect. But the prescribed fix (matrix doc §"Flag for Design Officer" section) is component-level mitigation or a Visual Design Officer-ratified reshade, explicitly **not** an automated-tooling fix — the doc already anticipated and rejected the "just regenerate the ramp" shortcut for governance reasons.
- Perceptually-uniform ramp generation is a reasonable tool for a *greenfield* palette. Retrofitting it onto six already-ratified, already-failing-for-known-reasons colors changes nothing about whether they pass contrast (Leonardo doesn't know these need to work as small solid indicator dots vs. the specific `space`/`panel` backgrounds any better than the existing script does) and doesn't route around the governance requirement that blocks reshading them today.

---

## "No administration for its own sake"

All three candidates would add a second, parallel token toolchain (build step, dependency, generated-file diffs to review) on top of a system that is small (51 vars, 6 department colors, 4 state colors), already documented, already contrast-validated by a correct method, and changed only a handful of times in the repo's history. None of the three real gaps found (no Figma consumer, a stale-but-fixable matrix doc, a governance-blocked department palette) are solved by the tooling — they're solved by process (re-run the script, get VDO sign-off), which the tooling can't substitute for.

## What would change this decision

- A Figma-based design handoff workflow gets adopted for this org → revisit Candidate 1.
- Token count or theme count grows enough that manual contrast re-validation becomes a recurring bottleneck (not just one stale doc) → revisit Candidate 2, but reach first for a small script around the already-validated formula before reaching for Leonardo specifically.
- The Visual Design Officer commissions a *new* department/status palette from scratch (not a reshade of the ratified one) → Leonardo-style ramp generation is worth a look at that point, as a one-time design aid, not a standing pipeline.

## Recommended near-term action (outside this decision's scope, filed as a follow-up)

File a small script (not a dependency) that re-runs the existing WCAG relative-luminance check from `PHASE-1A-CONTRAST-MATRIX.md` §2 against current `tailwind.config.ts` / `globals.css` values, and either wire it into CI or re-run it manually whenever those files change, so the matrix doc stops drifting. This closes the one real gap found above without adopting either tool.
