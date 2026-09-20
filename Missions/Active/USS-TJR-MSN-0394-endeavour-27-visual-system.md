# USS-TJR-MSN-0394 — TJR HQ Endeavour 27 Visual System, Responsive Experience & Portal UI Convergence

## Mission Header

- **Mission ID:** USS-TJR-MSN-0394 (minted via `python3 tools/mint_id.py MSN`, 2026-09-20 —
  the registry's stored counter had drifted to 390 against a true repo max of 393; the tool
  self-corrected before minting, so this number is confirmed current as of mint time, not
  guessed)
- **Priority:** P1 — visual/UX transformation, not backend-critical, but large in scope and
  explicitly Captain-authorised (this mission doc, plus the source mockups, constitute the
  Visual Design Officer sign-off that Mission 7 (USS-TJR-MSN-0393) repeatedly deferred to —
  see its §5 item 14/§3.12 and item 15)
- **Source:** Captain-authored mission brief ("TJR HQ — Endeavour 27") plus 4 reference
  mockups (LifeOS Hub/Ready Room/Human Systems/Briefs), reviewed and converted into this
  document by the Mission 7 session, per Captain's explicit direction to fully scope it
  before handoff, sequenced to start only after Mission 7 item 1 closes (both missions touch
  overlapping shared chrome — `WorkbenchShell.tsx`, `globals.css` — and this repo has a
  documented concurrent-session corruption incident; see AGENTS.md)

## Pre-flight

1. **Existing-entry check.** This mission doesn't add a row to an existing list/registry in
   the AGENTS.md sense (not a source, ADR, scheduler, or specialist entry) — it's a new
   mission doc. The one registry-like check that matters here is the mission ID itself:
   ```
   $ python3 tools/mint_id.py MSN
   id_registry: counter drift detected for MSN -- stored=390 true_max=393 (source=repo scan,
   MSN-0393). Auto-bumping counter before minting.
   USS-TJR-MSN-0394
   ```
   Confirmed free and now reserved.

2. **Premise verification.** Every claim below was checked against the real repo state
   2026-09-20, not assumed from the source brief or the mockups:
   - *Claimed:* a 5-theme selector exists and would need retiring.
     *Verified:* `lcars-portal/src/app/globals.css` — 5 `:root[data-theme='X']` blocks
     (archive/command/midnight/horizon/sanctuary), selected via `src/lib/theme.ts`'s
     `useTheme()`, `data-theme` attribute set pre-hydration by an inline script in
     `layout.tsx`. Real, live, fully shipped (Adaptive Themes mission, 2026-09-05).
   - *Claimed:* status colours are theme-invariant and this constrains the new palette.
     *Verified:* `globals.css` lines 103-115 — `--wb-ok/--wb-warn/--wb-crit` and their
     `-on` variants are defined exactly once, on bare `:root`, never overridden per theme.
     Separately, `tailwind.config.ts`'s `state.*` family (a *different* token set, MSN-0315
     Phase 1A) is also flat hex, not CSS vars. Both confirmed theme-invariant by inspection,
     not assumption. The specific contrast-math constraint (a flat colour cannot pass 4.5:1
     against both a near-white and a near-black surface at once) is proven in
     `lib/departments.ts`'s `stateToneClasses()` doc comment, added 2026-09-20 this session —
     read it before designing new semantic colours.
   - *Claimed:* the legacy LCARS system is mostly retired already.
     *Verified:* every route under `(app)/` is 5-62 lines (checked all 20 remaining
     directories directly) — all confirmed stubs/redirects except `delivery` (41 lines,
     genuinely live, `MSN-EDO-002`) and `stage-progression` (28 lines, a deliberate
     "retired — prototype data" notice page, not real). So the LCARS-legacy migration
     surface is much smaller than the source brief implied: effectively 1 real page
     (`delivery`) plus whichever shared components it depends on.
   - *Claimed (implicit in "audit LCARSPanel usage"):* `LCARSPanel` is used in ~17 files.
     *Verified false* — first-pass grep matched 17 files, but 3 were comment-only mentions
     (`knowledge-workbench/operating-model/page.tsx`, `human-systems-workbench/weight/
     page.tsx`, `app/search/page.tsx` — all this session's own new pages, explaining in
     their own header comments that they *don't* use it). Real importers, re-checked with
     `grep -rl "<LCARSPanel\|import.*LCARSPanel"`: 8 files. Of those, 4 components
     (`AlertPanel.tsx`, `HumanSystemsPanel.tsx`, `LearningStatusPanel.tsx`,
     `WellnessInsightPanel.tsx`) have **zero importers anywhere in the app** — dead code,
     confirmed by a second grep for each name. Real remaining LCARS-legacy surface:
     `(app)/delivery/page.tsx`, `(app)/stage-progression/page.tsx`, `DeliveryPanel.tsx`
     (delivery's own panel), `LCARSPanel.tsx` itself. This is a **much smaller** migration
     job than "audit 17 files" suggested — say so plainly rather than re-deriving it.
   - *Claimed:* the sidebar in the mockups matches the current one.
     *Verified false* — current `components/ui/Sidebar.tsx` has 5 primary items (Home,
     Workbenches, Library, Missions, Alerts) + Settings + Help, deliberately minimal per its
     own header comment ("Missions/Alerts... lower priority... not places captains land
     often"). The mockups show 9 top-level items (LifeOS Hub, Ready Room, Chair, Human
     Systems, Briefs, Advisory/Number One, Workbenches, Knowledge, Settings) — a real
     information-architecture change, not just a reskin. Flagged as a Stream A decision
     below, not assumed settled by the mockup alone.
   - *Claimed (implicit):* department/LCARS colour usage is contained.
     *Verified:* 12 files still use department colour classes
     (`text-command`/`bg-engineering`/etc. and friends) outside `WorkbenchShell`-shelled
     pages; 28 files use `lcars-*` prefixed classes app-wide. Full paths below in Discovery.
   - *Claimed:* breakpoint conventions need to be invented.
     *Verified false* — `sm:` is already used 119 times, `md:` 40, `lg:` 26, `xl:` 30
     (the Sidebar/desktop-chrome threshold), `2xl:` never. A working mobile-first convention
     already exists; extend it, don't replace it.

3. **Explicitly not in scope.** See dedicated section below.

## Explicitly Not In Scope

- **Mission 7's own remaining item (the per-workbench PURPOSE/ENTRY/EXIT template
  write-up)** — a different, code-reading-and-interaction-testing exercise, not a visual
  redesign. Runs to completion first; this mission starts only once it's done (see Mission
  Header — same shared-file risk, plus running both at once would make Mission 7's findings
  about current-state UI obsolete mid-review).
- **Any canonical logic**: Number One's deterministic routing, cross-turn context, Capture,
  Remember, Attention State, Follow-Through, capacity model, evidence/adaptation,
  notifications, deep-link contracts, canonical completion/defer semantics. Presentation
  only, per the source brief's own explicit boundary (§ "MISSION INTENT" in the original).
  If the redesign surfaces a real functional defect underneath, record it — fix only if the
  new UI cannot function correctly without the fix, and it's small.
- **The `(app)` group's already-completed retirements** (medical, captains-log,
  automation-centre, intelligence, engineering, operations) — Mission 7 already converted
  these to honest stubs; this mission doesn't need to touch them again.
- **`operating-model`'s doctrine content** (the Domains/Principles/Schedule text itself,
  reviewed and reaffirmed by Mission 7 Phase 13) — this mission may reshell the page, not
  rewrite what it says.
- **New backend capability of any kind** — if a mockup element (e.g. Briefs' coloured status
  dots, Human Systems' "Helpful N/10 times" stats) doesn't map to a real canonical field,
  that's a Discovery finding to report, not something to build a new table/endpoint for.

## 1. Design North Star (condensed from the source brief + mockup analysis)

Not a literal LCARS recreation, not a generic enterprise dashboard, not a TJR Mind & Body
clone, not a differently-themed-Workbench collection. Distinctive, futuristic, calm,
intelligent, human, premium, functional, restrained. "Starfleet philosophy, not Star Trek
cosplay." Brand relationship: TJR Mind & Body contributes calm/humanity/warmth/navy+sand
heritage; Endeavour contributes command/structure/discipline/resilience. Together: **calm
command**. Design test: *"Command where it helps. Calm where it matters. Always TJR HQ."*

### 1.1 What the mockups actually show (verified against the images, not re-described from
    the text brief alone — this is new information the text brief didn't fully specify)

**Important refinement to the Command/Focus/Read model:** in the mockups, Command (Hub) and
Focus (Ready Room, Human Systems) are visually near-identical — same dark navy shell, same
gold/champagne accents, same card treatment. The real difference between them is
**information density and hierarchy**, not a colour-identity shift:
- **Command (Hub):** a 4-tile status grid (Capacity/Focus/In Progress/Wellbeing) + 3 peer
  cards (Where You Left Off / Today / Quick Access) — scannable, multi-item, orientation-
  first.
- **Focus (Ready Room):** ONE dominant task card taking most of the layout, a "Feeling
  stuck?" support panel, a lightweight Context panel, Pick Up Later — single-item depth, not
  a grid of equals.
- **Read (Briefs) is the only mode that visually shifts surface lightness** — the reading
  pane genuinely switches to a warm cream/off-white background while the header/sidebar
  chrome stays dark navy. This is the "HQ Command environment ↓ Intelligence document"
  transition the text brief's §11 described, now confirmed as a real light/dark surface
  swap, not just "calmer" within the same dark shell.

This matters for implementation: **Command and Focus can likely share one dark `Surface`
variant differentiated by a density/layout prop**, while **Read genuinely needs its own
light surface variant** — closer to 2 real surface treatments plus a density axis than 3
fully independent visual systems. Verify this reading against the mockups again before
locking the token architecture; it's my read of 4 static images, not confirmed with the
Captain sentence-by-sentence.

**Palette observed in the mockups** (colour-picked from the images, treat as a starting
point for real token values, not final hex — no tool here can extract exact hex from a
flattened image reliably):
- Deep navy/midnight background, close to the existing `midnight` theme's `--wb-bg:
  #111820` — worth checking whether the existing `midnight` theme is already close enough
  to reuse as the Command/Focus base rather than inventing a new dark from scratch.
- Gold/champagne accent (buttons, active nav pill, header rule) — matches the source brief's
  §4 "WARM IDENTITY" family and is close in spirit to the existing `--wb-gold: #C9A84C`
  token (already defined, already theme-invariant, currently underused).
- Status colours in the tiles: green (capacity/healthy), amber-gold (focus/attention), blue
  (in-progress/interactive), neutral grey (wellbeing/steady) — broadly consistent with
  existing `state-ok/warn/info` semantics, not a new vocabulary.
- Read surface: warm cream, close to the existing `sanctuary` theme's `--wb-bg: #F4F0E8` or
  `archive`'s `#F5F1EA` — again, worth checking reuse before inventing new hex.

**Persistent chrome elements visible in every panel** (cross-reference these against real
code before building anything new):
- Personalised greeting ("Good evening, Captain." + a short affirmation line) — a
  `Good morning/afternoon/evening` daypart pattern **already exists**, in
  `src/components/home/HomeScreen.tsx:79` — currently dead code (the `/home` route it
  belonged to is retired, confirmed 25-line stub). Reusable, not to be reinvented, but
  currently orphaned.
- "TJ" avatar circle, search bar, settings icon in the header.
- Sidebar with 9 top-level items (see Pre-flight finding above — real IA change from
  today's 5-item Sidebar, needs a decision, not silent adoption).
- Sidebar footer motto: "DISCIPLINE / CLARITY / PROGRESS / FREEDOM" — new copy, not found
  anywhere in the current codebase; needs Captain confirmation as final copy, not assumed.

**Specific mockup elements that map to real, existing canonical data — reuse, don't
reinvent:**
- Hub's "Where You Left Off" card → `lib/personalTasks.ts`'s `pickUpItems()`, already used
  by Hub (Mission 6B) and Ready Room's `PickUpBanner`. Continue/Help me start/Not now map
  directly to existing actions.
- Ready Room's "Feeling stuck?" 4-option panel (Break it down / Help me start / This feels
  too much / Take a breath) → maps near 1:1 to Mission 4's existing canonical capabilities
  (decomposition, UNSTICK ME, overload support, regulation) already built into
  `DecomposeView.tsx`. Relabeling/reshelling, not new logic.
- Ready Room's "Pick Up Later" (Not now/snooze, Set a time) → `deferNotToday()` and
  `snoozed_until` already exist in `lib/personalTasks.ts`.
- Human Systems' 4-tile grid (Current Capacity/Execution Posture/Energy/Focus) → real
  `capacity_checkins`-derived fields already computed in
  `human-systems-workbench/trends/page.tsx` (`TREND_CAPACITY`, `TREND_NS`, etc.).
- Human Systems' "Capacity Trend — Last 14 days" bar chart → the existing `Sparkline`
  component and `TREND_GROUPS` structure in the same file — a real, already-built chart,
  needs restyling not rebuilding.
- Briefs' Latest/Areas/Saved/Archive tabs, article list + reading pane with Executive
  Summary/Key Points → the existing Briefs workbench (`intelligence_briefs`/
  `captains_daily_briefs`), already absorbed Intelligence's Briefs-shaped tabs in Mission 7.

**Specific mockup elements that need verification before building — real §31 (no fabricated
data) risk if skipped:**
- Human Systems' "What Helps" stats in the exact form "Helpful 8/10 times" / "Helpful 7/10
  times" — a `WhatHelpsMeCard` component and test file exist
  (`_components/WhatHelpsMeCard.tsx`/`.test.tsx`), so *something* real likely backs this —
  confirm the exact ratio-format stat is derivable from real data before shipping that exact
  presentation, don't assume the mockup's numbers are achievable as shown.
- "Watch For" common-early-signs list — check whether this maps to a real signal (patterns
  work already exists per `PatternsView.tsx`) or would need inventing.
- Hub/Ready Room's background photography (earth from space, ocean cliffs) — decorative
  stock imagery. Needs a real licensing/sourcing decision (a real asset pipeline, not a
  placeholder), or should be treated as illustrative-only and not implemented as literal
  photography — flag for a Captain call, don't silently source images.
- Ready Room's "Context" panel (Notes (3), Related items (2), Activity) — check whether
  personal_tasks or captured_items has real per-task note/relation counts before showing
  numbers; if not, this is new surface for existing-but-unsurfaced data, or genuinely new
  scope — verify which before implementing.

## 2. Colour Philosophy & Token Architecture

(Condensed from the source brief §3-§5 — full semantic-colour rules and the CANVAS/
SURFACES/BLUE/WARM/TEXT/BORDERS token family list are unchanged from the original brief;
not repeated here verbatim to avoid drift between two copies — see the original brief text,
attached/linked in Reporting below, for the exhaustive token-family list.)

**Decision locked in (Captain-confirmed, 2026-09-20): Endeavour 27 REPLACES the 5-theme
selector entirely.** Concretely:
- Retire all 5 `:root[data-theme='X']` blocks in `globals.css`.
- Retire `components/ui/ThemeSelector.tsx` (the "◐ Archive ▾" picker) — deleted, not
  repurposed, unless Stream work finds a real reason Command/Focus/Read needs its own
  switcher (unlikely; density should follow page/context, not a Captain-facing setting).
- One fixed dark Command/Focus identity + Read as a contextual light surface within the same
  system — not 5 independently-selectable whole-app palettes.
- **Before locking any new hex value:** re-run the WCAG relative-luminance contrast check
  (same method Mission 7 Phase 8 used, not eyeballed) against both the dark Command/Focus
  surface and the light Read surface for every text/status colour. Given only 2 real surface
  lightnesses now (not 5), this constraint is *easier* to satisfy than the old system, not
  harder — but still needs computing, not assuming.

## 3. Discovery — Full Findings (done directly, this session, no live browser needed for
   any of it)

### 3.1 Route inventory
21 `*-workbench`/top-level app routes (per `lib/workbenches.ts`'s `LIVE_WORKBENCHES`, same
canonical list Mission 7 used — re-read that file directly when this starts, don't hand-copy
in case it's drifted) + `/settings` (+7 sub-sections) + `/hub` + `/workbenches` (directory)
+ `/model-crew` + `/investigate` + the legacy `(app)` group (20 directories, all confirmed
stubs/redirects except `delivery`).

### 3.2 Legacy LCARS surface — smaller than the source brief assumed
- **Real, live LCARS-legacy page:** `(app)/delivery/page.tsx` (41 lines, `MSN-EDO-002`,
  genuinely live) + its `DeliveryPanel.tsx`.
- **Stub, not real:** `(app)/stage-progression/page.tsx` (28 lines, deliberate "retired —
  prototype data" notice).
- **Dead code, zero importers — safe to delete outright, not migrate:**
  `components/AlertPanel.tsx`, `components/HumanSystemsPanel.tsx`,
  `components/LearningStatusPanel.tsx`, `components/WellnessInsightPanel.tsx`. Confirm with
  a fresh `grep -rl "import.*{.*\bComponentName\b"` before deleting (repo state may have
  moved between this Discovery pass and implementation).
- `components/LCARSPanel.tsx` itself — retire once `delivery` is migrated (its last real
  consumer).

### 3.3 Department/LCARS colour usage outside the already-clean `wb-*` system
12 files still reference department colour classes (`text-command`, `bg-engineering`, etc.):
`ROSPanels.tsx`, `MobileAlertDrawer.tsx`, `DeliveryPanel.tsx`, `RecoveryConfidencePanel.tsx`,
`LearningStatusPanel.tsx` (dead, see above), `AlertPanel.tsx` (dead), `MissionCard.tsx`,
`HumanSystemsPanel.tsx` (dead), `ApprovalQueue.tsx`, `app/timeline/page.tsx`,
`(app)/delivery/page.tsx`. 28 files use `lcars-*` prefixed classes app-wide — full list not
enumerated here, re-run `grep -rlE "\b(bg|text|border)-lcars-" lcars-portal/src --include="*.tsx"`
at implementation time (this list will have moved by then).

### 3.4 Shared component inventory (`components/ui/`)
`Badge`, `Button`, `Card`, `DomainToggle`, `Input`, `KpiStat`, `Modal`, `Navigation`,
`NumberOne`, `Progress`, `QuickCapture`, `RiskPill`, `Sidebar`, `ThemeSelector` (retiring),
`WorkbenchCard`, `WorkbenchShell`. Most have Storybook stories already
(`*.stories.tsx`) — reuse that harness for visual regression during this mission rather than
inventing a new one.

### 3.5 Navigation — real gap vs. mockups
Current `Sidebar.tsx`: 5 primary items (deliberately minimal, per its own header comment).
Mockups show 9. This is a real information-architecture decision, not implied by "visual
refresh" — resolve explicitly in Stream A (Foundation) before Phase 2 reference surfaces are
built, since Hub/Ready Room/Human Systems/Briefs all render the sidebar and need to agree on
what's in it.

### 3.6 Responsive/breakpoint baseline
`sm:` 119 uses, `md:` 40, `lg:` 26, `xl:` 30 (current Sidebar/desktop-chrome threshold),
`2xl:` unused. A working mobile-first convention already exists — extend it, don't invent a
parallel one.

### 3.7 Reusable pre-existing pattern, currently orphaned
`components/home/HomeScreen.tsx`'s daypart greeting (`Good morning`/`Good afternoon`/
`Good evening`) — dead code since `/home`'s retirement, but exactly what the mockups' header
greeting needs. Reuse the logic, don't rewrite it from scratch.

## 4. Scope / Streams

**Stream A — Foundation.** Design tokens (colour, typography, spacing, radius, breakpoints —
extend the existing `sm/md/lg/xl` convention, don't replace it). Resolve the Command/Focus
shared-surface-variant question (§1.1). Resolve the 9-item vs. 5-item sidebar IA question
(§3.5) — Captain decision, not assumed from the mockups alone. Retire the 5-theme selector
(`globals.css` theme blocks + `ThemeSelector.tsx`). Accessibility baseline. Read
`stateToneClasses()`'s doc comment before finalising any status-colour values.

**Stream B — Reference surfaces**, one per mockup, in this order, each validated across all
5 target viewports before moving to the next: LifeOS Hub (Command) → Ready Room (Focus,
preserve the `?domain=unstick&task=` contract from Mission 7 Phase 12) → Human Systems
(Focus/Insight) → Briefs (Read). Reuse the real canonical-data mappings in §1.1 rather than
inventing new surface for existing data; flag (don't silently build) the items marked
"needs verification" in §1.1.

**Stream C — System convergence.** Migrate remaining workbenches by classification
(Command/Focus/Read/Utility). Extend `WorkbenchShell` with a density/mode prop rather than
forking 3 new Surface components — that shell was deliberately consolidated from 6 forks in
a prior mission (WORKBENCH-REVIEW.md H9/H12); re-forking it needs a strong stated reason.

**Stream D — Legacy migration.** `delivery`'s LCARS dependency (§3.2), the 12
department-colour files (§3.3), the 28 `lcars-*`-class files, the 4 dead Panel components
(delete, don't migrate, after a fresh importer check).

**Stream E — Responsive hardening.** Real rendered checks at all 5 viewport classes
(desktop/laptop/iPad landscape/iPad portrait/iPhone) — needs live-environment/browser
access, same wall Mission 7 hit repeatedly. If the implementing session doesn't have it,
say so and hand off rather than guessing — don't ship unverified responsive claims.

**Stream F — Accessibility + adversarial review.** WCAG contrast computed (not eyeballed,
same method as Mission 7 Phase 8), keyboard nav, screen reader, reduced motion, long
content/empty/error states, colourblind-safe status.

**Stream G — Cleanup + reporting.** Remove old theme/colour residue for real (not left dead
"just in case"), knowledge record, honest residual-debt register.

Per AGENTS.md's concurrent-session git safety: any stream run in parallel with another gets
its own isolated worktree (`git worktree add <path> -b <branch>`, session/mission-ID-suffixed
name) — don't edit the same shared checkout concurrently, this repo has a documented
corruption incident from exactly that.

## 5. Acceptance

- One coherent token architecture; no raw hex scattered through components.
- 5-theme selector fully retired — `ThemeSelector.tsx` and all 5 `globals.css` theme blocks
  gone, not left dead in place.
- Command/Focus/Read demonstrated clearly on Hub/Ready Room/Human Systems/Briefs, matching
  the mockups' actual hierarchy (density difference for Command/Focus, real surface-lightness
  swap for Read) — not a literal 3-colour-scheme reskin.
- Sidebar IA question (5 vs. 9 items) resolved as an explicit decision, documented, not
  silently inherited from the mockups.
- Status never depends on colour alone; `state-*`/`wb-ok` etc. contrast math respected
  (computed against the new 2-surface-lightness reality), not rediscovered from scratch.
- All 5 target viewports genuinely usable — verified with real rendered checks, not CSS
  review alone.
- Canonical Mission 1-7 behaviour intact, especially the `?domain=unstick&task=` contract
  and Mission 7 Phase 15's mobile header-overflow fix pattern.
- No fabricated data — every mockup element flagged "needs verification" in §1.1 resolved
  one way or the other before shipping, not silently implemented as shown.
- Full test suite green, production build succeeds.
- Residual debt honestly documented.

## 6. Reporting

Phase-by-phase build record inside this same doc, same discipline as Mission 7's own
(§3.x-numbered sections per phase, updated in place as work lands — not a separate status
doc). Knowledge record on completion at `knowledge/missions/` following this mission's own
naming convention once one exists. SUOC Platform Registry: check whether this counts as a
new capability build (likely yes, given the scale — a new design-system layer) before
deciding whether it needs an entry; don't skip that check by assuming "just a redesign."

Original source material (the full 45-section Captain-authored brief and the 4 reference
mockup images) should travel with whatever session starts this — request them from the
Captain/session history if not already attached; this document condenses and grounds them
against the real repo but does not reproduce every detail (e.g. the full CANVAS/SURFACES
token-family list from the original §4) to avoid two copies drifting apart.
