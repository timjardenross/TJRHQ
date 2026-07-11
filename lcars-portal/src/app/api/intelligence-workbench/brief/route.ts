// Phase B — single brief detail (Screens 2/3/4). Read-only.
// GET /api/intelligence-workbench/brief?id=<brief_id>
// Returns the brief, its linked signals (real Phase A columns incl. score_breakdown),
// and the audit timeline (audit_events where details.record_id = brief_id).

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id');
  if (!id) return NextResponse.json({ error: 'missing id' }, { status: 400 });

  try {
    const sb = await createSupabaseServerClient();

    const { data: briefRows } = await sb
      .from('intelligence_briefs')
      .select(
        'brief_id,generated_at,period_start,period_end,overall_risk,approval_status,approval_audit,executive_snapshot,bottom_line,emerging_themes,forward_watch,signal_ids,published_at',
      )
      .eq('brief_id', id)
      .limit(1);
    const brief = briefRows?.[0] ?? null;
    if (!brief) return NextResponse.json({ brief: null, signals: [], audit: [] });

    const ids: string[] = brief.signal_ids ?? [];
    let signals: unknown[] = [];
    if (ids.length) {
      const { data } = await sb
        .from('intelligence_events')
        .select(
          'event_id,raw_title,raw_summary,sector,geography,risk_rating,rank_score,source_tier,score_breakdown,confidence_level,cluster_similarity,analysis_summary,signal_status',
        )
        .in('event_id', ids)
        .order('rank_score', { ascending: false });
      signals = data ?? [];
    } else {
      const { data } = await sb
        .from('intelligence_events')
        .select(
          'event_id,raw_title,raw_summary,sector,geography,risk_rating,rank_score,source_tier,score_breakdown,confidence_level,cluster_similarity,analysis_summary,signal_status',
        )
        .eq('brief_id', id)
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
    return NextResponse.json(
      { error: 'brief_read_failed', detail: String(err), brief: null, signals: [], audit: [] },
      { status: 200 },
    );
  }
}
