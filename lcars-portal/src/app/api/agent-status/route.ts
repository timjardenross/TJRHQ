// Agent/Job Status API — reads scheduler job state from domain_heartbeats.
//
// The platform has no scheduler_runs or job_log table (confirmed: only 3
// JSON schema files exist in schemas/). The single source of truth for
// scheduler job state is domain_heartbeats, written by every scheduled job
// via core/platform/heartbeat.py::record_heartbeat(). This route fetches
// the latest heartbeat row per domain_key and maps it onto the known job
// definitions so the UI can show meaningful labels and domain groupings.
//
// The Event Bus (core_events) is intentionally NOT queried here — it has
// zero agent lifecycle events; querying it for job status would produce
// misleading "last activity" figures from unrelated data sources.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

/** Known scheduler jobs extracted from intelligence/scheduler.py and
 *  platform-runtime/human_systems_scheduler.py. Each entry maps the
 *  domain_key written to domain_heartbeats to a human label and domain. */
const SCHEDULER_JOBS: ReadonlyArray<{ domainKey: string; label: string; domain: string }> = [
  // intelligence/scheduler.py jobs ─────────────────────────────────────────
  { domainKey: 'captains_daily_briefs',                label: 'Captain\'s Daily Briefs',           domain: 'intelligence'  },
  { domainKey: 'morning_brief',                        label: 'Morning Brief (Telegram)',           domain: 'intelligence'  },
  { domainKey: 'intelligence_collection',              label: 'Daily Source Collection',            domain: 'intelligence'  },
  { domainKey: 'intraday_status_collection',           label: 'Intraday Status Collection',         domain: 'intelligence'  },
  { domainKey: 'intelligence_suppression_audit',       label: 'Suppression Audit',                  domain: 'intelligence'  },
  { domainKey: 'health_osint_weekly_fetch',            label: 'Health OSINT Weekly Fetch',          domain: 'health'        },
  { domainKey: 'health_osint_auto_curation',           label: 'Health OSINT Auto-Curation',         domain: 'health'        },
  { domainKey: 'health_mission_correlation',           label: 'Health-Mission Correlation',         domain: 'health'        },
  { domainKey: 'downdetector_priority_tiered_collection', label: 'Downdetector Priority Polling',  domain: 'intelligence'  },
  { domainKey: 'downdetector_threshold_recompute',     label: 'Downdetector Threshold Recompute',   domain: 'intelligence'  },
  { domainKey: 'source_fidelity_audit',                label: 'Source Fidelity Audit',              domain: 'intelligence'  },
  { domainKey: 'evolved_captain_insight_generation',   label: 'Captain Insight Generation',         domain: 'intelligence'  },
  { domainKey: 'attention_engine_drill',               label: 'Attention Engine Weekly Drill',      domain: 'intelligence'  },
  { domainKey: 'brief_qa_agent_nightly',               label: 'Brief QA Pre-screen',                domain: 'intelligence'  },
  { domainKey: 'adhd_task_nudge',                      label: 'ADHD Task Nudge',                    domain: 'human-systems' },
  // platform-runtime/human_systems_scheduler.py jobs ───────────────────────
  { domainKey: 'human_systems',                        label: 'Human Systems Scheduler',            domain: 'human-systems' },
  // Other domains that write heartbeats from the TS side ───────────────────
  { domainKey: 'captains_log',                         label: 'Captain\'s Log',                     domain: 'platform'      },
];

export interface AgentStatusEntry {
  /** Unique identifier matching domain_heartbeats.domain_key. */
  domainKey: string;
  /** Human-readable job label. */
  label: string;
  /** Logical grouping for display. */
  domain: string;
  /** ok | failed | skipped | unknown — directly from the heartbeats table or
   *  "unknown" when no heartbeat has been recorded for this job yet. */
  status: 'ok' | 'failed' | 'skipped' | 'unknown';
  /** ISO-8601 timestamp of the most recent heartbeat (domain_heartbeats.checked_at), or null. */
  lastRun: string | null;
  /** Short detail or error message from the most recent heartbeat, or null. */
  lastAction: string | null;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    // Fetch the 200 most recent heartbeat rows — enough to get at least one
    // row per known job for platforms that have been running a few days.
    // We de-duplicate to the latest row per domain_key in JS so the query
    // stays simple and index-friendly (domain_heartbeats is expected to grow
    // to thousands of rows across all jobs over time).
    const { data, error } = await sb
      .from('domain_heartbeats')
      .select('domain_key, status, detail, error_message, checked_at')
      .order('checked_at', { ascending: false })
      .limit(500);

    if (error) throw error;

    // Build a map: domain_key → latest row (first seen is latest due to desc order).
    const latestByDomainKey = new Map<string, {
      status: string;
      detail: string | null;
      error_message: string | null;
      checked_at: string | null;
    }>();
    for (const row of data ?? []) {
      if (!latestByDomainKey.has(row.domain_key)) {
        latestByDomainKey.set(row.domain_key, row);
      }
    }

    const entries: AgentStatusEntry[] = SCHEDULER_JOBS.map((job) => {
      const heartbeat = latestByDomainKey.get(job.domainKey);

      if (!heartbeat) {
        return {
          domainKey: job.domainKey,
          label: job.label,
          domain: job.domain,
          status: 'unknown',
          lastRun: null,
          lastAction: null,
        };
      }

      const rawStatus = heartbeat.status;
      const status: AgentStatusEntry['status'] =
        rawStatus === 'ok' || rawStatus === 'failed' || rawStatus === 'skipped'
          ? rawStatus
          : 'unknown';

      // Surface the error message for failed runs; detail text for ok/skipped.
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
      };
    });

    return NextResponse.json({ jobs: entries, fetchedAt: new Date().toISOString() });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Agent status query failed', detail }, { status: 500 });
  }
}
