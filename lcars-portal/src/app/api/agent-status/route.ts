// Agent/Job Status API — reads scheduler job state from domain_heartbeats.
//
// The platform has no scheduler_runs or job_log table (confirmed: only 3
// JSON schema files exist in schemas/). The single source of truth for
// scheduler job state is domain_heartbeats, written by every scheduled job
// via core/platform/heartbeat.py::record_heartbeat(). This route queries
// domain_heartbeats_latest (a DISTINCT ON view — one row per domain_key,
// most recent) so infrequent jobs (weekly, nightly) are never buried by
// high-frequency domains that write every few minutes.
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
  { domainKey: 'captains_daily_briefs',                   label: 'Captain\'s Daily Briefs',           domain: 'intelligence'  },
  { domainKey: 'morning_brief',                           label: 'Morning Brief (Telegram)',           domain: 'intelligence'  },
  { domainKey: 'intelligence_collection',                 label: 'Daily Source Collection',            domain: 'intelligence'  },
  { domainKey: 'intraday_status_collection',              label: 'Intraday Status Collection',         domain: 'intelligence'  },
  { domainKey: 'intelligence_suppression_audit',          label: 'Suppression Audit',                  domain: 'intelligence'  },
  { domainKey: 'health_osint_weekly_fetch',               label: 'Health OSINT Weekly Fetch',          domain: 'health'        },
  { domainKey: 'health_osint_auto_curation',              label: 'Health OSINT Auto-Curation',         domain: 'health'        },
  { domainKey: 'health_mission_correlation',              label: 'Health-Mission Correlation',         domain: 'health'        },
  { domainKey: 'downdetector_priority_tiered_collection', label: 'Downdetector Priority Polling',     domain: 'intelligence'  },
  { domainKey: 'downdetector_threshold_recompute',        label: 'Downdetector Threshold Recompute',   domain: 'intelligence'  },
  { domainKey: 'source_fidelity_audit',                   label: 'Source Fidelity Audit',              domain: 'intelligence'  },
  { domainKey: 'evolved_captain_insight_generation',      label: 'Captain Insight Generation',         domain: 'intelligence'  },
  { domainKey: 'attention_engine_drill',                  label: 'Attention Engine Weekly Drill',      domain: 'intelligence'  },
  { domainKey: 'brief_qa_agent_nightly',                  label: 'Brief QA Pre-screen',                domain: 'intelligence'  },
  { domainKey: 'adhd_task_nudge',                         label: 'ADHD Task Nudge',                    domain: 'human-systems' },
  // intelligence/proactive_cadences.py jobs (migrated from Slack bot 2026-08-23)
  { domainKey: 'decision_review',                         label: 'Decision Review (Fri)',              domain: 'intelligence'  },
  { domainKey: 'weekly_review',                           label: 'Weekly Review (Fri)',                 domain: 'intelligence'  },
  { domainKey: 'knowledge_freshness',                     label: 'Knowledge Freshness (Wed)',           domain: 'intelligence'  },
  { domainKey: 'decision_outcome_reminder',               label: 'Decision Outcome Reminder (Wed)',     domain: 'intelligence'  },
  { domainKey: 'forgotten_decisions',                     label: 'Forgotten Decisions (Mon+Thu)',       domain: 'intelligence'  },
  { domainKey: 'fortnightly_idea_review',                 label: 'Fortnightly Idea Review',            domain: 'intelligence'  },
  { domainKey: 'shakedown_digest',                        label: 'Shakedown Digest (Daily)',            domain: 'platform'      },
  { domainKey: 'monthly_lessons_digest',                  label: 'Monthly Lessons Digest',             domain: 'intelligence'  },
  { domainKey: 'ko_monthly_brief',                        label: 'KO Monthly Brief',                   domain: 'intelligence'  },
  { domainKey: 'mission_registry_sync',                   label: 'Mission Registry Sync',              domain: 'platform'      },
  { domainKey: 'content_pipeline',                        label: 'Content Pipeline',                   domain: 'intelligence'  },
  { domainKey: 'pending_research_sweep',                  label: 'Pending Research Sweep',             domain: 'intelligence'  },
  // human_systems_scheduler.py ─────────────────────────────────────────────
  { domainKey: 'human_systems',                           label: 'Human Systems Scheduler',            domain: 'human-systems' },
  // Platform domains (heartbeats from TS or verification side) ─────────────
  { domainKey: 'knowledge_library',                       label: 'Knowledge Library',                  domain: 'platform'      },
  { domainKey: 'core_events',                             label: 'Event Bus',                          domain: 'platform'      },
  { domainKey: 'command_centre_backend',                  label: 'Command Centre Backend',             domain: 'platform'      },
  { domainKey: 'verification_engine',                     label: 'Verification Engine',                domain: 'platform'      },
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

    // Query domain_heartbeats_latest — a DISTINCT ON view that returns exactly
    // one row per domain_key (most recent). Avoids the old pattern of fetching
    // N rows ordered by checked_at DESC and deduplicating in JS, which buried
    // infrequent jobs (weekly, nightly) when high-frequency domains generated
    // 35k+ rows and the per-request limit excluded older records.
    const knownKeys = SCHEDULER_JOBS.map((j) => j.domainKey);
    const { data, error } = await sb
      .from('domain_heartbeats_latest')
      .select('domain_key, status, detail, error_message, checked_at')
      .in('domain_key', knownKeys);

    if (error) throw error;

    // Build lookup map — one row per domain guaranteed by the view.
    const latestByDomainKey = new Map<string, {
      status: string;
      detail: string | null;
      error_message: string | null;
      checked_at: string | null;
    }>();
    for (const row of data ?? []) {
      latestByDomainKey.set(row.domain_key, row);
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
