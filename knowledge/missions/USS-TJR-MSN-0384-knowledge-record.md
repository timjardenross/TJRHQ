# Knowledge Record — USS-TJR-MSN-0384: KPI/Stat-Tile Consolidation

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0384 |
| Priority | P3 |
| Date | 2026-09-13 |
| Status | **DONE** — 3 real dupes consolidated onto a shared local primitive; Tremor rejected at pre-flight |

## Pre-flight: naive grep hit list did not survive inspection

Mission brief's 9-file grep hit list de-duplicated to 6 real files before any
migration work started (same discipline as MSN-0383):
`settings/_components/IntelligenceSection.tsx` was a form-field grid, not a
KPI grid (false positive); the two workbench `page.tsx` files were just
import/render call sites for `KpiDashboard`, already counted via the
component file itself.

## Tremor rejected — brief's own verification gate (#2) did not survive inspection

The brief commissioned "introduce Tremor's KPI/card primitives... verify
Tailwind-native holds for this repo before committing to the library."
Checked:

- Tremor 3.18.7 supports React 18 (repo has 18.3.1) — compatible.
- But Tremor's `Card`/`Metric`/`Grid` theme via a fixed internal
  `tremor-*` color-name palette, not arbitrary CSS custom properties —
  re-theming to `wb-*` tokens needs a tailwind color-key remap, not a
  straight Tailwind pass.
- None of the 3 real `KpiDashboard.tsx` files' actual per-tile needs
  (clickable stat cells with `wb-sage-deep` focus rings, tone-conditional
  coloring, chip breakdowns, badge-as-value, loading/error card states)
  exist in Tremor's primitives — all would be rebuilt inside its wrapper
  anyway. Net value-add of the dependency ≈ 0; cost = new dep + retheming
  plumbing that itself risks a second design-system fork alongside the
  legacy-LCARS-vs-wb split already tracked ([[legacy-app-page-migration]]).

Put to the user directly; decision was to skip Tremor and consolidate onto a
local shared primitive instead — no new dependency, same duplication fixed.

## Per-file verified outcome (all 6)

| File | Verified pattern | Outcome |
|---|---|---|
| `captains-brief-workbench/_components/KpiDashboard.tsx` | Real KPI strip: `ConfidenceMeter` + 3 plain-number stat cells, click-to-jump | **Migrated** — local `Stat()` replaced with shared `KpiStat` |
| `capture-workbench/_components/KpiDashboard.tsx` | Real KPI strip: 3 plain-number stat cells (tone-conditional) + chip breakdowns + loading/error states | **Migrated** — local `Stat()` replaced with shared `KpiStat`; chip/loading/error logic untouched (not a stat-cell concern) |
| `human-systems-workbench/_components/KpiDashboard.tsx` | Real KPI strip: 3 bordered cards, badge-as-value + sub-text | **Migrated** — local `KpiCard()` replaced with shared `KpiCard` (byte-identical extraction) |
| `knowledge-workbench/_components/LibraryKpis.tsx` | Real stat-tile grid, but already wired to a shared `@/components/StatTile` — on the **legacy LCARS token system** (`rounded-lcars`, `border-edge`, `text-lcars-muted`), not `wb-*` | **Not migrated** — different design system entirely (legacy-vs-wb migration is its own tracked mission, [[legacy-app-page-migration]]); folding it into this consolidation would conflate two migrations mid-flight |
| `captains-chair-workbench/_components/CommandStatus.tsx` | NOT a KPI/stat-tile grid — posture headline + "Why?" disclosure + signal chips | **Not migrated** — wrong pattern match by name-association alone; brief explicitly warned against extending the finding this way |
| `human-systems-workbench/_components/NowView.tsx` | NOT a KPI grid itself — just imports and renders `KpiDashboard` inside the tab layout | **Not migrated** — no independent pattern to consolidate |

## What shipped

- `src/components/ui/KpiStat.tsx` (new): `KpiStat` (plain number/label
  stat cell, tone-conditional, optional click-to-jump) and `KpiCard`
  (bordered tile with badge/sub-text slot) — both `wb-*`-tokened, exported
  from `@/components/ui`.
- Three `KpiDashboard.tsx` call sites updated to use the shared primitives;
  local duplicate `Stat`/`KpiCard` functions removed from all three.
- Visual output unchanged — same markup/classes, just de-duplicated.

## Verification

- `npx tsc --noEmit` — clean.
- `npx next build` — clean, no regressions across the route manifest.
- No visual redesign: primitives are direct extractions of the pre-existing
  JSX/classes, not a new look.

## Explicitly not touched (per brief's scope fence)

- Emergency Alert Hub — not re-evaluated for dashboard/charting; that
  question was closed this session prior to this mission.
- Any workbench outside the verified 6-file list.

## Related

[[legacy-app-page-migration]] — the LCARS-vs-wb token split `LibraryKpis`
surfaced is the next real duplication seam, not this one.
