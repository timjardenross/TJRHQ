// Shared scheduler-job registry for the HQ Status workbench (route
// /agent-status-workbench).
//
// Extracted from api/agent-status/route.ts (Phase 3 uplift, 2026-09-06) so
// the overview/sources/pipeline-quality/history routes can compute
// job-derived health without duplicating this list.
//
// HQ Status uplift (2026-09-06): added `capability` + `criticality` to each
// entry. This is the "job declares metadata once" half of the interpreter
// pipeline (see lib/hqStatusInterpreter.ts) — the interpreter groups jobs by
// `capability` and weighs failures by `criticality` to produce an honest
// HQ-level posture instead of a raw failed-job count. `criticality` here is
// a superset of domain_registry.critical (migration 0173): that DB flag is
// deliberately narrow (P1-for-the-morning-brief only); this field is the
// broader, workbench-level materiality judgement described in the mission
// spec §27, informed by but not identical to the DB flag.
//
// Also added eight domain_keys that already heartbeat in production
// (confirmed via record_heartbeat()/record_heartbeat_ok()/_failed() call
// sites, not just a domain_registry row) but had drifted out of this
// hand-maintained list — a real gap the mission's own registry audit
// called out as a risk (spec §14):
//   self_improvement_cycle (migration 0180), capacity_checkins (0181),
//   intraday_media_collection (0188) — found in the initial 2026-09-06 pass;
//   content_intelligence (core/content/draft_worker.py), engineering_handoff
//   (core/coordination/delivery_reconciler.py), weekly_health_synthesis
//   (core/health/weekly_synthesis.py), follow_through_engine
//   (intelligence/adhd/follow_through_engine.py), emergency_alert_hourly_summary
//   (intelligence/emergency_alert_summary.py) — found in a second,
//   exhaustive domain_registry-vs-SCHEDULER_JOBS diff during the HQ Status
//   PR audit, cross-checked against live record_heartbeat() call sites so
//   only genuinely-live jobs were added (not merely-registered-but-dead
//   Phase-0 rows). Fixing these closes a false-"never seen" hole rather
//   than adding scope. `content_pipeline`'s capability was also corrected
//   from 'morning_intelligence' to 'content_workbench' in the same pass —
//   it is intelligence/proactive_cadences.py's Content Workbench promotion/
//   drafting job, not an intelligence-briefing job; the original mapping
//   went by label similarity, not the actual code path.
//
// 'data'-category domain_registry rows (missions, decisions, health_daily_
// logs, physical_readiness, advisory_sessions, governance_records,
// insight_outcomes, lessons_learned, recovery_pulses) were deliberately
// left out of this diff — they are content-freshness domains, not
// scheduler jobs, and were out of SCHEDULER_JOBS' scope before this PR too;
// including them would be a scope expansion (a different, data-freshness
// concept) not a drift fix.

export type Criticality = 'critical' | 'important' | 'supporting' | 'background';

/** Known scheduler jobs extracted from intelligence/scheduler.py and
 *  platform-runtime/human_systems_scheduler.py. Each entry maps the
 *  domain_key written to domain_heartbeats to a human label, domain,
 *  cadence, and (for HQ Status) the capability it feeds and how material
 *  its failure is.
 *
 *  `cadenceLabel` (2026-08-25 fix): the workbench previously showed every
 *  job's "last run" as a bare relative time with no cadence context — a
 *  weekly Friday job showing "5d ago" read identically to a broken daily
 *  job showing "5d ago", which is exactly what made the Captain read 21/32
 *  "stale" jobs as "dead" when most were correctly waiting for their next
 *  scheduled slot. This is deliberately a label, not a computed
 *  stale/not-stale verdict — cron-edge-case math (has this job's day
 *  actually come around since the last restart?) is easy to get subtly
 *  wrong; showing the real cadence lets the Captain judge it correctly
 *  instead of trusting a possibly-wrong boolean.
 *  fortnightly_idea_review is deliberately omitted — its cadence was
 *  disabled this session (no dedup/ack, re-nagged every cycle).
 *
 *  `capability` groups jobs into the human-facing outcomes HQ Status
 *  reports on (see CAPABILITIES in hqStatusInterpreter.ts) — never the raw
 *  job list. `criticality` is a materiality hint, not a machine-vs-human
 *  status:
 *    critical    — failure may materially affect HQ or need TJR's attention
 *    important   — failure degrades a real capability but HQ stays usable
 *    supporting  — enrichment/analytics; failure is background noise
 *    background  — retired/disabled/best-effort; never moves HQ posture
 *  `retired` / `disabled` are knowable, deterministic facts (not guesses)
 *  that override heartbeat-derived status entirely — see
 *  buildAgentStatusEntries below. */
export const SCHEDULER_JOBS: ReadonlyArray<{
  domainKey: string;
  label: string;
  domain: string;
  cadenceLabel: string;
  capability: string;
  criticality: Criticality;
  retired?: boolean;
  disabled?: boolean;
}> = [
  // intelligence/scheduler.py jobs ─────────────────────────────────────────
  { domainKey: 'captains_daily_briefs', label: "Captain's Daily Briefs", domain: 'intelligence', cadenceLabel: 'Daily · 07:00/12:30/18:00', capability: 'morning_intelligence', criticality: 'critical' },
  { domainKey: 'morning_brief', label: 'Morning Brief (Telegram)', domain: 'intelligence', cadenceLabel: 'Daily · 07:00', capability: 'morning_intelligence', criticality: 'critical' },
  { domainKey: 'intelligence_collection', label: 'Daily Source Collection', domain: 'intelligence', cadenceLabel: 'Daily · 06:00', capability: 'morning_intelligence', criticality: 'critical' },
  { domainKey: 'intraday_status_collection', label: 'Intraday Status Collection', domain: 'intelligence', cadenceLabel: 'Every 3h', capability: 'technical_intelligence', criticality: 'important' },
  { domainKey: 'intelligence_suppression_audit', label: 'Suppression Audit', domain: 'intelligence', cadenceLabel: 'Daily · 06:40', capability: 'technical_intelligence', criticality: 'supporting' },
  { domainKey: 'health_osint_weekly_fetch', label: 'Health OSINT Weekly Fetch', domain: 'health', cadenceLabel: 'Weekly · Sun 02:00', capability: 'health_intelligence', criticality: 'important' },
  { domainKey: 'health_osint_auto_curation', label: 'Health OSINT Auto-Curation', domain: 'health', cadenceLabel: 'Weekly · Sun 02:00', capability: 'health_intelligence', criticality: 'supporting' },
  { domainKey: 'health_mission_correlation', label: 'Health-Mission Correlation', domain: 'health', cadenceLabel: 'Daily · 07:30', capability: 'health_intelligence', criticality: 'supporting' },
  { domainKey: 'downdetector_priority_tiered_collection', label: 'Downdetector Priority Polling', domain: 'intelligence', cadenceLabel: 'Every 2h', capability: 'technical_intelligence', criticality: 'supporting' },
  { domainKey: 'downdetector_threshold_recompute', label: 'Downdetector Threshold Recompute', domain: 'intelligence', cadenceLabel: 'Daily · 05:00', capability: 'technical_intelligence', criticality: 'background' },
  { domainKey: 'source_fidelity_audit', label: 'Source Fidelity Audit', domain: 'intelligence', cadenceLabel: 'Daily · 06:45', capability: 'technical_intelligence', criticality: 'supporting' },
  { domainKey: 'evolved_captain_insight_generation', label: 'Captain Insight Generation', domain: 'intelligence', cadenceLabel: 'Every 4h', capability: 'technical_intelligence', criticality: 'supporting' },
  { domainKey: 'attention_engine_drill', label: 'Attention Engine Weekly Drill', domain: 'intelligence', cadenceLabel: 'Weekly · Mon 08:00', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'brief_qa_agent_nightly', label: 'Brief QA Pre-screen', domain: 'intelligence', cadenceLabel: 'Daily · 02:00', capability: 'morning_intelligence', criticality: 'supporting' },
  { domainKey: 'adhd_task_nudge', label: 'ADHD Task Nudge', domain: 'human-systems', cadenceLabel: 'Hourly', capability: 'human_systems', criticality: 'background' },
  // follow_through_engine (intelligence/adhd/follow_through_engine.py) runs
  // inside the adhd_task_nudge job slot in intelligence/scheduler.py but
  // heartbeats under its own domain_key — registered late (2026-09-06
  // registry-drift audit), confirmed live.
  { domainKey: 'follow_through_engine', label: 'Adaptive Follow-Through Engine', domain: 'human-systems', cadenceLabel: 'Hourly (adhd_task_nudge slot)', capability: 'human_systems', criticality: 'background' },
  // intelligence/proactive_cadences.py jobs (migrated from Slack bot 2026-08-23)
  { domainKey: 'decision_review', label: 'Decision Review (Fri)', domain: 'intelligence', cadenceLabel: 'Weekly · Fri 16:00', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'weekly_review', label: 'Weekly Review (Fri)', domain: 'intelligence', cadenceLabel: 'Weekly · Fri 16:30', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'knowledge_freshness', label: 'Knowledge Freshness (Wed)', domain: 'intelligence', cadenceLabel: 'Weekly · Wed 09:00', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'decision_outcome_reminder', label: 'Decision Outcome Reminder (Wed)', domain: 'intelligence', cadenceLabel: 'Weekly · Wed 09:15', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'forgotten_decisions', label: 'Forgotten Decisions (Mon+Thu)', domain: 'intelligence', cadenceLabel: '2x/week · Mon+Thu 09:30', capability: 'weekly_review', criticality: 'supporting' },
  { domainKey: 'monthly_lessons_digest', label: 'Monthly Lessons Digest', domain: 'intelligence', cadenceLabel: 'Monthly · 1st 08:00', capability: 'weekly_review', criticality: 'background' },
  { domainKey: 'ko_monthly_brief', label: 'KO Monthly Brief', domain: 'intelligence', cadenceLabel: 'Monthly · 1st 08:30', capability: 'weekly_review', criticality: 'background' },
  { domainKey: 'mission_registry_sync', label: 'Mission Registry Sync', domain: 'platform', cadenceLabel: 'Daily · 06:45', capability: 'platform_core', criticality: 'supporting' },
  { domainKey: 'google_tasks_sync', label: 'Google Tasks Sync', domain: 'platform', cadenceLabel: 'Every 15min', capability: 'ready_room', criticality: 'important' },
  // content_pipeline (intelligence/proactive_cadences.py: opportunity
  // promotion + drafting) and content_intelligence (core/content/
  // draft_worker.py: two-pass AI drafting worker) are both Content
  // Workbench pipeline stages, not intelligence-briefing jobs — corrected
  // 2026-09-06 registry-drift audit: content_pipeline was originally
  // mis-mapped to 'morning_intelligence' (label similarity, not actual
  // code path); verified live in intelligence/proactive_cadences.py.
  { domainKey: 'content_pipeline', label: 'Content Pipeline', domain: 'intelligence', cadenceLabel: 'Daily · 06:15', capability: 'content_workbench', criticality: 'supporting' },
  { domainKey: 'content_intelligence', label: 'Content Draft Worker', domain: 'platform', cadenceLabel: 'Every ~30min', capability: 'content_workbench', criticality: 'supporting' },
  { domainKey: 'pending_research_sweep', label: 'Pending Research Sweep', domain: 'intelligence', cadenceLabel: 'Every 5min', capability: 'technical_intelligence', criticality: 'background' },
  { domainKey: 'intraday_media_collection', label: 'Intraday Media Collection', domain: 'intelligence', cadenceLabel: 'Every 90min', capability: 'technical_intelligence', criticality: 'supporting' },
  { domainKey: 'self_improvement_cycle', label: 'HQ Evolution — Self-Improvement Cycle', domain: 'platform', cadenceLabel: 'Daily · ~07:00', capability: 'hq_evolution', criticality: 'important' },
  // Registered late (2026-09-06 registry-drift audit): confirmed live via
  // record_heartbeat() call sites in core/coordination/delivery_reconciler.py
  // and core/health/weekly_synthesis.py respectively — both write heartbeats
  // today but had never been added to this hand-maintained list.
  { domainKey: 'engineering_handoff', label: 'Engineering Handoff Reconciler', domain: 'platform', cadenceLabel: 'Every 15min', capability: 'platform_core', criticality: 'supporting' },
  { domainKey: 'weekly_health_synthesis', label: 'Weekly Health Synthesis', domain: 'health', cadenceLabel: 'Weekly · Sat 08:00', capability: 'health_intelligence', criticality: 'supporting' },
  // Emergency Alert Hub (migration 0174, intelligence/emergency_alerts.py) ──
  { domainKey: 'emergency_alert_nsw_rfs', label: 'Emergency Alert Hub — NSW RFS', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_vic', label: 'Emergency Alert Hub — VicEmergency', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_qld', label: 'Emergency Alert Hub — QLD Fire', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_sa', label: 'Emergency Alert Hub — SA CFS', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_act', label: 'Emergency Alert Hub — ACT ESA', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_wa', label: 'Emergency Alert Hub — WA DFES', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_tas', label: 'Emergency Alert Hub — TAS Fire (scrape-tier, not yet implemented)', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_nt', label: 'Emergency Alert Hub — NT SecureNT (scrape-tier, not yet implemented)', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'critical' },
  { domainKey: 'emergency_alert_bom_nsw', label: 'Emergency Alert Hub — BOM NSW/ACT', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_nt', label: 'Emergency Alert Hub — BOM NT', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_qld', label: 'Emergency Alert Hub — BOM QLD', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_sa', label: 'Emergency Alert Hub — BOM SA', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_tas', label: 'Emergency Alert Hub — BOM TAS', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_vic', label: 'Emergency Alert Hub — BOM VIC', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_wa', label: 'Emergency Alert Hub — BOM WA', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  { domainKey: 'emergency_alert_bom_act', label: 'Emergency Alert Hub — BOM ACT', domain: 'emergency-alerts', cadenceLabel: 'Every 15min', capability: 'emergency_monitoring', criticality: 'important' },
  // Registered late (2026-09-06 registry-drift audit): confirmed live via
  // intelligence/emergency_alert_summary.py; sibling to the feed-poll jobs
  // above but a derived hourly digest, not a raw feed itself.
  { domainKey: 'emergency_alert_hourly_summary', label: 'Emergency Alert Hub — Hourly Summary Email', domain: 'emergency-alerts', cadenceLabel: 'Hourly', capability: 'emergency_monitoring', criticality: 'important' },
  // human_systems_scheduler.py ─────────────────────────────────────────────
  // Confirmed 2026-08-25: NOT actually live — its only invoker,
  // start_in_process(), is called solely from platform-runtime/app.py,
  // which exists only in a backup directory, not the live repo; its sole
  // live trigger, starfleet-slack-bot.service, has been disabled since
  // 2026-07-07. Kept in this list (rather than removed) so "Disabled" here
  // accurately signals it, instead of silently dropping the row or
  // misreporting it as a broken/unknown live job.
  { domainKey: 'human_systems', label: 'Human Systems Scheduler', domain: 'human-systems', cadenceLabel: 'Disabled since 2026-07-07 — see comment', capability: 'human_systems', criticality: 'background', disabled: true },
  { domainKey: 'capacity_checkins', label: 'Capacity Check-ins', domain: 'human-systems', cadenceLabel: 'On capture (Telegram/portal/Command Centre)', capability: 'human_systems', criticality: 'background' },
  // Platform domains (heartbeats from TS or verification side) ─────────────
  { domainKey: 'knowledge_library', label: 'Knowledge Library', domain: 'platform', cadenceLabel: 'Hourly', capability: 'platform_core', criticality: 'important' },
  { domainKey: 'core_events', label: 'Event Bus', domain: 'platform', cadenceLabel: 'Continuous', capability: 'platform_core', criticality: 'critical' },
  { domainKey: 'command_centre_backend', label: 'Command Centre Backend', domain: 'platform', cadenceLabel: 'Every 5min', capability: 'platform_core', criticality: 'critical' },
  { domainKey: 'verification_engine', label: 'Verification Engine', domain: 'platform', cadenceLabel: 'Every 5min', capability: 'platform_core', criticality: 'critical' },
];

/** domainKeys deliberately excluded from "attention" arithmetic — retired
 *  or never-live jobs whose "unknown"/"failed"-looking state is expected,
 *  not a real problem. Derived from the registry so retired/disabled is
 *  declared once, on the job entry itself (spec §14), not duplicated here. */
export const NON_LIVE_DOMAIN_KEYS: ReadonlySet<string> = new Set(
  SCHEDULER_JOBS.filter((j) => j.retired || j.disabled).map((j) => j.domainKey),
);

export type JobStatus = 'ok' | 'failed' | 'skipped' | 'unknown' | 'retired' | 'disabled';

export interface AgentStatusEntry {
  domainKey: string;
  label: string;
  domain: string;
  status: JobStatus;
  lastRun: string | null;
  lastAction: string | null;
  cadenceLabel: string;
  capability: string;
  criticality: Criticality;
}

/** Given the domain_heartbeats_latest rows keyed by domain_key, builds the
 *  full AgentStatusEntry list (including jobs with no heartbeat yet).
 *  Retired/disabled jobs report that status directly — it's a known,
 *  declared fact from the registry, not a guess from missing heartbeat
 *  data, so it must never be shown as plain "Unknown" (spec §15). */
export function buildAgentStatusEntries(
  latestByDomainKey: Map<string, { status: string; detail: string | null; error_message: string | null; checked_at: string | null }>,
): AgentStatusEntry[] {
  return SCHEDULER_JOBS.map((job) => {
    const heartbeat = latestByDomainKey.get(job.domainKey);

    if (job.retired || job.disabled) {
      return {
        domainKey: job.domainKey,
        label: job.label,
        domain: job.domain,
        status: job.retired ? 'retired' : 'disabled',
        lastRun: heartbeat?.checked_at ?? null,
        lastAction: heartbeat?.detail ?? null,
        cadenceLabel: job.cadenceLabel,
        capability: job.capability,
        criticality: job.criticality,
      };
    }

    if (!heartbeat) {
      return {
        domainKey: job.domainKey,
        label: job.label,
        domain: job.domain,
        status: 'unknown',
        lastRun: null,
        lastAction: null,
        cadenceLabel: job.cadenceLabel,
        capability: job.capability,
        criticality: job.criticality,
      };
    }

    const rawStatus = heartbeat.status;
    const status: JobStatus =
      rawStatus === 'ok' || rawStatus === 'failed' || rawStatus === 'skipped'
        ? rawStatus
        : 'unknown';

    const lastAction =
      status === 'failed'
        ? (heartbeat.error_message ?? heartbeat.detail ?? null)
        : (heartbeat.detail ?? null);

    return {
      domainKey: job.domainKey,
      label: job.label,
      domain: job.domain,
      status,
      lastRun: heartbeat.checked_at ?? null,
      lastAction,
      cadenceLabel: job.cadenceLabel,
      capability: job.capability,
      criticality: job.criticality,
    };
  });
}

/** Shared query used by both /api/agent-status (Jobs tab) and
 *  /api/agent-status-workbench/overview (Needs Attention + Jobs summary) —
 *  one place that knows how to turn domain_heartbeats_latest into
 *  AgentStatusEntry[], so the two routes can't drift on this logic. */
export async function fetchAgentStatusEntries(sb: {
  from: (table: string) => any;
}): Promise<AgentStatusEntry[]> {
  const knownKeys = SCHEDULER_JOBS.map((j) => j.domainKey);
  const { data, error } = await sb
    .from('domain_heartbeats_latest')
    .select('domain_key, status, detail, error_message, checked_at')
    .in('domain_key', knownKeys);

  if (error) throw error;

  const latestByDomainKey = new Map<string, {
    status: string;
    detail: string | null;
    error_message: string | null;
    checked_at: string | null;
  }>();
  for (const row of data ?? []) {
    latestByDomainKey.set(row.domain_key, row);
  }

  return buildAgentStatusEntries(latestByDomainKey);
}
