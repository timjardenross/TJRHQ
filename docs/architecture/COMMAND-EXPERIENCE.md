# TJR HQ — Command Experience Architecture

Status: **Phase 1 (correctness repair) and Phase 2 (LifeOS vNext / Captain's
Chair vNext presentation redesign) both delivered — see §11.**

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
HQ Status (hqStatusInterpreter.ts) ────┤          │
HQ Evolution ───────────────────────────┘          ▼
                                          Command State (commandState.ts)
                                          deriveCommandPosture() /
                                          buildNeedsYouItems() /
                                          deriveIntelligenceHeadline()
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

Phase 2 added a second shared layer above the hooks:
`src/lib/commandState.ts`, a pure-function module (no React, no fetch) that
both pages call with the same inputs to get the same outputs —
`deriveCommandPosture()` (the top-level "what kind of day is this" read,
§11), `buildNeedsYouItems()` (the one curated Needs You list, §5), and
`deriveIntelligenceHeadline()` (the one Brief/Emergency/Operational-Risk
headline, §7). `captainsChairSynthesis.ts`'s `deriveCommandStatus()` still
sits underneath it and is still called directly by both pages for the
personal/environment 2×2 interpretation (§3, §6) — `commandState.ts`
composes `deriveCommandStatus()`'s output rather than replacing it.

## 2. Domain owners (unchanged by this mission)

| Domain | Canonical owner | Notes |
|---|---|---|
| Human Systems posture/capacity | `src/app/api/human-systems/assessed-context.ts` (`getAssessedContext`) | See §3. |
| Ready Room execution state | Ready Room's own API/UI (`src/app/ready-room/`) | Reminders surfaced via `useReminders()` (personal tasks), not full task state. |
| Calendar | `src/app/api/calendar/{today,upcoming}` | See §4. |
| Canonical Brief | `src/app/api/captain-brief/route.ts` | External context-service process; documented fragile source. |
| Emergency Alert Hub | `src/app/emergency-alert-hub-workbench/page.tsx` + `/api/emergency-alerts` | Severity tiers: `emergency_warning` > `watch_and_act` > advice/unclassified. |
| HQ Status | `src/lib/hqStatusInterpreter.ts` | Pure interpreter over `AgentStatusEntry[]`; command surfaces consume its `buildCaptainChairSummary()` output via `/api/agent-status-workbench/overview` (§8). |
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

`src/lib/captainsChairSynthesis.ts` exports the `NeedsYouItem`/`NeedsYouKind`
types and `sortNeedsYou()` (priority ordering — safety first, triage last).
The list itself is built by `buildNeedsYouItems()` in
`src/lib/commandState.ts`, one function called identically by both Captain's
Chair (`captains-chair-workbench/page.tsx`) and LifeOS (`hub/page.tsx`) —
Phase 2 closed the gap the Phase 1 doc flagged as deferred (LifeOS not
rendering a curated Needs You list at all). Sources wired into it: emergency
`emergency_warning` tier, Brief `interrupt_now`, HQ Status `ATTENTION`
posture (only `ATTENTION` generates an item — `DEGRADED` never does, see
§8), Content awaiting-publish decisions, Human Systems wellness risk flags,
Notebook items ready for routing, Capture pending triage, HQ Evolution
pending decisions, and critical live alerts (capped at 2). None of these are
raw backlog/queue counts — each is filtered to items genuinely awaiting a
TJR decision. An empty list renders "Nothing needs your attention right
now" (Captain's Chair's `NeedsYou.tsx`) or "Nothing needs your attention."
(LifeOS).

Sharing the interpretation was not enough on its own — both surfaces also
had to share the *raw-data fetches* feeding it, or they could still drift
by reading two different snapshots of the same underlying data. Phase 2
moved `useAttentionCounts()` (Content/Capture/Wellness counts),
`useEvolutionSignal()` (HQ Evolution's pending-decision count and
highest-value opportunity), and `useNotebookReadyCount()` out of
`captains-chair-workbench/page.tsx` and into `src/lib/captainsChairData.ts`,
alongside the hooks that were already shared (`useHumanSystemsContext()`,
`useEmergencyAlerts()`, `useTodaysBriefing()`, `useHqStatusSummary()`). Both
pages now call the same six-plus hooks and feed the same
`buildNeedsYouItems()` inputs — there is exactly one Needs You
fetch-and-interpret path, not two that happen to agree today.

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

**Before Phase 2:** `useAgentHealth()` (`captainsChairData.ts`, hitting
`/api/agent-status`) surfaced a failed-job count and worst label,
re-derived from the raw job list on the command-surface side — a second,
cruder HQ-health interpretation living outside HQ Status's own module.

**After Phase 2:** `useAgentHealth()` is deleted. Both surfaces read
`useHqStatusSummary()` (`captainsChairData.ts`), which calls
`/api/agent-status-workbench/overview` and reads its `captainSummary`
field — the already-interpreted `CaptainChairSummary` that
`hqStatusInterpreter.ts`'s `buildCaptainChairSummary()` builds for exactly
this purpose. The hook exposes `{ posture, summary, needsAttentionCount,
attentionItems }`, where `posture` is one of HQ Status's own
`NORMAL | DEGRADED | ATTENTION | UNKNOWN` values (uppercased from
`HQPosture`). There is now exactly one HQ-health interpretation
(`hqStatusInterpreter.ts`'s), not two.

This is a behavior change, not just a wiring change:
`captainsChairSynthesis.ts`'s `deriveCommandStatus()` now takes
`hqPosture`/`hqSummary`/`hqUnavailable` instead of a raw failed-job count,
and only `ATTENTION` counts as an environment concern —
`environmentConcern()` checks `inputs.hqPosture === 'attention'`, not any
nonzero failed-job count. `DEGRADED` is HQ's own business and generates no
command-surface concern, no Needs You item, and no RESPOND posture
(mission rule: a degraded HQ needs no action, only `ATTENTION` does — see
§11). Both Captain's Chair (`SystemStatus.tsx`, a small dedicated section —
the old "Systems" fold inside Situation is gone) and LifeOS (the tiny HQ
status line at the foot of the page) read this one hook.

## 9. Evolution consumption

`useEvolutionSignal()` reads `/api/self-improvement/evolution-summary` for
a pending-decision count and the single highest-value opportunity title —
never the full Discover/Investigate/Improve/Learned surface. Phase 2 moved
it from being inline in `captains-chair-workbench/page.tsx` into
`captainsChairData.ts` (see §5) so LifeOS could call it too. Captain's
Chair surfaces it in a dedicated `HqEvolution.tsx` section (AHEAD →
CAPACITY → **HQ EVOLUTION** → SYSTEM STATUS, §11) that hides itself
entirely when there is nothing to consider; LifeOS does not render a
dedicated Evolution section but feeds the same pending-decision count into
`buildNeedsYouItems()`, so a pending Evolution decision surfaces there as a
Needs You item on both pages.

## 10. Freshness / UNKNOWN / unavailable rules

These rules are enforced today for Human Systems (the P0 fix) and were
already correctly enforced for Calendar, Emergency, and HQ Status before
this mission:

- Human Systems: no current check-in → `UNKNOWN`, never a mock posture.
- Calendar: `disconnected`/`error` states are distinct from an empty day.
- Emergency: worst tier is read from currently-active alerts only
  (`activeOnly=true`); no persisted-but-stale alert is treated as current.
- HQ Status: `useHqStatusSummary()`'s `error !== null` (the
  `/api/agent-status-workbench/overview` fetch itself failing) feeds
  `hqUnavailable`, which renders as "Unknown," never "Nominal" — distinct
  from a successful read reporting `DEGRADED`, which is worded as
  "no action required," not "unknown."
- Brief: `interruptNow` is `null` (not `0`) when the brief fetch fails, and
  `deriveCommandStatus()` treats a null interrupt count as "not urgent" but
  never as "confirmed clear" — see `hasUrgentException` semantics in
  `captainsChairSynthesis.ts`.

## 11. Command posture — the top-level "what kind of day is this" taxonomy

`src/lib/commandState.ts`'s `deriveCommandPosture()` produces a
`CommandPosture`: `RESPOND | RECOVER | PROTECT | FOCUS | STEADY | UNKNOWN`.
This is a distinct vocabulary from Human Systems' own `SystemPostureBand`
(`ENGAGE | STEADY | PROTECT | RECOVER | RESET | UNKNOWN`,
`assessed-context.ts` / §3), and the module header is explicit about why:
**Human Systems contributes to the command posture. Human Systems does
NOT become the command posture.** The MSN-0364-era Captain's Chair used
Human Systems' posture band directly as the page headline — that conflated
"what is my capacity" with "what kind of day is this," which is wrong
whenever something material is happening *outside* Human Systems (an
emergency, an HQ outage, a full calendar) while capacity itself reads fine,
or vice versa. `CommandStatus.tsx`'s "Why?" expansion (§9.1 of the mission
brief) exists precisely so the Human Systems contribution stays visible as
an explanation without becoming the headline.

`deriveCommandPosture()`'s inputs are themselves already-interpreted:
`hasEnvironmentConcern` (from `deriveCommandStatus()`, §6, which already
folds in operational risk, escalations, emergency tier, Brief interrupt-now,
and HQ Status `ATTENTION`), a genuine curated `needsYouCount`
(`buildNeedsYouItems().length` — never a raw backlog count),
`humanSystemsUnavailable`/`hasCheckinToday`/`humanSystemsPosture` (Human
Systems' own contract, §3), and `meaningfulCommitmentsToday` (Calendar
event count, but only when `calendarStatus === 'ok'` — 0 when
disconnected/errored, never treated as "nothing scheduled"). The module
does not re-derive any domain's own truth; it composes.

Derivation precedence, in order:

1. **RESPOND** — `hasEnvironmentConcern || needsYouCount > 0`. A material
   external condition or a genuine human-attention item always wins,
   regardless of recovery posture ("emergency overrides calm presentation;
   no hiding behind recovery posture" — mission scenario D).
2. **UNKNOWN** — if RESPOND doesn't fire: `humanSystemsUnavailable` (the
   `/context` fetch itself failed) or `!hasCheckinToday` (no capacity
   check-in yet today). Today is unknown, not clear, in either case — this
   mirrors the honesty rule in §3/§10 (no fabricated "clear" day when the
   underlying data simply isn't in yet).
3. **RECOVER** — Human Systems posture is `RECOVER`. Recovery conditions
   dominate discretionary demand; nothing external overrode it in step 1,
   so nothing does now either.
4. **PROTECT** — Human Systems posture is `PROTECT` or `RESET`. Capacity is
   constrained; same reasoning as RECOVER, one notch less severe.
5. **FOCUS** — none of the above, and `meaningfulCommitmentsToday > 0`.
   Capacity is workable and there is something on the calendar worth
   protecting attention for.
6. **STEADY** — the fallback: capacity is workable and nothing external or
   scheduled needs priority. A normal operating day.

Each result carries a `headline` (the posture word itself, e.g.
`"RESPOND"`) and a one-sentence `explanation` safe to read aloud verbatim —
this is what LifeOS's TTS reads (§12) and what both pages render as the
TODAY/day headline.

## 12. LifeOS presentation model and sanctuary mode

Phase 2 rewrote `hub/page.tsx` from a permanent 5-badge situation strip
(Recovery Posture / Operational Risk / Interrupt Now / Emergency Alerts /
Background Systems) plus a raw "Live Alerts" list into the mission's
target ~3–10-second information model, answering five questions and
nothing else:

1. Day / date / time.
2. Command posture headline + one-sentence explanation
   (`deriveCommandPosture()`, §11).
3. Next commitments — today's Calendar events, honest on
   `disconnected`/`error`/empty (§4) — **omitted entirely in sanctuary
   mode**.
4. Needs You — 0–3 items from the same `buildNeedsYouItems()` Captain's
   Chair uses (§5); a calm end state ("Nothing else needs you.") when
   empty.
5. World / intelligence headline (`deriveIntelligenceHeadline()`, §7) —
   also omitted in sanctuary mode.
6. A tiny one-line HQ status readout (`useHqStatusSummary()`, §8):
   "Operating normally" / "Degraded — no action required" / "Needs you —
   {summary}" / "HQ status unknown."

**Sanctuary (quiet) mode:** when `commandPosture.posture` is `PROTECT` or
`RECOVER` **and** `needsYouItems.length === 0`, the Next and World sections
collapse to nothing — only the posture headline, Needs You's empty state,
and the HQ line remain. This never hides genuine risk: `RESPOND` always
takes priority in `deriveCommandPosture()`'s precedence (§11), so an
emergency or a genuine Needs You item forces the page out of sanctuary
before the quiet-mode check ever runs.

Text-to-speech ("Read aloud") was rewritten to read the command picture —
posture headline + explanation, the next commitment if any, the Needs You
count and top item (or "Nothing needs you right now"), and the
intelligence headline/detail — instead of a raw alerts inventory.

## 13. What this mission delivered

The mission brief described a two-phase change: a required P0 correctness
repair (§3, "REQUIRED CORRECTNESS REPAIRS — DO FIRST"), landed first as its
own reviewable change, and a broader LifeOS vNext / Captain's Chair vNext
presentation redesign, landed second as Phase 2. Both are now complete.

**Phase 1 — P0 correctness repair:**
- Both surfaces consume the canonical Human Systems assessed context
  exclusively; the mock-fallback posture path (`useROSData()` /
  `?? mockPosture`) is gone from both pages (§3).
- `deriveCommandStatus()` rewritten onto the canonical `SystemPostureBand`
  vocabulary, with distinct, tested wording for known/no-checkin/
  unavailable states.
- Removed the dead second capacity-read hook (`useCapacityToday`).
- P3 doc correction (Calendar wiring — see
  `HQ-V1-INTEGRATION-CONTRACTS.md`).

**Phase 2 — presentation redesign:**
- `src/lib/commandState.ts`: the new shared composition layer
  (`deriveCommandPosture()`, `buildNeedsYouItems()`,
  `deriveIntelligenceHeadline()`) — §1, §11, §12.
- `deriveCommandStatus()` extended to consume the canonical, interpreted HQ
  Status summary (`hqPosture`/`hqSummary`/`hqUnavailable`) instead of a raw
  failed-job count; only HQ `ATTENTION` counts as an environment concern,
  `DEGRADED` does not — §8.
- `useAgentHealth()` deleted; replaced by `useHqStatusSummary()` — §8.
- `useAttentionCounts()`, `useEvolutionSignal()`, and
  `useNotebookReadyCount()` centralized into `captainsChairData.ts` so both
  surfaces share the raw-data fetches, not just the interpretation — §5.
- Captain's Chair restructured into the target information architecture:
  TODAY (`CommandStatus.tsx`, posture headline + "Why?" drill-down) → NEEDS
  YOU → INTELLIGENCE (`Intelligence.tsx`) → AHEAD (unchanged) → CAPACITY
  (`Capacity.tsx`, the dedicated Human Systems display) → HQ EVOLUTION
  (`HqEvolution.tsx`, hides itself when empty) → SYSTEM STATUS
  (`SystemStatus.tsx`, tiny). The old Situation panel's Personal/
  Environment/Systems fold (`Situation.tsx`) is deleted — its
  responsibilities are now split across Intelligence, Capacity, and System
  Status, each consuming one canonical contract instead of re-curating raw
  signals on the page.
- LifeOS rewritten onto the target ambient information model, with
  sanctuary/quiet mode — §12.

**Still open (tracked, not addressed by either phase):**
- The Alerts taxonomy audit (decision/escalation/blocked/review/wellness
  vs. `NeedsYouKind`/`AlertSeverity`) named in the original mission brief.
  `src/lib/alerts.ts`'s `AlertSeverity` still does not map 1:1 onto
  `NeedsYouKind` — see `HQ-V1-INTEGRATION-CONTRACTS.md`'s "known remaining
  duplication" section. This is an audit, not a required repair, per the
  mission brief's own scoping.
- Ready Room's own assessed execution-state contract (analogous to Human
  Systems' `assessed-context.ts`) does not exist yet; both surfaces still
  read a personal-tasks reminder slice (`useReminders()`) rather than a
  full execution-state summary (§2, `HQ-V1-INTEGRATION-CONTRACTS.md`).
