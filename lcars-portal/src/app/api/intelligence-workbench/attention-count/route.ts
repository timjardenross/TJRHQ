// Technical OSINT attention counts — for Captain's Chair's "Needs Your
// Attention" strip. Deliberately separate from /api/home/needs-attention,
// which queries the same two tables but with .limit(3)/.limit(5) — correct
// for "show me the top few", wrong for a count tile (a true count of 1,851
// degraded sources would silently read as "3"). True {count:'exact',
// head:true} counts here instead, no cap.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since7d = new Date(Date.now() - 7 * 86_400_000).toISOString();
    const oneHourAgo = new Date(Date.now() - 3_600_000).toISOString();

    const [hotSignalsRes, sourcesDegradedRes] = await Promise.all([
      sb.from('intelligence_events')
        .select('event_id', { count: 'exact', head: true })
        .eq('suppressed', false)
        .in('risk_rating', ['RED', 'AMBER'])
        .gte('collected_at', since7d),
      sb.from('intelligence_source_health')
        .select('source_id', { count: 'exact', head: true })
        .in('status', ['stale', 'failed'])
        .lte('checked_at', oneHourAgo),
    ]);

    if (hotSignalsRes.error) throw new Error(`Failed to count hot signals: ${hotSignalsRes.error.message}`);
    if (sourcesDegradedRes.error) throw new Error(`Failed to count degraded sources: ${sourcesDegradedRes.error.message}`);

    return NextResponse.json({
      hotSignals: hotSignalsRes.count ?? 0,
      sourcesDegraded: sourcesDegradedRes.count ?? 0,
    });
  } catch (err) {
    console.error('[intelligence-workbench/attention-count] read failed:', err);
    return NextResponse.json(
      { error: 'attention_count_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
