// GET /api/comms — list comms_content items for the pipeline page.
// Optional ?status=opportunity|draft|review|approved|ready_to_publish|published

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

const STATUS_ORDER = [
  'opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published',
];

export async function GET(req: NextRequest) {
  const status = req.nextUrl.searchParams.get('status');
  // Phase 1C: domain filter — best-effort, derived via signal_source_id join
  // below (comms_content itself has no domain column; items created outside
  // the signal flow, e.g. via capture, have no domain and are treated as
  // 'operational' to match content_signals' own default).
  const domain = req.nextUrl.searchParams.get('domain');
  try {
    const sb = await createSupabaseServerClient();
    let query = sb
      .from('comms_content')
      .select('id,title,pillar,status,source_kind,source_ref,signal_source_id,notes,body,draft_generated_at,sensitive,created_at,updated_at')
      .neq('status', 'archived')
      .order('created_at', { ascending: false });
    if (status) query = query.eq('status', status);
    const { data, error } = await query;
    if (error) throw error;
    const rawItems = data ?? [];

    const signalIds = [...new Set(rawItems.map(i => i.signal_source_id).filter(Boolean))];
    const domainMap: Record<string, string> = {};
    if (signalIds.length > 0) {
      const { data: sigRows } = await sb
        .from('content_signals')
        .select('event_id_text,domain')
        .in('event_id_text', signalIds);
      for (const r of sigRows ?? []) domainMap[r.event_id_text] = r.domain;
    }
    let items = rawItems.map(i => ({
      ...i,
      domain: (i.signal_source_id && domainMap[i.signal_source_id]) || 'operational',
    }));
    if (domain === 'health' || domain === 'operational') {
      items = items.filter(i => i.domain === domain);
    }

    // Pipeline counts
    const counts: Record<string, number> = {};
    for (const s of STATUS_ORDER) counts[s] = 0;
    for (const item of items) {
      if (counts[item.status] !== undefined) counts[item.status]++;
    }

    return NextResponse.json({ items, counts, status_order: STATUS_ORDER });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Comms query failed', detail }, { status: 500 });
  }
}
