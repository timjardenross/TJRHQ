# USS-TJR-MSN-0383: TanStack Table Migration — Knowledge Record

**Date:** 2026-09-13
**Branch:** `msn-0383-work`
**Status:** Complete — premise did not hold. **0 of 12 files migrated, 12 of 12
verified-not-applicable.** `@tanstack/react-table` was **not** installed (the brief
forbids speculative installation before a first real migration; there was no first
real migration).

## Headline

The 12-file list in the brief is a grep hit list, and the brief was right to flag it as
unverified — but the false-positive rate turned out to be **100%, not one file**. Every
one of the 12 was read in full before any judgement. None of them contains hand-rolled
sort state, and none of them contains client-side pagination.

The decisive, checkable fact:

```
$ grep -rn "currentPage\|pageSize\|sortBy\|sortKey\|sortDir\|sortOrder\|setSort" <all 12 files>
(no output — exit 1)
```

The pre-flight grep in the brief was an alternation:
`\.sort((a, b)|useState.*sortBy|useState.*sortKey|currentPage|pageSize`.
**Only the first alternative — the bare `.sort((a, b)` literal — ever matched.** The
`currentPage`/`pageSize`/`useState…sort*` halves matched zero of the twelve. So what the
hit list actually enumerated was "files containing a JavaScript array sort", which in this
codebase means aggregation ranking (top-5 lists), fixed reverse-chronological merges, and
one-shot `[0]` pickers — not user-controlled table sorting.

Two wider sweeps confirm this is a property of the whole portal, not of these 12 files:

- **No user-controlled sorting exists anywhere in `lcars-portal/src`.**
  `grep -rl "useState.*[sS]ort" --include="*.tsx" src` → **zero files**. There is not one
  clickable sort header in the application.
- **Only 8 files in the portal render a `<table>` at all**, and of those only one
  (`SourcesView.tsx`) contains a `.sort()` — a fixed status-severity ordering with no
  header controls and no pagination.

`getSortedRowModel` has nothing to take over, and `getPaginationRowModel` has nothing to
take over. Introducing the dependency would have added row-model ceremony to lists that
are already one-line static orderings, for zero behaviour change and zero de-duplication —
which is precisely the "forcing a migration onto something that isn't a table" outcome the
brief prohibits.

## Per-file outcomes

| # | File | Outcome | Real reason |
|---|------|---------|-------------|
| 1 | `physical-readiness/history/page.tsx` | verified-not-applicable | Analytics page. The four `.sort()` calls rank aggregation `Map`s into top-5 leaderboards (`mostUsed`, `mostSkipped`, `painFlagged`, `cardioRanked`) and are immediately `.slice(0, 5)`d. "Recent Sessions" is a `<ul>` in Supabase's own `.order('started_at', desc).limit(30)` order. No sort control, no pagination, no table. |
| 2 | `intelligence-workbench/escalation/[id]/page.tsx` | verified-not-applicable | Single-incident detail screen. The one `.sort()` is a max-picker: `signals.slice().sort(...)[0]` to select the top-ranked signal for the risk breakdown. The audit trail below it is an unsorted, unpaginated `<div>` list in API order. |
| 3 | `self-improvement-findings/_components/OpportunityDetail.tsx` | verified-not-applicable | Single-opportunity detail card. Its one `.sort()` puts `outcome.evaluation_history` into fixed chronological order inside a collapsed `<details>` — a provenance trail, not a sortable list. |
| 4 | `knowledge-workbench/_components/MemoryView.tsx` | verified-not-applicable | Tabbed card lists (Decisions / Lessons / All). The `.sort()` is a fixed `created_at desc` merge of two already-server-ordered sources for the "All" tab. Filtering is a debounced substring search over ≤100 rows; there is no sort control and no pagination. |
| 5 | `(app)/search/page.tsx` | verified-not-applicable | Universal search. Results from four searchers are merged and sorted once by timestamp inside `runSearch`, then grouped by type into per-section button lists. Each searcher is already `.limit(4–6)`-capped server-side, so there is nothing to paginate. |
| 6 | `(app)/timeline/page.tsx` | verified-not-applicable | Vertical event timeline with a connector spine. Fixed `timestamp desc` merge of five fetchers; the only controls are a day-window selector (7/14/30, which re-queries Supabase) and source filter chips. No column model, no sort control, no pages. |
| 7 | `mission-workbench/page.tsx` | verified-not-applicable | Responsive `MissionCard` grid, not a table. Open missions arrive in Supabase `.order('priority')` order; the single `.sort()` orders the Closed tab by `closed_at desc`. Tabs and the D-055 capacity filter are filters, not sort/page state. |
| 8 | `content-workbench/_components/TodayView.tsx` | verified-not-applicable | Prioritised "what needs you" card sections. Two fixed sorts (`rank_score desc` capped at 5; `scheduled_for asc` capped at 5) feed distinct card components. The `.slice(0, 5)` caps are editorial limits, not page slices — there is no page 2 and no next control. |
| 9 | `content-workbench/_components/QueueView.tsx` | verified-not-applicable | Flat button list ordered by one deterministic `priorityScore()` (stage weight + focus boost + rank). The ordering is the feature; there is no way for the user to change it and no pagination. |
| 10 | `agent-status-workbench/_components/SourcesView.tsx` | verified-not-applicable | The only genuine `<table>` in the hit list — two of them — but both are ordered by one fixed `STATUS_ORDER` severity rank (failing → healthy) with no clickable headers and no pagination. Wrapping a static rank comparator in `useReactTable` would add a dependency and a full column-def block while still hand-rendering every `<td>`, delivering no behaviour change and nothing to de-duplicate. Flagged as the single file that would become a real migration target *if* sortable headers are ever added. |
| 11 | `capture-workbench/_components/KpiDashboard.tsx` | verified-not-applicable | **Exactly the false positive the brief predicted.** It is a 3-up stat grid plus two rows of filter chips. The two `.sort()` calls rank `Object.entries()` of a counts object into top-5/top-6 chip lists. There is no row, no column and no table anywhere in the file. |
| 12 | `shopping-list-workbench/page.tsx` | verified-not-applicable | Drag-to-reorder CRUD list. Order is the user's own persisted `priority_rank` (written back via `reorderShoppingList`), never a computed sort — the only `.sort()` in the file is `uniqueSorted()`, which alphabetises the *filter dropdown options*. A TanStack row model would sit directly on top of index-based drag-and-drop, which is an active hazard rather than a neutral swap. |

**Totals: migrated 0 · verified-not-applicable 12.**

## Flagged, not fixed (out of scope)

Real pagination *does* exist in this portal — just not in any of the 12 files, and not
client-side:

- `intelligence-workbench/_components/LibraryView.tsx`
- `health-osint/_components/LibraryView.tsx`
- `knowledge-workbench/_components/LibraryView.tsx`

All three hold a `page` state whose only job is to be sent to the server
(`sp.set('page', …)`, `params.set('offset', String(page * PAGE_SIZE))`) with the row
count coming back as a `total` from the API. That is **server-side pagination**, which the
brief puts explicitly out of scope, and `getPaginationRowModel` cannot serve it — it
paginates rows already in the browser. Flagged here per the brief's instruction to flag
rather than silently expand scope. The knowledge-workbench one additionally mirrors
page/filter state into the URL (MSN-0334), so any future change there has a URL contract
to preserve.

## Verification

- No source file under `lcars-portal/` was modified. `package.json` and
  `package-lock.json` are untouched; `@tanstack/react-table` is still absent from the
  dependency tree.
- Baseline confirmed clean on this branch after `npm ci`:
  - `npx tsc --noEmit` → exit 0, no diagnostics.
  - `npm run build` (Next.js production build) → completed, full route table emitted, no
    errors.
- Because no file changed, there were no per-file commits to gate on a build; this record
  is the mission's only commit.

## Lesson

An alternation grep reports a hit list, never a scope — and it does not tell you *which*
alternative matched. Splitting the alternation before trusting the count would have shown
in one command that the `currentPage|pageSize|useState.*sort*` half of this mission's
pre-flight pattern matched nothing at all, and that the entire 12-file case rested on the
bare `.sort((a, b)` literal. The brief's own instinct was right (it named
`KpiDashboard.tsx` as a likely false positive); the discipline it prescribed simply needed
to be applied to all twelve rather than to the one that looked suspicious from its
filename.

The substantive finding underneath is worth more than the migration would have been: the
LCARS portal has **no user-sortable table anywhere**, and its list-heavy workbenches
deliberately hand the Captain one curated ordering rather than a sortable grid. If
sortable/paginated tables are wanted, that is a product decision to make first — and
`@tanstack/react-table` would then be the right tool, starting with
`agent-status-workbench/_components/SourcesView.tsx`, the one real table with a real
ordering rule.
