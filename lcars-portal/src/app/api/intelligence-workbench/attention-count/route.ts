// Technical OSINT top signal — for Captain's Chair's "Signal Snapshot"
// card. Deliberately not a count: a raw count (verified live: 1,851
// degraded intelligence_source_health rows) reads as noise, not a
// curated signal, on a Captain-facing summary (2026-08-22 feedback on
// the first pass at this). Returns the single highest-rated RED (else
// AMBER) event from the last 7 days, or null.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

interface TopSignal {
  title: string;
  risk_rating: string;
  canonical_url: string | null;
  collected_at: string;
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since7d = new Date(Date.now() - 7 * 86_400_000).toISOString();

    // RED first, AMBER only if nothing RED — text ordering can't express
    // that priority directly (alphabetically AMBER < RED), so two
    // targeted queries instead of one ORDER BY.
    let top: TopSignal | null = null;
    for (const risk of ['RED', 'AMBER']) {
      const { data, error } = await sb
        .from('intelligence_events')
        .select('raw_title,risk_rating,canonical_url,collected_at')
        .eq('suppressed', false)
        .eq('risk_rating', risk)
        .gte('collected_at', since7d)
        .order('collected_at', { ascending: false })
        .limit(1);
      if (error) throw new Error(`Failed to fetch top ${risk} signal: ${error.message}`);
      if (data && data.length > 0) {
        top = {
          title: data[0].raw_title,
          risk_rating: data[0].risk_rating,
          canonical_url: data[0].canonical_url,
          collected_at: data[0].collected_at,
        };
        break;
      }
    }

    return NextResponse.json({ top });
  } catch (err) {
    console.error('[intelligence-workbench/attention-count] read failed:', err);
    return NextResponse.json(
      { error: 'attention_count_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
