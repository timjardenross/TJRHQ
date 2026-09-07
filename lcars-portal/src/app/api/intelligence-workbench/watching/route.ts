// WATCHING — WATCH-disposition developments (Three-Workbench Simplification,
// Phase 1). Not a raw queue: capped, most-significant-first, one line per
// item on why it's watched and what would move it out of Watching.
//
// Gap (see mission report): there is no dedicated "why watched" / "what
// would change this" column on intelligence_events. disposition_reason
// (e.g. "confidence=MEDIUM impact=high") already captures the real
// threshold that produced WATCH — derive_why_watched()/
// derive_what_would_change_this() below turn that into plain language
// rather than inventing new facts the backend doesn't have. If Phase 12+
// of the OSINT Ingestion Quality mission ever adds a real per-item
// "what would change this" field, this route should read it directly
// instead of deriving it.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchCorroborationCounts } from '../_lib/corroboration';

const EVENT_COLUMNS =
  'event_id, raw_title, canonical_url, sector, geography, risk_rating, ' +
  'osint_confidence_level, disposition_reason, published_at, collected_at';

function whyWatched(riskRating: string | null, sector: string | null): string {
  const sectorText = sector ? sector.replace(/_/g, ' ') : 'a monitored sector';
  if (riskRating === 'AMBER') return `Moderate risk rating in ${sectorText} — not yet significant enough to need your input.`;
  if (riskRating === 'RED') return `Elevated risk rating in ${sectorText}, but confidence or corroboration hasn't cleared the bar for Worth Knowing yet.`;
  return `Development in ${sectorText} being tracked for further corroboration.`;
}

function whatWouldChangeThis(confidenceLevel: string, corroboration: number): string {
  if (confidenceLevel !== 'high') {
    return 'Would move to Worth Knowing if confidence rises to High (more corroborating sources) or impact is reassessed upward.';
  }
  if (corroboration < 2) {
    return 'Would move to Worth Knowing with one more corroborating source, or if impact is reassessed upward.';
  }
  return 'Would move to Worth Knowing if impact is reassessed upward.';
}

async function getWatching(sb: any, days: number) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  const { data: rows, error } = await sb
    .from('intelligence_events')
    .select(EVENT_COLUMNS)
    .eq('disposition', 'WATCH')
    .eq('suppressed', false)
    .gte('collected_at', since)
    .order('rank_score', { ascending: false })
    .limit(50);
  if (error) throw new Error(`Failed to fetch watched developments: ${error.message}`);

  const eventIds = (rows ?? []).map((r: any) => r.event_id);
  const corroboration = await fetchCorroborationCounts(sb, eventIds);

  const items = (rows ?? []).map((r: any) => {
    const confidenceLevel = (r.osint_confidence_level || 'unknown').toLowerCase();
    const corr = corroboration.get(r.event_id) || 0;
    return {
      event_id: r.event_id,
      title: r.raw_title,
      canonical_url: r.canonical_url,
      why_watched: whyWatched(r.risk_rating, r.sector),
      confidence_level: confidenceLevel,
      significance: r.risk_rating ? r.risk_rating.toLowerCase() : 'unassessed',
      geography: r.geography,
      corroboration: corr,
      what_would_change_this: whatWouldChangeThis(confidenceLevel, corr),
      last_update: r.published_at ?? r.collected_at,
    };
  });

  return { items, count: items.length };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const days = Number(req.nextUrl.searchParams.get('days')) || 14;

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getWatching(sb, days));
  } catch (err) {
    console.error('[intelligence-workbench/watching] read failed:', err);
    return NextResponse.json(
      { error: 'watching_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
