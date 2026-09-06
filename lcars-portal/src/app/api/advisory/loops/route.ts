// GET /api/advisory/loops — returns open advisory records (outcome: null).
//
// Goes through the same HTTP-backend-first / Python-CLI-fallback chain as
// /api/advisory (lib/advisoryRuntime.ts) rather than reading
// logs/advisory/ADV-*.json directly off the local filesystem: that
// directory only ever exists on the VM. On Vercel, a direct readdir()
// always throws (ENOENT) and previously fell back to `{ loops: [] }`
// silently — indistinguishable from "every advisory has a recorded
// outcome," which OutcomesView.tsx renders as "everything has one
// recorded." Going through the same backend as every other advisory action
// means this route sees real data whenever the VM/Command Centre is
// reachable, exactly like the rest of the Advisor Hub.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { callAdvisoryAction } from '@/lib/advisoryRuntime';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface AdvisoryRecord {
  advisory_id: string;
  recorded_at: string;
  question: string;
  recommendation: string;
  outcome: string | null;
  confidence_band?: string | null;
  decision_mode?: string;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const result = await callAdvisoryAction('loops', { action: 'loops' }, ['--action', 'loops', '--format', 'json']);
    const records = (Array.isArray((result as { loops?: unknown })?.loops)
      ? (result as { loops: AdvisoryRecord[] }).loops
      : Array.isArray(result)
        ? (result as AdvisoryRecord[])
        : []
    ).filter((r) => !r.outcome);
    records.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
    return NextResponse.json({ loops: records });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load loops', detail }, { status: 502 });
  }
}
