// GET /api/health-osint/library — retained studies / evidence summaries /
// reference research (Phase 2 mission spec). Supports search, topic filter,
// evidence-contribution filter, date filter, evidence-strength filter.
// Does NOT default to browsing every ingested paper: with no filters this
// still applies a default lookback window and a page size cap, same
// "don't dump the whole table" instinct as the other health-osint routes.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { topicForDomain } from '@/lib/healthOsintTopics';

const DAYS_365 = 365 * 86_400_000;
const PAGE_SIZE = 40;

const STRENGTH_TO_CONFIDENCE: Record<string, string[]> = {
  STRONG: ['HIGH'],
  MODERATE: ['MEDIUM'],
  LIMITED: ['LOW', 'UNKNOWN'],
};

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const sp = req.nextUrl.searchParams;
  const q = sp.get('q')?.trim() || null;
  const topicKey = sp.get('topic') || null;
  const evidenceContribution = sp.get('evidence_contribution') || null;
  const strength = sp.get('strength') || null;
  const since = sp.get('since') || null; // ISO date string
  const until = sp.get('until') || null;
  const page = Math.max(0, parseInt(sp.get('page') || '0', 10) || 0);

  try {
    const sb = await createSupabaseServerClient();

    let query = sb
      .from('health_signals')
      .select(`
        signal_id, title, description, health_domain, confidence_level, rank_score,
        study_design, sample_size, published_at, collected_at, canonical_url,
        disposition, evidence_contribution, safety_relevance,
        health_source_registry ( source_name, source_url )
      `, { count: 'exact' })
      .eq('suppressed', false);

    if (q) query = query.or(`title.ilike.%${q}%,description.ilike.%${q}%`);
    if (evidenceContribution) query = query.eq('evidence_contribution', evidenceContribution);
    if (strength && STRENGTH_TO_CONFIDENCE[strength]) {
      query = query.in('confidence_level', STRENGTH_TO_CONFIDENCE[strength]);
    }
    if (since) query = query.gte('collected_at', since);
    if (until) query = query.lte('collected_at', until);
    if (!since && !until) query = query.gte('collected_at', new Date(Date.now() - DAYS_365).toISOString());

    query = query.order('collected_at', { ascending: false }).range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1);

    const { data, error, count } = await query;
    if (error) throw new Error(error.message);

    let rows = (data ?? []).map((s: any) => ({
      signal_id: s.signal_id,
      title: s.title,
      summary: s.description ? s.description.slice(0, 240) : null,
      source_url: s.canonical_url || s.health_source_registry?.source_url || null,
      source_name: s.health_source_registry?.source_name || 'Unknown',
      topic_key: topicForDomain(s.health_domain).key,
      topic_label: topicForDomain(s.health_domain).label,
      confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
      study_design: s.study_design,
      sample_size: s.sample_size,
      published_at: s.published_at,
      collected_at: s.collected_at,
      evidence_contribution: s.evidence_contribution,
      disposition: s.disposition,
      safety_relevance: !!s.safety_relevance,
    }));

    // topic filter applied post-query (topic is a derived grouping over
    // health_domain, not a stored column, so it can't be pushed into the
    // Postgres filter above).
    if (topicKey) rows = rows.filter((r) => r.topic_key === topicKey);

    return NextResponse.json({
      items: rows,
      total: count ?? rows.length,
      page,
      page_size: PAGE_SIZE,
      has_more: (count ?? 0) > (page + 1) * PAGE_SIZE,
    });
  } catch (err) {
    console.error('[health-osint/library] read failed:', err);
    return NextResponse.json(
      { error: 'library_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
