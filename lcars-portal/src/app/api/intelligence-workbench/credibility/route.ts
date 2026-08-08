// Signal Credibility API — annotates hot signals with source reliability context.
// Shows brief composition by tier, signal confidence levels, and corroboration strength.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

// confidence is stored 0-1 (max observed 0.98), not 0-100 — the original
// value of 60 here compared a 0-1 column against a 0-100 threshold, so this
// route always returned zero signals regardless of real data.
const MIN_CONFIDENCE = 0.6;

async function getCredibilityData(sb: any, days: number) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  const { data: briefs, error: briefErr } = await sb
    .from('intelligence_briefs')
    .select('brief_id,signal_ids,overall_risk,executive_snapshot,generated_at')
    .eq('approval_status', 'PUBLISHED')
    .order('generated_at', { ascending: false })
    .limit(1);

  if (briefErr) throw new Error(`Failed to fetch brief: ${briefErr.message}`);

  const latestBrief = briefs?.[0];

  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      risk_rating,
      rank_score,
      confidence,
      osint_confidence_level,
      collected_at,
      source_id,
      intelligence_source_registry (
        source_name,
        reliability_tier,
        reliability_score,
        category
      )
    `)
    .eq('suppressed', false)
    .gte('confidence', MIN_CONFIDENCE)
    .gte('collected_at', since)
    .not('raw_title', 'ilike', 'CVE-%')
    .not('raw_title', 'ilike', 'CWE-%')
    .order('rank_score', { ascending: false })
    .limit(20);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const eventIds = (signals ?? []).map((s: any) => s.event_id);
  const { data: corroborations, error: corrErr } = eventIds.length
    ? await sb
        .from('signal_corroboration')
        .select('signal_id, corroborating_signal_id')
        .or(`signal_id.in.(${eventIds.join(',')}),corroborating_signal_id.in.(${eventIds.join(',')})`)
    : { data: [], error: null };
  if (corrErr) throw new Error(`Failed to fetch corroborations: ${corrErr.message}`);

  const corroborationCount = new Map<string, number>();
  (corroborations ?? []).forEach((c: any) => {
    corroborationCount.set(c.signal_id, (corroborationCount.get(c.signal_id) || 0) + 1);
    corroborationCount.set(c.corroborating_signal_id, (corroborationCount.get(c.corroborating_signal_id) || 0) + 1);
  });

  const signalList = (signals ?? []).map((s: any) => {
    const source = s.intelligence_source_registry;
    const tier = source?.reliability_tier || 'TIER_4';
    const srs = source?.reliability_score ?? 0.75;

    return {
      event_id: s.event_id,
      raw_title: s.raw_title,
      risk_rating: s.risk_rating,
      rank_score: s.rank_score,
      confidence: s.confidence,
      source: {
        source_id: s.source_id,
        source_name: source?.source_name || 'Unknown',
        category: source?.category || 'unknown',
        tier,
        srs,
      },
      corroboration: corroborationCount.get(s.event_id) || 0,
      confidence_level: (s.osint_confidence_level || 'unknown').toLowerCase(),
    };
  });

  const tierCounts = { TIER_1: 0, TIER_2: 0, TIER_3: 0, TIER_4: 0 };
  signalList.forEach((s: any) => {
    if (tierCounts[s.source.tier as keyof typeof tierCounts] !== undefined) {
      tierCounts[s.source.tier as keyof typeof tierCounts]++;
    }
  });

  const total = signalList.length;
  const composition = {
    tier1_pct: total > 0 ? Math.round((tierCounts.TIER_1 / total) * 100) : 0,
    tier2_pct: total > 0 ? Math.round((tierCounts.TIER_2 / total) * 100) : 0,
    tier3_pct: total > 0 ? Math.round((tierCounts.TIER_3 / total) * 100) : 0,
    tier4_pct: total > 0 ? Math.round((tierCounts.TIER_4 / total) * 100) : 0,
  };

  return {
    domain: 'credibility',
    brief: {
      brief_id: latestBrief?.brief_id || null,
      executive_snapshot: latestBrief?.executive_snapshot || null,
      generated_at: latestBrief?.generated_at || null,
      overall_risk: latestBrief?.overall_risk || null,
      composition,
      tier_counts: tierCounts,
      total_signals: total,
    },
    signals: signalList.sort((a: any, b: any) => b.rank_score - a.rank_score),
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const days = Number(req.nextUrl.searchParams.get('days')) || 7;

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getCredibilityData(sb, days));
  } catch (err) {
    console.error('[credibility-workbench] read failed:', err);
    return NextResponse.json(
      { error: 'credibility_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
