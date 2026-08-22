// GET /api/briefs — full intelligence_briefs archive, independent of any
// one domain workbench. Briefs synthesize across domains (see
// brief_generator.py); nesting their only listing under
// /intelligence-workbench (OSINT-branded) was the actual gap — this is
// that list, /intelligence-workbench/brief/[id] stays the single detail
// view (not duplicated here).

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('intelligence_briefs')
      .select('brief_id,generated_at,published_at,period_start,period_end,overall_risk,approval_status,executive_snapshot')
      .order('generated_at', { ascending: false })
      .limit(100);
    if (error) throw error;

    const briefs = data ?? [];
    const counts = { IN_REVIEW: 0, QA_PASSED: 0, PUBLISHED: 0 } as Record<string, number>;
    for (const b of briefs) {
      if (b.approval_status && b.approval_status in counts) counts[b.approval_status] += 1;
    }

    return NextResponse.json({ briefs, counts });
  } catch (err) {
    console.error('[briefs] read failed:', err);
    return NextResponse.json({ error: 'briefs_read_failed' }, { status: 500 });
  }
}
