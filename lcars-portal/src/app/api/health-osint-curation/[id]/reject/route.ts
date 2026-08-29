// POST /api/health-osint-curation/[id]/reject — reject an auto-ingested
// health signal. Doesn't delete it (keeps a record of what was reviewed
// and declined, same reasoning as this platform's other suppress-don't-
// delete patterns) — sets auto_ingest_reviewed=true (migration 0143) so it
// drops off the /pending queue permanently, and leaves suppressed=true so
// it never shows in the main dashboard either.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';
import { fetchGovernedRow } from '@/lib/governedFetch';

interface HealthSignalRow {
  signal_id: string;
  auto_ingested: boolean;
}

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = serviceClient();
    const fetched = await fetchGovernedRow<HealthSignalRow>(
      sb,
      'health_signals',
      'signal_id',
      params.id,
      'signal_id, auto_ingested',
      {
        predicate: (r) => r.auto_ingested,
        ineligibleStatus: 400,
        ineligibleMessage: () => 'Not an auto-ingested signal — nothing to reject',
      },
    );
    if (!fetched.ok) {
      return NextResponse.json({ error: fetched.error }, { status: fetched.status });
    }

    const { error: updateErr } = await sb
      .from('health_signals')
      .update({ suppressed: true, auto_ingest_reviewed: true })
      .eq('signal_id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[health-osint-curation/reject]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
