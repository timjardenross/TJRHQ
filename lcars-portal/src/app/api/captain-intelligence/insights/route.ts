// MSN-0329 Phase 5 — reads already-generated Captain Intelligence insights
// from insight_outcomes directly (fast, no subprocess). Generation itself
// (slow — real LLM synthesis, 50-260s) is a separate, explicit action via
// POST /api/captain-intelligence/generate. This route only ever reads.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase
      .from('insight_outcomes')
      .select('id, generated_at, observation, why_it_matters, potential_impact, insight_confidence, recommended_action, alternatives, trade_offs, expected_outcome, recommendation_confidence, outcome, source_domains')
      .order('generated_at', { ascending: false })
      .limit(20);

    if (error) throw error;

    return NextResponse.json({ insights: data ?? [], count: data?.length ?? 0 });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to fetch Captain Intelligence insights', detail },
      { status: 500 },
    );
  }
}
