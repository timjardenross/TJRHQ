# LCARS Portal UI-Layer Debt — Session Kickoff Brief

**Written:** 2026-08-29, by Claude (Sonnet 5) following two council reviews of workbench structure.
**Purpose:** hand off the UI-layer findings a prior audit flagged, re-verified fresh today rather than trusted as-is. Two of the four original findings turned out **stale or wrong** — don't re-derive the old numbers, start from what's below.

## Context

Today's session consolidated backend duplication (notification senders, config loaders — done, committed, tested, CI-gated). The council explicitly parked UI-layer work for its own session: different skillset (frontend), different verification method (visual/manual, not a test suite), and the backend momentum shouldn't drag it into a rushed side-quest.

Before writing this brief, every finding below was re-checked against the current codebase — not copied from the original audit. Two were stale. Trust the numbers here, not the ones in older memory notes.

---

## Finding 1: Severity/status vocabulary sprawl — **still real, confirmed**

`stateToneClasses` (`src/lib/departments.ts:118`) is the canonical `ok/warn/crit/unknown` token set and is genuinely adopted — 15 files use it, real progress since it was introduced. But at least **6 more independent vocabularies** coexist untouched, doing the same job differently:

| Location | Vocabulary |
|---|---|
| `src/app/self-improvement-findings/page.tsx` | `info \| low \| medium \| high \| critical` |
| `src/app/emergency-alert-hub-workbench/page.tsx` | own `SEVERITY_LABELS`/`SEVERITY_BADGE` maps |
| `src/components/ProactiveSignals.tsx` | `Severity = critical \| high \| medium` |
| `src/lib/alerts.ts` | `AlertSeverity = critical \| high \| warning` (note: "warning" not "medium" — different word for the same tier) |
| `src/lib/hygieneRules.ts` | own `critical \| high \| medium` + a separate `SEVERITY_RANK` |
| `src/lib/intelligenceRisk.ts` | `RiskLevel = HIGH \| MEDIUM \| LOW \| ''` (uppercase, different casing convention entirely) |

Also worth checking while in this area: `src/lib/capture.ts` and `src/lib/types.ts` each independently define their own `ProcessingStatus` and `ReviewStatus` types with **different value sets** — that's not domain variety, that's the same concept duplicated with drift. Worth a specific look, not just folded into the severity work.

**Suggested first step:** pick the target taxonomy (`stateToneClasses`'s 4-tier `ok/warn/crit/unknown` is the existing canonical one — extend it rather than inventing a 5th), then migrate the 6 vocabularies above one at a time. This is the same "canonical exists, unenforced" shape as today's backend work — the pattern that worked today (migrate + CI gate) likely transfers, though a severity *taxonomy* gate would need to check for new bespoke type unions, not a grep signature like today's — worth designing that check before or alongside the migration, not after.

## Finding 2: API layer has no backend abstraction at all — **original framing was wrong, reframe entirely**

The old finding was "25/29 routes bypass the Command Centre backend." That's stale in a specific way: **there is no Command Centre backend to bypass.**

- Total API routes today: **90** (`route.ts` files under `src/app/api`) — the surface has roughly tripled since the old 29-route baseline.
- `src/lib/command-centre.ts` exists (273 lines, looks like exactly the central layer the old finding assumed) but **has zero importers anywhere in the codebase, including its own API routes.** It's dead code that was never wired in.
- **89 of 90 routes talk directly to Supabase.** The one exception (`api/advisory/loops/route.ts`) reads local files — not a bypass case, just a different kind of route.

This is worse than the original finding implied, but differently shaped: it's not "most routes skip the good layer," it's "the good layer was built once, never adopted, and everything grew up around it instead." Given 90 routes now exist directly coupled to Supabase, a lift-and-shift onto `command-centre.ts` is a much bigger job than it would have been at 29 routes — this needs a real scoping decision (retrofit vs. accept direct-Supabase as the actual pattern and formally retire `command-centre.ts`) before any migration work starts, not a mechanical "migrate them all."

**Suggested first step:** don't start migrating routes. First decide: is `command-centre.ts` worth reviving as the real abstraction layer, or is "routes talk to Supabase directly" simply what this platform's API layer actually is now and `command-centre.ts` should be deleted as dead code? That's a 30-minute architectural call, not a coding task, and it determines whether the other 89 routes are a problem at all.

## Finding 3: Health OSINT / Human Systems domain split — **unresolved, unchanged**

Both remain fully separate top-level workbenches with separate routes, APIs, and data domains:
- **Health OSINT** (`/health-osint`) — external clinical-trial/performance-research intelligence.
- **Human Systems** (`/human-systems-workbench`) — personal recovery/medical/readiness tracking. Recently had an internal VNext consolidation (its own tab split was removed per the page's own comment), but that was internal tidying, not a cross-workbench boundary decision.

No comments, ADRs, or code found addressing whether these two should have a clearer boundary or whether the split is intentional and just needs documenting as such. This is a genuine open question, not obviously a bug — worth a short "is this actually two domains" decision before any restructuring.

## Finding 4: Nav unreachability — **mostly stale, the 59% figure does not hold**

This was the biggest surprise. Re-checked properly (traced actual `Link`/`href` references, not just the primary sidebar list):

- The literal top-level sidebar nav (`src/lib/nav.ts`) is sparse — only 2-3 direct links.
- But `WorkbenchShell.tsx`'s persistent workbench switcher renders all 11 entries from `src/lib/workbenches.ts` (`LIVE_WORKBENCHES`) on every page — so those 11 workbenches are genuinely one click away from anywhere in the app, even though they're not in the literal `nav.ts` list. The old 59%-unreachable stat likely counted against `nav.ts` alone and missed this switcher.
- Of 38 real page routes (excluding the legacy `(app)/` directory and API routes), the **actual confirmed orphans — zero incoming links anywhere in the codebase** — are just two:
  - `src/app/comms-workbench/page.tsx`
  - `src/app/self-improvement-findings/page.tsx`
- `src/app/investigate/page.tsx` is effectively orphaned too: it's only reachable through `HomeScreen.tsx`, which is exclusively mounted inside the legacy `(app)/captains-chair/page.tsx` — not the live app.
- A few others (`mission-workbench`, `knowledge-workbench`, `health-osint-curation`) are reachable but only through secondary in-app links (buried in another workbench's UI, not a nav tile) — worth a look for discoverability, but not orphaned.
- `/home` is a deliberate retired redirect stub, not a bug.

**Real orphan count: ~3 of 38 pages (~8%), not 59%.** Still worth fixing — `comms-workbench` and `self-improvement-findings` genuinely have no path in from the live app — but this is a small, bounded fix (add 2-3 tiles/links), not the large nav-IA rework the original number implied.

---

## Suggested order for the next session

1. **Nav orphans (Finding 4)** — smallest, cleanest win. Add `comms-workbench` and `self-improvement-findings` to `LIVE_WORKBENCHES` (or wherever makes sense), fix `investigate`'s reachability. Bounded, single-session.
2. **Command Centre decision (Finding 2)** — not code, a scoping call. Decide revive-vs-retire before anything else touches the API layer. Do this early since it affects whether Finding 2 is even a real task.
3. **Severity vocabulary consolidation (Finding 1)** — biggest real chunk of work, same shape as today's backend consolidation (canonical exists, migrate + gate). Good candidate for its own multi-commit session once the target taxonomy is picked.
4. **Health OSINT / Human Systems (Finding 3)** — a decision, not urgent. Fold into whichever session touches either workbench next, doesn't need to be dedicated time on its own.

## Files to start from

`src/lib/nav.ts`, `src/lib/workbenches.ts`, `src/components/ui/WorkbenchShell.tsx`, `src/lib/departments.ts` (canonical `stateToneClasses`), `src/lib/alerts.ts`, `src/lib/hygieneRules.ts`, `src/lib/intelligenceRisk.ts`, `src/app/self-improvement-findings/page.tsx`, `src/app/emergency-alert-hub-workbench/page.tsx`, `src/lib/command-centre.ts`, `src/lib/capture.ts` + `src/lib/types.ts` (duplicate `ProcessingStatus`/`ReviewStatus`).

---

## 2026-08-29 session update: Finding 4 done, full 12-workbench design audit run

### Finding 4 (nav orphans) — done, and corrected further

Before fixing, re-verified once more and found the doc's own "3 orphans" was still one correction too shallow:

- **`comms-workbench`** was NOT an accidental orphan — its replacement, `content-workbench/page.tsx`, has its own header comment stating it was deliberately delisted 2026-08 in favor of Content Workbench (a confirmed superset). Deleted the page/`_components`/`QUICK-START.md` outright (zero real importers of its components; its shared API routes stay, used directly by Content Workbench) rather than re-adding it to nav.
- **`investigate`** was NOT an accidental orphan either — its own header comment cites MSN-0353 and documents it as deliberately zero-nav, contextual-entry-only (same pattern as `/decide`, `/ask`, `/recommended`). Left alone.
- **`self-improvement-findings`** was the one real bug — added to `LIVE_WORKBENCHES`.

Also made `workbenches.ts`'s `LIVE_WORKBENCHES` array an enforced canonical master list: strengthened its header comment, added `docs/LIVE-WORKBENCHES.md` as a synced human-readable mirror, and wired `tools/check_workbench_registry.py` into CI (`workbench-registry-gate`) so a new route landing without a decision on it fails the build instead of waiting for the next audit to rediscover it.

### Full design-audit sweep, all 12 live workbenches

Ran the project's `design-audit` skill (`.claude/skills/design-audit/`) across every workbench in `LIVE_WORKBENCHES`, then fixed the bounded, unambiguous findings directly. Typecheck + lint clean after all fixes.

**Fixed this session:**
- `self-improvement-findings/page.tsx` — **real functional bug**: `riskClass`/`RiskPill` only recognize the RED/AMBER/GREEN/HIGH/MEDIUM/LOW vocabulary; this page passed its own independent severity (`info/low/medium/high/critical`) and decision (`approved/rejected/more_evidence`) unions into them, so severity and decision badges silently rendered as the same neutral grey — the one signal a findings-triage UI exists to show was flattened to nothing. Remapped onto `Badge`'s status vocabulary directly (`SEVERITY_STATUS`/`DECISION_STATUS` maps); exported `STATUS_CLASSES` from `Badge.tsx` for the one block-level (non-pill) usage. Also fixed non-responsive `grid-cols-4`/`grid-cols-3` (no breakpoint) and one `transition-all`.
- `health-osint/page.tsx:172` — contrast failure: `text-wb-ink2/80` computed to ~4.13:1 on body text (below 4.5:1 AA); full-strength `text-wb-ink2` passes at ~7.5:1 per the token's own contrast-matrix comment. Dropped the opacity modifier.
- `human-systems-workbench/_components/CollapsibleSection.tsx` — the `<summary>` toggle (keyboard-focusable, controls every section) had zero `:focus-visible` styling, unlike every other interactive element in the app. Added the standard focus-ring classes. Also fixed `RecoveryView.tsx`'s Capacity Balance bar: `transition-all` → explicit `transition-[margin,width,background-color]` (it genuinely animates all three, so `transition-all` wasn't wrong, just imprecise per the gate).
- `ready-room/_components/TaskRow.tsx:128` — the follow-through mute/unmute toggle's entire visible content was a bare emoji (🔔/🔕) with only a `title` attribute, no accessible name for screen readers. Added `aria-label` + focus-ring.
- `advisory-workbench/_components/ProactiveBanner.tsx` — Dismiss button missing `:focus-visible`, inconsistent with every other button in the same workbench. Added the standard focus-ring.
- `captains-chair-workbench/notebook/page.tsx` — capture-error text (×2 locations) had no reserved space, so the Capture button shifted position when an error appeared/disappeared; wrapped in a fixed `min-h-[1lh]` slot. Also added `aria-expanded` to the note-card collapse toggle (no ARIA equivalent for the ▲/▼ visual state).
- `intelligence-workbench/brief/[id]/page.tsx` — signal-card button combined two simultaneous hover effects (`hover:-translate-y-px` + `hover:border-wb-sage-deep`); dropped the translate, kept the color change (`transition-colors`).
- `briefs/page.tsx` — filter buttons had no `whitespace-nowrap` (would wrap to two lines with a count suffix at narrow widths) and no `:focus-visible`/`aria-pressed`; brief-card `Link`s also had no `:focus-visible`. Fixed all three.
- `agent-status-workbench/page.tsx` — truncated `lastAction` cell had no way to read the full value; added `title` attribute.
- `emergency-alert-hub-workbench/page.tsx` — Close button had no `:focus-visible` and used a bare `✕` glyph redundant with its own "Close" text; added focus-ring, dropped the glyph.

**Investigated, NOT fixed — false positive, corrected during this pass:**
- `intelligence-workbench`'s `bg-wb-crit-on`/`bg-wb-warn-on` usage as button fills was flagged by the audit as a possible "`-on` token misused as fill" bug. Checked `tailwind.config.ts`'s own comment (line ~74-83): the `wb-*-on` variants are **explicitly documented as the AA-safe white-on-fill button variant** — plain `wb-crit`/`wb-warn` are the ones that fail AA as a solid button background. This is the opposite of `departments.ts`'s `state-*` family, where `-on` is a darkened *text* color for tinted backgrounds, not a fill. Initially "fixed" this the wrong way (swapped to plain `wb-crit`), caught it against the actual token source before committing, and reverted. **Two token families, two different and mutually incompatible `-on` conventions — this is real, deeper severity-vocab sprawl than Finding 1 originally scoped** (the sprawl isn't only in TS type unions, it's baked into the Tailwind token layer itself). Left both usages as-is; don't "fix" one against the other's convention without designing the unification first.

**Not fixed — logged as backlog, needs a decision or a dedicated pass, not a quick patch:**
- **`emergency-alert-hub-workbench/page.tsx`** mixes both token families in one file (`wb-crit`/`wb-crit-on` for the loading-error banner, `state-crit`/`state-warn-on` for the stat tiles) — both render, to two different reds. Concrete proof-point for Finding 1's scope, not a new finding.
- **7th severity vocabulary found**: `advisory-workbench/_components/LoopsView.tsx`'s `OUTCOME_OPTS` (`success | partial | failure`) — add to Finding 1's migration list (now 7 vocabularies + the `ProcessingStatus`/`ReviewStatus` duplication, not 6).
- **`content-workbench/_components/ContentBoard.tsx:660-677`** — "Discard this item" opens a confirmation dialog, but the item's own copy says it's reversible ("removed from the board, not deleted"). Named anti-pattern: confirm dialogs belong on irreversible actions; this should be optimistic-with-Undo instead. Real UX redesign, not a one-line fix.
- **No defined type scale** — `text-[11px]`/`[12.5px]`/`[13.5px]`/etc. arbitrary bracket sizes are pervasive and consistent across the whole app (reads as a real, undocumented scale, not one-off improvisation), but nothing stops silent drift. Worth promoting to named `text-*` tokens if/when the token layer gets touched for the severity-vocab work.
- Minor taste calls not acted on: `content-workbench/_components/CaptureBox.tsx:63`'s unexplained 3-stop gradient bar; a handful of bare-Unicode-glyph buttons (`✓`/`✗`/`?` on self-improvement-findings' decision buttons) that already pair the glyph with a text label, so not urgent.

No critical/major findings at all in: `weekly-review`, `agent-status-workbench` (0/0), `content-workbench` (0 crit), `advisory-workbench` (0 crit after the one major fixed). Cleanest workbenches in the sweep.

---

## 2026-08-29, same-session follow-up: backlog items 1-2, 5-6 resolved; 3 given a bounded fix; 4 deliberately declined

- **1. Emergency Alert Hub token split** — resolved. The file already used `state-*` for its stat tiles; migrated the loading-error banner's `wb-crit`/`wb-crit-on` to `state-crit`/`state-crit-on` to match (identical usage shape — tinted `/10` bg + `-on` text — so a safe drop-in, not a cross-family redesign). One file now internally consistent; the two-family question app-wide is still open.
- **2. 7th severity vocabulary (`OUTCOME_OPTS`)** — resolved. Migrated `advisory-workbench/_components/LoopsView.tsx` off its own hardcoded style strings onto `stateToneClasses` (success→ok, partial→warn, failure→crit). Note for next migration: `stateToneClasses`'s return value can't be interpolated into a `hover:` prefix at runtime — Tailwind's content scanner needs the literal class string in source, so the hover backgrounds are a small static lookup (`OUTCOME_HOVER_BG`) instead. Same constraint will bite any future migration that tries to compose `hover:${tone.bg}`.
- **3. Confirm-dialog-for-reversible-action (`ContentBoard.tsx`)** — given a bounded fix, not the full optimistic-refetch pattern the audit suggested. No un-archive trigger exists on `/api/comms/[id]/advance` (its `TRANSITIONS` table has no reverse edge out of `archived`), so true post-commit undo isn't available without a backend change. Implemented instead: clicking "Discard" starts a 5s grace-window timer before the API call actually fires; "Undo" cancels the pending timer. Functionally equivalent to undo (nothing is committed until the window elapses) without adding a new state-machine capability.
- **4. Undefined type scale — declined, not attempted.** Checked before touching anything: 101 files use Tailwind's *default* `text-xs`/`sm`/`base`/`lg`/`xl`. Any `fontSize` scale added under `theme.extend` using those same key names would silently override every one of those 101 files' rendered size — a large, untested blast radius from what was meant to be an additive change. Only sampled ~2 workbenches' worth of arbitrary bracket values during the audit, nowhere near a real inventory. Needs a full-codebase font-size audit before any scale is defined, named with non-colliding keys — not attempted this session.
- **5. Content Workbench gradient bar** — fixed, dropped (`CaptureBox.tsx`'s unexplained 3-stop gradient removed rather than wired to a real signal, per the audit's own suggested fix).
- **6. Bare-glyph decision buttons (`self-improvement-findings/page.tsx`)** — fixed, dropped the `✓`/`?`/`✗` glyphs, kept the text labels (already color-coded via `bg-wb-ok`/`warn`/`crit`).

Items 7 (Health OSINT / Human Systems domain split) and 8 (Command Centre revive-vs-retire) intentionally left for later — Captain wants to look at those separately.

Typecheck + lint clean after all of the above.
