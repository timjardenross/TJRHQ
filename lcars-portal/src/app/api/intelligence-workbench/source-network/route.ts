// Source Network API — corroboration patterns and source trending
//
// Reads the persisted signal_corroboration table (populated by
// tools/intelligence/recompute_signal_scores.py) instead of recomputing
// title-word overlap in-memory on every request. Trending reads real
// source_reliability_snapshot history — until 30 days of daily snapshots
// accumulate, reports insufficient_data honestly rather than the 2
// hardcoded placeholder entries this route used to return.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

async function getSourceNetwork(sb: any, days: number, includeSuppressed: boolean) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  let query = sb
    .from('intelligence_events')
    .select('event_id, source_id, intelligence_source_registry(source_name, reliability_tier, reliability_score)')
    .gte('collected_at', since)
    .order('rank_score', { ascending: false })
    .limit(100);

  if (!includeSuppressed) query = query.eq('suppressed', false);

  const { data: signals, error: signalsErr } = await query;
  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const signalList = signals ?? [];
  const eventIds = signalList.map((s: any) => s.event_id);

  const { data: corroborations, error: corrErr } = await sb
    .from('signal_corroboration')
    .select('signal_id, corroborating_signal_id, title_word_overlap')
    .or(`signal_id.in.(${eventIds.join(',') || 'null'}),corroborating_signal_id.in.(${eventIds.join(',') || 'null'})`);

  if (corrErr) throw new Error(`Failed to fetch corroborations: ${corrErr.message}`);

  const signalToSource = new Map<string, string>();
  signalList.forEach((s: any) => signalToSource.set(s.event_id, s.intelligence_source_registry?.source_name || 'Unknown'));

  const corroboratedSignalIds = new Set<string>();
  (corroborations ?? []).forEach((c: any) => {
    corroboratedSignalIds.add(c.signal_id);
    corroboratedSignalIds.add(c.corroborating_signal_id);
  });

  const correlations: Record<string, any> = {};
  signalList.forEach((s: any) => {
    const name = s.intelligence_source_registry?.source_name || 'Unknown';
    if (!correlations[name]) {
      correlations[name] = { signal_count: 0, corroboration_count: 0 };
    }
    correlations[name].signal_count++;
    if (corroboratedSignalIds.has(s.event_id)) correlations[name].corroboration_count++;
  });
  Object.values(correlations).forEach((c: any) => {
    c.avg_confirmation_per_signal = c.signal_count > 0 ? Number((c.corroboration_count / c.signal_count).toFixed(2)) : 0;
  });

  // Trending: real 30-day snapshot history, not hardcoded placeholders.
  const since30d = new Date(Date.now() - 30 * 86_400_000).toISOString();
  const { data: snapshots, error: snapErr } = await sb
    .from('source_reliability_snapshot')
    .select('source_id, reliability_score, snapshotted_at, intelligence_source_registry(source_name)')
    .gte('snapshotted_at', since30d)
    .order('snapshotted_at', { ascending: true });

  if (snapErr) throw new Error(`Failed to fetch snapshots: ${snapErr.message}`);

  const bySource = new Map<string, any[]>();
  (snapshots ?? []).forEach((s: any) => {
    const arr = bySource.get(s.source_id) || [];
    arr.push(s);
    bySource.set(s.source_id, arr);
  });

  const trending = Array.from(bySource.entries()).map(([sourceId, snaps]) => {
    const name = snaps[0].intelligence_source_registry?.source_name || sourceId;
    if (snaps.length < 2) {
      return { source: name, direction: 'insufficient_data', from: null, to: snaps[0]?.reliability_score ?? null, days: 0 };
    }
    const from = snaps[0].reliability_score;
    const to = snaps[snaps.length - 1].reliability_score;
    const spanDays = Math.round((new Date(snaps[snaps.length - 1].snapshotted_at).getTime() - new Date(snaps[0].snapshotted_at).getTime()) / 86_400_000);
    const direction = to > from + 0.02 ? 'up' : to < from - 0.02 ? 'down' : 'stable';
    return { source: name, direction, from, to, days: spanDays };
  });

  return {
    domain: 'source-network',
    correlations,
    trending,
    note: trending.every((t: any) => t.direction === 'insufficient_data')
      ? 'No source has 30 days of reliability snapshots yet (daily job just activated) — reporting current scores only.'
      : undefined,
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const days = Number(req.nextUrl.searchParams.get('days')) || 7;
  const includeSuppressed = req.nextUrl.searchParams.get('suppressed') === 'true';

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getSourceNetwork(sb, days, includeSuppressed));
  } catch (err) {
    console.error('[source-network] read failed:', err);
    return NextResponse.json(
      { error: 'network_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
