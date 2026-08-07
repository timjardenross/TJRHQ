import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_7 = 7 * 86_400_000;

async function getIntelligenceSummary(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select('event_id, raw_title, risk_rating, rank_score, collected_at, source_id, intelligence_source_registry(source_name, reliability_tier, reliability_score)')
    .eq('suppressed', false)
    .gte('collected_at', since7d)
    .gte('rank_score', 50)
    .order('rank_score', { ascending: false })
    .limit(50);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const signalList: any[] = (signals ?? []).map((s: any) => {
    const tier = s.intelligence_source_registry?.reliability_tier || 'TIER_4';
    let confidenceLevel = 'low';
    if (tier === 'TIER_1') confidenceLevel = 'high';
    else if (tier === 'TIER_2') confidenceLevel = 'medium';

    return {
      event_id: s.event_id,
      raw_title: s.raw_title,
      confidence_level: confidenceLevel,
      source_name: s.intelligence_source_registry?.source_name || 'Unknown',
      rank_score: s.rank_score,
    };
  });

  return {
    domain: 'intelligence-summary',
    high: signalList.filter((s: any) => s.confidence_level === 'high').slice(0, 10),
    medium: signalList.filter((s: any) => s.confidence_level === 'medium').slice(0, 10),
    low: signalList.filter((s: any) => s.confidence_level === 'low').slice(0, 5),
    unknowns: [
      { title: 'Internal network security', impact: 'Blind to internal compromise', need: 'SIEM integration' },
      { title: 'Supply chain threats', impact: 'Third-party compromise', need: 'Vendor monitoring' },
    ],
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getIntelligenceSummary(sb));
  } catch (err) {
    console.error('[intelligence-summary] read failed:', err);
    return NextResponse.json(
      { error: 'summary_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
