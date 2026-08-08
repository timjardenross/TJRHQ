// Health Source Network API — corroboration patterns and source reliability
//
// Corroboration uses the real health_signal_corroboration table (unlike the
// technical workbench's title-word-overlap heuristic — health signals carry
// an explicit corroboration table). Trending is reported as a current
// snapshot: reliability_score is a GENERATED column with no historical
// series stored yet, so we do not fabricate direction/from/to — that needs
// a daily SRS-snapshot job per HEALTH_OSINT_WORKBENCH.md section 6.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

async function getSourceNetwork(sb: any) {
  const since = new Date(Date.now() - DAYS_365).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('health_signals')
    .select('signal_id, source_id, health_source_registry ( source_name, reliability_tier, reliability_score )')
    .eq('suppressed', false)
    .gte('collected_at', since);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const { data: corroborations, error: corrErr } = await sb
    .from('health_signal_corroboration')
    .select('signal_id, corroborating_signal_id, agreement_strength');

  if (corrErr) throw new Error(`Failed to fetch corroborations: ${corrErr.message}`);

  const signalToSource = new Map<string, { source_id: string; source_name: string }>();
  (signals ?? []).forEach((s: any) => {
    signalToSource.set(s.signal_id, {
      source_id: s.source_id,
      source_name: s.health_source_registry?.source_name || 'Unknown',
    });
  });

  const corroboratedSignalIds = new Set<string>();
  const agreementBySource: Record<string, number[]> = {};
  (corroborations ?? []).forEach((c: any) => {
    corroboratedSignalIds.add(c.signal_id);
    corroboratedSignalIds.add(c.corroborating_signal_id);
    const src = signalToSource.get(c.signal_id);
    if (src) {
      agreementBySource[src.source_name] = agreementBySource[src.source_name] || [];
      agreementBySource[src.source_name].push(c.agreement_strength ?? 0);
    }
  });

  const correlations: Record<string, any> = {};
  (signals ?? []).forEach((s: any) => {
    const name = s.health_source_registry?.source_name || 'Unknown';
    if (!correlations[name]) {
      correlations[name] = { signal_count: 0, corroborating_signals: 0, agreement_strength: 0 };
    }
    correlations[name].signal_count++;
    if (corroboratedSignalIds.has(s.signal_id)) correlations[name].corroborating_signals++;
  });
  Object.entries(agreementBySource).forEach(([name, vals]) => {
    if (correlations[name]) {
      correlations[name].agreement_strength = Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2));
    }
  });

  const bySourceName = new Map<string, any>();
  (signals ?? []).forEach((s: any) => {
    const name = s.health_source_registry?.source_name;
    if (name && !bySourceName.has(name)) bySourceName.set(name, s.health_source_registry);
  });
  const trending = Array.from(bySourceName.entries()).map(([name, reg]: any) => ({
    source: name,
    direction: 'insufficient_data',
    srs_from: reg.reliability_score,
    srs_to: reg.reliability_score,
    days: 0,
  }));

  return {
    domain: 'source-network',
    correlations,
    trending,
    note: 'Trending requires a daily SRS-snapshot job (not yet scheduled) — showing current reliability_score only.',
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getSourceNetwork(sb));
  } catch (err) {
    console.error('[health-osint/source-network] read failed:', err);
    return NextResponse.json(
      { error: 'network_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
