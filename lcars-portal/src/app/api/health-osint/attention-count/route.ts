// Health OSINT top signal — for Captain's Chair's "Signal Snapshot" card.
// Mirrors threat-assessment/route.ts's own escalation rule exactly
// (severity -> impact, confidence-gated: escalate = high confidence +
// critical/severe severity, see SEVERITY_IMPACT there), but returns the
// single highest-rated escalating signal instead of the full ranked
// matrix or a raw count — a curated top item, not noise (2026-08-22).

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

interface TopSignal {
  title: string;
  severity: string;
  confidence_level: string;
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - DAYS_365).toISOString();

    // 'critical' severity first, 'severe' only if nothing critical.
    let top: TopSignal | null = null;
    for (const severity of ['critical', 'severe']) {
      const { data, error } = await sb
        .from('health_signals')
        .select('title,severity,confidence_level,rank_score')
        .eq('suppressed', false)
        .gte('collected_at', since)
        .in('signal_type', ['adverse_event', 'safety_alert'])
        .eq('severity', severity)
        .ilike('confidence_level', 'high')
        .order('rank_score', { ascending: false })
        .limit(1);
      if (error) throw new Error(`Failed to fetch top ${severity} signal: ${error.message}`);
      if (data && data.length > 0) {
        top = { title: data[0].title, severity: data[0].severity, confidence_level: data[0].confidence_level };
        break;
      }
    }

    return NextResponse.json({ top });
  } catch (err) {
    console.error('[health-osint/attention-count] read failed:', err);
    return NextResponse.json(
      { error: 'attention_count_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
