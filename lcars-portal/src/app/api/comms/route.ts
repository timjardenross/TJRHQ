// GET /api/comms — list comms_content items for the pipeline page.
// Optional ?status=opportunity|draft|review|approved|ready_to_publish|published

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

const STATUS_ORDER = [
  'opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published',
];

export async function GET(req: NextRequest) {
  const status = req.nextUrl.searchParams.get('status');
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
    const items = data ?? [];

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
