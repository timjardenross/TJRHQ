// Threat Assessment API — probability × impact × confidence escalation matrix

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_7 = 7 * 86_400_000;

async function getThreatAssessment(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      risk_rating,
      rank_score,
      operational_relevance,
      banking_relevance,
      intelligence_source_registry (
        reliability_tier,
        reliability_score
      )
    `)
    .eq('suppressed', false)
    .gte('collected_at', since7d)
    .gte('rank_score', 70)
    .order('rank_score', { ascending: false })
    .limit(20);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const threats = (signals ?? []).map((s: any) => {
    const tier = s.intelligence_source_registry?.reliability_tier || 'TIER_4';
    const probMap = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
    const probability = probMap[s.risk_rating as keyof typeof probMap] || 'medium';
    const impact = s.banking_relevance ? 'critical' : 'high';

    let confidence = 'low';
    if (tier === 'TIER_1') confidence = 'high';
    else if (tier === 'TIER_2') confidence = 'medium';

    let escalation = 'monitor';
    if (confidence === 'high' && impact === 'critical') escalation = 'escalate';
    else if (confidence === 'high' || impact === 'critical') escalation = 'watch';

    return {
      threat: s.raw_title,
      probability,
      impact,
      confidence,
      escalation,
    };
  });

  return {
    domain: 'threat-assessment',
    threats,
    gaps: [
      { area: 'Internal compromise', risk: 'high' },
      { area: 'Supply chain', risk: 'medium' },
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
    return NextResponse.json(await getThreatAssessment(sb));
  } catch (err) {
    console.error('[threat-assessment] read failed:', err);
    return NextResponse.json(
      { error: 'assessment_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
