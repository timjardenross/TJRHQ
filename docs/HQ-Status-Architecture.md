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
- **Fixed in passing**: an exhaustive diff of every `domain_key` ever
  inserted into `domain_registry` (across all 190+ migrations) against
  `SCHEDULER_JOBS`, cross-checked against live `record_heartbeat()` call
  sites so only genuinely-live jobs were added, surfaced **eight**
  domain_keys that already heartbeat in production but had drifted out of
  this hand-maintained registry: `self_improvement_cycle`,
  `capacity_checkins`, `intraday_media_collection` (found in the initial
  pass), plus `content_intelligence`, `engineering_handoff`,
  `weekly_health_synthesis`, `follow_through_engine`, and
  `emergency_alert_hourly_summary` (found in a follow-up audit pass — see
  §4). One existing entry's capability was also corrected:
  `content_pipeline` was mapped to `morning_intelligence` by label
  similarity; it is actually `intelligence/proactive_cadences.py`'s Content
  Workbench promotion/drafting job, now correctly mapped to a new
  `content_workbench` capability alongside `content_intelligence`. Every
  other `domain_registry` key not in `SCHEDULER_JOBS` is either explicitly
  retired (`active = false`, e.g. `appointment_prep`, `pain_escalation`,
  `stale_missions_job`) or a `data`-category content-freshness domain
  (`missions`, `decisions`, `health_daily_logs`, etc.) that was out of this
  registry's scope before this PR too. All additive fixes, not redesigns.

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

### Registry drift audit (method + result)

To bound that drift risk concretely rather than leave it as an abstract
"known risk," every `domain_key` literal ever inserted into `domain_registry`
across all migrations was diffed against `SCHEDULER_JOBS`, then every
`job`/`infra`-category leftover was checked two ways: (1) does a later
migration set `active = false` for it (confirmed retired), and (2) does a
repo-wide grep for `record_heartbeat`/`record_heartbeat_ok`/
`record_heartbeat_failed` calls show it's still actually written today
(confirmed live, not just registered). Result:

- **8 genuinely live, previously-invisible domains** — added (see §1).
- **`appointment_prep`, `pain_escalation`, `stale_missions_job`,
  `decision_review`\*, `knowledge_freshness`\*** and others — confirmed
  `active = false` in `domain_registry` (migrations 0113/0114), correctly
  absent. \*`decision_review`/`knowledge_freshness` were retired in 0114
  then explicitly reactivated in migration 0172 once a real live writer
  (`intelligence/proactive_cadences.py`) replaced the dead one — both ARE in
  `SCHEDULER_JOBS` today, correctly, matching their reactivated state.
- **`missions`, `decisions`, `health_daily_logs`, `physical_readiness`,
  `advisory_sessions`, `governance_records`, `insight_outcomes`,
  `lessons_learned`, `recovery_pulses`** — `data`-category content-freshness
  domains, a different concept from scheduler jobs; out of `SCHEDULER_JOBS`'
  scope by design, not a gap.

No further drift found after this pass.

## 5. Cadence / staleness — resolved (HQ V1 Integration QA)

`domain_registry.expected_cadence_minutes` + `grace_period_minutes` do exist
and, via the pre-existing `domain_heartbeat_latest` view (migration 0071,
the original verification-engine design), already compute an `is_stale`
verdict. This uplift originally did **not** wire that in, for two reasons:

1. **Coverage gap.** Cross-checking `domain_registry` against
   `SCHEDULER_JOBS` showed most, but not provably all, registry entries had
   a matching `domain_registry` row with real cadence data.
2. **Cron-edge-case risk.** Preferring "schedule known, freshness verdict
   unavailable" over an automated stale/fresh boolean unless DST,
   weekly/monthly edges, and restart-timing were all proven safe.

**Resolved by the HQ V1 Integration QA mission:**

1. The exhaustive registry-drift audit that mission ran found and fixed the
   only 3 remaining gaps (`hq_evolution_cycle`, `google_tasks_sync`,
   `episodic_memory_decay` — migrations 0192/0193), closing reason #1.
2. Reason #2 is sidestepped entirely rather than solved by proof: no new
   cadence math was written. `fetchStaleOkDomainKeys()`
   (`lib/agentStatusJobs.ts`) reads the *already-computed* `is_stale`
   column from `domain_heartbeat_latest` — a mature view that has been
   computing this exact DST/weekly/monthly-safe verdict against
   `expected_cadence_minutes`/`grace_period_minutes` since migration 0071,
   independent of and predating this workbench. A job currently reporting
   `'ok'` that the view flags `is_stale` is downgraded to `'unknown'`
   (never fabricated as `'failed'` — the job may simply have stopped
   heartbeating, which is exactly the "missing data, not known-bad data"
   case) before reaching `computeCapabilities()`. `'failed'`/`'unknown'`
   jobs need no such check — they already correctly aren't `'healthy'`.

`cadenceLabel` is unchanged and still shown verbatim (a human-readable
string, e.g. "Weekly · Fri 16:30") — this is a status-value fix, not a
label replacement. See `lib/__tests__/agentStatusJobs.staleOk.test.ts` for
the regression coverage.

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

### Resolved (HQ V1 Integration QA): ATTENTION now distinguishes a fresh failure from a persistent one

Mission §25-26 draws a line between a **system issue** ("HQ knows about it
and will retry/recover automatically" — no human task) and something that
**needs attention** ("cannot recover automatically or materially blocks a
capability"). Previously the rule collapsed that distinction for critical
capabilities: a critical job's *single* latest `failed` heartbeat produced
`unavailable` → `ATTENTION` immediately, even if that job retries every few
minutes and would self-heal before a human ever looks — e.g. a lone,
transient `core_events` blip read identically to `core_events` being stuck
down for hours. `domain_heartbeats_latest` only exposes the single most
recent attempt per domain, which wasn't enough to tell "just failed once"
from "failed N times in a row."

**Fix (HQ V1 Integration QA, this mission):** `fetchAgentStatusEntries()`
(`lib/agentStatusJobs.ts`) now checks, only for critical jobs that are
*currently* `failed` (the common healthy-HQ case adds zero extra queries),
whether the immediately preceding heartbeat for that same `domain_key` was
`ok` — a bounded, per-domain read of the raw `domain_heartbeats` event log
(the same table/shape History already reads; see `fetchIsolatedFailureFlags`).
If so, the failure is marked `isIsolatedFailure: true` and
`computeCapabilities()` (`lib/hqStatusInterpreter.ts`) holds the capability
at `degraded` for that cycle instead of escalating to `unavailable` —
letting a job that fails once and recovers on its own next scheduled run
self-heal without ever crossing into `ATTENTION`. Two consecutive failures
(or a missing/errored history query) still escalate to `unavailable` →
`ATTENTION` exactly as before: the default is fail-safe (escalate), and only
a *positively confirmed* isolated first attempt relaxes it. This is
deliberately narrow — a two-row persistence check, not general cadence math
— per the "do not add cadence math unless a correctness defect makes it
necessary" instruction. See `lib/__tests__/hqStatusInterpreter.test.ts` and
`lib/__tests__/agentStatusJobs.isolatedFailure.test.ts` for the regression
coverage.

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
