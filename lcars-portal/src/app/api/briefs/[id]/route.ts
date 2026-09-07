// GET /api/briefs/[id] — canonical single-brief detail (Briefs canonical
// uplift, Section 19-20). Same read shape as
// /api/intelligence-workbench/brief (brief + linked signals + audit trail)
// plus the new content-model columns (top_events, comparison, coverage,
// domain_picture, known_unknowns, morning_cycle_id). Read-only — no write
// actions here; the legacy QA/Publish/Escalate workflow stays on
// /intelligence-workbench/brief/[id] (see BRIEFS_CANONICAL_UPLIFT.md §3).

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type { BriefDetail } from '@/lib/briefsShared';

const BRIEF_DETAIL_COLUMNS =
  'brief_id,generated_at,period_start,period_end,overall_risk,approval_status,executive_snapshot,' +
  'bottom_line,emerging_themes,forward_watch,cps230_implications,signal_ids,published_at,' +
  'morning_cycle_id,top_events,comparison,coverage,domain_picture,known_unknowns';

const SIGNAL_COLUMNS =
  'event_id,raw_title,raw_summary,sector,geography,risk_rating,rank_score,source_tier,' +
  'score_breakdown,confidence_level,cluster_similarity,analysis_summary,signal_status,' +
  'canonical_url,published_at,collected_at,event_type,operational_relevance,customer_impact,' +
  'banking_relevance,cps230_relevance,dependency_risk,confidence';

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const id = params.id;
  if (!id) return NextResponse.json({ error: 'missing id' }, { status: 400 });

  try {
    const sb = await createSupabaseServerClient();

    // .returns<>() pins the row shape explicitly — see /api/briefs/route.ts's
    // comment on why the widened select string needs this.
    const { data: briefRows } = await sb
      .from('intelligence_briefs')
      .select(BRIEF_DETAIL_COLUMNS)
      .eq('brief_id', id)
      .limit(1)
      .returns<BriefDetail[]>();
    const brief = briefRows?.[0] ?? null;
    if (!brief) return NextResponse.json({ brief: null, signals: [], audit: [] });

    const ids: string[] = brief.signal_ids ?? [];
    let signals: unknown[] = [];
    if (ids.length) {
      const { data } = await sb
        .from('intelligence_events')
        .select(SIGNAL_COLUMNS)
        .in('event_id', ids)
        .not('raw_title', 'ilike', 'CVE-%')
        .order('rank_score', { ascending: false });
      signals = data ?? [];
    } else {
      const { data } = await sb
        .from('intelligence_events')
        .select(SIGNAL_COLUMNS)
        .eq('brief_id', id)
        .not('raw_title', 'ilike', 'CVE-%')
        .order('rank_score', { ascending: false })
        .limit(20);
      signals = data ?? [];
    }

    const { data: audit } = await sb
      .from('audit_events')
      .select('id,category,actor,action,outcome,details,created_at')
      .eq('details->>record_id', id)
      .order('created_at', { ascending: true })
      .limit(50);

    return NextResponse.json({ brief, signals, audit: audit ?? [] });
  } catch (err) {
    console.error('[briefs/id] read failed:', err);
    return NextResponse.json({ error: 'brief_read_failed' }, { status: 500 });
  }
}
