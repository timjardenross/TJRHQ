// Health Intelligence Summary API — HIGH/MEDIUM/LOW/UNKNOWN buckets + known unknowns

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

// Captain-directed 2026-08-27 — mirrors
// tools/health-osint/priority_domains.py (no shared config crosses the
// Python/TypeScript boundary anywhere else in this platform; kept in sync
// by comment cross-reference, same convention as MedicalView.tsx's
// STIMULATION_STATE_LABEL). Chronic Pain coverage added same day
// (migration 0178, parse_europepmc_chronic_pain.py) — 8 chronic_pain_*
// sub-tags now included below.
const PRIORITY_DOMAINS = new Set([
  'mental_health', 'supplement', 'performance',
  'neuro_adhd', 'neuro_autism', 'neuro_audhd',
  'neuro_sensory', 'neuro_regulation', 'neuro_executive_function',
  'neuro_burnout', 'neuro_masking', 'neuro_sleep', 'neuro_treatment',
  'neuro_work', 'neuro_lived_experience', 'neuro_australia_policy',
  'chronic_pain', 'chronic_pain_lived_experience',
  'chronic_pain_central_sensitization', 'chronic_pain_fibromyalgia',
  'chronic_pain_neuropathic', 'chronic_pain_medication',
  'chronic_pain_treatment', 'chronic_pain_flare',
]);

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
      p_value, published_at, collected_at, actionable_recommendation, canonical_url,
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
    source_url: s.canonical_url || s.health_source_registry?.source_url || null,
    signal_type: s.signal_type,
    health_domain: s.health_domain,
    confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
    source_name: s.health_source_registry?.source_name || 'Unknown',
    rank_score: s.rank_score,
    sample_size: s.sample_size,
    study_design: s.study_design,
    p_value: s.p_value,
    published_at: s.published_at,
    collected_at: s.collected_at,
    actionable_recommendation: s.actionable_recommendation,
  }));

  // Priority domains sort first within each confidence bucket (stable sort
  // — ties keep their existing rank_score DESC order from the query), so a
  // priority-area signal isn't crowded out of the top-N slice below by an
  // equally-ranked non-priority one. Confidence level itself is untouched;
  // this only reorders within a bucket, never moves a signal between them.
  const byPriorityThenRank = (a: any, b: any) => {
    const aPriority = PRIORITY_DOMAINS.has(a.health_domain) ? 1 : 0;
    const bPriority = PRIORITY_DOMAINS.has(b.health_domain) ? 1 : 0;
    return bPriority - aPriority;
  };

  return {
    domain: 'intelligence-summary',
    high: signalList.filter((s: any) => s.confidence_level === 'high').sort(byPriorityThenRank).slice(0, 15),
    medium: signalList.filter((s: any) => s.confidence_level === 'medium').sort(byPriorityThenRank).slice(0, 15),
    low: signalList.filter((s: any) => s.confidence_level === 'low').sort(byPriorityThenRank).slice(0, 8),
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
