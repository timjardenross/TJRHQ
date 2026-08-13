// Health Confidence Matrix API — signal distribution by health category & confidence level

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

const CATEGORIES = ['Epidemiology', 'Treatment', 'Adverse Events', 'Performance', 'Research Quality'] as const;

// health_domain has two live vocabularies: the original flat 6 values
// (epidemiology/treatment/supplement/performance/mental_health/vaccine,
// still used by hand-curated PubMed/ClinicalTrials.gov signals via
// tools/health/collect_health_signals.py) and the granular
// HEALTH_OSINT_IMPLEMENTATION.md section-3 taxonomy the 6 automated-fetch
// parsers use (epi_*, safety_*, evidence_*, performance_*, factor_*,
// mental_health_*) — both need to map into the same 5 UI buckets, not
// just the flat one (everything from the granular vocabulary was
// silently falling through to "Treatment" before this fix).
function categorize(signalType: string, healthDomain: string, methodologyQuality: number | null): string {
  if (signalType === 'adverse_event' || healthDomain.startsWith('safety_')) return 'Adverse Events';
  if (healthDomain === 'epidemiology' || healthDomain.startsWith('epi_')) return 'Epidemiology';
  if (healthDomain === 'performance' || healthDomain.startsWith('performance_')) return 'Performance';
  if (healthDomain.startsWith('evidence_')) return 'Research Quality';
  if (methodologyQuality !== null && methodologyQuality < 0.4) return 'Research Quality';
  return 'Treatment';
}

async function getConfidenceMatrix(sb: any) {
  const since = new Date(Date.now() - DAYS_365).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('health_signals')
    .select(`
      signal_id,
      title,
      signal_type,
      health_domain,
      methodology_quality_score,
      confidence_level,
      rank_score,
      source_id,
      canonical_url,
      health_source_registry ( source_name, source_url, reliability_tier, reliability_score )
    `)
    .eq('suppressed', false)
    .gte('collected_at', since)
    .order('rank_score', { ascending: false });

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const signalList = (signals ?? []).map((s: any) => ({
    signal_id: s.signal_id,
    title: s.title,
    health_domain: s.health_domain,
    signal_type: s.signal_type,
    category: categorize(s.signal_type, s.health_domain, s.methodology_quality_score),
    confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
    rank_score: s.rank_score,
    source_name: s.health_source_registry?.source_name || 'Unknown',
    source_url: s.canonical_url || s.health_source_registry?.source_url || null,
    srs: s.health_source_registry?.reliability_score ?? null,
  }));

  const matrix: Record<string, Record<string, number>> = {};
  for (const c of CATEGORIES) matrix[c] = { high: 0, medium: 0, low: 0, unknown: 0 };

  signalList.forEach((s: any) => {
    if (matrix[s.category] && matrix[s.category][s.confidence_level] !== undefined) {
      matrix[s.category][s.confidence_level]++;
    }
  });

  return {
    domain: 'confidence-matrix',
    matrix,
    signals: signalList.slice(0, 50),
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getConfidenceMatrix(sb));
  } catch (err) {
    console.error('[health-osint/confidence-matrix] read failed:', err);
    return NextResponse.json(
      { error: 'matrix_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
