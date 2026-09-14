# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0384
- **Priority:** P3 — real, verified duplication; no external deadline
- **Source:** workbench UI review (this session, 2026-09-13) — third-ranked visible item after Radix (MSN-0381) and TanStack Table (MSN-0383).

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -n "tremor" lcars-portal/package.json
   → no matches. Not installed, no prior adoption to conflict with.
   ```

2. **Premise verification — the naive 9-file grep hit list does not survive inspection.**
   Same lesson as MSN-0383's own pre-flight: a pattern grep is a starting point, not a
   verified scope. Checked all 9 real hits directly:
   ```
   settings/_components/IntelligenceSection.tsx
   → grid-cols-1 gap-x-6 gap-y-1 — a settings form-field layout, NOT a KPI/stat-tile grid.
     False positive. Excluded.

   captains-brief-workbench/page.tsx, capture-workbench/page.tsx
   → both just `import { KpiDashboard } from './_components/KpiDashboard'` and render it —
     the actual pattern lives in the component file, already counted separately below.
     Double-counted. Excluded as separate items.
   ```
   **Real, de-duplicated list — 6 files:**
   ```
   captains-brief-workbench/_components/KpiDashboard.tsx
   capture-workbench/_components/KpiDashboard.tsx
   human-systems-workbench/_components/KpiDashboard.tsx
   knowledge-workbench/_components/LibraryKpis.tsx
   captains-chair-workbench/_components/CommandStatus.tsx
   human-systems-workbench/_components/NowView.tsx
   ```
   Three of these are **literally named `KpiDashboard.tsx`** in three unrelated workbenches
   — the strongest concrete duplication signal in this whole review: three independent
   engineering efforts arrived at the same component name and (presumably) similar shape
   without sharing code. `LibraryKpis.tsx`/`CommandStatus.tsx`/`NowView.tsx` need their own
   real-JSX check per file before assuming they fit the same pattern — don't extend the
   "3 KpiDashboards" finding to them by name-association alone.

3. **Explicitly not in scope:**
   - Any workbench NOT in the verified 6-file list — do not re-expand scope based on the
     original 9-file grep, which is now known to overcount.
   - Charting/dashboard additions to Emergency Alert Hub — explicitly evaluated and
     rejected this session; that page is deliberately not a dashboard by its own
     documented design intent, and this mission must not reopen that question.
   - Any visual redesign beyond what Tremor's own components provide re-themed to
     `wb-*` tokens — this is a consolidation of existing KPI displays onto one shared,
     accessible implementation, not a new visual language.

## Scope

1. Read each of the 6 real files' actual JSX first — confirm genuine KPI/stat-tile
   rendering (numbers, trend indicators, small multi-stat grids), not assume from filename.
2. Introduce Tremor's KPI/card primitives, re-themed via Tailwind config to use existing
   `wb-*` tokens (Tremor is Tailwind-native — no CSS-in-JS fight expected, verify this
   holds for this repo's actual Tailwind config before committing to the library).
3. Replace the three independent `KpiDashboard.tsx` implementations with one shared
   component (or three call sites of one shared primitive, if their data shapes differ
   enough to warrant separate wrappers — verify, don't force a single component if the
   real data shapes don't actually match).
4. Migrate `LibraryKpis.tsx`/`CommandStatus.tsx`/`NowView.tsx` only if their real JSX
   confirms the same KPI-grid pattern — "verified, different pattern, no change" is a
   legitimate per-file outcome.

## Acceptance

- Real per-file verification recorded for all 6, including any found to not actually
  need migration.
- The three `KpiDashboard.tsx` files converge onto one real shared implementation
  (or a documented reason they can't, e.g. genuinely incompatible data shapes).
- No visual regression — re-themed via existing tokens, not a new look.
- `tsc`/`next build` clean per commit, one file/consolidation step at a time.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0384-knowledge-record.md`), listing each of the 6 files' real outcome — same per-file reporting discipline as MSN-0381/0383.
