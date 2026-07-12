// Phase B — Intelligence Workbench API (Overview / Screen 1).
// Supports both Operational Intelligence (Phase A) and Health Intelligence modes.
// Domain-aware: ?domain=operational (default) or ?domain=health

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

async function getOperationalData(sb: any, since: string) {
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
  const redActive = briefList.filter((b: any) => b.overall_risk === 'RED').length;

  const hot = (signals ?? []).slice().sort(
    (a: any, b: any) => (RISK_ORDER[a.risk_rating] ?? 3) - (RISK_ORDER[b.risk_rating] ?? 3),
  );

  return {
    domain: 'operational',
    kpis: {
      signals_7d: signals7d ?? 0,
      briefs_pending: briefList.length,
      red_active: redActive,
    },
    briefs: briefList,
    hotSignals: hot,
  };
}

async function getHealthData(sb: any, since: string) {
  // Latest health insights (synthesis-level) WITH source articles.
  const { data: insights } = await sb
    .from('health_insights')
    .select('insight_id,created_at,synthesis_period_start,synthesis_period_end,overall_status,wellness_narrative,key_findings,source_articles,committed_to_memory,committed_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(10);

  // Health events (7d) for detail view with source tracking.
  const { data: events } = await sb
    .from('health_events')
    .select('event_id,logged_at,event_type,value,notes,source')
    .gte('logged_at', since)
    .order('logged_at', { ascending: false })
    .limit(20);

  // KPI-like metrics (fetch latest).
  const { data: dailyMetrics } = await sb
    .from('analytics_health_daily')
    .select('date,capacity_score,readiness_score,sleep_hours,pain_level')
    .order('date', { ascending: false })
    .limit(7);

  const latest = dailyMetrics?.[0] ?? {};
  const insightList = insights ?? [];

  return {
    domain: 'health',
    kpis: {
      capacity_score: latest.capacity_score ?? 0,
      readiness_score: latest.readiness_score ?? 0,
      sleep_hours: latest.sleep_hours ?? 0,
      pain_level: latest.pain_level ?? 0,
    },
    insights: insightList,
    recentEvents: events ?? [],
    dailyMetrics: dailyMetrics ?? [],
  };
}

export async function GET(req: NextRequest) {
  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - 7 * 86_400_000).toISOString();
    const domain = req.nextUrl.searchParams.get('domain') ?? 'operational';

    if (domain === 'health') {
      return NextResponse.json(await getHealthData(sb, since));
    }

    return NextResponse.json(await getOperationalData(sb, since));
  } catch (err) {
    return NextResponse.json(
      {
        error: 'workbench_read_failed',
        detail: String(err),
        domain: 'operational',
        kpis: {},
        briefs: [],
        hotSignals: [],
      },
      { status: 200 },
    );
  }
}
