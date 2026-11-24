// Home dashboard — "needs attention" aggregation across all surfaces
// Pulls from: hot signals, interrupt_now, stale sources

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';
import { materialExceptions, type MaterialException } from '@/lib/sourceEffectiveness';
import { loadSourceRows } from '@/app/api/intelligence-workbench/_lib/sourceCoverage';
import { fetchIncidentSnapshot, incidentViewEnabled, type IncidentRow } from '@/lib/incidents';

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

    // 2026-08-22: the IN_REVIEW/QA_PASSED "pending briefs" section that used
    // to live here is gone — briefs now auto-publish at generation
    // (intelligence/persistence/intelligence_store.py:save_brief()), so
    // this is a single-user platform with no review queue left to surface.
    // The ~27 rows still sitting IN_REVIEW/QA_PASSED are pre-redesign
    // history that will never move (nothing publishes them, nothing ever
    // will) — querying them here just showed the same 3 stale legacy
    // briefs forever, permanently reading as "awaiting your decision" when
    // there was nothing to decide. See /briefs (defaults to Today) for the
    // real archive, including that legacy history if wanted.

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

    // Source coverage: only a material exception (a BROKEN priority source,
    // 3+ days without a successful check; one entry per stable key). Additive and best-effort: a failure here never breaks the
    // existing sections.
    let sourceCoverage: MaterialException[] = [];
    try {
      sourceCoverage = materialExceptions(await loadSourceRows(sb));
    } catch (e) {
      console.error('[home/needs-attention] source coverage failed:', e);
    }

    // Clustered incidents (INCIDENT_VIEW_V1, default OFF): alert-level incidents and material exceptions, one entry per incident_key -
    // the same key the Telegram alert and the Decisions inbox use. Unavailable snapshot data adds nothing (never an all-clear claim).
    const incidentsOn = incidentViewEnabled();
    const incidents: IncidentRow[] = incidentsOn
      ? (await fetchIncidentSnapshot(sb, { attentionOnly: true, limit: 50 })).incidents.slice(0, 5)
      : [];

    const items = {
      hotSignals: hotSignals ?? [],
      ...(incidentsOn ? { incidents } : {}),
      interrupts: interrupts ?? [],
      staleSources: staleSources ?? [],
      sourceCoverage,
      hasAnything: (hotSignals?.length ?? 0) +
                   (interrupts?.length ?? 0) + (staleSources?.length ?? 0) + sourceCoverage.length + incidents.length > 0,
    };

    return NextResponse.json(items);
  } catch (err) {
    const detail = errorDetail(err);
    return NextResponse.json({ error: 'Failed to load home data', detail }, { status: 500 });
  }
}
