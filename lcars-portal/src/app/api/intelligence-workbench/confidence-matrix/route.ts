// Confidence Matrix API — signal distribution by category & confidence level
// Shows coverage gaps and over-reliance patterns for OSINT tradecraft

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

async function getConfidenceMatrix(sb: any, days: number, includeSuppressed: boolean) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  // osint_confidence_level is persisted server-side by tools/intelligence/
  // recompute_signal_scores.py (source tier + corroboration count, per
  // TECHNICAL_OSINT_WORKBENCH.md section 3) — not derived live from tier here
  // anymore, so it reflects real corroboration, not just source tier alone.
  let query = sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      sector,
      risk_rating,
      rank_score,
      osint_confidence_level,
      source_id,
      intelligence_source_registry (
        reliability_tier,
        reliability_score,
        category
      )
    `)
    .gte('collected_at', since)
    .order('rank_score', { ascending: false });

  if (!includeSuppressed) query = query.eq('suppressed', false);
  query = query.neq('signal_status', 'DUPLICATE');

  const { data: signals, error: signalsErr } = await query;
  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  // Map signal sectors to OSINT categories. Keys match intelligence_events.sector's
  // actual values (verified against live data — the prior map used
  // 'cybersecurity'/'infrastructure'/'operational'/'compliance', none of which
  // occur in the column; every row fell through to the 'Intelligence' default).
  const categoryMap: Record<string, string> = {
    'cyber_security': 'Cybersecurity',
    'technology': 'Infrastructure',
    'energy': 'Infrastructure',
    'transport': 'Infrastructure',
    'emergency_management': 'Infrastructure',
    'financial_services': 'Regulatory',
    'general': 'Intelligence',
    'cross_sector': 'Intelligence',
  };

  const signalList = (signals ?? []).map((s: any) => {
    const tier = s.intelligence_source_registry?.reliability_tier || 'TIER_4';
    const category = categoryMap[s.sector?.toLowerCase() || 'intelligence'] || 'Intelligence';
    const confidenceLevel = (s.osint_confidence_level || 'UNKNOWN').toLowerCase();

    return {
      event_id: s.event_id,
      raw_title: s.raw_title,
      category,
      confidence_level: confidenceLevel,
      tier,
      srs: s.intelligence_source_registry?.reliability_score ?? 0.75,
      rank_score: s.rank_score,
    };
  });

  const matrix: Record<string, Record<string, number>> = {
    'Cybersecurity': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Infrastructure': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Regulatory': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Intelligence': { high: 0, medium: 0, low: 0, unknown: 0 },
  };

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

  const days = Number(req.nextUrl.searchParams.get('days')) || 7;
  const includeSuppressed = req.nextUrl.searchParams.get('suppressed') === 'true';

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getConfidenceMatrix(sb, days, includeSuppressed));
  } catch (err) {
    console.error('[confidence-matrix] read failed:', err);
    return NextResponse.json(
      { error: 'matrix_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
