# Radix migration pattern (from ApprovalQueue.tsx)

## The recipe

1. Read the file first. Do not assume which Radix primitive is needed from the survey/mission description — verify against the actual JSX. ApprovalQueue's brief guessed Dialog/DropdownMenu/Tooltip; the real pattern in the file was an inline disclosure (Collapsible), not an overlay.
2. Map the existing interaction to the closest Radix primitive:
   - Inline expand/collapse toggling a region within the same layout flow (no overlay) → `@radix-ui/react-collapsible`.
   - A menu of actions opened from a trigger button → `@radix-ui/react-dropdown-menu`.
   - A modal that should trap focus and dim/replace the page → `@radix-ui/react-dialog`.
   - A hover/focus hint → `@radix-ui/react-tooltip`.
3. Preserve every existing `wb-*`/token/Tailwind class exactly. Wrap the *existing* styled `<button>`/element in `<Primitive.Trigger asChild>` (or `.Root`/`.Content` as needed) rather than replacing it with the primitive's own default-styled element. `asChild` merges the primitive's behavior/ARIA props onto your existing element via `React.cloneElement` — no visual change, no class rewrite.
4. Let the primitive own open/close state semantics where possible: drive `open`/`onOpenChange` from your existing `useState`, and remove manual `onClick` handlers on the trigger that duplicated what `onOpenChange` now does (Radix's trigger already toggles `open` on click).
5. Content that should only render while open: use `Primitive.Content` — Radix unmounts it when closed by default (same behavior as the old ternary render), so no extra conditional needed around it.
6. Verify with `tsc --noEmit` and `next build` before commit — Radix's typed props catch a wrong prop shape immediately.

## What ApprovalQueue.tsx got

- Added `@radix-ui/react-collapsible` (pinned `1.1.3`).
- Wrapped the per-item Approve/Reject row + reason-capture row in `Collapsible.Root`, with `open`/`onOpenChange` driven by the existing `rejectReasonFor` state (no new state variables).
- The "Reject" button became `Collapsible.Trigger asChild` wrapping the same styled `<button>` — same classes, same disabled logic, no visual change.
- The reason-input block became `Collapsible.Content` — same JSX, now Radix-owned mount/unmount instead of a manual ternary.

### Before → after accessibility, concretely

**Before:** the "Reject" button was a bare `<button>` with no state exposed. A screen reader announced only "Reject, button" — nothing communicated that clicking it would reveal a new region, and nothing tied that region back to the button that opened it. Closing (Cancel) was a second unrelated button with no relationship to the trigger.

**After:** Radix's `Collapsible.Trigger` automatically stamps `aria-expanded="false"|"true"` and `aria-controls="<generated-id>"` on the Reject button, and `Collapsible.Content` carries that matching `id` plus `data-state="open"|"closed"`. A screen reader now announces "Reject, button, collapsed" before activation and "expanded" after — and can jump directly from the trigger to its controlled region via `aria-controls`. This is a static-analysis verification (traced Radix's documented `Trigger`/`Content` prop behavior against the rendered props); a live screen-reader pass with a dev server was not run in this environment — flag for a follow-up manual check before/after screenshots if the mission wants that recorded.

Keyboard behavior: no change was needed for Tab order (native `<button>`/`<input>` already tab correctly), but the Reject trigger is now also independently activatable with Enter/Space per Radix's `Trigger` (same as a native button, so no regression — the point is the *state* is now announced, not that keyboard reachability changed).

## Follow-up queue — remaining raw-`<button>` files (not migrated by this task)

Each of these still uses raw `<button>` elements for interactions that may warrant a Radix primitive (Dialog/DropdownMenu/Tooltip/Collapsible depending on what's actually in each file — verify before assuming, per step 1 above):

1. `src/components/MobileAlertDrawer.tsx`
2. `src/components/CaptainIntelligencePanel.tsx`
3. `src/components/TodaysBriefPanel.tsx`
4. `src/components/SignOutButton.tsx`
5. `src/components/LCARSNav.tsx`
6. `src/app/intelligence-workbench/page.tsx`
7. `src/app/engineering-handoffs/page.tsx`
8. `src/app/model-crew/page.tsx`
9. `src/app/self-improvement-findings/page.tsx`
10. `src/app/briefs/page.tsx`
11. `src/app/health-osint-curation/page.tsx`
12. `src/app/human-systems-workbench/page.tsx`
13. `src/app/mission-workbench/page.tsx`
14. `src/components/ui/QuickCapture.tsx`

(14 listed — mission brief estimated 10; grep found more raw-`<button>` files than the original survey counted. Migrate one at a time, following this pattern, verifying build + accessibility evidence for each before moving to the next.)
