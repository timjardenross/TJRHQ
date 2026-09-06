# HQ V1 Integration Contracts

Status: corrected 2026-09-06 as part of the Captain's Chair + LifeOS
Command-Surface Correctness Repair mission (Phase 1), then updated
2026-09-06 for the Phase 2 presentation redesign (HQ Status consumption
change, below). See `docs/architecture/COMMAND-EXPERIENCE.md` for the
fuller architecture writeup this file's contracts feed into.

This document tracks, per integration point, which command surfaces
(Captain's Chair `/captains-chair-workbench`, LifeOS `/hub`) are wired to
which canonical contract, and any known drift between documentation and
implementation.

## Calendar (P3 — corrected)

**Prior documentation state:** stated Calendar was "not yet wired into
command-surface consumption."

**Actual implementation (confirmed 2026-09-06):** Calendar has been wired
into both command surfaces since the MSN-0364 Captain's Chair redesign.

- Captain's Chair (`captains-chair-workbench/page.tsx`) consumes both
  `useCalendarToday()` (today's events, the "Ahead" section's TODAY block)
  and `useCalendarUpcoming(2)` (the next 2 days, "Ahead"'s TOMORROW/LATER
  blocks).
- LifeOS (`hub/page.tsx`) consumes `useCalendarToday()` only (today's
  events card).
- Both hooks live in one place — `src/lib/captainsChairData.ts` — so there
  is exactly one Calendar read/interpretation path for both surfaces, not
  two.
- Both hooks expose a three-state status (`'ok' | 'disconnected' |
  'error'`), sourced from `/api/calendar/today` and
  `/api/calendar/upcoming`. Confirmed honest on all three states:
  - `disconnected` → an explicit "Google Calendar isn't connected. Connect
    it." message with a reconnect link (`/api/auth/google-calendar/connect`)
    on LifeOS; Captain's Chair's `Ahead` component renders the same status
    distinctly from an empty day.
  - `error` → a distinct "Failed to load calendar" message, never rendered
    as zero events.
  - No fabricated events are ever synthesized for either non-`ok` status.
- No duplicate Calendar store or interpretation exists — both pages call
  the same two hooks, which call the same two API routes.

**Disposition:** documentation-only correction. No behavior change was
needed or made to Calendar itself (mission classification: P3, do not
redesign).

## Human Systems posture / capacity (P0 — corrected, behavior changed)

**Prior state:** Captain's Chair and LifeOS each read posture/capacity via
`useROSData()` (`src/lib/useROSData.ts`), which wraps the retired
`get_recovery_posture()` RPC and falls back to a hardcoded mock posture
(`STABLE`/`MODERATE`) whenever there was no check-in for the day. Neither
page read the hook's `isLive` flag, so this fabricated value was
indistinguishable from a real live reading.

**Current state:** both surfaces read `useHumanSystemsContext()`
(`src/lib/captainsChairData.ts`), which calls
`/api/human-systems/context` — the canonical `AssessedContext` boundary
owned by `src/app/api/human-systems/assessed-context.ts`, the same one
Ready Room (`/api/human-systems/context` route) and Weekly Review
(`/api/weekly-review`) already consumed before this mission. This path has
no mock fallback; "no check-in today" surfaces as posture `UNKNOWN` with
an honest message, not a fabricated band.

Full detail, including the exact repair made to
`captainsChairSynthesis.ts`'s `deriveCommandStatus()`, is in
`docs/architecture/COMMAND-EXPERIENCE.md` §3.

**Disposition:** behavior change, landed with unit + component-level test
coverage (`src/lib/__tests__/captainsChairSynthesis.test.ts`,
`src/app/captains-chair-workbench/__tests__/page.test.tsx`).

**Phase 2 addendum:** this same canonical `SystemPostureBand` now also
feeds `src/lib/commandState.ts`'s `deriveCommandPosture()` — the top-level
command-posture taxonomy (`RESPOND | RECOVER | PROTECT | FOCUS | STEADY |
UNKNOWN`) both surfaces render as their day headline. Human Systems'
posture is one *input* to that derivation, not the value itself — see
`COMMAND-EXPERIENCE.md` §11.

## Emergency Alert Hub

Both surfaces read `useEmergencyAlerts()` (`captainsChairData.ts` →
`/api/emergency-alerts?activeOnly=true`) for `{ worstTier, count,
worstHeadline }`. Confirmed: no duplicate emergency interpretation exists
between the two pages; both derive materiality from the same
`worstTier`/`count` shape. Not modified by this mission.

## HQ Status (P2 — corrected, behavior changed)

**Prior state:** both surfaces read `useAgentHealth()`
(`captainsChairData.ts` → `/api/agent-status`) for `{ failedCount,
worstLabel }` — a failed-job count re-derived from the raw job list on the
command-surface side. The underlying posture interpretation
(`normal`/`degraded`/`attention`/`unknown`) was owned by
`src/lib/hqStatusInterpreter.ts`, but the command surfaces did not consume
that interpretation directly — they recomputed a cruder health signal from
the raw counts instead, a second (if lower-stakes) instance of the same
"re-derive instead of consume" pattern the Human Systems P0 repair fixed.

**Current state (Phase 2):** `useAgentHealth()` is deleted. Both surfaces
read `useHqStatusSummary()` (`captainsChairData.ts` →
`/api/agent-status-workbench/overview`), which reads that response's
`captainSummary` field — the `CaptainChairSummary` object
`hqStatusInterpreter.ts`'s `buildCaptainChairSummary()` builds specifically
for Captain's Chair/LifeOS consumption. The hook exposes `{ posture,
summary, needsAttentionCount, attentionItems }`, `posture` being one of HQ
Status's own `NORMAL | DEGRADED | ATTENTION | UNKNOWN` values. HQ health
now has exactly one interpretation path, not two.

This also changed behavior in `captainsChairSynthesis.ts`'s
`deriveCommandStatus()`: it now takes `hqPosture`/`hqSummary`/
`hqUnavailable` instead of a raw failed-job count, and only HQ posture
`ATTENTION` counts as an environment concern — `DEGRADED` does not (mission
rule: a degraded HQ needs no action, only `ATTENTION` does). `HQPosture ===
'attention'` also now generates a Needs You item via
`commandState.ts`'s `buildNeedsYouItems()`; `DEGRADED` never does. Full
detail in `docs/architecture/COMMAND-EXPERIENCE.md` §8, §11.

**Disposition:** behavior change, part of the Phase 2 presentation
redesign (2026-09-06).

## Canonical Brief

Both surfaces read `useTodaysBriefing()` (`captainsChairData.ts` →
`/api/captain-brief`) but, per the Captain-locked MSN-0364 decision, only
consume `interruptNow` from it directly — the full narrative is rendered
once via the shared `TodaysBriefPanel` component, not re-summarized by
either page. `/api/captain-brief` remains a known-fragile external
dependency (documented prior silent-breakage on Vercel); `interruptNow` is
treated as `null` (unknown), never `0`, on fetch failure. Not modified by
this mission.

## Ready Room

Both surfaces read `useReminders()` (`captainsChairData.ts`, via
`fetchTasks()`/`attendBucket()` from `src/lib/personalTasks.ts`), filtered
to the `'now'` attend-bucket. This is a personal-tasks reminder slice, not
Ready Room's full execution-state contract — Ready Room's own assessed
execution context (if/when one exists analogous to Human Systems'
`assessed-context.ts`) is out of scope for this correction pass. Not
modified by this mission.

## HQ Evolution

Both surfaces read `useEvolutionSignal()` (`/api/self-improvement/
evolution-summary`) for a pending-decision count and the single
highest-value opportunity. Phase 2 moved this hook from being inline in
`captains-chair-workbench/page.tsx` into `captainsChairData.ts` so LifeOS
could call it too — see `COMMAND-EXPERIENCE.md` §9. Captain's Chair
surfaces it in a dedicated `HqEvolution.tsx` section (hidden when there is
nothing to consider); LifeOS does not render a dedicated Evolution section,
but a pending decision count feeds `buildNeedsYouItems()` on both pages, so
it can surface as a Needs You item on either surface. Not modified further
since the Phase 2 move.

## Known remaining duplication / drift (tracked, not fixed here)

- The Alerts page's prose taxonomy (decision/escalation/blocked/review/
  wellness) does not map 1:1 onto either `NeedsYouKind`
  (`captainsChairSynthesis.ts`) or `AlertSeverity` (`src/lib/alerts.ts`).
  Flagged for a future pass; not addressed by either phase of this mission
  (the original mission brief scopes this as an audit, not a required
  repair). See `COMMAND-EXPERIENCE.md` §13.
- Ready Room's own assessed execution-state contract (analogous to Human
  Systems' `assessed-context.ts`) does not exist yet; both surfaces read a
  personal-tasks reminder slice (`useReminders()`, the `'now'` attend-bucket)
  rather than a full execution-state summary — unchanged by either phase.

Resolved by Phase 2 (kept here for history): LifeOS previously rendered a
raw "Live Alerts" list rather than a curated Needs You presentation, so the
two surfaces agreed on underlying emergency/interrupt data but not on
"what needs you" semantics. Both surfaces now call the identical
`buildNeedsYouItems()` (`commandState.ts`) over identical shared raw-data
hooks (`captainsChairData.ts`) — see `COMMAND-EXPERIENCE.md` §5.
