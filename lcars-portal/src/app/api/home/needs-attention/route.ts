// Home dashboard — "needs attention" aggregation across all surfaces
// Pulls from: hot signals, interrupt_now, IN_REVIEW briefs, stale sources

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    // ── Hot signals (last 7 days, RED/AMBER risk) ────────────────────────
    const { data: hotSignals, error: signalsError } = await sb
      .from('intelligence_events')
      .select('event_id,raw_title,risk_rating,sector,collected_at,canonical_url')
      .eq('suppressed', false)
      .in('risk_rating', ['RED', 'AMBER'])
      .gte('collected_at', new Date(Date.now() - 7 * 86400000).toISOString())
      .order('collected_at', { ascending: false })
      .limit(5);
    if (signalsError) throw signalsError;

    // ── Pending QA briefs (IN_REVIEW status) ─────────────────────────────
    const { data: pendingBriefs, error: briefs Error } = await sb
      .from('intelligence_briefs')
      .select('brief_id,overall_risk,approval_status,generated_at,executive_snapshot')
      .eq('approval_status', 'IN_REVIEW')
      .order('generated_at', { ascending: true })
      .limit(3);
    if (briefsError) throw briefsError;

    // ── Captain's Brief interrupt_now items ──────────────────────────────
    const { data: interrupts, error: interruptsError } = await sb
      .from('captains_daily_briefs')
      .select('id,brief_type,signals_count,generated_at')
      .eq('brief_type', 'interrupt_now')
      .order('generated_at', { ascending: false })
      .limit(2);
    if (interruptsError) throw interruptsError;

    // ── Source health (stale or failed sources) ──────────────────────────
    const oneHourAgo = new Date(Date.now() - 3600000).toISOString();
    const { data: staleSources, error: sourcesError } = await sb
      .from('intelligence_source_health')
      .select('source_id,status,checked_at,error_message')
      .in('status', ['stale', 'failed'])
      .lte('checked_at', oneHourAgo)
      .order('checked_at', { ascending: true })
      .limit(3);
    if (sourcesError) throw sourcesError;

    const items = {
      hotSignals: hotSignals ?? [],
      pendingBriefs: pendingBriefs ?? [],
      interrupts: interrupts ?? [],
      staleSources: staleSources ?? [],
      hasAnything: (hotSignals?.length ?? 0) + (pendingBriefs?.length ?? 0) +
                   (interrupts?.length ?? 0) + (staleSources?.length ?? 0) > 0,
    };

    return NextResponse.json(items);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load home data', detail }, { status: 500 });
  }
}
