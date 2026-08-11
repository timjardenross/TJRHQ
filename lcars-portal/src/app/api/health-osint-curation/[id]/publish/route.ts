// POST /api/health-osint-curation/[id]/publish — approve an auto-ingested
// health signal, making it visible in the main /health-osint dashboard
// (clears suppressed). Only ever acts on auto_ingested signals — this is
// not a general-purpose unsuppress endpoint.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

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
    const { data: row, error: fetchErr } = await sb
      .from('health_signals')
      .select('signal_id, auto_ingested')
      .eq('signal_id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (!row.auto_ingested) {
      return NextResponse.json({ error: 'Not an auto-ingested signal — nothing to publish' }, { status: 400 });
    }

    const { error: updateErr } = await sb
      .from('health_signals')
      .update({ suppressed: false, auto_ingest_reviewed: true })
      .eq('signal_id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[health-osint-curation/publish]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
