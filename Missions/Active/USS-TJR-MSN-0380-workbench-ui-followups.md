# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0380
- **Priority:** P3 — Stream 1 is real backlog surfaced by CI, not an outage; Streams 2-3 are optional convenience additions
- **Source:** Workbench-UI review of consequences from MSN-0374/0375/0376/0377/0378/0379 (this session, 2026-09-13) — see that review for the full "required / not required / worth considering" breakdown. This mission only covers the items that involve writing UI code.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -n "cycle_summary|artifacts_commit|git_commit|scheduler|garak|deepteam|deepeval|promptfoo" \
     lcars-portal/src/app/self-improvement-findings/page.tsx
   → no matches. Confirmed: no existing page reads any of today's new eval-tool output.

   agent-status-workbench/_components/UsageView.tsx header comment
   → confirmed this tracks LLM call volume/tokens/spend (migration 0197's views over
     llm_call_metrics), NOT Supabase's own plan-level quota (DB size/egress). Different
     "usage" entirely — no naming collision to worry about, but also no existing surface
     to extend; Stream 2 below is a new panel, not an addition to an existing one.

   engineering-handoffs/page.tsx
   → already Card/Badge/WorkbenchShell-based, straightforward to add one more Card.
   ```

2. **Premise verification.** The exact contrast-violation list for Stream 1 already exists —
   it does not need re-discovery. `lcars-portal/scripts/storybook-a11y-check.mjs` (added by
   MSN-0374 Stream 1) produced the real numbers already cited (28 stories checked, 8 with
   violations, all `color-contrast`/serious, across Input/Navigation/Progress stories). Stream
   1 below starts by re-running that exact script to get the current precise list (colors may
   have drifted since), not by re-deriving contrast math from scratch.

3. **Explicitly not in scope:**
   - Flipping the Storybook a11y CI job from report-only to blocking — a separate decision
     for whoever owns that job's "Next Planned Evolution," not bundled into the fix itself.
   - Any change to `agent-status-workbench`'s existing `UsageView` (LLM usage) — Stream 2
     is additive, not a rename/repurpose of that tab.
   - Deciding whether Supabase's Management API is an acceptable new external dependency
     for the portal to call directly (real security/credential-scope question) — Stream 2's
     pre-flight below flags this as unresolved, this mission does not resolve it unilaterally.

## Scope / Streams

### Stream 1 — Fix the 8 real color-contrast violations (required)
Re-run `node lcars-portal/scripts/storybook-a11y-check.mjs` against current `main` to get
the precise current list (component, story, exact contrast ratio). Fix each via existing
design tokens (`text-wb-ink2` etc.) — this is a token/class-choice fix, not new components.
Re-run the script after to confirm 0 violations remain on the fixed stories; the CI job
itself will show the same on its next run.

### Stream 2 — Supabase usage panel (worth considering, real open dependency question)
**Pre-flight-of-pre-flight, must be answered before writing any component code**: does the
portal already hold (or can it acceptably hold) a Supabase Management API token with
project-usage read scope, or does this panel instead just render whatever MSN-0378's
Stream 0 investigation produces (a periodically-updated static/DB-cached snapshot, not a
live API call)? This mission does not assume the answer — resolve it first, cheaply
(a static snapshot fed by MSN-0378's findings is the lower-risk default if a live
Management API integration isn't already an accepted pattern elsewhere in the codebase).
Once resolved: add a new panel/tab to `agent-status-workbench` (not a change to the
existing `UsageView`) showing Database Size and Egress against their quota.

### Stream 3 — Link the log4brains ADR site from Engineering Handoffs (worth considering, trivial)
Add one `Card` to `engineering-handoffs/page.tsx` linking to the log4brains output.
Since `.log4brains/out/` is git-ignored generated output (per MSN-0374 Stream 4), this
needs wherever that site is actually hosted/served (not yet decided — Stream 4's own
knowledge record explicitly left hosting as a future decision) — this stream is blocked
on that hosting decision, not on any UI-code difficulty. If hosting isn't decided yet,
this stream should wait rather than link to a path that doesn't resolve anywhere.

## Acceptance

- Stream 1: 0 real contrast violations remain on the 8 previously-flagged stories, confirmed
  by re-running the actual script, not by inspection alone.
- Stream 2: the Management-API-vs-static-snapshot question is answered and documented before
  any component ships; the panel shows real numbers matching the Supabase dashboard at time
  of check, not placeholder/mock data.
- Stream 3: either shipped with a real, resolved hosting URL, or explicitly deferred with the
  hosting decision named as the blocker — not shipped with a dead/local-only link.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0380-knowledge-record.md`), noting per-stream outcome (including "deferred, blocked on X" as a legitimate outcome for Streams 2-3).
