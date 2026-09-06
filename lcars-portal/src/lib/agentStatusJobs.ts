// Shared scheduler-job registry for the Agent & Job Status workbench.
//
// Extracted from api/agent-status/route.ts (Phase 3 uplift, 2026-09-06) so
// the new overview/sources/pipeline-quality routes can compute job-derived
// health (e.g. "is the job feeding this pipeline stage currently failing?")
// without duplicating this 40-entry list. No behavioural change versus the
// original inline array.

/** Known scheduler jobs extracted from intelligence/scheduler.py and
 *  platform-runtime/human_systems_scheduler.py. Each entry maps the
 *  domain_key written to domain_heartbeats to a human label and domain.
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
 *  disabled this session (no dedup/ack, re-nagged every cycle). */
export const SCHEDULER_JOBS: ReadonlyArray<{ domainKey: string; label: string; domain: string; cadenceLabel: string }> = [
  // intelligence/scheduler.py jobs ─────────────────────────────────────────
  { domainKey: 'captains_daily_briefs',                   label: 'Captain\'s Daily Briefs',           domain: 'intelligence',  cadenceLabel: 'Daily · 07:00/12:30/18:00' },
  { domainKey: 'morning_brief',                           label: 'Morning Brief (Telegram)',           domain: 'intelligence',  cadenceLabel: 'Daily · 07:00' },
  { domainKey: 'intelligence_collection',                 label: 'Daily Source Collection',            domain: 'intelligence',  cadenceLabel: 'Daily · 06:00' },
  { domainKey: 'intraday_status_collection',              label: 'Intraday Status Collection',         domain: 'intelligence',  cadenceLabel: 'Every 3h' },
  { domainKey: 'intelligence_suppression_audit',          label: 'Suppression Audit',                  domain: 'intelligence',  cadenceLabel: 'Daily · 06:40' },
  { domainKey: 'health_osint_weekly_fetch',               label: 'Health OSINT Weekly Fetch',          domain: 'health',        cadenceLabel: 'Weekly · Sun 02:00' },
  { domainKey: 'health_osint_auto_curation',              label: 'Health OSINT Auto-Curation',         domain: 'health',        cadenceLabel: 'Weekly · Sun 02:00' },
  { domainKey: 'health_mission_correlation',              label: 'Health-Mission Correlation',         domain: 'health',        cadenceLabel: 'Daily · 07:30' },
  { domainKey: 'downdetector_priority_tiered_collection', label: 'Downdetector Priority Polling',     domain: 'intelligence',  cadenceLabel: 'Every 2h' },
  { domainKey: 'downdetector_threshold_recompute',        label: 'Downdetector Threshold Recompute',   domain: 'intelligence',  cadenceLabel: 'Daily · 05:00' },
  { domainKey: 'source_fidelity_audit',                   label: 'Source Fidelity Audit',              domain: 'intelligence',  cadenceLabel: 'Daily · 06:45' },
  { domainKey: 'evolved_captain_insight_generation',      label: 'Captain Insight Generation',         domain: 'intelligence',  cadenceLabel: 'Every 4h' },
  { domainKey: 'attention_engine_drill',                  label: 'Attention Engine Weekly Drill',      domain: 'intelligence',  cadenceLabel: 'Weekly · Mon 08:00' },
  { domainKey: 'brief_qa_agent_nightly',                  label: 'Brief QA Pre-screen',                domain: 'intelligence',  cadenceLabel: 'Daily · 02:00' },
  { domainKey: 'adhd_task_nudge',                         label: 'ADHD Task Nudge',                    domain: 'human-systems', cadenceLabel: 'Hourly' },
  // intelligence/proactive_cadences.py jobs (migrated from Slack bot 2026-08-23)
  { domainKey: 'decision_review',                         label: 'Decision Review (Fri)',              domain: 'intelligence',  cadenceLabel: 'Weekly · Fri 16:00' },
  { domainKey: 'weekly_review',                           label: 'Weekly Review (Fri)',                 domain: 'intelligence',  cadenceLabel: 'Weekly · Fri 16:30' },
  { domainKey: 'knowledge_freshness',                     label: 'Knowledge Freshness (Wed)',           domain: 'intelligence',  cadenceLabel: 'Weekly · Wed 09:00' },
  { domainKey: 'decision_outcome_reminder',               label: 'Decision Outcome Reminder (Wed)',     domain: 'intelligence',  cadenceLabel: 'Weekly · Wed 09:15' },
  { domainKey: 'forgotten_decisions',                     label: 'Forgotten Decisions (Mon+Thu)',       domain: 'intelligence',  cadenceLabel: '2x/week · Mon+Thu 09:30' },
  { domainKey: 'shakedown_digest',                        label: 'Shakedown Digest (RETIRED 2026-08-27)', domain: 'platform',      cadenceLabel: 'Retired — was Daily · 20:00' },
  { domainKey: 'monthly_lessons_digest',                  label: 'Monthly Lessons Digest',             domain: 'intelligence',  cadenceLabel: 'Monthly · 1st 08:00' },
  { domainKey: 'ko_monthly_brief',                        label: 'KO Monthly Brief',                   domain: 'intelligence',  cadenceLabel: 'Monthly · 1st 08:30' },
  { domainKey: 'mission_registry_sync',                   label: 'Mission Registry Sync',              domain: 'platform',      cadenceLabel: 'Daily · 06:45' },
  { domainKey: 'google_tasks_sync',                       label: 'Google Tasks Sync',                  domain: 'platform',      cadenceLabel: 'Every 15min' },
  { domainKey: 'content_pipeline',                        label: 'Content Pipeline',                   domain: 'intelligence',  cadenceLabel: 'Daily · 06:15' },
  { domainKey: 'pending_research_sweep',                  label: 'Pending Research Sweep',             domain: 'intelligence',  cadenceLabel: 'Every 5min' },
  // Emergency Alert Hub (migration 0174, intelligence/emergency_alerts.py) ──
  { domainKey: 'emergency_alert_nsw_rfs',                 label: 'Emergency Alert Hub — NSW RFS',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_vic',                     label: 'Emergency Alert Hub — VicEmergency',  domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_qld',                     label: 'Emergency Alert Hub — QLD Fire',      domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_sa',                      label: 'Emergency Alert Hub — SA CFS',        domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_act',                     label: 'Emergency Alert Hub — ACT ESA',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_wa',                      label: 'Emergency Alert Hub — WA DFES',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_tas',                     label: 'Emergency Alert Hub — TAS Fire (scrape-tier, not yet implemented)', domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_nt',                      label: 'Emergency Alert Hub — NT SecureNT (scrape-tier, not yet implemented)', domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_nsw',                 label: 'Emergency Alert Hub — BOM NSW/ACT',   domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_nt',                  label: 'Emergency Alert Hub — BOM NT',        domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_qld',                 label: 'Emergency Alert Hub — BOM QLD',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_sa',                  label: 'Emergency Alert Hub — BOM SA',        domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_tas',                 label: 'Emergency Alert Hub — BOM TAS',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_vic',                 label: 'Emergency Alert Hub — BOM VIC',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_wa',                  label: 'Emergency Alert Hub — BOM WA',        domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  { domainKey: 'emergency_alert_bom_act',                 label: 'Emergency Alert Hub — BOM ACT',       domain: 'emergency-alerts', cadenceLabel: 'Every 15min' },
  // human_systems_scheduler.py ─────────────────────────────────────────────
  // Confirmed 2026-08-25: NOT actually live — its only invoker,
  // start_in_process(), is called solely from platform-runtime/app.py,
  // which exists only in a backup directory, not the live repo; its sole
  // live trigger, starfleet-slack-bot.service, has been disabled since
  // 2026-07-07. Kept in this list (rather than removed) so "Unknown/Never"
  // here accurately signals it, instead of silently dropping the row.
  { domainKey: 'human_systems',                           label: 'Human Systems Scheduler',            domain: 'human-systems', cadenceLabel: 'Not currently live — see route.ts comment' },
  // Platform domains (heartbeats from TS or verification side) ─────────────
  { domainKey: 'knowledge_library',                       label: 'Knowledge Library',                  domain: 'platform',      cadenceLabel: 'Hourly' },
  { domainKey: 'core_events',                             label: 'Event Bus',                          domain: 'platform',      cadenceLabel: 'Continuous' },
  { domainKey: 'command_centre_backend',                  label: 'Command Centre Backend',             domain: 'platform',      cadenceLabel: 'Every 5min' },
  { domainKey: 'verification_engine',                     label: 'Verification Engine',                domain: 'platform',      cadenceLabel: 'Every 5min' },
];

/** domainKeys deliberately excluded from "attention" arithmetic — retired
 *  or never-live jobs whose "unknown"/"failed"-looking state is expected,
 *  not a real problem. */
export const NON_LIVE_DOMAIN_KEYS: ReadonlySet<string> = new Set([
  'shakedown_digest',   // retired 2026-08-27
  'human_systems',      // never live, see comment above
]);

export type JobStatus = 'ok' | 'failed' | 'skipped' | 'unknown';

export interface AgentStatusEntry {
  domainKey: string;
  label: string;
  domain: string;
  status: JobStatus;
  lastRun: string | null;
  lastAction: string | null;
  cadenceLabel: string;
}

/** Given the domain_heartbeats_latest rows keyed by domain_key, builds the
 *  full AgentStatusEntry list (including jobs with no heartbeat yet). */
export function buildAgentStatusEntries(
  latestByDomainKey: Map<string, { status: string; detail: string | null; error_message: string | null; checked_at: string | null }>,
): AgentStatusEntry[] {
  return SCHEDULER_JOBS.map((job) => {
    const heartbeat = latestByDomainKey.get(job.domainKey);

    if (!heartbeat) {
      return {
        domainKey: job.domainKey,
        label: job.label,
        domain: job.domain,
        status: 'unknown',
        lastRun: null,
        lastAction: null,
        cadenceLabel: job.cadenceLabel,
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
