// GET /api/health-osint-curation/pending — auto-ingested health signals
// awaiting Sunday-night curation (HEALTH_OSINT_IMPLEMENTATION.md Phase 5).
//
// Only signals with auto_ingested=true AND auto_ingest_reviewed=false — a
// dedicated review-status column (migration 0143), not suppressed alone:
// suppressed just controls whether a signal shows in the main dashboard,
// and both publish (suppressed=false) and reject (suppressed stays true)
// need to make a signal disappear from THIS queue once decided, which
// suppressed alone can't distinguish. A signal published via any other
// path (PubMed/ClinicalTrials.gov hand-curated ingestion, manual insert)
// never shows up here — this is specifically the automated-fetch review
// queue, not a general moderation inbox.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    const { data: signals, error } = await sb
      .from('health_signals')
      .select(`
        signal_id, title, description, signal_type, health_domain,
        contributing_factor_type, source_id, collected_at, published_at,
        canonical_url,
        mission_relevance, relevance_reason, evidence_contribution,
        population_fit, safety_relevance, disposition, disposition_reason,
        health_source_registry(source_name)
      `)
      .eq('auto_ingested', true)
      .eq('auto_ingest_reviewed', false)
      // Oldest first, matching health_signal_curation.py's own oldest-first
      // processing order — if the backlog ever exceeds this cap, it's the
      // newest (least overdue) rows that fall off the human queue, not the
      // most-overdue ones the engine keeps re-classifying into ESCALATE
      // every cycle while nobody ever sees them.
      .order('collected_at', { ascending: true })
      .limit(500);
    if (error) throw error;

    const { data: fetchStats } = await sb
      .from('health_source_fetch_config')
      .select('last_fetch, last_fetch_status, last_fetch_message, health_source_registry(source_name)')
      .order('last_fetch', { ascending: false });

    return NextResponse.json({
      signals: (signals ?? []).map((s) => ({
        ...s,
        source_name: (s as any).health_source_registry?.source_name ?? null,
      })),
      fetch_stats: (fetchStats ?? []).map((r) => ({
        source_name: (r as any).health_source_registry?.source_name ?? null,
        last_fetch: r.last_fetch,
        last_fetch_status: r.last_fetch_status,
        last_fetch_message: r.last_fetch_message,
      })),
    });
  } catch (err) {
    console.error('[health-osint-curation/pending]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
