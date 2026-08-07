// Signal Credibility API — annotates hot signals with source reliability context.
// Shows brief composition by tier, signal confidence levels, and corroboration strength.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_7 = 7 * 86_400_000;
const MIN_CONFIDENCE = 60;

async function getCredibilityData(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();

  // Get latest published brief
  const { data: briefs, error: briefErr } = await sb
    .from('intelligence_briefs')
    .select('brief_id,signal_ids,overall_risk,executive_snapshot,generated_at')
    .eq('approval_status', 'PUBLISHED')
    .order('generated_at', { ascending: false })
    .limit(1);

  if (briefErr) throw new Error(`Failed to fetch brief: ${briefErr.message}`);

  const latestBrief = briefs?.[0];

  // Get 7-day signals with source reliability context
  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      risk_rating,
      rank_score,
      confidence,
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
    .gte('collected_at', since7d)
    .not('raw_title', 'ilike', 'CVE-%')
    .not('raw_title', 'ilike', 'CWE-%')
    .order('rank_score', { ascending: false })
    .limit(20);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  // Corroboration: count other signals with high word overlap
  const signalList = (signals ?? []).map((s: any) => {
    const titleWords = new Set(
      (s.raw_title || '')
        .toLowerCase()
        .match(/\w{4,}/g) || []
    );

    const corroboratingCount = (signals ?? []).reduce((count: number, other: any) => {
      if (other.event_id === s.event_id) return count;
      if (other.source_id === s.source_id) return count;

      const otherWords = new Set(
        (other.raw_title || '')
          .toLowerCase()
          .match(/\w{4,}/g) || []
      );

      const overlap = [...titleWords].filter(w => otherWords.has(w)).length;
      return overlap >= 2 ? count + 1 : count;
    }, 0);

    const source = s.intelligence_source_registry;
    const tier = source?.reliability_tier || 'TIER_4';
    const srs = source?.reliability_score ?? 0.75;

    // Confidence level logic
    let confidenceLevel = 'low';
    if ((tier === 'TIER_1' || tier === 'TIER_2') && corroboratingCount >= 1) {
      confidenceLevel = 'high';
    } else if (tier === 'TIER_1') {
      confidenceLevel = 'high';
    } else if (tier === 'TIER_2' || (tier === 'TIER_3' && corroboratingCount >= 2)) {
      confidenceLevel = 'medium';
    } else if (tier === 'TIER_3') {
      confidenceLevel = 'medium';
    }

    return {
      event_id: s.event_id,
      raw_title: s.raw_title,
      risk_rating: s.risk_rating,
      rank_score: s.rank_score,
      confidence: s.confidence,
      collected_at: s.collected_at,
      source: {
        source_id: s.source_id,
        source_name: source?.source_name || 'Unknown',
        category: source?.category || 'unknown',
        tier: tier,
        srs: srs,
      },
      corroboration: corroboratingCount,
      confidence_level: confidenceLevel,
    };
  });

  // Brief composition (tier breakdown)
  const tierCounts = { TIER_1: 0, TIER_2: 0, TIER_3: 0, TIER_4: 0 };
  signalList.forEach((s: any) => {
    tierCounts[s.source.tier as keyof typeof tierCounts]++;
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
      composition: composition,
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

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getCredibilityData(sb));
  } catch (err) {
    console.error('[credibility-workbench] read failed:', err);
    return NextResponse.json(
      { error: 'credibility_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
