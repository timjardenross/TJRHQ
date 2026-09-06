# HQ Status — Architecture

Route: `/agent-status-workbench` (title "HQ Status" in `lib/workbenches.ts`;
the route path itself is unchanged — see Migration below). This document
describes the implementation as it exists after the 2026-09-06 "HQ Status"
uplift, not aspiration. It replaces the mission spec's own audit questions
with their answers.

## 1. What changed vs. what was preserved

The prior "Agent & Job Status" workbench (Phase 3, same date) already had:
System Health / Source Health / Pipeline Health / Jobs tabs, the
`domain_heartbeats_latest` dedup view, a hand-maintained job registry, and
explicit retired/non-live handling (`shakedown_digest`, `human_systems`).
All of that is preserved. This uplift added one new layer — interpretation
— on top, and did not touch the underlying telemetry:

- **Preserved, unchanged**: `domain_heartbeats` / `domain_heartbeats_latest`
  as the sole scheduler-truth source; `record_heartbeat()`; the exclusion of
  `core_events` as a scheduler-lifecycle log; the Sources tab's ownership of
  detailed source-health UI; the read-only boundary; the 30s auto-refresh on
  the Automations (formerly "Jobs") tab.
- **New**: a deterministic interpreter (`lib/hqStatusInterpreter.ts`) that
  turns job/source/pipeline signals into an HQ-level posture; a capability +
  criticality field on every job in the registry; a History tab; a Sources
  tab that nests the old separate Source Health / Pipeline Health tabs
  behind one secondary toggle instead of two top-level tabs; a small stable
  Captain's-Chair/LifeOS summary shape.
- **Fixed in passing**: three domain_keys that already heartbeat and already
  have `domain_registry` rows (`self_improvement_cycle`, `capacity_checkins`,
  `intraday_media_collection`) had drifted out of the hand-maintained
  `SCHEDULER_JOBS` registry — a real gap the mission's own audit flagged as
  a drift risk (job registry duplication). Added, not redesigned.

## 2. Telemetry sources (unchanged from Phase 3)

- `domain_heartbeats` (migration 0071): rolling event log, one row per run
  attempt. `domain_key`, `checked_at`, `status` (`ok|failed|skipped`),
  `detail`, `error_message`, `latency_ms`.
- `domain_heartbeats_latest` (migration 0168): `DISTINCT ON (domain_key)`
  view, most recent row per domain. This — not the older, richer
  `domain_heartbeat_latest` (singular) view from migration 0071 — is what
  the app queries; it exists specifically so infrequent jobs aren't buried
  by high-frequency ones in a top-N-rows-deduped-in-JS approach.
- `domain_registry`: static config, one row per domain, with
  `expected_cadence_minutes` + `grace_period_minutes` (a real, DB-native
  schedule definition) and a narrow `critical` boolean (migration 0173,
  "P1 for the morning-brief narrative only"). **Not used for computed
  stale/fresh verdicts in this uplift** — see §5.
- `record_heartbeat()` (`core/platform/heartbeat.py`): the single write path
  every scheduled job uses; POSTs directly to the REST API, never raises.

## 3. Why `core_events` is not a scheduler-lifecycle source

`core_events` (the Event Bus) is a poll-based index over domain-specific
detail tables and has zero agent lifecycle events. It does itself heartbeat
under `domain_key='core_events'` — that's `core_events`-as-one-of-44-
monitored-domains, not `core_events`-as-a-log-of-other-jobs. Querying it for
"when did job X last run" would produce misleading results. This was true
before this uplift and remains true; nothing here changes it.

## 4. The job registry (`lib/agentStatusJobs.ts`)

`SCHEDULER_JOBS` is a hand-maintained array: `domainKey`, `label`, `domain`,
`cadenceLabel`, and (new) `capability` + `criticality`, plus optional
`retired`/`disabled` flags. This is the "job declares metadata once" model —
telemetry still comes from `domain_heartbeats`; this registry only supplies
the static facts telemetry can't (what a domain_key means to a human, what
capability it feeds, how material its failure is).

`retired`/`disabled` are **declared facts**, not inferred from missing
heartbeats: `shakedown_digest` is `retired: true` (confirmed retired
2026-08-27), `human_systems` is `disabled: true` (confirmed non-live since
2026-07-07 — its sole invoker path doesn't exist in the live repo). A job
in either state reports that status directly in `AgentStatusEntry.status`
(`'retired'` / `'disabled'`) rather than falling through to `'unknown'` —
so the UI never shows "Unknown/broken" for a state that's actually known
and intentional (mission §15). `NON_LIVE_DOMAIN_KEYS` is derived from these
flags, not maintained separately, so retirement/disablement is declared in
exactly one place.

A canonical, non-duplicated registry (job metadata declared in the Python
scheduler code itself, consumed here) was considered and rejected as
out-of-scope for this uplift: it would require a cross-language contract
(Python scheduler → TS workbench) that doesn't exist yet. Classified
**FUTURE** per the mission's own audit categories — the current
hand-maintained list is a known, bounded drift risk, not a blocker.

## 5. Cadence / staleness — Phase A only, deliberately

`domain_registry.expected_cadence_minutes` + `grace_period_minutes` do exist
and, via the older `domain_heartbeat_latest` view, could support a computed
`is_stale` verdict. This uplift does **not** wire that in, for two reasons:

1. **Coverage gap.** Cross-checking `domain_registry` against
   `SCHEDULER_JOBS` shows most, but not provably all, of the 44 registry
   entries have a matching `domain_registry` row with real cadence data —
   several were added to `SCHEDULER_JOBS` across many migrations
   (0071/0072/0083/0171/0172/0174/0176/0177/0180/0181/0188) and a silent gap
   would mean some jobs get a computed verdict and others don't, which is
   worse than consistent labels.
2. **Cron-edge-case risk.** The mission spec itself (§13, §41) explicitly
   prefers "Schedule known, freshness verdict unavailable" over an
   automated stale/fresh boolean unless DST, weekly/monthly edges, and
   restart-timing are all proven safe — none of that proving work was done
   here.

So this uplift keeps `cadenceLabel` (a human-readable string, e.g.
"Weekly · Fri 16:30") exactly as Phase 3 left it, shown alongside computed
status rather than replacing it. Wiring real cadence math is Phase B,
tracked as **FUTURE**.

## 6. The interpreter (`lib/hqStatusInterpreter.ts`)

Pure, framework-free, unit-tested without a DB
(`lib/__tests__/hqStatusInterpreter.test.ts`, 21 cases). Pipeline:

```
domain_heartbeats (via lib/agentStatusJobs)
  + pipeline-stage signal (existing Phase 26 views)
  + source-health signal (existing intelligence/health source views)
        ↓
computeCapabilities()   — group live (non-retired/disabled) jobs by
                          capability, compute each capability's tone
        ↓
applyCapabilitySignal() — fold in non-job signals (pipeline/source) by
                          taking the more severe tone, never overwriting
        ↓
computePosture()        — NORMAL / DEGRADED / ATTENTION / UNKNOWN from
                          capability tones, weighted by criticality
        ↓
interpretHQStatus()     — headline, impact-first narrative, attention list
        ↓
buildCaptainChairSummary() — small stable summary for Captain's Chair/LifeOS
```

No LLM anywhere in this path (mission §31) — every string is a template
over already-determined state.

### Capability tone rules (per capability, from its own live jobs)

- No live job has ever reported (`known.length === 0`) → **unknown**.
  Missing data is never healthy.
- Any live job `failed` → **unavailable** if the capability's criticality is
  `critical`, else **degraded**. A known failure on a critical capability is
  treated as materially blocking (mission's `domain_registry.critical`
  language: "directly breaks something the Captain relies on today");
  anything less stays a system issue, not a forced HQ-wide signal.
- Some jobs `ok`, some never reported (partial telemetry) → **unknown**. A
  capability is never called healthy on partial evidence.
- All live jobs report ok/skipped → **healthy**.

Retired/disabled jobs are excluded from their capability's job list
entirely — a capability made up solely of retired/disabled jobs produces no
capability result at all (there's nothing live to report on), and a
retired/disabled job's `criticality` never contributes to its capability's
effective criticality.

### HQ posture rules (deterministic, not a failed-job count)

Only `critical` and `important` capabilities are "material" — `supporting`
and `background` capability failures never move HQ posture, however many
of them fail at once (mission §26: machine workload ≠ human workload).
Precedence, most severe first:

1. **ATTENTION** — any critical capability is `unavailable`.
2. **UNKNOWN** — any material capability's tone is `unknown` (and no
   critical capability is `unavailable`). Ranked above DEGRADED
   deliberately: not knowing is treated at least as seriously as knowing
   something is partially broken (mission §40).
3. **DEGRADED** — any material capability is `degraded` (or `unavailable`
   without being critical — the interpreter never actually produces that
   combination today, kept for defensiveness).
4. **NORMAL** — every material capability is healthy.

`needsAttentionCount` counts only critical-and-unavailable capabilities —
never raw failure volume. Seventeen failing supporting jobs contribute
`0` to this count and leave HQ `normal`; see the interpreter tests.

## 7. What each tab owns

- **Status** (`StatusView.tsx`, `/api/agent-status-workbench/overview`):
  the interpreted posture, impact-first narrative, and a capability list.
  Calm when healthy — no per-job table by default.
- **Automations** (`JobsView.tsx`, `/api/agent-status`): the full job table,
  30s auto-refresh, now annotated with each job's capability + criticality
  so a row can be read against the Status tab's verdict.
- **Sources** (`SourcesTabView.tsx` nesting `SourcesView.tsx` +
  `PipelineHealthView.tsx` behind a secondary toggle,
  `/api/agent-status-workbench/{sources,pipeline-quality}`): detailed
  source and pipeline-stage health. Still the sole owner of this UI across
  the platform — Technical/Health OSINT link here rather than duplicating
  it. Emergency Alert Hub's own `/api/emergency-alerts/sources` endpoint
  (which independently re-derives source health from `domain_heartbeats`,
  rather than deferring to this workbench) was identified as a candidate
  duplicate during the audit for this uplift but was **not** absorbed here
  — that's a larger cross-workbench change tracked as **FUTURE**, not
  bundled into this interpretation-layer mission.
- **History** (`HistoryView.tsx`, `/api/agent-status-workbench/history`):
  reads the raw `domain_heartbeats` event log (not `_latest`) over a 72h
  window and collapses each domain's own time series to down/up
  *transitions* only — no per-row flood, no new table. A domain with a
  `failed → ok` transition reports its outage duration; repeated
  consecutive failures and `skipped` transitions are not surfaced.

## 8. Captain's Chair / LifeOS contract

`buildCaptainChairSummary()` produces:

```ts
{
  hq_posture: 'NORMAL' | 'DEGRADED' | 'ATTENTION' | 'UNKNOWN',
  summary: string,               // headline (+ impact, if not normal)
  material_degradations: string[],
  needs_attention_count: number, // genuine attention items only
  unknown_material_count: number,
  last_updated: string,          // ISO timestamp
  freshness: 'live' | 'unavailable',
}
```

Returned as `captainSummary` in the overview API response. Neither
Captain's Chair nor LifeOS UI was touched by this mission — this is only
the small, stable shape a future integration can consume without ever
rendering a wall of job health.

## 9. Read-only boundary

No mutation endpoints exist in this workbench. No retry/rerun/disable/
acknowledge action was added or is planned without a future mission
explicitly authorising and governing it (mission §46).

## 10. Freshness of HQ Status itself

If the overview route's own Supabase queries fail, it returns HTTP 500 with
`posture: 'unknown'` in the body rather than omitting posture — the client
(`StatusView.tsx`) treats a load error as "HQ Status is unavailable" (⚪),
explicitly distinct from "HQ is healthy" (mission §49). It does not attempt
its own partial-success degraded state (e.g. jobs loaded but sources
didn't) — the current implementation is all-or-nothing per request; a
finer-grained per-signal freshness report is **FUTURE**.

## 11. Explicit non-duplication

This uplift did not create a new telemetry table, a new source-health
store, or a new scheduler-lifecycle log. `domain_heartbeats` remains the
single write path; History reads it directly rather than adding a
derived-events table. The only new persistent artifact is code (the
interpreter, the registry fields) — no new migration was required or
written.
