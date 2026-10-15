// HQ Status interpreted-overview API (backs the "Status" tab).
//
// This is the HQ HEALTH INTERPRETER layer (spec §29) wired to live data:
// domain_heartbeats_latest (via lib/agentStatusJobs) for job health, plus
// the Phase 26 pipeline-quality views and intelligence/health source-health
// views for two capabilities (Technical/Health Intelligence) where job
// heartbeats alone don't see a stalled pipeline stage or a failing source.
// All three signal sources are read-only and already governed elsewhere in
// this workbench (Automations/Sources tabs) — this route does not invent a
// fourth. Posture math itself lives in lib/hqStatusInterpreter.ts and is
// unit-tested there without a DB; this route's only job is to gather
// signals and hand them to that pure function.
//
// 2026-09-06 HQ Status uplift: replaces the old allClear/attention-list
// shape (which showed a flat "Needs Attention" list of every failed job or
// source) with an interpreted capability posture — NORMAL/DEGRADED/
// ATTENTION/UNKNOWN — plus a small Captain's-Chair-ready summary. Retired
// sources (active=false) and non-live jobs are still excluded from signal
// computation for the same reason as before: a permanently-retired item's
// last-known state must never render as an ongoing problem.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { buildAgentStatusOverview } from '@/lib/agentStatusOverview';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await buildAgentStatusOverview(sb));
  } catch (err) {
    console.error('[agent-status-workbench/overview] read failed:', err);
    return NextResponse.json(
      {
        error: 'overview_read_failed',
        detail: err instanceof Error ? err.message : 'Unknown error',
        // Honest failure shape (spec §49): the caller must never assume
        // NORMAL when this route itself can't determine health.
        posture: 'unknown',
      },
      { status: 500 },
    );
  }
}
