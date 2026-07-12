// POST /api/content/signals-to-opportunities — Phase 1C batch converter.
// Atomically creates comms_content opportunities from top-ranked, non-suppressed
// content_signals. TS port of core/content/signal_opportunity_converter.py — this
// is the path the deployed Next.js app actually calls (Vercel has no Python
// runtime); the Python module remains the CLI/cron entry point for the same
// logic. Both must stay behaviourally identical.
//
// Atomicity: a single Supabase `.insert(rows)` call compiles to one SQL INSERT
// statement, so it is all-or-nothing at the database level — either every row
// lands or the whole request fails and nothing is written. No client-side
// rollback step exists or is needed.
//
// Body: { signal_ids?: string[], limit?: number, min_rank_score?: number, domain?: 'health' | 'operational' | null }
// If signal_ids is given, that exact set is used (the Signals tab's checkbox
// selection) — otherwise the top `limit` signals by rank_score are taken
// (the "batch create top N" one-click flow).
//
// Core logic lives in @/lib/signalsToOpportunities so it can be unit tested
// against a mocked Supabase client — see src/lib/__tests__/signalsToOpportunities.test.ts.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { createOpportunitiesFromSignals } from '@/lib/signalsToOpportunities';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const signalIds: string[] | null = Array.isArray(body.signal_ids) && body.signal_ids.length > 0 ? body.signal_ids : null;
  const limit: number = Number.isFinite(body.limit) ? body.limit : 5;
  const minRankScore: number = Number.isFinite(body.min_rank_score) ? body.min_rank_score : 0.7;
  const domain: 'health' | 'operational' | null = body.domain === 'health' || body.domain === 'operational' ? body.domain : null;

  if (!signalIds && limit < 1) {
    return NextResponse.json({ error: 'limit must be >= 1' }, { status: 400 });
  }

  const sb = serviceClient();

  try {
    const result = await createOpportunitiesFromSignals(sb, { signalIds, limit, minRankScore, domain });

    // Best-effort audit trail — never fail the request on a logging error.
    if (result.status === 'completed' || result.status === 'failed') {
      await sb.from('staff_autonomy_log').insert({
        actor: 'comms-workbench',
        action: 'batch_create_opportunities',
        rationale: `Batch ${result.status}: ${result.created} of ${result.requested} opportunities created (domain=${domain ?? 'both'}, min_rank_score=${minRankScore})`,
        mission_ref: 'MSN-1C-COMMS',
      }).then(() => {}, () => {});
    }

    return NextResponse.json(result);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Batch create failed', detail }, { status: 500 });
  }
}
