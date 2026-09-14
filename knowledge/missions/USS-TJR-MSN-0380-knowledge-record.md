# Knowledge Record — USS-TJR-MSN-0380: Workbench UI Follow-ups

Three independent streams from the MSN-0374/0375/0376/0377/0378/0379 workbench-UI
consequence review. Executed in parallel as three isolated worktrees/branches
(msn-0380-stream1/2/3), one per stream, no file overlap. Outcomes below.

---

## Stream 1 — Color-contrast fixes

**Outcome: shipped.**

### Context
Re-ran `lcars-portal/scripts/storybook-a11y-check.mjs` (added by MSN-0374 Stream 1,
report-only) to get the real current violation list rather than trusting the old cited
numbers blind.

### Environment note
`lcars-portal/node_modules` and `storybook-static` did not exist in the worktree. Required
`npm ci`, `npx playwright install --with-deps chromium`, and `npm run build-storybook`
before the check script could run at all. Anyone re-running this cold needs the same steps.

### Before (current code, pre-fix)
```
Stories checked: 28
Stories with violations: 8
Total violations: 8
Total passing axe checks: 145
```
8 serious `color-contrast` violations across:
- Input > Text Field, Textarea Field, Select Field, Form Layout
- Navigation > Tab Nav
- Progress > Bar, Multiple Bars, Steps

The old count (8 stories/8 violations, all color-contrast/serious, same three components)
had **not** drifted — confirmed by re-running the real script.

### Root cause (single cause, all 8)
Token `text-wb-ink2` (`#657080` on `#F5F1EA`) measures **4.45:1**, a hairline miss under
the required 4.5:1 (WCAG AA, normal text) — not a broad color-system problem, one
under-threshold token used in labels/hints/counters across Input, Navigation, Progress.

### Fix
Token/class-choice only — swapped affected call sites from `text-wb-ink2` to the existing
`text-wb-ink` token (`#273248`, already used elsewhere in the same components for
primary/complete text; comfortably clears 4.5:1). No new tokens, no new components.
- `lcars-portal/src/components/ui/Input.tsx` — label + hint text (placeholder text left
  untouched; axe didn't flag it)
- `lcars-portal/src/components/ui/Navigation.tsx` — inactive tab text (redundant hover
  variant dropped since resting state now matches it)
- `lcars-portal/src/components/ui/Progress.tsx` — value counter + pending-step label
  (ink/ink2 ternary collapsed to a single class)

### After (post-fix, storybook-static rebuilt)
```
Stories checked: 28
Stories with violations: 0
Total violations: 0
Total passing axe checks: 145
```
Same 28 stories, 0 violations, nothing regressed. `npx tsc --noEmit` clean.

Committed on `msn-0380-stream1` (`60526121e`). Flipping the CI job from report-only to
blocking remains a separate, explicitly out-of-scope decision.

---

## Stream 2 — Supabase usage panel

**Outcome: deferred**, blocked on:
1. A credential/scope decision — whether the portal gets a Supabase Management API token
   with project-usage read scope. No such token or precedent exists anywhere in the
   codebase today (only hit found: an XO-bot doc confirming no Management API access
   exists on the host). Minting one is a decision reserved for the Captain, out of this
   mission's scope.
2. MSN-0378 Stream 0 completing and producing an actual persisted, queryable usage
   snapshot. MSN-0378 (`Missions/Active/USS-TJR-MSN-0378-supabase-usage-reduction.md`) has
   not been actioned — no knowledge record exists, no snapshot table/cache exists. The
   Database Size/Egress numbers quoted in MSN-0378's own brief are one-time motivating
   context, not a re-fetchable, panel-bindable source.

Per the brief's explicit instruction, no component code was written and no panel was
faked with stale/hardcoded numbers. `agent-status-workbench`'s existing `UsageView.tsx`
(LLM usage, unrelated) was left untouched. No commit made — nothing to commit.

**Unblocks when:** either a Management API token is provisioned and accepted as a pattern,
or MSN-0378 Stream 0 ships a real persisted snapshot this panel can read from.

---

## Stream 3 — log4brains ADR link

**Outcome: deferred**, blocked on the log4brains output hosting/publishing decision.

Confirmed via grep, git log, and both MSN-0374 Stream 4 knowledge records plus the SUOC
Platform Registry (all updated the same day, 2026-09-13) that the hosting decision for
`.log4brains/out/` has not been made since MSN-0374 shipped: no CI publish workflow, no
static route in `lcars-portal/vercel.json`, no nginx/CDN config, `.log4brains/out/` still
git-ignored. Linking to it from `engineering-handoffs/page.tsx` today would be dead or
local-filesystem-only. Per the brief's instruction, `engineering-handoffs/page.tsx` was
left untouched rather than shipping a link that resolves to nothing. No commit made.

**Unblocks when:** a future mission decides where `.log4brains/out/` is hosted (GitHub
Pages, a Vercel static route, etc.) — at that point this becomes a trivial one-`Card`
addition.

---

## Cross-stream note
All three streams ran as independent git worktrees off the same base commit (74b826589)
with zero file overlap, confirming the brief's "no dependency between them" premise held
in practice.
