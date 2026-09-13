# Knowledge Record — USS-TJR-MSN-0381: Radix follow-up queue migration

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0381 |
| Title | Land the ApprovalQueue Radix pilot; migrate the 14-file raw-`<button>` follow-up queue |
| Date | 2026-09-13 |
| Status | **DONE** — pilot merged, all 14 files triaged (4 migrated, 10 verified no-change), screen-reader question explicitly re-deferred |

## Stream 0 — landed the pilot

`msn-ui-radix-approvalqueue` (commit `6b69065`) was not yet merged to `main`.
Repo has 74 concurrent peer sessions sharing the working checkout at
`/opt/starship-endeavour` — worked in an isolated `git worktree`
(`/tmp/msn-0381-wt`, branch `msn-0381-radix-followup` off `origin/main`)
instead of `git checkout` on the shared tree, per the prior git-shared-worktree
collision lesson. Merged cleanly (no conflicts) onto current `origin/main`
(`eaded5d8a`, one commit ahead of the branch's own stale base). `tsc --noEmit`
and `next build` both verified clean on the merged, current-main state — not
just the branch's own stale CI run.

## Stream 1 — the 14 files

Each file was read in full before deciding anything (the pilot's own step 1:
don't assume the primitive from the filename/survey). 4 needed a primitive;
10 verified as plain action buttons with no disclosure/menu/dialog/tooltip
shape — a legitimate "no change needed" outcome per the mission's acceptance
criteria, not a gap.

| # | File | Outcome |
|---|---|---|
| 1 | `src/components/MobileAlertDrawer.tsx` | **Migrated → `@radix-ui/react-dialog`** (1.1.23). The one file in the queue that's a genuine overlay (`role="dialog" aria-modal="true"`, backdrop, bottom sheet) — not a Collapsible. |
| 2 | `src/components/CaptainIntelligencePanel.tsx` | No change — plain single-action buttons (Generate, outcome-feedback). |
| 3 | `src/components/TodaysBriefPanel.tsx` | No change — single plain "Read aloud" action button. |
| 4 | `src/components/SignOutButton.tsx` | No change — single plain action button. |
| 5 | `src/components/LCARSNav.tsx` | **Migrated → `@radix-ui/react-collapsible`**. Nav section header toggling a sibling `<ul>` — exact Collapsible shape. |
| 6 | `src/app/intelligence-workbench/page.tsx` | No change — "Technical view" is a plain link-style action button (view switch via router state, not a disclosure/overlay). |
| 7 | `src/app/engineering-handoffs/page.tsx` (`ArtifactViewer`) | **Migrated → Collapsible**. `toggle()` showed/hid an inline artifact region below the trigger — same shape as the pilot's own ApprovalQueue disclosure. |
| 8 | `src/app/model-crew/page.tsx` | No change — plain "Refresh" action button. |
| 9 | `src/app/self-improvement-findings/page.tsx` | No change — 16 buttons are all plain decision/filter/selection actions (master-detail inline panel, not a modal). One section already uses native `<details>/<summary>` (browser-native disclosure) — left alone; already accessible, not a raw `<button>`. |
| 10 | `src/app/briefs/page.tsx` (`ExploreView`) | **Migrated → Collapsible**. "Show/Hide advanced filters" toggled an inline legacy-filter block — Collapsible shape. |
| 11 | `src/app/health-osint-curation/page.tsx` | No change — Publish/Reject are plain single-action buttons. |
| 12 | `src/app/human-systems-workbench/page.tsx` | No change — TRENDS/REPORT buttons are real `router.push` navigation, not a disclosure. |
| 13 | `src/app/mission-workbench/page.tsx` | No change — Open/Closed and All/Today are mutually-exclusive filter toggles (segmented-control shape), not Collapsible/Dialog/DropdownMenu/Tooltip. |
| 14 | `src/components/ui/QuickCapture.tsx` | No change — overlay is already delegated to the existing `Modal` component (real `role="dialog"`/`aria-modal`/Escape-close/focus-on-open, not a raw-button pattern); QuickCapture's own buttons are a plain trigger, a capture-type toggle group, and a submit button. |

One file per commit, `tsc --noEmit` + `next build` verified before each, exactly
as the pilot's own worked example did.

### Before → after accessibility (same evidentiary bar as the pilot)

- **LCARSNav / ArtifactViewer / briefs advanced-filters (Collapsible):** before,
  the trigger button carried no `aria-expanded`/`aria-controls` — a screen
  reader announced only the label, with no signal that activating it reveals
  a region or which region that is. After, `Collapsible.Trigger`/`.Content`
  stamp matching `aria-expanded`/`aria-controls`/`id`/`data-state`, so a
  screen reader announces expanded/collapsed and can jump straight to the
  controlled region — verified by static prop-trace against Radix's
  documented behavior, not a live pass (see Stream 2).
- **MobileAlertDrawer (Dialog):** before, `role="dialog"`/`aria-modal`/
  `aria-hidden` were set by hand with no focus trap, no Escape binding, and
  no `aria-hidden` on the rest of the page while open. After, Radix owns
  focus-trap-on-open, Escape-to-close, and background `aria-hidden` — a real
  accessibility gain, not just a relabeling. The slide-up/down animation and
  every `wb-*`/token class were preserved exactly (first attempt at this
  migration let Radix's default unmount-on-close silently kill the
  transition in both directions; fixed with `forceMount` + the original
  open-ternary classing before verifying and committing).

No `wb-*`/Tailwind class was changed on any migrated file — every migration
used `asChild` to wrap the existing styled element, per the established
pattern. `git diff --stat` on each commit shows only structural JSX
(wrapper tags, prop moves), no className edits except the two additions
required to *not* change the rendered result (`aria-hidden` on
MobileAlertDrawer's now-duplicate `<h2>`, and a `sr-only` `Dialog.Title`).

## Stream 2 — screen-reader verification: explicitly re-deferred

Decision: **defer**, recorded here rather than silently carried forward a
third time.

Reasoning: this environment has no interactive browser/screen-reader tooling
available to the session (no `next dev` + VoiceOver/NVDA/JAWS pass is
possible from this non-interactive worktree). The pilot already flagged this
gap explicitly and deferred it once; this mission inherits that same
constraint unchanged — the environment didn't change between the pilot and
this follow-up, so re-attempting it would produce the same non-answer.
Every migration above was verified the way the pilot verified ApprovalQueue:
a static trace of Radix's documented `Trigger`/`Content`/`Overlay` prop
behavior against the actual rendered props, confirmed via `tsc --noEmit` +
`next build`, not a live assistive-technology pass.

**Recommendation for whoever picks this up next:** the fix is environmental,
not code — run `npm run dev` in `lcars-portal/` and do one real VoiceOver/NVDA
pass over the pilot file (`ApprovalQueue.tsx`) plus at least
`MobileAlertDrawer.tsx` (the Dialog case) and one Collapsible
(`LCARSNav.tsx`) from a machine with real AT installed. Until that happens,
treat every "before → after" claim in this record and the pilot's own docs
as verified-by-code-trace, not verified-by-listening.

## Scope discipline (per mission brief)

- Radix vs. Base UI was **not** re-litigated — `RADIX-VS-BASEUI-DECISION.md`'s
  reasoning stands, and no third primitive library was introduced.
- No primitive was assumed from a filename — every file was read in full
  first; the 10 "no change" verdicts are the direct result of that check,
  not a shortcut.
- No visual/token change on any file — `asChild` used throughout.

## Verification

- `tsc --noEmit`: clean after every commit.
- `next build`: clean after every commit (final full build also clean on the
  merged branch with all 4 migrations + the pilot together).
- No test suite regression: no existing test file references any of the 4
  migrated components (confirmed via search before starting).
