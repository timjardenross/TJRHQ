# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0383
- **Priority:** P2 — real, verified debt footprint; no external deadline
- **Source:** workbench UI review (this session, 2026-09-13) — second-ranked item after the Radix migration (MSN-0381) on the "what would improve workbenches" list.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -n "\"table\"|react-table|tanstack" lcars-portal/package.json
   → no matches. Not installed, no prior adoption to conflict with.

   grep -rl "\.sort((a, b)|useState.*sortBy|useState.*sortKey|currentPage|pageSize" \
     lcars-portal/src/app --include="*.tsx" | grep -v __tests__
   → 12 real files, listed below. Not a guess — this is the actual grep hit list.
   ```

2. **Premise verification — the 12-file list is a grep hit list, not a verified scope.**
   Exactly the same discipline MSN-0381's own pattern doc insists on (its Stream 1 rule:
   "read the file first, do not assume from the survey/mission description") applies here.
   `grep` for `currentPage`/`pageSize`/manual `.sort()` will catch real hand-rolled
   sort-and-paginate logic, but it can also catch unrelated uses of those variable names
   (e.g. `capture-workbench/KpiDashboard.tsx`'s name suggests it may be a stat-tile
   dashboard, not a table — verify before assuming it needs TanStack Table at all). Each
   of the 12 needs a real look at its JSX before migrating, same as the Radix queue.

   The 12 files:
   ```
   physical-readiness/history/page.tsx
   intelligence-workbench/escalation/[id]/page.tsx
   self-improvement-findings/_components/OpportunityDetail.tsx
   knowledge-workbench/_components/MemoryView.tsx
   (app)/search/page.tsx
   (app)/timeline/page.tsx
   mission-workbench/page.tsx
   content-workbench/_components/TodayView.tsx
   content-workbench/_components/QueueView.tsx
   agent-status-workbench/_components/SourcesView.tsx
   capture-workbench/_components/KpiDashboard.tsx
   shopping-list-workbench/page.tsx
   ```

3. **Explicitly not in scope:**
   - Any visual/token change — this is a headless logic swap. TanStack Table has zero
     built-in markup/styling; every existing `<table>`/`<tr>`/`<td>`/card-list JSX and its
     `wb-*` classes stay exactly as they are.
   - Any file where the real JSX turns out not to be a sortable/paginated list (per the
     `KpiDashboard.tsx` caution above) — "verified, not a table" is a legitimate per-file
     outcome, not a gap, same as MSN-0381's Stream 1 allows for its own queue.
   - Server-side pagination/sorting changes (API routes, Supabase queries) — this mission
     is client-side rendering logic only, unless a file's real bug turns out to be
     server-side, in which case flag it rather than silently expanding scope.
   - Introducing a second table library alongside TanStack Table for any reason.

## Scope

Migrate the verified subset of the 12 files, one at a time, one commit per file:
1. Read the real JSX first — confirm it's actually hand-rolled sort/pagination over a list,
   not a false grep hit.
2. Replace the manual sort-state/`.sort()`/page-slice logic with `@tanstack/react-table`'s
   `useReactTable` + `getSortedRowModel`/`getPaginationRowModel`, keeping every existing
   `<tr>`/`<td>`/card markup and `wb-*` class as-is — TanStack Table only supplies row/column
   model logic, not rendering.
3. Verify `tsc --noEmit` + `next build` clean, and that sort/pagination behavior is
   unchanged from a user's perspective (same default sort, same page size) before committing.

## Acceptance

- Each of the 12 files has a stated real outcome: migrated, or verified-not-applicable
  (with the real reason, e.g. "KpiDashboard.tsx is a stat grid, not a table").
- No visual regression — every migrated file's rendered markup/classes unchanged.
- `tsc`/`next build` clean on every commit, one file at a time, not batched.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0383-knowledge-record.md`), listing each of the 12 files' individual outcome — same structure as MSN-0381's per-file reporting.
