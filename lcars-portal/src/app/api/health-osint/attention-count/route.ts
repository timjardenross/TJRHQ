// Health OSINT attention count — for Captain's Chair's "Needs Your
// Attention" strip. Mirrors threat-assessment/route.ts's own
// escalation rule exactly (severity -> impact, confidence-gated), but as
// a single count rather than the full ranked matrix, and without that
// route's .limit(20) — an attention count must reflect every signal that
// would escalate, not just the top-20 by rank_score.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

// escalate requires confidence 'high' AND impact 'critical' or 'high' —
// impact 'critical' comes from severity 'critical', impact 'high' comes
// from severity 'severe' (see threat-assessment/route.ts's SEVERITY_IMPACT).
const ESCALATE_SEVERITIES = ['critical', 'severe'];

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - DAYS_365).toISOString();

    const { count, error } = await sb
      .from('health_signals')
      .select('signal_id', { count: 'exact', head: true })
      .eq('suppressed', false)
      .gte('collected_at', since)
      .in('signal_type', ['adverse_event', 'safety_alert'])
      .in('severity', ESCALATE_SEVERITIES)
      .ilike('confidence_level', 'high');

    if (error) throw new Error(`Failed to count health signals: ${error.message}`);

    return NextResponse.json({ count: count ?? 0 });
  } catch (err) {
    console.error('[health-osint/attention-count] read failed:', err);
    return NextResponse.json(
      { error: 'attention_count_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
