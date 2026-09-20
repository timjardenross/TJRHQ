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
- **Source:** Captain-authored mission brief ("TJR HQ — Endeavour 27") plus 3 reference
  mockup images, reviewed and converted into this document by the Mission 7 session, per
  Captain's explicit direction to fully scope it before handoff, sequenced to start only
  after Mission 7 item 1 closes (both missions touch overlapping shared chrome —
  `WorkbenchShell.tsx`, `globals.css` — and this repo has a documented concurrent-session
  corruption incident; see AGENTS.md). The 3 mockup images, in the order they were supplied:
  1. **Image 1 (4-panel, desktop):** LifeOS Hub / Ready Room / Human Systems / Briefs —
     the primary reference set §1.1 below was originally built from.
  2. **Image 2 (10-panel, responsive grid + style guide):** the same 4 surfaces at desktop,
     iPad landscape, iPad portrait, and iPhone widths, plus a "Key Design Elements" panel
     giving concrete typography and component specs. See §1.3/§1.4 below.
  3. **Image 3 (7-panel, "Interface Concepts — Like-for-like redesigns"):** direct visual
     redesign concepts for specific existing real workbenches — Emergency Alerts, Shopping
     List, Technical OSINT, Health OSINT, a second Briefs treatment, Captain's Chair, plus an
     iPhone Hub view — with a footer legend giving named hex values. See §1.5 below. Two
     genuine discrepancies against Image 1/the text brief surfaced here and are flagged, not
     silently resolved, in §1.6.

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

**Palette — superseded by Image 3's named footer legend.** Image 1 was colour-picked from a
flattened image (approximate, never reliable); Image 3's footer gives 4 explicitly named
hex values, which are authoritative over any colour-picked estimate and now replace it as
the starting point for token values (still not final — re-verify against contrast math
per §2 before locking anything):
- **Primary Navy / Command — `#0B1E2E`.** The dark Command/Focus base. Close to, but not
  identical to, the existing `midnight` theme's `--wb-bg: #111820` — near enough that reusing/
  adjusting `midnight` as the Command/Focus base is still the right starting hypothesis, but
  confirm the delta is deliberate (a genuinely darker navy) rather than colour-picking noise
  before treating `#0B1E2E` as gospel.
- **Surface Slate — `#142B3D`.** A second, slightly lighter dark tone — most likely the card/
  panel surface sitting on top of the Primary Navy background (standard bg/surface pairing),
  not a competing background. Confirm against the mockups' actual layering before assuming.
- **Accent TJR Blue — `#3B82F6`.** A blue accent distinct from the gold/champagne accent
  Image 1 showed — Image 1's mockups read as gold-accented (buttons, active nav pill), so
  this blue is either a second accent (interactive/link colour, distinct from the
  celebratory/brand gold) or specific to the surfaces shown in Images 2/3. Don't assume it
  replaces gold — verify which elements use which accent before implementation.
- **Sand Warm Accent — `#D6B88C`.** Matches the "warm navy+sand heritage" language in §1's
  Design North Star and is close in spirit to the existing `--wb-gold: #C9A84C` token
  (already defined, theme-invariant, currently underused) — likely the same accent family,
  not a new one; confirm whether this literally replaces `--wb-gold` or sits alongside it.
- Status colours in the Hub tiles: green (capacity/healthy), amber-gold (focus/attention),
  blue (in-progress/interactive), neutral grey (wellbeing/steady) — broadly consistent with
  existing `state-ok/warn/info` semantics, not a new vocabulary. No named hex given for these
  in Image 3's legend — still colour-picked estimates, still needs real values chosen via the
  contrast-math process in §2, not lifted from the image.
- Read surface: warm cream, close to the existing `sanctuary` theme's `--wb-bg: #F4F0E8` or
  `archive`'s `#F5F1EA` — no named hex given for this either; still an estimate, worth
  checking reuse before inventing new hex.

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

### 1.2 Mobile navigation — replace the current 3-tab bar with Image 2's 4-item nav, and
    remove a real duplication found while verifying it

The original text brief and Image 1 didn't specify phone navigation; Image 2's iPhone panels
show a **fixed 4-item bottom nav: Hub / Ready / Ask / More**. Verifying this against the
actual current mobile nav (`components/MobileCommandBar.tsx`, read in full this session)
confirms the current bar is stale and should be replaced outright, not preserved —
**Captain's explicit direction: update it to the new world and remove the duplication it
currently has**, per the following concrete findings:

- **Current state:** `MobileCommandBar` is a **3-tab bar: Home (⌂ /hub), Capture (＋
  /capture-workbench), Readiness (✚ /physical-readiness)**. Its own doc comment states
  plainly: *"This is the ONLY nav rendered on mobile/tablet... a page not listed here is
  unreachable below 1280px, full stop."* — confirmed by its `xl:hidden` gating (same
  threshold `Sidebar.tsx` uses to appear), and it's unconditionally mounted inside
  `WorkbenchShell` (~20 workbenches) as well as `(app)` pages, so it really is the single
  mobile nav surface today.
- **The duplication, confirmed by reading `QuickCapture.tsx`:** a global floating capture
  button is **already mounted on every single page** that mounts `MobileCommandBar` (both are
  siblings inside `WorkbenchShell`, and both are also on `/hub` directly) — "Mounted once
  inside WorkbenchShell (every workbench) and once on the hub, so a capture is always at most
  one click away" per its own doc comment. So today's mobile Captain has **two separate paths
  to the same capture action**: the bottom bar's "Capture" tab (→ `/capture-workbench`) and
  the always-present floating QuickCapture button (→ an inline modal, same underlying
  `captureItem()` pipeline). This is exactly the kind of stale duplication to remove: drop the
  dedicated "Capture" tab from the bottom bar (QuickCapture already covers it, unconditionally,
  on every screen) rather than carrying two capture entry points into the new nav.
- **Net redesign:** replace the 3-tab bar's item set with the mockup's **Hub / Ready / Ask /
  More**, dropping "Capture" as a duplicate (per above) and folding **Physical Readiness**
  into "More" rather than losing it — `WorkbenchShell`'s own header logo already links every
  workbench page to `/workbenches` (the full directory) below `xl`, so Physical Readiness
  doesn't strand even before "More" is built, but "More" should still surface it directly
  (one tap, not two) since it was a deliberately-kept primary-nav item before this redesign,
  per the current bar's own doc comment.
- Resolve what "Ask" links to (likely Number One / the advisory surface — cross-check against
  `NumberOne.tsx`, also unconditionally mounted in `WorkbenchShell` today, before assuming it
  needs a brand-new destination) as part of Stream B2, not left undefined.
- Also fix in the same pass: the current bar's colours (`bg-white/95`,
  `text-[#243b7a]`/`text-[#61718c]`) are **hardcoded, not theme-aware** (`wb-*` tokens) —
  pre-existing debt, unrelated to the tab-set change but worth fixing in the same touch since
  the component is being rewritten anyway.
- **The Sidebar IA question (§3.5, 5 vs. 9 items)** and this mobile nav redesign are two
  different information architectures for two breakpoints, both drawn from the same mockup
  set — confirm they're meant to coexist (desktop sidebar expands to 9, phone collapses to
  Hub/Ready/Ask/More) at the same Stream A decision point, rather than drafted independently.

### 1.3 Typography & component specs from Image 2's "Key Design Elements" panel

Image 2 includes a style-guide panel giving concrete type and component rules, more specific
than the text brief's general "distinctive, calm, premium" language:
- **Type scale (named, not measured in px from the image):** H1 Page Title, H2 Section Title,
  Body/Secondary text, Status Label — a 4-level hierarchy. Exact sizes/weights/line-heights
  need measuring against the actual mockup asset (or a fresh Captain-supplied spec) at
  implementation time; this doc records the *names* of the levels, not fabricated px values.
- **Component styles named:** Primary Button, Secondary Button, and 3 capacity-badge variants
  (Green/Amber/Red) — i.e. the same 3-state semantic pattern already in the codebase as
  `state-ok/warn/crit` (§2, Pre-flight), not a new vocabulary. Badge *styling* (pill shape,
  border treatment, icon-or-not) should be taken from the mockup image directly at build time,
  not guessed from this text description.
- Treat this panel as a starting style guide, not a finished spec — Stream A (Foundation)
  should formalise it into real Tailwind tokens/component variants, cross-checked against the
  existing `Badge`/`Button` components in `components/ui/` (§3.4) rather than built fresh.

### 1.4 Responsive layout notes from Image 2's tablet/phone panels

Image 2 shows each of the 4 primary surfaces (Hub/Ready Room/Human Systems/Briefs) at 4
widths: desktop, iPad landscape, iPad portrait, iPhone. This directly informs Stream E
(Responsive hardening) target viewports — already listed there as "desktop/laptop/iPad
landscape/iPad portrait/iPhone," now confirmed to match the mockup set exactly rather than
being an assumed list. No new viewport classes needed; existing Stream E scope stands
verified, not expanded.

### 1.5 Additional reference surfaces from Image 3 ("Interface Concepts — Like-for-like
    redesigns")

Image 3's own footer explicitly labels its 7 panels "Interface Concepts (Like-for-like
redesigns)" — confirming these are meant as direct visual redesigns of *specific existing
real workbenches*, not new concept surfaces. All 5 named workbenches (of the 7 panels — the
other 2 are the Briefs re-treatment and the iPhone Hub view, covered separately below) were
re-verified directly against `lib/workbenches.ts`'s `LIVE_WORKBENCHES` list this session,
not assumed from the panel titles alone:
```
$ grep -iE "title:|href:" lcars-portal/src/lib/workbenches.ts
```
- **Emergency Alerts → `/emergency-alert-hub-workbench`.** Real, live entry in
  `LIVE_WORKBENCHES`. Note this is a *different* surface from `AlertPanel.tsx` (flagged
  dead/zero-importers in §3.2) — don't conflate the two; confirm which component actually
  renders `/emergency-alert-hub-workbench` at implementation time.
- **Shopping List → `/shopping-list-workbench`.** Real, live entry.
- **Technical OSINT → `/intelligence-workbench`** (listed in `LIVE_WORKBENCHES` as "Technical
  OSINT Workbench" — same page, current title already matches the mockup's shorthand).
  Real, live entry.
- **Health OSINT → `/health-osint`.** Real, live entry.
- **Captain's Chair → `/captains-chair-workbench`.** Real, live entry, referenced elsewhere in
  this repo including Mission 7's `NeedsYou.tsx` work and `captainsChairSynthesis.ts`. See
  the discrepancy flagged in §1.6 below before classifying its mode.
- **A second Briefs treatment** — see §1.6 below; does not match the first Briefs mockup
  (Image 1) already analysed in §1.1/§3.
- **An iPhone Hub view** — a second angle on the same Hub surface already covered by Image 2's
  iPhone panel; treat as reinforcing, not contradicting, §1.4's responsive notes unless a
  build-time comparison finds a real conflict.

These 6 additional named surfaces (Emergency Alerts, Shopping List, Technical OSINT, Health
OSINT, Captain's Chair, the second Briefs treatment) should be added to Stream B/C's
per-workbench build list as concrete reference targets beyond the original 4
(Hub/Ready Room/Human Systems/Briefs) — see Stream B note below.

**Important scope clarification (Captain, 2026-09-20): the mockups are illustrative samples,
not the full page list.** All 10 mocked-up surfaces across the 3 images (Hub, Ready Room,
Human Systems, Briefs x2, Emergency Alerts, Shopping List, Technical OSINT, Health OSINT,
Captain's Chair) are worked *examples* of the Command/Focus/Read treatment — the Captain
explicitly confirmed the look and feel is meant to apply **across every live workbench**, not
only the ones mocked up. This was already this doc's Stream C intent ("migrate remaining
workbenches by classification") but is now stated explicitly rather than left implicit. See
§1.7 for the full confirmed page list this mission covers.

### 1.6 Discrepancies found in Image 3 — flagged, not silently resolved

Two real conflicts surfaced comparing Image 3 against Image 1 and the text brief. Both need a
Captain decision before implementation locks either interpretation in:

1. **Captain's Chair — mode conflict.** Image 3 shows Captain's Chair with a **light/cream
   background**, matching the Read-mode surface treatment. But both the original text brief
   and this doc's own §1.1 classify Chair under **Command mode (dark)**, grouped with Hub.
   These are genuinely incompatible for one page — either the text brief/§1.1 classification
   is wrong and Chair is actually Read-mode (it does involve reading synthesis/summaries, per
   `captainsChairSynthesis.ts`, so a Read classification isn't implausible), or Image 3's
   mockup is an inconsistent draft. **Do not silently pick one** — surface this explicitly to
   the Captain at Stream A/B kickoff before building Chair's surface.
2. **Briefs — two different tab structures shown.** Image 1's Briefs mockup shows
   **Latest / Areas / Saved / Archive** tabs (already cross-referenced in §1.1 against the
   real `intelligence_briefs`/`captains_daily_briefs`-backed Briefs workbench). Image 3's
   second Briefs treatment shows a **different tab set: Domains / Timeline / Explore**. These
   don't obviously map onto each other 1:1 (Domains/Timeline/Explore reads like a different
   information architecture, not just a restyle of the same 4 tabs). **Do not assume Image 3
   supersedes Image 1** — both are Captain-supplied, so which is authoritative (or whether
   they're two options to choose between) needs an explicit Captain call before Stream B
   builds the Briefs reference surface, not a session-level guess either way.

### 1.7 Full scope confirmation — every live workbench, not just the mocked-up subset

Re-read directly from `lib/workbenches.ts`'s `LIVE_WORKBENCHES` this session (the same
canonical list §3.1's Discovery already inventoried) to state the full in-scope surface
explicitly, since the mockups only sampled roughly half of it:
```
$ grep -iE "title:|href:" lcars-portal/src/lib/workbenches.ts
```
20 entries, confirmed real and current as of 2026-09-20: LifeOS Hub (`/hub`), Capture
Workbench (`/capture-workbench`), Captain's Chair (`/captains-chair-workbench`), Mission
Workbench (`/mission-workbench`), Weekly Review (`/weekly-review`), Ready Room
(`/ready-room`), Technical OSINT Workbench (`/intelligence-workbench`), Health OSINT
Workbench (`/health-osint`), Emergency Alerts (`/emergency-alert-hub-workbench`), Human
Systems (`/human-systems-workbench`), Physical Readiness (`/physical-readiness`), Shopping
List (`/shopping-list-workbench`), Content Workbench (`/content-workbench`), Advisory
(`/advisory-workbench`), Briefs (`/briefs`), Knowledge Workbench (`/knowledge-workbench`),
Search (`/search`), Timeline (`/timeline`), HQ Status (`/agent-status-workbench`), HQ
Evolution (`/self-improvement-findings`), Engineering Handoffs (`/engineering-handoffs`).

**Of these, 9 are directly covered by a mockup** (Hub, Ready Room, Human Systems, Briefs,
Emergency Alerts, Shopping List, Technical OSINT Workbench, Health OSINT Workbench,
Captain's Chair) **and 11 have no mockup at all**: Capture Workbench, Mission Workbench,
Weekly Review, Physical Readiness, Content Workbench, Advisory, Knowledge Workbench, Search,
Timeline, HQ Status, HQ Evolution, Engineering Handoffs. Per the Captain's explicit
instruction, the unmocked 11 are **not out of scope** — they get the same Command/Focus/Read
treatment (per Stream A's shared tokens/`WorkbenchShell` mode prop), classified by the same
Command/Focus/Read/Utility rubric Stream C already defines, extrapolated from the mocked-up
examples rather than redesigned from scratch. Stream C's existing wording ("migrate remaining
workbenches by classification") already meant this; this section makes the full list and the
9-mocked/11-unmocked split explicit and checkable rather than leaving "remaining workbenches"
vague.

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
(Focus/Insight) → Briefs (Read — resolve the §1.6.2 tab-structure discrepancy with the
Captain before building, don't guess which tab set is authoritative). Reuse the real
canonical-data mappings in §1.1 rather than inventing new surface for existing data; flag
(don't silently build) the items marked "needs verification" in §1.1.

**Stream B2 — Additional like-for-like redesign surfaces (§1.5, Image 3).** Once Stream B's
4 primary surfaces are validated, extend the same reference-surface pattern to: Emergency
Alerts, Shopping List, Technical OSINT, Health OSINT, Captain's Chair (resolve the §1.6.1
Command-vs-Read mode discrepancy with the Captain first). Same discipline as Stream B:
identify the real route/component per surface before redesigning it, don't build against an
assumed file.

**Stream B3 — Mobile nav rewrite (§1.2, Captain-directed).** Replace `MobileCommandBar.tsx`'s
current 3-tab set (Home/Capture/Readiness) with Hub/Ready/Ask/More per the mockup: drop the
Capture tab (duplicates the always-mounted `QuickCapture` floating button — see §1.2), fold
Physical Readiness into "More" (don't strand it), confirm "Ask" routes to the advisory/Number
One surface, and switch the component's hardcoded colours to `wb-*` tokens in the same pass.
Not gated on Stream B's 4 primary surfaces — can land alongside Stream A once the token
architecture exists, since it's one component, not a per-page migration.

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
- Both §1.6 discrepancies (Captain's Chair Command-vs-Read mode; Briefs' two conflicting tab
  structures) resolved by explicit Captain decision before the affected surface is built —
  not silently picked by the implementing session.
- Stream B2's additional reference surfaces (Emergency Alerts, Shopping List, Technical
  OSINT, Health OSINT, Captain's Chair) redesigned against their real existing
  routes/components, not assumed ones.
- `MobileCommandBar` rewritten to Hub/Ready/Ask/More (Stream B3) with the Capture-tab/
  QuickCapture duplication removed, Physical Readiness reachable via "More", and hardcoded
  colours converted to `wb-*` tokens.
- Every one of the 20 `LIVE_WORKBENCHES` entries (§1.7) carries the Command/Focus/Read
  treatment, not only the 9 directly mocked up — the mocked surfaces are worked examples,
  the full roster is the acceptance bar.
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
