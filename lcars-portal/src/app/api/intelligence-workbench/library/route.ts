// LIBRARY — historical assessments, past-briefed items, REFERENCE-disposition
// items and resolved watch items (Three-Workbench Simplification, Phase 1).
// Supports search, date range, sector ("domain") and disposition filters.
// SUPPRESS items are excluded by default (mission: hidden from all normal
// views) but remain queryable here via an explicit ?disposition=SUPPRESS —
// never hard-deleted, never hidden from the database.
//
// Gap: ~80% of historical rows predate migration 0186's disposition
// backfill and have disposition = NULL (Phase 13 reprocessing, OSINT
// Ingestion Quality mission, has not run). Those rows are surfaced here as
// disposition "UNCLASSIFIED" rather than silently dropped — Library is
// explicitly the place mission spec says historical/older items belong,
// so hiding the un-backfilled majority of history would be worse than
// labelling it honestly.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchCorroborationCounts } from '../_lib/corroboration';

const EVENT_COLUMNS =
  'event_id, raw_title, canonical_url, sector, geography, disposition, ' +
  'osint_confidence_level, published_at, collected_at, brief_id';

const PAGE_SIZE = 40;

async function getLibrary(sb: any, params: {
  q: string | null;
  since: string | null;
  until: string | null;
  sector: string | null;
  disposition: string | null;
  page: number;
}) {
  let query = sb
    .from('intelligence_events')
    .select(EVENT_COLUMNS, { count: 'exact' })
    .neq('signal_status', 'DUPLICATE')
    .order('collected_at', { ascending: false });

  if (params.disposition === 'SUPPRESS') {
    query = query.eq('disposition', 'SUPPRESS');
  } else if (params.disposition === 'UNCLASSIFIED') {
    query = query.is('disposition', null).eq('suppressed', false);
  } else if (params.disposition) {
    query = query.eq('disposition', params.disposition).eq('suppressed', false);
  } else {
    // Default view: everything except hidden (SUPPRESS) items.
    query = query.eq('suppressed', false).or('disposition.is.null,disposition.neq.SUPPRESS');
  }

  if (params.q) query = query.ilike('raw_title', `%${params.q}%`);
  if (params.since) query = query.gte('collected_at', params.since);
  if (params.until) query = query.lte('collected_at', params.until);
  if (params.sector) query = query.eq('sector', params.sector);

  const from = params.page * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;
  query = query.range(from, to);

  const { data: rows, error, count } = await query;
  if (error) throw new Error(`Failed to fetch library items: ${error.message}`);

  const eventIds = (rows ?? []).map((r: any) => r.event_id);
  const corroboration = await fetchCorroborationCounts(sb, eventIds);

  const items = (rows ?? []).map((r: any) => ({
    event_id: r.event_id,
    title: r.raw_title,
    canonical_url: r.canonical_url,
    disposition: r.disposition ?? 'UNCLASSIFIED',
    sector: r.sector,
    geography: r.geography,
    confidence_level: (r.osint_confidence_level || 'unknown').toLowerCase(),
    corroboration: corroboration.get(r.event_id) || 0,
    published_at: r.published_at ?? r.collected_at,
    brief_id: r.brief_id,
  }));

  return { items, total: count ?? items.length, page: params.page, page_size: PAGE_SIZE };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const sp = req.nextUrl.searchParams;
  const params = {
    q: sp.get('q'),
    since: sp.get('since'),
    until: sp.get('until'),
    sector: sp.get('sector'),
    disposition: sp.get('disposition'),
    page: Math.max(0, Number(sp.get('page')) || 0),
  };

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getLibrary(sb, params));
  } catch (err) {
    console.error('[intelligence-workbench/library] read failed:', err);
    return NextResponse.json(
      { error: 'library_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
