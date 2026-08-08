// Threat Assessment API — probability × impact × confidence escalation matrix

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

function impactFromCriticality(score: number | null): string {
  if (score === null || score === undefined) return 'medium';
  if (score >= 0.85) return 'critical';
  if (score >= 0.60) return 'high';
  if (score >= 0.35) return 'medium';
  return 'low';
}

async function getThreatAssessment(sb: any, days: number, includeSuppressed: boolean) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  let query = sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      risk_rating,
      rank_score,
      criticality_score,
      osint_confidence_level,
      intelligence_source_registry (
        reliability_tier,
        reliability_score
      )
    `)
    .gte('collected_at', since)
    // Top-N rather than an absolute rank_score cutoff: the fixed SRS
    // validation loop (previously dead — see recompute_signal_scores.py)
    // means most sources are still TIER_4 while real accuracy samples
    // accumulate, so today's realistic rank_score ceiling is well under
    // the ~90s the spec's own examples assumed. An absolute >=70 gate
    // would return zero rows right now and recreate the "empty workbench"
    // symptom this whole gap-closure effort was chasing.
    .order('rank_score', { ascending: false })
    .limit(20);

  if (!includeSuppressed) query = query.eq('suppressed', false);

  const { data: signals, error: signalsErr } = await query;
  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const threats = (signals ?? []).map((s: any) => {
    const probMap: Record<string, string> = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
    const probability = probMap[s.risk_rating as keyof typeof probMap] || 'medium';
    // criticality_score, not banking_relevance — per TECHNICAL_OSINT_WORKBENCH.md
    // section 6 ("Assign impact from criticality_score + domain relevance").
    const impact = impactFromCriticality(s.criticality_score);
    const confidence = (s.osint_confidence_level || 'UNKNOWN').toLowerCase();

    let escalation = 'monitor';
    if (confidence === 'high' && impact === 'critical') escalation = 'escalate';
    else if (confidence === 'high' || impact === 'critical') escalation = 'watch';
    else if (confidence === 'medium' && impact === 'high') escalation = 'watch';

    const recommendation =
      escalation === 'escalate' ? 'Immediate action required'
      : escalation === 'watch' ? 'Monitor for spread, coordinate response'
      : 'Research and await confirmation';

    return {
      threat: s.raw_title,
      probability,
      impact,
      confidence,
      escalation,
      recommendation,
    };
  });

  return {
    domain: 'threat-assessment',
    threats,
    gaps: [
      { area: 'Internal compromise', risk: 'high', blind_spot: 'No visibility into internal network anomalies' },
      { area: 'Supply chain', risk: 'medium', blind_spot: 'Limited third-party compromise detection' },
    ],
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const days = Number(req.nextUrl.searchParams.get('days')) || 7;
  const includeSuppressed = req.nextUrl.searchParams.get('suppressed') === 'true';

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getThreatAssessment(sb, days, includeSuppressed));
  } catch (err) {
    console.error('[threat-assessment] read failed:', err);
    return NextResponse.json(
      { error: 'assessment_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
