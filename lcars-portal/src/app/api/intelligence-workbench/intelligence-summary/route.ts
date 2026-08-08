import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

async function getIntelligenceSummary(sb: any, days: number, includeSuppressed: boolean) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  let query = sb
    .from('intelligence_events')
    .select('event_id, raw_title, risk_rating, rank_score, collected_at, source_id, osint_confidence_level, intelligence_source_registry(source_name, reliability_tier, reliability_score)')
    .gte('collected_at', since)
    // Top-N rather than an absolute rank_score cutoff — see threat-assessment/
    // route.ts for why: the corrected SRS scoring means today's realistic
    // ceiling is well under the fixed >=50 this used to require.
    .order('rank_score', { ascending: false })
    .limit(50);

  if (!includeSuppressed) query = query.eq('suppressed', false);

  const { data: signals, error: signalsErr } = await query;
  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const signalList: any[] = (signals ?? []).map((s: any) => ({
    event_id: s.event_id,
    raw_title: s.raw_title,
    confidence_level: (s.osint_confidence_level || 'UNKNOWN').toLowerCase(),
    source_name: s.intelligence_source_registry?.source_name || 'Unknown',
    rank_score: s.rank_score,
  }));

  return {
    domain: 'intelligence-summary',
    high: signalList.filter((s: any) => s.confidence_level === 'high').slice(0, 10),
    medium: signalList.filter((s: any) => s.confidence_level === 'medium').slice(0, 10),
    low: signalList.filter((s: any) => s.confidence_level === 'low').slice(0, 5),
    unknowns: [
      { title: 'Internal network security', impact: 'Blind to internal compromise', need: 'SIEM integration' },
      { title: 'Supply chain threats', impact: 'Third-party compromise', need: 'Vendor monitoring' },
      { title: 'Zero-day activity', impact: 'Unpatched vulnerabilities in use', need: 'EDR, threat hunting' },
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
    return NextResponse.json(await getIntelligenceSummary(sb, days, includeSuppressed));
  } catch (err) {
    console.error('[intelligence-summary] read failed:', err);
    return NextResponse.json(
      { error: 'summary_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
