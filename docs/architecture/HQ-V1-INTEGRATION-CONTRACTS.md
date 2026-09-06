# HQ V1 Integration Contracts

Status: corrected 2026-09-06 as part of the Captain's Chair + LifeOS
Command-Surface Correctness Repair mission. See
`docs/architecture/COMMAND-EXPERIENCE.md` for the fuller architecture
writeup this file's contracts feed into.

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

## Emergency Alert Hub

Both surfaces read `useEmergencyAlerts()` (`captainsChairData.ts` →
`/api/emergency-alerts?activeOnly=true`) for `{ worstTier, count,
worstHeadline }`. Confirmed: no duplicate emergency interpretation exists
between the two pages; both derive materiality from the same
`worstTier`/`count` shape. Not modified by this mission.

## HQ Status

Both surfaces read `useAgentHealth()` (`captainsChairData.ts` →
`/api/agent-status`) for `{ failedCount, worstLabel }`. The underlying
interpretation (`normal`/`degraded`/`attention`/`unknown` posture) is owned
by `src/lib/hqStatusInterpreter.ts` and is not re-derived by either
command surface — they only read the summary counts. Not modified by this
mission.

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

Captain's Chair reads a small morning signal (`useEvolutionSignal()`,
inline in `captains-chair-workbench/page.tsx` → `/api/self-improvement/
evolution-summary`) for a pending-decision count and the single
highest-value opportunity. LifeOS does not currently surface HQ Evolution
at all. Not modified by this mission.

## Known remaining duplication / drift (tracked, not fixed here)

- LifeOS still renders a raw "Live Alerts" list (`useAlerts()`) rather than
  the curated Needs You presentation Captain's Chair has — the two
  surfaces do not yet present identical "what needs you" semantics, only
  identical underlying emergency/interrupt data. See
  `COMMAND-EXPERIENCE.md` §11.
- The Alerts page's prose taxonomy (decision/escalation/blocked/review/
  wellness) does not map 1:1 onto either `NeedsYouKind`
  (`captainsChairSynthesis.ts`) or `AlertSeverity` (`src/lib/alerts.ts`).
  Flagged for a future pass; not addressed by this mission (mission §11
  scopes this as an audit, not a required repair).
