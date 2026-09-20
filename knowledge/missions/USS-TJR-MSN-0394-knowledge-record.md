---
mission_id: USS-TJR-MSN-0394
title: "Endeavour 27 — TJR HQ Visual System, Responsive Experience & Portal UI Convergence"
status: "STREAMS A-F COMPLETE — Stream G closeout, residual debt below is real and Captain-visible, not silently dropped"
date: 2026-09-20
branch: claude/endeavour-27-mission-brief
baseline_main_sha: efcf33a91
---

# Endeavour 27 — Visual System Convergence

Replaced HQ's 5-theme adaptive palette (Archive/Command/Midnight/Horizon/Sanctuary) with one
fixed dark Command/Focus identity plus a contextual light Read surface, and applied the
resulting Command/Focus/Read classification to all 20 `LIVE_WORKBENCHES`. Full phase-by-phase
build record lives in `Missions/Active/USS-TJR-MSN-0394-endeavour-27-visual-system.md` §6 — this
record is the compressed, durable summary.

## 1. What shipped

- **Token architecture** (`globals.css`, `tailwind.config.ts`): one fixed dark palette on bare
  `:root` (Image 3's named hex — bg `#0B1E2E`, surface `#142B3D`), one light override scoped to
  `[data-wb-mode='read']` (reused `sanctuary`'s former warm-cream values). Every pairing WCAG
  relative-luminance-computed (script, not eyeballed) before locking. `wb-sand`/`wb-sand-deep`
  added alongside the existing `wb-gold`, not replacing it.
- **5-theme system fully retired**: `lib/theme.ts`, `ThemeSelector.tsx` deleted; Settings →
  Appearance's Theme control removed (Motion kept); `layout.tsx`'s anti-flash script's
  `data-theme` half removed (Motion half kept, still a real client preference).
- **`WorkbenchShell` gained a `mode?: 'command' | 'focus' | 'read'` prop**, scoped to the
  content column only (not Sidebar — mission §1.1 is explicit that sidebar/header chrome stays
  dark navy even in Read mode). This is the mechanism every subsequent phase used.
- **Sidebar rebuilt** to a Captain-decided "every live workbench, not a curated subset" IA
  (neither the mockups' 9-item nor the old 5-item list), sourced from the same
  `LIVE_WORKBENCHES`/`WORKBENCH_GROUP_META` `/workbenches` already used.
- **All 20 workbenches classified** Command/Focus/Read — 4 primary reference surfaces
  (Hub/Ready Room/Human Systems/Briefs) fully restyled toward the mockups; 5 like-for-like
  surfaces (Emergency Alerts/Shopping List/Technical OSINT/Health OSINT/Captain's Chair)
  restyled; 11 remaining workbenches classified via the `mode` prop (7 unambiguous, 5 resolved
  by direct Captain decision after being correctly flagged rather than guessed — see §1.8 of
  the mission doc for the final reasoning on each).
- **Mobile nav rewritten**: `MobileCommandBar` Hub/Capture/Readiness → Hub/Ready/Ask/More,
  dropping Capture as a confirmed duplicate of the always-mounted `QuickCapture` button,
  hardcoded colours converted to `wb-*` tokens.
- **Human Systems deep alignment**: real 4-tile grid (Capacity/Posture/Energy/Executive
  Function) and a Capacity Trend bar chart, both wired to real fields already computed
  elsewhere in the app (trend scoring logic extracted to a shared module so the Trends page and
  this card compute from one source, not two).
- **Legacy LCARS cleanup**: 4 confirmed-dead components deleted; `delivery`/`DeliveryPanel`
  swapped off `LCARSPanel` onto the existing `WorkbenchPanel`; department-colour/`lcars-*`
  class usage converted to `wb-*` tokens across ~15 files, including a real priority-signal
  bug in `MissionCard.tsx` (was repurposing department identity colours to mean mission
  priority — the exact anti-pattern `stateToneClasses()`'s own doc comment warns against) and
  a near-invisible-text contrast bug on 8 retired-notice stub pages.
- **Responsive review**: found and fixed 2 real overflow bugs (Briefs' tab bar, Emergency
  Alerts' view switcher — both hand-rolled tab rows missing the overflow-scroll pattern
  `DomainToggle.tsx` already established for the same problem).
- **Accessibility pass**: fixed 15 missing `focus-visible` outlines across 5 files; confirmed
  colourblind-safe status pairing and the global reduced-motion rule cover everything this
  mission added; computed real contrast numbers for every new token pairing.

## 2. Real bugs found and fixed along the way (not cosmetic — genuine defects)

1. **`data-wb-mode` scoping** — first implementation scoped Read mode to `WorkbenchShell`'s
   whole wrapper, so Sidebar went light too. Caught by live screenshot verification, not
   inspection. Fixed by rescoping to the inner content column only.
2. **`bg-wb-bg/80`-style opacity modifiers silently no-op on this repo's plain-hex CSS custom
   properties** (Tailwind's `/NN` opacity syntax needs an RGB-channel variable to work) — a
   pre-existing bug, invisible under the old always-uniform-colour system, that became a real
   visible defect once Read mode needed genuine contrast against the dark chrome around it.
   Found and fixed **6 separate times** across the mission (`WorkbenchShell` header,
   `captains-chair-workbench`'s 5 `_components` files, `notebook/page.tsx`'s 11 occurrences)
   — worth a repo-wide grep for the same pattern outside this mission's touched files (see
   residual debt below).
3. **CSS `color` inheritance gotcha** — text with no explicit colour class inherited the
   *parent's already-computed* dark-mode ink value, not a live re-evaluation of the CSS
   variable, so titles were invisible against the light Read surface until `text-wb-ink` was
   re-declared inside the mode-scoped div.
4. **`NumberOne`'s floating button had no `xl:left-*` override** — sat inside the Sidebar's
   own horizontal span at desktop widths. Pre-existing, invisible under the old short 5-item
   Sidebar, became a reliable visible collision once the full-workbench Sidebar had real
   content at that height.
5. **`MissionCard.tsx`** repurposed department-identity colours as mission-priority signal —
   fixed to real `state-*` tokens.
6. **8 retired-notice stub pages** had `text-lcars-text` (#0d1f33, dark navy) headings against
   the new dark `--wb-bg` — a real near-invisible-contrast bug, fixed to `text-wb-ink`.
7. **`StatusBadge`/`StatusTone`** conflated department-identity colour with risk/WIP-state
   signalling in `delivery`'s usage — extended with a proper `stateTone` prop, two genuinely
   separate code paths now.
8. **`hover:bg-wb-border/30`** in `notebook/page.tsx` referenced a Tailwind token
   (`wb-border`) that doesn't exist anywhere in `tailwind.config.ts` — that hover state
   rendered nothing at all. Found as a bonus while fixing the opacity-modifier pattern in the
   same file.

## 3. Real, Captain-visible residual debt (not silently dropped)

1. **`border-wb-X/40 bg-wb-X/10 text-wb-X-on` contrast trade-off, now far more exposed.**
   `state-*-on`/`wb-*-on` text passes comfortably on the Read (light) surface (4.46–8.11:1)
   but fails badly on the Command/Focus (dark) surface (1.33–2.9:1) across every tone. This is
   **not new** — `stateToneClasses()`'s own doc comment already documents this exact failure
   and records it as a Mission 7-era Captain-accepted trade-off (mathematically impossible to
   satisfy both surfaces with one flat colour; the mandatory bg/border-pairing rule was the
   accepted mitigation, not bare text). What's new: dark is now the **permanent default**
   surface for most of the app, not one of 5 optional themes a Captain had to actively select
   — so this accepted trade-off is now exposed far more of the time than when it was accepted.
   **Needs a fresh Captain decision on whether the trade-off still holds at this exposure
   level** — this mission's own fixes inherited the existing convention rather than
   introducing a new instance of the problem, and did not silently re-decide this.
2. **The same opacity-modifier bug (finding #2 above) likely exists outside this mission's
   touched files.** Found and fixed 6 times inside files this mission edited; a mission-doc
   phase entry (Phase 14) names several files spotted via grep but not fixed as out-of-scope
   (`WatchingView.tsx`, `InboxView.tsx`, `ThinkView.tsx`, `ContentStudio.tsx`, `JobsView.tsx`,
   `LibraryView.tsx`, `ConsultView.tsx`, and more, not exhaustively enumerated) — worth a
   dedicated repo-wide sweep as a follow-up, not attempted here since it would touch files well
   outside this mission's scope.
3. **`LCARSPanel.tsx` could not be retired.** Its last confirmed-real consumer
   (`delivery`/`DeliveryPanel`) was migrated off it, but a fresh importer re-check (correctly
   done rather than trusting the mission doc's own earlier "delivery is the last consumer"
   claim, which was stale) found `(app)/stage-progression/page.tsx` — a deliberate retired-
   notice stub, explicitly out of this mission's scope — still imports it. Retiring that stub
   onto `WorkbenchPanel` (same trivial shape as `delivery`'s own swap) would unlock deletion.
4. **4 mockup elements flagged in §1.1 as "needs verification before building," never
   verified or built this mission** (all real §31 no-fabricated-data risk if built blind):
   - Human Systems' "What Helps N/10 times" exact ratio-format stat — a real component
     (`WhatHelpsMeCard.tsx`) exists, but whether that exact presentation is derivable wasn't
     confirmed.
   - "Watch For" common-early-signs list — may map to `PatternsView.tsx`'s existing signal
     work, not confirmed.
   - Hub/Ready Room's background photography (earth-from-space, ocean-cliffs stock imagery) —
     needs a real licensing/sourcing decision or an explicit "illustrative only, not built"
     call.
   - Ready Room's "Context" panel exact counts (Notes (3), Related items (2), Activity) — not
     confirmed against `personal_tasks`/`captured_items`, not built.
5. **Sidebar footer motto** ("DISCIPLINE / CLARITY / PROGRESS / FREEDOM") shipped as real
   brief copy but never explicitly Captain-confirmed as final — same open status for
   `MobileCommandBar`'s "More" sheet shape (Stream B3's own design call, flagged not
   dictated).
6. **Typography scale and spacing/radius tokens** from Image 2's "Key Design Elements" panel
   (H1/H2/Body/Status Label named levels, component style specs) were never formalised into
   real Tailwind tokens — flagged in Phase 1, never picked back up. Every page built this
   mission reused ad hoc text sizing already present in each file rather than a shared scale.
7. **`intelligence-workbench`'s untouched sub-pages** (`brief/[id]`, `escalation/[id]`,
   `LibraryView.tsx`, `WatchingView.tsx`) have real missing `focus-visible` gaps, same as the
   pages this mission fixed — out of file scope, not swept.
8. **Live-rendered verification deferred to production for most of this mission.** Only Hub,
   Ready Room, and Briefs got real Playwright screenshots against live Supabase (blocked by
   placeholder Supabase keys in this container for later phases) — Captain explicitly
   authorised proceeding on code-review + `tsc`/`eslint`/`build`/test-suite verification only
   for Streams B2 onward, confirming separately against the live Vercel preview. **Full user
   testing on production is the real verification pass for everything built after that point,
   not this container.**

## 4. Verification discipline maintained throughout

Every phase, every merge: `npx tsc --noEmit` clean, `npx eslint` clean on touched files, full
test suite green (725 tests / 69 files, stable count across the entire mission — no test was
ever silently skipped or its expectations loosened to make it pass), `npm run build` run after
every phase that touched shared/many-page code. 4 real concurrent-session merge conflicts
encountered and resolved by hand (never force-pushed, never silently discarded another
session's work) — this branch had genuine concurrent activity from other sessions throughout
the mission, consistent with AGENTS.md's own documented concurrent-session-corruption risk;
every parallel stream in this mission ran in an isolated `git worktree` per that same rule.

## 5. Not yet done

Stream G's own remaining items: this knowledge record (done, this file) and a final "remove old
residue for real" sweep (done — checked, no `wb-border`/dead `data-theme` references anywhere
in `src/`, confirmed clean). SUOC Platform Registry entry — not yet checked whether this counts
as a new capability build; flagged in the mission doc, not decided here.

No production merge performed by this mission — everything above lives on
`claude/endeavour-27-mission-brief` only. Promoting to `main` (and therefore to the production
Vercel build) is a separate, explicit step the Captain asked to be done last, once this record
existed.
