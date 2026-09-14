# MSN-0372 — Workbench Mobile Sizing Fixes

**Mission ID is provisional** — minted as next-after-371 by scanning for the highest existing `MSN-0xxx` (same minting-drift gap MSN-0363 already flagged; no canonical counter exists in-repo). Confirm/reissue before this is cited elsewhere.

**Status:** Scoped, not started.
**Owner:** unassigned.
**Requested by:** Captain (TJR), 2026-09-12 — "write a mission brief to address all those items."

---

## 1. Objective

Close every finding from the Workbench Mobile Sizing Audit (2026-09-12): 6 critical, 13 major, 17 minor mobile/iPhone layout defects across the 20 live workbench routes, found by a five-way parallel source-level review (130 files read in full) as a direct follow-up to PR #193 (removed the fixed bottom nav bar that was overlapping QuickCapture and clipping page content on phones).

This mission fixes what PR #193 didn't touch: header rows and toggle/tab bars that overflow instead of wrapping, rigid two-column grids with no mobile fallback, free text with no overflow guard, and a scatter of focus-ring/disabled-state/tap-target inconsistencies against the shared component contract.

## 2. Context & Source of Truth

Full punch list, every finding with exact `file:line`, risk, and fix, is published at the audit artifact: **Workbench Mobile Sizing Audit** (https://claude.ai/code/artifact/00fba046-9fee-42d4-8677-3abf96d8e133). This brief organizes that punch list into buildable work packages — it does not restate every line of reasoning; read the artifact before starting a package if the one-line summary below isn't enough context.

**Methodology note, carried over from the audit:** this was a source-level review, not a browser session — the sandbox it ran in has no real Supabase credentials, and the app's auth middleware gates every workbench route, so nothing here was confirmed against a live rendered iPhone viewport. Treat each fix as "verified in code, not yet verified on device" until someone with real credentials (or a staging deploy) actually loads the page on a phone. See §9.

**Coverage:** all 20 routes in `src/lib/workbenches.ts`'s `LIVE_WORKBENCHES`. Four came back fully clean: Agent Status Workbench, Briefs, Weekly Review, Emergency Alert Hub Workbench — no work packages below touch them.

## 3. Touch-Surface Notes (read before starting)

- `src/components/ui/WorkbenchShell.tsx` was just touched by PR #193 (MobileCommandBar removal). WP01 touches it again (header row wrap) — do this as its own commit so a revert of one doesn't drag the other.
- `src/components/ui/Navigation.tsx` is shared (currently only consumed by `self-improvement-findings`, per the audit) — WP02's fix there is low-risk but grep for other consumers before assuming it's single-use.
- Several findings exist because a page hand-rolled an input/button/select instead of using the shared `Input`/`Select`/`Button` primitives (`src/components/ui/`), which the audit confirmed already implement correct disabled-state, focus-ring, and tap-target handling. Where a work package below says "switch to the shared component," that's the actual fix — not a parallel one-off patch.
- Knowledge Workbench's `LibraryView`/`DocumentDetail`/`BatchTriageBar` are currently dead code — the Library tab is pulled back to draft (`page.tsx` only renders `MemoryView`/`ArchitectureIndex`). Fixes there (WP03, WP04, WP05) are worth doing now, before the tab reopens, but are not user-visible today — lowest priority to schedule, safe to batch into whichever PR touches that directory anyway.

## 4. Work Packages

Ordered by leverage (systemic fixes first, since they close multiple findings per change), not strictly by severity. Each package is independently mergeable.

### WP01 — Header-row overflow guard (2 critical)

Root cause: `WorkbenchShell`'s header row (`WorkbenchShell.tsx:103`) has no `flex-wrap` and no overflow handling; it already carries a logo, title, Settings icon, ThemeSelector, and WorkbenchSwitcher at every width. Two routes additionally inject extra controls into the `right` slot instead of the dedicated `tabs` row every other workbench uses, and both overflow on real iPhone widths as a result.

- `src/app/captains-brief-workbench/page.tsx:83-94` — move the 2-tab `DomainToggle` into the `tabs` prop (matching content-workbench/intelligence-workbench); keep `right` to just the Refresh button.
- `src/app/health-osint/page.tsx:75-78` — shorten "Details (Technical view)" to "Details" and/or move it into the `tabs` row.
- Consider, as a backstop rather than a replacement for the above two fixes: add `flex-wrap` to `WorkbenchShell.tsx:103`'s header row so a future page making the same mistake degrades to two lines instead of overflowing. Discuss with whoever owns WorkbenchShell before doing this — it changes shared chrome.

### WP02 — Clipped / non-wrapping action & toggle rows (4 critical)

Same failure shape in four unrelated files: fixed-width buttons/chrome packed into one non-wrapping (or `overflow-hidden`) flex row with no scroll fallback.

- `src/app/captains-chair-workbench/notebook/page.tsx:271` — Approve/Archive row clipped by the card's `overflow-hidden`. Add `flex-wrap` to the row, or drop `overflow-hidden` on the card. (Also fix the metadata row at `:183` in the same pass — WP-major below, same file, same root cause.)
- `src/app/human-systems-workbench/trends/page.tsx:273-303` — 5-button date-range toggle sits in `overflow-hidden`. Apply the same fix the team already shipped for this exact shape in `DomainToggle.tsx` (`overflow-x-auto` + `shrink-0` on the buttons).
- `src/app/shopping-list-workbench/_components/ItemRow.tsx:45` — image + badge + 3 buttons + drag handle in one row, min-width 450px+, overflows on every iPhone size. Stack action buttons below the content row under `sm` (or collapse to an overflow menu); wrap in `overflow-x-auto` as a fallback.
- `src/components/ui/Navigation.tsx:18` (consumed by `self-improvement-findings/page.tsx:257-269`) — persistent 5-tab nav with dynamic counts, no wrap/scroll. Wrap in `overflow-x-auto` + `flex-nowrap` (a scrollable tab strip), or allow `flex-wrap`. This is a shared component — check other consumers before changing its default behavior.

### WP03 — Rigid two-column grids, no mobile stacking (3 major)

- `src/app/knowledge-workbench/_components/DocumentDetail.tsx:103` — 7-pair `grid-cols-2` detail grid. `grid-cols-1 sm:grid-cols-2`.
- `src/app/intelligence-workbench/brief/[id]/page.tsx:248` — 8-row `grid-cols-2` signal-detail grid inside a Modal. Same fix.
- `src/app/intelligence-workbench/brief/[id]/page.tsx:200` and `escalation/[id]/page.tsx:149` — fixed `w-[140px]` timestamp column crowds the audit-trail row on a 375px card. Drop the fixed width or stack the timestamp above the entry text below `sm`.

### WP04 — Focus-ring / outline-none sweep (6 major)

All the same bug: `focus:border-* focus:outline-none` instead of the app-wide `focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2` pattern. Do this as one PR, one commit per file, since it's a mechanical find-and-replace once you've confirmed each site.

- `src/app/capture-workbench/_components/CaptureView.tsx:97` — the primary Quick Capture textarea. Highest priority in this package (most-used field).
- `src/app/knowledge-workbench/_components/MemoryView.tsx:128` — the one live Knowledge Workbench search input.
- `src/app/knowledge-workbench/_components/BatchTriageBar.tsx:49`, `DocumentDetail.tsx:172`, `LibraryView.tsx:322` — dormant Library tab, same pattern, worth doing before it reopens.

### WP05 — Overflow-wrap / break-words safety net (4 major, 1 minor)

Free text (AI output, titles, filenames from upstream data) with no guard against a single long unbroken token pushing the container wider than the viewport.

- `src/app/content-workbench/_components/ContentStudio.tsx:121` — item title. Add `break-words`/`min-w-0`, matching `ItemCard`'s own treatment in the same directory.
- `src/app/knowledge-workbench/_components/DocumentDetail.tsx:78` — filename heading. Add `break-words` (the `source_path` right below it already does this correctly — copy that pattern).
- `src/app/advisory-workbench/_components/shared.tsx:254`, plus `ConsultView.tsx:238-241` and `PerspectivesView.tsx:354-357` — AI free-text output (`ResultSection` paragraphs, `.prose` markdown wrappers). Add `break-words` / `overflow-wrap: anywhere`.
- `src/app/engineering-handoffs/page.tsx:149-154` (minor) — handoff title next to a `shrink-0` badge, no `min-w-0`/`break-words`. Same fix, lower priority — free-text titles here are shorter in practice.

### WP06 — Design-token discipline (1 major)

- `src/app/hub/page.tsx:216, 242, 271` — "Next"/"Needs You"/"World" cards use `bg-white` instead of `bg-wb-surface`. Breaks in dark theme on the one page most likely to actually run in dark mode (the always-on wall-tablet front door). Straight token swap, three lines.

### WP07 — Tab/action-row wrap guards, preventive (2 major)

Not overflowing today, but no fallback once content grows — cheap to fix now rather than wait for a bug report.

- `src/app/mission-workbench/page.tsx:166` — Open/Closed tab row, no wrap/scroll. Add `overflow-x-auto` or allow wrap.
- `src/app/self-improvement-findings/page.tsx:881` (right block at `:934`) — historical-decisions row: text block vs. a `shrink-0` cluster of up to 2 buttons + 2 badges. Let the row wrap, or stack the action cluster below the text under `sm`.

### WP08 — Disabled-state `cursor-not-allowed` sweep (7 minor)

Every one of these already sets the real `disabled` attribute and `disabled:opacity-*` — they're missing `disabled:cursor-not-allowed` alongside it, so the pointer still shows as clickable over a disabled control. Mechanical, low-risk, do as one grep-driven pass rather than seven separate diffs:

- `src/app/captains-chair-workbench/_components/CaptainsLog.tsx:73`
- `src/app/capture-workbench/_components/CaptureView.tsx:120`
- `src/app/capture-workbench/_components/CaptureRow.tsx:44` (shared `ActionBtn`, used 8× per row — fixing this one call site fixes every instance)
- `src/app/knowledge-workbench/_components/BatchTriageBar.tsx:76` (dormant Library tab; prefer switching to the shared `Button` component instead of patching the raw button)
- `src/app/advisory-workbench/_components/ThinkView.tsx:140`, `PerspectivesView.tsx:274`, `ConsultView.tsx:196`
- `src/app/human-systems-workbench/report/page.tsx:106-112`
- `src/app/hub/page.tsx:296-303`

### WP09 — Tap-target sizing (3 minor)

- `src/app/captains-chair-workbench/_components/CaptainsLog.tsx:73` — primary capture "+" button is 36×36 (`h-9 w-9`) on the most-visited dashboard page. Bump to `h-11 w-11` (44px).
- `src/app/ready-room/_components/TaskRow.tsx:186, 196` — mute/pin icon toggles, ~16×16px hit area. Add `p-2` (or `min-h-11 min-w-11`).
- `src/app/ready-room/_components/TaskRow.tsx:144` — "···" overflow-menu trigger, ~24-28px. Increase padding to at least `p-2.5`/`min-h-11`.

### WP10 — Breakpoint convention drift, `lg:` → `xl:` (2 minor, optional)

Not currently overflow-risky (the app's `Sidebar` is `xl:`-gated, so nothing else competes for space in the 1024–1279px band on these two pages today) but drifts from the convention the rest of the app follows. Fold into WP03/WP04 if those PRs already touch these files; otherwise low priority.

- `src/app/content-workbench/_components/ContentStudio.tsx:137`
- `src/app/knowledge-workbench/_components/LibraryView.tsx:358` (dormant Library tab)

### WP11 — Remaining minors (5)

- `src/app/physical-readiness/page.tsx:84` — session summary row, no stacking rule for a longer label. Add `flex-wrap sm:flex-nowrap` or `shrink-0` on the badge as a safety margin.
- `src/app/health-osint/_components/LibraryView.tsx:90, 101, 102` — hand-rolled filter inputs, no focus ring, height mismatch vs. the adjacent Select. Switch to the shared `Input`/`Select` components.
- `src/app/health-osint/_components/TodayView.tsx:192-216` — Include/Ignore curation controls, hand-rolled, no focus ring. Switch to shared `Button`/`Select`.
- `src/app/health-osint/_components/LibraryView.tsx:120-121` — pagination buttons, no focus ring. Switch to shared `Button` (`variant="secondary" size="sm"`).
- `src/app/self-improvement-findings/page.tsx:764-768` — 3 equal-width decision buttons risk a 2-line wrap on "More Evidence" at narrow widths. Allow `flex-wrap`, or drop to 2-up + full-width below `sm`.

## 5. Explicitly Out of Scope

- No redesign of any workbench's layout beyond what each fix requires — this mission closes the audit's findings, it doesn't re-architect anything.
- No reactivation of Knowledge Workbench's dormant Library tab. WP03/WP04/WP05/WP10's Library-tab fixes land in dead code on purpose (cheaper to fix now than to rediscover later) — reopening the tab is a separate decision for whoever owns that mission.
- No changes to `MobileCommandBar.tsx`, `GlobalAlertNotifier.tsx`, or the `globals.css` mobile input font-size rule — those are PR #193's territory and are already shipped/under review.
- No live-device or real-browser verification as part of this mission — see §9.

## 6. Suggested Sequencing / PR split

Independent, mergeable in any order, but grouped to keep diffs reviewable:

1. **WP01 + WP02** (all 6 critical) — one PR, ships first.
2. **WP04 + WP08** (the two mechanical sweeps) — one PR each, since they're both "same fix, many sites" and easy to review as a unit.
3. **WP03 + WP05 + WP07** (structural majors) — one PR.
4. **WP06** — trivial, can ride along with any of the above or ship alone.
5. **WP09 + WP10 + WP11** (remaining minors) — one PR, lowest priority, fine to defer past the majors/criticals if time-constrained.

## 7. Verification Plan

Per package, before pushing:

- `npx tsc --noEmit`, `npx next lint`, `npx vitest run` (656 tests as of PR #193; watch for regressions in `WorkbenchShell has no axe violations` and any test touching a file in this mission).
- `npm run build` — confirm every touched route still prerenders.
- Re-read the specific finding's "why it's a risk" line from the audit artifact and confirm the fix actually addresses it, not just the letter of the "fix" one-liner.

## 8. Definition of Done

- All 6 critical findings resolved.
- All 13 major findings resolved, or explicitly deferred here with a stated reason (e.g. "Library tab is dormant, deferred to its reactivation mission").
- All 17 minor findings resolved, or explicitly deferred with a reason.
- `tsc`/`lint`/`vitest`/`build` clean on every PR in §6.
- No PR in this mission touches a file outside the paths listed in its work package without a note added here explaining why.

## 9. Open Decisions for Captain

- Confirm mission ID (provisional MSN-0372) against a canonical registry before this is cited elsewhere — same caveat MSN-0363 already carries.
- This mission's fixes are unverified on a real device (see §2/§9 methodology note). Decide whether to: (a) merge on code review + the automated checks in §7 alone, or (b) hold merge until someone can load the deployed preview on a real iPhone across a few of the fixed pages. No blocker either way, just a risk tradeoff to own.
- WP10 (breakpoint convention drift) is marked optional/low-priority — confirm whether it's worth doing at all right now versus tracking as a backlog note.
- Sequencing in §6 is a suggestion, not a constraint — reorder freely if a different grouping fits better with whoever ends up picking this up.
