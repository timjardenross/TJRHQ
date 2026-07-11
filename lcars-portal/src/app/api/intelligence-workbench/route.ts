// Phase B — Intelligence Workbench API (Overview / Screen 1).
// Reads the real Phase A (migration 0077) columns directly from Supabase:
// intelligence_events.{risk_rating,source_tier,signal_status,score_breakdown},
// intelligence_briefs.{approval_status,overall_risk}. Read-only; governed writes
// go through the Python dispatch bridge (see docs/PHASE-B-DESIGN-SIGN-OFF.md §5).

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

export async function GET(_req: NextRequest) {
  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - 7 * 86_400_000).toISOString();

    // Pending briefs (not yet published) + risk.
    const { data: briefs } = await sb
      .from('intelligence_briefs')
      .select('brief_id,generated_at,period_start,period_end,overall_risk,approval_status,executive_snapshot,signal_ids')
      .neq('approval_status', 'PUBLISHED')
      .order('generated_at', { ascending: false })
      .limit(20);

    // Hot signals (7d) — real risk_rating / source_tier from Phase A.
    const { data: signals } = await sb
      .from('intelligence_events')
      .select('event_id,raw_title,sector,geography,risk_rating,rank_score,source_tier,operational_relevance,signal_status')
      .eq('suppressed', false)
      .gte('collected_at', since)
      .order('operational_relevance', { ascending: false })
      .order('rank_score', { ascending: false })
      .limit(8);

    // KPI counts (head/count — no rows transferred).
    const { count: signals7d } = await sb
      .from('intelligence_events')
      .select('event_id', { count: 'exact', head: true })
      .gte('collected_at', since);

    const briefList = briefs ?? [];
    const redActive = briefList.filter((b) => b.overall_risk === 'RED').length;

    const hot = (signals ?? []).slice().sort(
      (a, b) => (RISK_ORDER[a.risk_rating] ?? 3) - (RISK_ORDER[b.risk_rating] ?? 3),
    );

    return NextResponse.json({
      kpis: {
        signals_7d: signals7d ?? 0,
        briefs_pending: briefList.length,
        red_active: redActive,
      },
      briefs: briefList,
      hotSignals: hot,
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'workbench_read_failed', detail: String(err), kpis: {}, briefs: [], hotSignals: [] },
      { status: 200 },
    );
  }
}
