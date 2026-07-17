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
  // Latest health insights (synthesis-level) WITH source articles (Phase 1B).
  const { data: rawInsights } = await sb
    .from('health_insights')
    .select('id, created_at, period_start, period_end, auto_health_status, llm_narrative, deterministic_findings, source_articles, committed_to_memory, committed_at, reviewed_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(10);

  // Health events for detail view with source tracking.
  const { data: rawEvents } = await sb
    .from('health_events')
    .select('id, event_date, event_type, title, description, source')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(20);

  // KPI-like metrics (fetch latest).
  const { data: dailyMetrics } = await sb
    .from('analytics_health_daily')
    .select('log_date, physical_capacity, overall_note, sleep_hours, pain_score')
    .order('log_date', { ascending: false })
    .limit(7);

  const latest = dailyMetrics?.[0] ?? {};
  const insightList = (rawInsights ?? []).map((i: any) => ({
    insight_id: i.id,
    created_at: i.created_at,
    synthesis_period_start: i.period_start,
    synthesis_period_end: i.period_end,
    overall_status: i.auto_health_status,
    wellness_narrative: i.llm_narrative,
    key_findings: i.deterministic_findings,
    source_articles: i.source_articles || null,
    committed_to_memory: i.committed_to_memory || false,
    committed_at: i.committed_at || null,
    reviewed_at: i.reviewed_at || null,
  }));

  const eventList = (rawEvents ?? []).map((e: any) => ({
    event_id: e.id,
    logged_at: e.event_date,
    event_type: e.event_type,
    value: e.title,
    notes: e.description,
    source: e.source,
  }));

  return {
    domain: 'health',
    kpis: {
      capacity_score: latest.physical_capacity ?? 0,
      readiness_score: latest.overall_note ? (latest.overall_note.length > 0 ? 1 : 0) : 0,
      sleep_hours: latest.sleep_hours ?? 0,
      pain_level: latest.pain_score ?? 0,
    },
    insights: insightList,
    recentEvents: eventList,
    dailyMetrics: dailyMetrics ?? [],
  };
}

export async function GET(req: NextRequest) {
  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - 30 * 86_400_000).toISOString();
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
