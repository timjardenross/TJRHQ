// Confidence Matrix API — signal distribution by category & confidence level
// Shows coverage gaps and over-reliance patterns for OSINT tradecraft

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_7 = 7 * 86_400_000;

async function getConfidenceMatrix(sb: any) {
  const since7d = new Date(Date.now() - DAYS_7).toISOString();

  // Get all signals with source reliability context
  const { data: signals, error: signalsErr } = await sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      sector,
      risk_rating,
      rank_score,
      confidence,
      source_id,
      intelligence_source_registry (
        reliability_tier,
        reliability_score,
        category
      )
    `)
    .eq('suppressed', false)
    .gte('collected_at', since7d)
    .order('rank_score', { ascending: false });

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  // Map signal sectors to OSINT categories
  const categoryMap: Record<string, string> = {
    'cybersecurity': 'Cybersecurity',
    'cyber': 'Cybersecurity',
    'infrastructure': 'Infrastructure',
    'operational': 'Infrastructure',
    'regulatory': 'Regulatory',
    'compliance': 'Regulatory',
    'intelligence': 'Intelligence',
  };

  // Determine confidence level from source tier
  const signalList = (signals ?? []).map((s: any) => {
    const tier = s.intelligence_source_registry?.reliability_tier || 'TIER_4';
    const category = categoryMap[s.sector?.toLowerCase() || 'intelligence'] || 'Intelligence';

    let confidenceLevel = 'low';
    if (tier === 'TIER_1') confidenceLevel = 'high';
    else if (tier === 'TIER_2') confidenceLevel = 'medium';
    else if (tier === 'TIER_3') confidenceLevel = 'low';

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

  // Build matrix: category × confidence
  const matrix: Record<string, Record<string, number>> = {
    'Cybersecurity': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Infrastructure': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Regulatory': { high: 0, medium: 0, low: 0, unknown: 0 },
    'Intelligence': { high: 0, medium: 0, low: 0, unknown: 0 },
  };

  signalList.forEach((s: any) => {
    if (matrix[s.category]) {
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
    console.error('[confidence-matrix] read failed:', err);
    return NextResponse.json(
      { error: 'matrix_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
