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
//
// 2026-09-06 (Phase 3 uplift): the SCHEDULER_JOBS registry and entry-builder
// moved to lib/agentStatusJobs.ts so the new overview/sources/pipeline-
// quality routes (agent-status-workbench) can share it instead of forking
// a second copy of this 40-entry list. No behavioural change here.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchAgentStatusEntries, type AgentStatusEntry } from '@/lib/agentStatusJobs';

export type { AgentStatusEntry };

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const entries = await fetchAgentStatusEntries(sb);
    return NextResponse.json({ jobs: entries, fetchedAt: new Date().toISOString() });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Agent status query failed', detail }, { status: 500 });
  }
}
