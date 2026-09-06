# TJR HQ — Command Experience Architecture

Status: **Phase 1 (correctness repair) complete. Phase 2 (full LifeOS vNext /
Captain's Chair vNext presentation redesign) not yet built — see §11.**

This document describes how Captain's Chair (`/captains-chair-workbench`)
and LifeOS Hub (`/hub`) are meant to relate to the rest of TJR HQ, what has
actually been built so far, and what remains open. It supersedes any
Captain's Chair / LifeOS section of `docs/architecture/HQ-V1-INTEGRATION-
CONTRACTS.md` that conflicts with it.

## 1. Command architecture

Captain's Chair and LifeOS are two presentations of one command truth, not
two independent dashboards:

```
Human Systems (assessed-context.ts) ──┐
Ready Room ────────────────────────────┤
Calendar (captainsChairData.ts) ───────┤
Canonical Brief (/api/captain-brief) ──┤──▶ Captain's Chair page-level synthesis
Emergency Alert Hub ────────────────────┤    (captainsChairSynthesis.ts)
HQ Status (hqStatusInterpreter.ts) ────┤
HQ Evolution ───────────────────────────┘
                                             │
                              ┌──────────────┴──────────────┐
                              ▼                              ▼
                      Captain's Chair                     LifeOS Hub
                (captains-chair-workbench/page.tsx)      (hub/page.tsx)
```

Neither surface re-derives domain truth. Each domain keeps its own
canonical interpretation; Captain's Chair/LifeOS only compose and present
already-assessed signals. Where a shared hook exists
(`src/lib/captainsChairData.ts`), both surfaces call the *same* hook rather
than each fetching and interpreting the underlying table/RPC themselves.

## 2. Domain owners (unchanged by this mission)

| Domain | Canonical owner | Notes |
|---|---|---|
| Human Systems posture/capacity | `src/app/api/human-systems/assessed-context.ts` (`getAssessedContext`) | See §3. |
| Ready Room execution state | Ready Room's own API/UI (`src/app/ready-room/`) | Reminders surfaced via `useReminders()` (personal tasks), not full task state. |
| Calendar | `src/app/api/calendar/{today,upcoming}` | See §4. |
| Canonical Brief | `src/app/api/captain-brief/route.ts` | External context-service process; documented fragile source. |
| Emergency Alert Hub | `src/app/emergency-alert-hub-workbench/page.tsx` + `/api/emergency-alerts` | Severity tiers: `emergency_warning` > `watch_and_act` > advice/unclassified. |
| HQ Status | `src/lib/hqStatusInterpreter.ts` | Pure interpreter over `AgentStatusEntry[]`; consumed by `/api/agent-status`. |
| HQ Evolution | `src/app/api/self-improvement/evolution-summary/route.ts` | Small morning-signal proxy, not the full Discover/Investigate surface. |
| Weekly Review | `src/app/api/weekly-review/route.ts` + `synthesis.ts` | Also consumes `getAssessedContext()`. |

Captain's Chair and LifeOS never query these domains' underlying tables or
RPCs directly — only their assessed/summary endpoints.

## 3. Human Systems posture — the P0 correctness repair

**Before this mission:** Captain's Chair and LifeOS each called
`useROSData()` (`src/lib/useROSData.ts`), which wraps the retired
`get_recovery_posture()` RPC over `analytics_health_daily` — a view whose
underlying tables stopped receiving rows once `capacity_checkins` replaced
them. `useROSData()` falls back to `mockPosture` (`?? mockPosture`) for
every field whenever the RPC returns null, and exposes an `isLive` flag
that neither page read. Result: a day with **no capacity check-in at all**
rendered a fabricated `STABLE`/`MODERATE` posture with full confidence —
false current-state truth, and Captain's Chair/LifeOS could each fabricate
a *different* mock value from each other.

**After this mission:** both surfaces call `useHumanSystemsContext()`
(`src/lib/captainsChairData.ts`), which fetches
`/api/human-systems/context` — the same small, fresh/stale-aware
`AssessedContext` boundary Ready Room and Weekly Review already consume
(`src/app/api/human-systems/assessed-context.ts`). This hook has **no mock
fallback of any kind**. Key properties of the canonical contract:

- `posture: SystemPostureBand` (`ENGAGE | STEADY | PROTECT | RECOVER |
  RESET | UNKNOWN`) — `deriveSystemPosture(null)` already returns
  `UNKNOWN` with an honest message when there is no check-in for today.
  There is no separate "is this fake" flag to remember to check — the
  posture itself is honest by construction.
- `has_checkin_today: boolean` — keyed strictly on today's row existing,
  independent of the 24h freshness window (a check-in from 11pm yesterday
  reads "fresh" by age but is still not "for today").
- `freshness: { status: 'fresh' | 'stale' | 'none', last_checkin_at }` —
  distinguishes a stale prior check-in from a genuinely absent one.
- `confidence` is capped to `'low'` whenever there is no check-in today,
  regardless of trajectory window depth.

`src/lib/captainsChairSynthesis.ts`'s `deriveCommandStatus()` was rewritten
to take this canonical shape (`posture`, `postureMessage`,
`availableCapacity`, `hasCheckinToday`, `humanSystemsUnavailable`) instead
of the legacy `RecoveryPostureBand`/`CapacityBand` pair. It distinguishes
three states, worded differently so they are never confused:

1. **Known, checked in today** — posture drives the interpretation as
   before (personal/environment 2×2 matrix).
2. **Known, no check-in today** (`hasCheckinToday: false`,
   `humanSystemsUnavailable: false`) — interpretation reads "No check-in
   today, so capacity is unknown," never a fabricated band.
3. **Unavailable** (`humanSystemsUnavailable: true`, the `/context` fetch
   itself failed) — interpretation reads "Human Systems is unavailable,"
   worded distinctly from case 2 so a genuine outage is never confused
   with an honest "nobody checked in yet."

The now-dead `useCapacityToday()` hook (a second, unused read of
`/api/human-systems?domain=recovery` for capacity/posture) was removed
from `captainsChairData.ts` rather than left as unreachable duplicate
interpretation surface.

`/api/human-systems?domain=recovery` (the full Recovery payload) is still
used by Captain's Chair — but only for `wellness.wellness.risk_flags`
(Needs You's "nervous-system load elevated" item), a sensitive field
`assessed-context.ts` deliberately excludes from its minimum-necessary
cross-workbench slice. It is no longer used as a second source of
posture/capacity.

`useROSData()` itself is untouched and remains correct for its other
consumers (`ROSPanels.tsx`, `/medical`) — this repair only removed
Captain's Chair and LifeOS as *consumers* of it. `ROSPanels.tsx` already
handled `isLive` correctly and was not touched.

## 4. Calendar

Both surfaces consume `useCalendarToday()` / `useCalendarUpcoming()`
(`src/lib/captainsChairData.ts`), which call `/api/calendar/today` and
`/api/calendar/upcoming?days=`. Both hooks expose a three-state status
(`ok | disconnected | error`) and never fabricate events for a disconnected
or errored calendar. This has been true since the MSN-0364 redesign wired
Calendar into both pages — see §5 for the doc-drift correction this
mission made.

## 5. Needs You — human-attention contract

`src/lib/captainsChairSynthesis.ts` exports `NeedsYouItem`/`sortNeedsYou`,
used only by Captain's Chair today (LifeOS does not yet render a Needs You
list — see §11 deferred work). Sources currently wired into it
(`captains-chair-workbench/page.tsx`): emergency `emergency_warning` tier,
Brief `interrupt_now`, Content awaiting-publish decisions, Human Systems
wellness risk flags, Notebook items ready for routing, Capture pending
triage, HQ Evolution pending decisions, and critical live alerts. None of
these are raw backlog/queue counts — each is filtered to items genuinely
awaiting a TJR decision. An empty list renders "Nothing needs your
attention right now" (see `NeedsYou.tsx`).

## 6. Emergency override

Emergency materiality is read once, via `useEmergencyAlerts()`
(`captainsChairData.ts`, hitting `/api/emergency-alerts?activeOnly=true`),
and the resulting `{ worstTier, count, worstHeadline }` feeds both
`deriveCommandStatus()`'s environment-concern check and the Needs You list.
Both surfaces call the same hook, so they cannot disagree on whether an
emergency is material.

## 7. Intelligence consumption

Both surfaces consume `useTodaysBriefing()` (`/api/captain-brief`) for
`interruptNow` only — its confidence/priority/warning/recommendation
counts are deliberately not rendered on either page (Captain-locked
decision from MSN-0364, unchanged by this mission). `TodaysBriefPanel` is
the one place the full brief narrative is read in detail, shared verbatim
between both pages.

## 8. HQ Status consumption

`useAgentHealth()` (`captainsChairData.ts`, hitting `/api/agent-status`)
surfaces a failed-job count and worst label only — never the raw job list.
Both Captain's Chair (Situation panel + Systems signal chip) and LifeOS
(Background Systems badge) read this one hook.

## 9. Evolution consumption

`useEvolutionSignal()` (inline in `captains-chair-workbench/page.tsx`)
reads `/api/self-improvement/evolution-summary` for a pending-decision
count and the single highest-value opportunity title — never the full
Discover/Investigate/Improve/Learned surface. Not yet surfaced on LifeOS.

## 10. Freshness / UNKNOWN / unavailable rules

These rules are enforced today for Human Systems (the P0 fix) and were
already correctly enforced for Calendar, Emergency, and HQ Status before
this mission:

- Human Systems: no current check-in → `UNKNOWN`, never a mock posture.
- Calendar: `disconnected`/`error` states are distinct from an empty day.
- Emergency: worst tier is read from currently-active alerts only
  (`activeOnly=true`); no persisted-but-stale alert is treated as current.
- HQ Status: `agentHealthError !== null` renders "Unknown," not "Nominal."
- Brief: `interruptNow` is `null` (not `0`) when the brief fetch fails, and
  `deriveCommandStatus()` treats a null interrupt count as "not urgent" but
  never as "confirmed clear" — see `hasUrgentException` semantics in
  `captainsChairSynthesis.ts`.

## 11. What this mission delivered vs. deferred

The full mission brief describes a much larger presentation redesign of
both surfaces (LifeOS vNext's ambient/sanctuary UI, Captain's Chair vNext's
TODAY/NEEDS YOU/INTELLIGENCE/AHEAD/CAPACITY/HQ EVOLUTION/SYSTEM STATUS
information architecture, a formal top-level "what kind of day is this"
command-posture taxonomy, and Sanctuary/low-stimulation behaviour). That
visual/IA redesign is **not** part of this change.

**Delivered (this change):**
- P0 correctness repair: both surfaces now consume the canonical Human
  Systems assessed context exclusively; the mock-fallback posture path is
  gone from both pages.
- `deriveCommandStatus()` rewritten onto the canonical `SystemPostureBand`
  vocabulary, with distinct, tested wording for known/no-checkin/
  unavailable states.
- Removed the dead second capacity-read hook (`useCapacityToday`).
- P3 doc correction (Calendar wiring — see
  `HQ-V1-INTEGRATION-CONTRACTS.md`).
- This document.

**Deferred (follow-on work, tracked but not built here):**
- LifeOS vNext presentation (command-posture headline, sanctuary/quiet
  mode, trimmed 3–10-second information model, removal of the 5-badge
  strip in favour of one posture headline).
- Captain's Chair vNext information architecture (TODAY / NEEDS YOU /
  INTELLIGENCE / AHEAD / CAPACITY / HQ EVOLUTION / SYSTEM STATUS sections,
  "Why?" drill-down, HQ Evolution/System Status trimming).
- A formal top-level command-posture taxonomy distinct from Human Systems
  posture (mission §6's PROTECT/FOCUS/RESPOND/RECOVER-style "what kind of
  day is this" layer) — today's `deriveCommandStatus()` is a *personal +
  environment concern* interpretation, not yet a full command-posture
  synthesis incorporating Calendar load and Evolution opportunity signal.
- Extending Needs You / intelligence-headline / HQ-status-tiny presentation
  to LifeOS (LifeOS currently still shows the 5-badge strip and a raw Live
  Alerts list, not a curated Needs You list).
- The Alerts taxonomy audit (decision/escalation/blocked/review/wellness
  vs. `NeedsYouKind`/`AlertSeverity`) named in mission §11.

Reason for scoping this way: the mission brief itself designates §3 (this
repair) as "REQUIRED CORRECTNESS REPAIRS — DO FIRST" and states the
broader redesign should not proceed by reopening domain workbenches or
introducing a second interpretation path. Landing the correctness fix as
its own reviewable change, with the target architecture documented here,
keeps that sequencing honest rather than bundling an unreviewed, largely
untested visual rewrite into the same change as a safety-relevant data
correctness fix.
