// Health Intelligence Summary API — HIGH/MEDIUM/LOW/UNKNOWN buckets + known unknowns

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

// Structural coverage gaps for health OSINT — HEALTH_OSINT_WORKBENCH.md section 7.
// Static because these are domain-level blind spots, not derived from current signals.
const KNOWN_UNKNOWNS = [
  { title: 'Long-term outcome data', impact: 'Most clinical trials run 6-12 months; long-term safety unknown', need: 'Multi-year follow-up studies' },
  { title: 'Real-world effectiveness', impact: 'Lab RCT results may not translate to actual population behavior', need: 'Post-market surveillance data' },
  { title: 'Rare adverse events', impact: 'Not detected in trial-sized samples', need: 'Larger post-market surveillance' },
  { title: 'Drug-drug interactions', impact: 'Polypharmacy effects underexplored', need: 'Interaction studies across common combinations' },
  { title: 'Bioindividuality', impact: 'Genetic/metabolic differences in response not captured by population averages', need: 'Stratified or personalized trial data' },
];

async function getIntelligenceSummary(sb: any) {
  const since = new Date(Date.now() - DAYS_365).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('health_signals')
    .select(`
      signal_id, title, description, signal_type, health_domain, rank_score, sample_size, study_design,
      p_value, published_at, actionable_recommendation,
      confidence_level, health_source_registry ( source_name, source_url, reliability_tier, reliability_score )
    `)
    .eq('suppressed', false)
    .gte('collected_at', since)
    .order('rank_score', { ascending: false })
    // 50 was too small a pool for a single source to not dominate it — see
    // the same fix on the technical intelligence-summary route.
    .limit(150);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const signalList = (signals ?? []).map((s: any) => ({
    signal_id: s.signal_id,
    title: s.title,
    summary: s.description ? s.description.slice(0, 220) : null,
    source_url: s.health_source_registry?.source_url || null,
    signal_type: s.signal_type,
    health_domain: s.health_domain,
    confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
    source_name: s.health_source_registry?.source_name || 'Unknown',
    rank_score: s.rank_score,
    sample_size: s.sample_size,
    study_design: s.study_design,
    p_value: s.p_value,
    published_at: s.published_at,
    actionable_recommendation: s.actionable_recommendation,
  }));

  return {
    domain: 'intelligence-summary',
    high: signalList.filter((s: any) => s.confidence_level === 'high').slice(0, 15),
    medium: signalList.filter((s: any) => s.confidence_level === 'medium').slice(0, 15),
    low: signalList.filter((s: any) => s.confidence_level === 'low').slice(0, 8),
    unknowns: KNOWN_UNKNOWNS,
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
    console.error('[health-osint/intelligence-summary] read failed:', err);
    return NextResponse.json(
      { error: 'summary_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
