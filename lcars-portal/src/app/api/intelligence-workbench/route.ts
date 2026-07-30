// Phase B — Intelligence Workbench API (Overview / Screen 1).
// Supports both Operational Intelligence (Phase A) and Health Intelligence modes.
// Domain-aware: ?domain=operational (default) or ?domain=health

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
const MIN_CONFIDENCE = 60;  // Operational signals require >= 60 confidence
const DAYS_7 = 7 * 86_400_000;
const DAYS_30 = 30 * 86_400_000;

async function getOperationalData(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();
  
  // Query briefs not yet published (pending approval)
  const { data: briefs, error: briefsErr } = await sb
    .from('intelligence_briefs')
    .select('brief_id,generated_at,period_start,period_end,overall_risk,approval_status,executive_snapshot,signal_ids')
    .neq('approval_status', 'PUBLISHED')
    .order('generated_at', { ascending: false })
    .limit(20);

  if (briefsErr) throw new Error(`Failed to fetch briefs: ${briefsErr.message}`);

  // Hot signals: 7-day, confidence >= 60, source-governed, no CVE/CWE
  // Using intelligence_events (not core_events) as that's where ORI signals live
  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select('event_id,raw_title,sector,geography,risk_rating,rank_score,source_tier,canonical_url')
    .eq('suppressed', false)
    .gte('confidence', MIN_CONFIDENCE)
    .gte('collected_at', since7d)
    .not('raw_title', 'ilike', 'CVE-%')
    .not('raw_title', 'ilike', 'CWE-%')
    .order('rank_score', { ascending: false })
    .limit(8);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  // 7-day signal count (high-confidence only)
  const { count: signals7d, error: countErr } = await sb
    .from('intelligence_events')
    .select('event_id', { count: 'exact', head: true })
    .eq('suppressed', false)
    .gte('confidence', MIN_CONFIDENCE)
    .not('raw_title', 'ilike', 'CVE-%')
    .not('raw_title', 'ilike', 'CWE-%')
    .gte('collected_at', since7d);

  if (countErr) throw new Error(`Failed to count signals: ${countErr.message}`);

  const briefList = briefs ?? [];
  const redActive = briefList.filter((b: any) => b.overall_risk === 'RED').length;
  const signalList = (signals ?? [])
    .slice()
    .sort((a: any, b: any) => (RISK_ORDER[a.risk_rating] ?? 3) - (RISK_ORDER[b.risk_rating] ?? 3));

  return {
    domain: 'operational',
    kpis: {
      signals_7d: signals7d ?? 0,
      briefs_pending: briefList.length,
      red_active: redActive,
    },
    briefs: briefList.map((b: any) => ({
      brief_id: b.brief_id,
      overall_risk: b.overall_risk,
      approval_status: b.approval_status,
      executive_snapshot: b.executive_snapshot,
      signal_ids: b.signal_ids,
    })),
    hotSignals: signalList.map((s: any) => ({
      event_id: s.event_id,
      raw_title: s.raw_title,
      sector: s.sector,
      geography: s.geography,
      risk_rating: s.risk_rating,
      rank_score: s.rank_score,
      source_tier: s.source_tier,
      canonical_url: s.canonical_url,
    })),
  };
}

async function getHealthData(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();
  const since30d = new Date(Date.now() - DAYS_30).toISOString();

  // Health insights with source articles (joined)
  const { data: insights, error: insightsErr } = await sb
    .from('health_insights')
    .select(`
      id,
      period_start,
      period_end,
      summary,
      auto_health_status,
      llm_narrative,
      deterministic_findings,
      committed_to_memory,
      committed_at,
      reviewed_at,
      health_source_articles (
        title,
        url,
        summary,
        published_date,
        source_type
      )
    `)
    .gte('period_start', since7d)
    .order('period_start', { ascending: false })
    .limit(10);

  if (insightsErr) throw new Error(`Failed to fetch insights: ${insightsErr.message}`);

  // Health events
  const { data: events, error: eventsErr } = await sb
    .from('health_events')
    .select('id,event_date,event_type,title,description,source')
    .gte('event_date', since30d)
    .order('event_date', { ascending: false })
    .limit(20);

  if (eventsErr) throw new Error(`Failed to fetch events: ${eventsErr.message}`);

  // Daily metrics (last 7 days)
  const { data: dailyMetrics, error: metricsErr } = await sb
    .from('analytics_health_daily')
    .select('log_date,physical_capacity,overall_note,sleep_hours,pain_score')
    .order('log_date', { ascending: false })
    .limit(7);

  if (metricsErr) throw new Error(`Failed to fetch metrics: ${metricsErr.message}`);

  const latest = dailyMetrics?.[0] ?? {};
  const insightList = (insights ?? []).map((i: any) => ({
    insight_id: i.id,
    created_at: i.period_start,
    overall_status: i.auto_health_status || 'OK',
    wellness_narrative: i.llm_narrative || i.summary,
    key_findings: i.deterministic_findings,
    source_articles: i.health_source_articles ?? null,
    committed_to_memory: i.committed_to_memory ?? false,
    committed_at: i.committed_at ?? null,
  }));

  const eventList = (events ?? []).map((e: any) => ({
    event_id: e.id,
    logged_at: e.event_date || new Date().toISOString(),
    event_type: e.event_type || 'unknown',
    value: e.title || '—',
    notes: e.description || null,
    source: e.source || '—',
  }));

  return {
    domain: 'health',
    kpis: {
      capacity_score: latest.physical_capacity ?? 0,
      sleep_hours: latest.sleep_hours ?? 0,
      pain_level: latest.pain_score ?? 0,
    },
    insights: insightList,
    recentEvents: eventList,
    dailyMetrics: dailyMetrics ?? [],
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const domain = req.nextUrl.searchParams.get('domain') ?? 'operational';

    if (domain === 'health') {
      return NextResponse.json(await getHealthData(sb));
    }

    return NextResponse.json(await getOperationalData(sb));
  } catch (err) {
    console.error('[intelligence-workbench] read failed:', err);
    return NextResponse.json(
      { error: 'workbench_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
