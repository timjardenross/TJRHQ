// GET /api/briefs — full intelligence_briefs archive, independent of any
// one domain workbench. Briefs synthesize across domains (see
// brief_generator.py); nesting their only listing under
// /intelligence-workbench (OSINT-branded) was the actual gap — this is
// that list. /briefs/[id] (see /api/briefs/[id]) is now the canonical
// detail view; /intelligence-workbench/brief/[id] stays live for its
// legacy QA/Publish/approval actions — see BRIEFS_CANONICAL_UPLIFT.md §3.
//
// 2026-09 Briefs canonical uplift: select widened to include the new
// content-model columns (top_events, comparison, coverage, domain_picture,
// known_unknowns, morning_cycle_id, bottom_line, forward_watch) so Latest
// and Timeline can render the brief as a real intelligence product instead
// of a truncated executive_snapshot string.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type { BriefListItem } from '@/lib/briefsShared';

const BRIEF_LIST_COLUMNS =
  'brief_id,generated_at,published_at,period_start,period_end,overall_risk,approval_status,' +
  'executive_snapshot,bottom_line,forward_watch,morning_cycle_id,top_events,comparison,coverage,' +
  'domain_picture,known_unknowns';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    // .returns<>() pins the row shape explicitly — the widened select string
    // above (16 columns incl. several jsonb ones) trips postgrest-js v2's
    // type-level select parser into a GenericStringError fallback otherwise.
    const { data, error } = await sb
      .from('intelligence_briefs')
      .select(BRIEF_LIST_COLUMNS)
      .order('generated_at', { ascending: false })
      .limit(100)
      .returns<BriefListItem[]>();
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
