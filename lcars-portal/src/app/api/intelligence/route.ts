// MSN-0201: OR Intelligence API — portal-side queries to Supabase intelligence tables.
// GET /api/intelligence?view=<signals|themes|sources|latest|archive|daily_briefs>

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET(req: NextRequest) {
  const view = req.nextUrl.searchParams.get('view') ?? 'latest';
  const days  = parseInt(req.nextUrl.searchParams.get('days')  ?? '7',  10);
  const limit = parseInt(req.nextUrl.searchParams.get('limit') ?? '20', 10);
  const risk  = req.nextUrl.searchParams.get('risk');    // HIGH|MEDIUM|LOW
  const type  = req.nextUrl.searchParams.get('type');    // cyber|weather|etc.

  try {
    const sb = await createSupabaseServerClient();

    // ── Latest ORI brief ────────────────────────────────────────────────────
    if (view === 'latest') {
      const { data, error } = await sb
        .from('intelligence_briefs')
        .select('brief_id,generated_at,period_start,period_end,overall_risk,executive_snapshot,bottom_line,emerging_themes,forward_watch,cps230_implications,events_included,sources_checked,sources_available,narrative_available,provider_used')
        .order('generated_at', { ascending: false })
        .limit(1);
      if (error) throw error;
      return NextResponse.json({ brief: data?.[0] ?? null });
    }

    // ── Emerging themes (latest brief) ──────────────────────────────────────
    if (view === 'themes') {
      const { data, error } = await sb
        .from('intelligence_briefs')
        .select('brief_id,generated_at,overall_risk,emerging_themes,forward_watch,executive_snapshot,period_start,period_end')
        .order('generated_at', { ascending: false })
        .limit(1);
      if (error) throw error;
      return NextResponse.json({ themes: data?.[0] ?? null });
    }

    // ── Intelligence signals (events) ────────────────────────────────────────
    if (view === 'signals') {
      const since = new Date(Date.now() - days * 86_400_000).toISOString();
      let query = sb
        .from('intelligence_events')
        .select('event_id,raw_title,raw_summary,event_type,geography,risk_rating,rank_score,collected_at,canonical_url,customer_impact,banking_relevance,cps230_relevance')
        .eq('suppressed', false)
        .gte('collected_at', since)
        .order('rank_score', { ascending: false })
        .limit(limit);
      if (risk)  query = query.eq('risk_rating', risk.toUpperCase());
      if (type)  query = query.ilike('event_type', `%${type}%`);
      const { data, error } = await query;
      if (error) throw error;
      return NextResponse.json({ signals: data ?? [], days });
    }

    // ── Source health ────────────────────────────────────────────────────────
    if (view === 'sources') {
      const [{ data: sources }, { data: health }] = await Promise.all([
        sb.from('intelligence_source_registry')
          .select('source_id,source_name,category,priority_rank,url,active,jurisdiction')
          .order('priority_rank', { ascending: true }),
        sb.from('intelligence_source_health')
          .select('source_id,checked_at,status,items_retrieved,latency_ms,error_message')
          .order('checked_at', { ascending: false })
          .limit(500),
      ]);
      // de-dup health to latest per source
      const latestHealth: Record<string, typeof health extends (infer T)[] | null ? T : never> = {};
      for (const h of health ?? []) {
        if (!latestHealth[h.source_id]) latestHealth[h.source_id] = h;
      }
      const merged = (sources ?? []).map(s => ({
        ...s,
        health: latestHealth[s.source_id] ?? null,
      }));
      const ok      = merged.filter(s => s.health?.status === 'ok').length;
      const failed  = merged.filter(s => s.health?.status === 'failed').length;
      const stale   = merged.filter(s => s.health?.status === 'stale').length;
      return NextResponse.json({ sources: merged, summary: { total: merged.length, ok, failed, stale } });
    }

    // ── ORI brief archive ────────────────────────────────────────────────────
    if (view === 'archive') {
      const { data, error } = await sb
        .from('intelligence_briefs')
        .select('brief_id,generated_at,period_start,period_end,overall_risk,events_included,narrative_available,sources_checked,provider_used')
        .order('generated_at', { ascending: false })
        .limit(limit);
      if (error) throw error;
      return NextResponse.json({ briefs: data ?? [] });
    }

    // ── Captain's daily brief history ────────────────────────────────────────
    if (view === 'daily_briefs') {
      const since = new Date(Date.now() - days * 86_400_000).toISOString();
      const { data, error } = await sb
        .from('captains_daily_briefs')
        .select('id,brief_type,brief_date,generated_at,signals_count,health_snapshot')
        .gte('generated_at', since)
        .order('generated_at', { ascending: false })
        .limit(limit);
      if (error) throw error;
      return NextResponse.json({ briefs: data ?? [] });
    }

    return NextResponse.json({ error: `Unknown view: ${view}` }, { status: 400 });

  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Intelligence query failed', detail }, { status: 500 });
  }
}
