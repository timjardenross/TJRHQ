// Ready Room Google Tasks sync-health indicator (HQ V1 Integration QA §21
// fix). The backend already correctly distinguishes "no tasks" from "sync
// failed" (google-tasks/sync/route.ts) and the google_tasks_sync job is
// already tracked in HQ Status — but Ready Room itself, the page where this
// distinction matters to the Captain in the moment, had no in-page signal
// at all. This route reuses the existing shared heartbeat read
// (fetchAgentStatusEntries, the same one HQ Status's own routes call) for
// just this one domain_key — no new query shape, no new interpretation.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchAgentStatusEntries } from '@/lib/agentStatusJobs';

export interface ReadyRoomSyncStatus {
  status: 'ok' | 'failed' | 'unknown';
  lastAction: string | null;
  lastRun: string | null;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const entries = await fetchAgentStatusEntries(sb);
    const job = entries.find((e) => e.domainKey === 'google_tasks_sync');

    const result: ReadyRoomSyncStatus = {
      status: job?.status === 'failed' ? 'failed' : job?.status === 'ok' ? 'ok' : 'unknown',
      lastAction: job?.lastAction ?? null,
      lastRun: job?.lastRun ?? null,
    };
    return NextResponse.json(result);
  } catch (err) {
    // Honest failure — never claim 'ok' when this route itself can't tell.
    return NextResponse.json(
      { status: 'unknown', lastAction: null, lastRun: null, error: err instanceof Error ? err.message : 'Unknown error' },
      { status: 200 },
    );
  }
}
