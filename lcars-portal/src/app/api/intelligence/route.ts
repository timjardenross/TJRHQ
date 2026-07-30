// MSN-0201: OR Intelligence API — portal-side queries to Supabase intelligence tables.
// GET /api/intelligence?view=<signals|themes|sources|latest|archive|daily_briefs>

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import { signalMatchesRisk } from '@/lib/intelligenceRisk';

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
      // risk_rating is not a DB column — risk is DERIVED from
      // customer_impact/banking_relevance (see @/lib/intelligenceRisk).
      // MSN-0351: the old filter did `.eq('customer_impact', level)`, which
      // silently dropped items that were HIGH only via banking_relevance —
      // filtering to "HIGH" could miss real high-risk items. We now over-fetch
      // and filter through the SAME deriveRisk() the badge uses, so the filter
      // and the displayed badge can never disagree.
      const fetchLimit = risk ? Math.min(limit * 5, 200) : limit;
      let query = sb
        .from('intelligence_events')
        .select('event_id,raw_title,raw_summary,event_type,geography,rank_score,collected_at,canonical_url,customer_impact,banking_relevance,cps230_relevance,organisation,sector,source_ref,resilience_themes,executive_relevance,dependency_risk')
        .eq('suppressed', false)
        .not('raw_title', 'ilike', 'CVE-%')
        .gte('collected_at', since)
        .order('rank_score', { ascending: false })
        .limit(fetchLimit);
      if (type)  query = query.ilike('event_type', `%${type}%`);
      const { data, error } = await query;
      if (error) throw error;
      let signals = data ?? [];
      if (risk) signals = signals.filter((s) => signalMatchesRisk(s, risk)).slice(0, limit);
      return NextResponse.json({ signals, days });
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
        .select('brief_id,generated_at,period_start,period_end,overall_risk,events_included,narrative_available,sources_checked,provider_used,executive_snapshot,bottom_line,emerging_themes,forward_watch')
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

    // ── Content signals (MSN-0202) ───────────────────────────────────────────
    if (view === 'content_signals') {
      const since = new Date(Date.now() - days * 86_400_000).toISOString();
      const pillar = req.nextUrl.searchParams.get('pillar');
      // Phase 1C: domain filter — 'health' | 'operational' | omitted for both
      const domain = req.nextUrl.searchParams.get('domain');

      let sigQuery = sb
        .from('content_signals')
        .select('event_id_text,source_name,pillar_key,pillar_name,content_relevance,rank_score,captain_focus,suggested_angle,scored_at,suppressed,raw_title,raw_summary,canonical_url,collected_at,domain')
        .eq('suppressed', false)
        .gte('scored_at', since)
        .order('rank_score', { ascending: false })
        .limit(limit * 2);
      if (pillar) sigQuery = sigQuery.eq('pillar_key', pillar);
      if (domain === 'health' || domain === 'operational') sigQuery = sigQuery.eq('domain', domain);

      const { data: sigData, error: sigErr } = await sigQuery;
      if (sigErr) throw sigErr;
      const signals = sigData ?? [];

      // Join intelligence_events for live title/url/collected_at — stored copies are the fallback
      const eventIds = signals.map((s: any) => s.event_id_text).filter(Boolean);
      let eventMap: Record<string, any> = {};
      if (eventIds.length > 0) {
        const { data: evData, error: evErr } = await sb
          .from('intelligence_events')
          .select('event_id,raw_title,raw_summary,canonical_url,collected_at,source_name')
          .in('event_id', eventIds);
        if (evErr) {
          console.warn('[intelligence/content_signals] event join failed:', evErr.message);
        }
        for (const e of evData ?? []) {
          eventMap[e.event_id] = e;
        }
      }

      const enriched = signals.slice(0, limit).map((s: any) => {
        const ev = eventMap[s.event_id_text] ?? {};
        return {
          ...s,
          event_id: s.event_id_text,
          // live join preferred; stored copy is the resilient fallback
          raw_title: ev.raw_title ?? s.raw_title ?? '(no title)',
          raw_summary: ev.raw_summary ?? s.raw_summary ?? null,
          canonical_url: ev.canonical_url ?? s.canonical_url ?? null,
          collected_at: ev.collected_at ?? s.collected_at ?? s.scored_at,
        };
      });

      // Pillar summary — group signals by pillar
      const pillarMap: Record<string, { key: string; name: string; signals: any[] }> = {};
      for (const s of signals) {
        const pk = s.pillar_key ?? 'unknown';
        if (!pillarMap[pk]) pillarMap[pk] = { key: pk, name: s.pillar_name ?? pk, signals: [] };
        pillarMap[pk].signals.push(s);
      }
      const byPillar = Object.values(pillarMap)
        .sort((a, b) => b.signals.length - a.signals.length)
        .map(g => ({
          pillar_key: g.key,
          pillar_name: g.name,
          signal_count: g.signals.length,
          avg_relevance: +(g.signals.reduce((acc: number, x: any) => acc + (x.content_relevance ?? 0), 0) / g.signals.length).toFixed(3),
          top_signal_title: eventMap[g.signals[0]?.event_id_text]?.raw_title ?? g.signals[0]?.raw_title ?? '',
        }));

      // Pipeline snapshot
      const { data: pipelineData } = await sb
        .from('comms_content')
        .select('status')
        .neq('status', 'archived');
      const pipeline: Record<string, number> = {};
      for (const r of pipelineData ?? []) {
        pipeline[r.status] = (pipeline[r.status] ?? 0) + 1;
      }

      return NextResponse.json({
        signals: enriched,
        by_pillar: byPillar,
        pipeline,
        captain_focus_count: enriched.filter((s: any) => s.captain_focus).length,
        days,
      });
    }

    return NextResponse.json({ error: `Unknown view: ${view}` }, { status: 400 });

  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Intelligence query failed', detail }, { status: 500 });
  }
}
