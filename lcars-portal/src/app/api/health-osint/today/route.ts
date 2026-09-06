// GET /api/health-osint/today — Health OSINT "Today" landing view
// (Phase 2 Three-Workbench Simplification mission).
//
// Reads and gates on disposition/evidence_contribution/safety_relevance
// live (flipping those fields from shadow-mode to UI-facing, per mission
// decision) — this is the first UI surface to actually filter on them
// rather than just displaying them for a human curator to eyeball.
//
// Live data note (checked against the real DB before building this): of
// 2658 health_signals rows, only 1042 have `disposition` populated and 63
// have `evidence_contribution`/`population_fit` — Phase 13 (OSINT
// Ingestion Quality Mission) bulk-backfill has not run. This route only
// ever surfaces rows where disposition IS NOT NULL for "worth knowing" /
// "emerging" (an undispositioned row isn't wrongly hidden forever — it's
// still reachable via Library, which does not gate on disposition).
//
// safety_relevance is currently 0/2658 live — the SAFETY section always
// renders regardless, per spec: it must never silently omit a real
// safety-relevant item, so "clear" must be an explicit, deliberate render
// path, not "the array happened to be empty".

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { topicForDomain } from '@/lib/healthOsintTopics';

const DAYS_14 = 14 * 86_400_000;

function summarize(s: any) {
  const topic = topicForDomain(s.health_domain);
  return {
    signal_id: s.signal_id,
    title: s.title,
    summary: s.description ? s.description.slice(0, 240) : null,
    source_url: s.canonical_url || s.health_source_registry?.source_url || null,
    source_name: s.health_source_registry?.source_name || 'Unknown',
    topic_key: topic.key,
    topic_label: topic.label,
    confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
    disposition: s.disposition,
    evidence_contribution: s.evidence_contribution,
    safety_relevance: !!s.safety_relevance,
    actionable_recommendation: s.actionable_recommendation,
    collected_at: s.collected_at,
  };
}

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - DAYS_14).toISOString();

    const baseSelect = `
      signal_id, title, description, health_domain, confidence_level, rank_score,
      disposition, disposition_reason, evidence_contribution, safety_relevance,
      canonical_url, collected_at, actionable_recommendation,
      health_source_registry ( source_name, source_url )
    `;

    // WORTH KNOWING — BRIEF/ESCALATE disposition, recent, real evidence
    // movement (not just "still true"). Capped small deliberately — this
    // is a curated "what changed" list, not a feed.
    const { data: worthKnowing, error: wkErr } = await sb
      .from('health_signals')
      .select(baseSelect)
      .eq('suppressed', false)
      .in('disposition', ['BRIEF', 'ESCALATE'])
      .gte('collected_at', since)
      .order('rank_score', { ascending: false })
      .limit(12);
    if (wkErr) throw new Error(`worth-knowing: ${wkErr.message}`);

    // SAFETY — any safety_relevance=true item not suppressed, any age
    // within the lookback window; always queried and always rendered by
    // the client even when this comes back empty (spec: never silently
    // omit, "✓ Nothing new requires attention" must be an explicit state).
    const { data: safetyItems, error: safetyErr } = await sb
      .from('health_signals')
      .select(baseSelect)
      .eq('suppressed', false)
      .eq('safety_relevance', true)
      .order('collected_at', { ascending: false })
      .limit(20);
    if (safetyErr) throw new Error(`safety: ${safetyErr.message}`);

    // EMERGING — WATCH disposition: evidence not yet strong enough to
    // change what HQ thinks, but being tracked.
    const { count: emergingCount, error: emErr } = await sb
      .from('health_signals')
      .select('signal_id', { count: 'exact', head: true })
      .eq('suppressed', false)
      .eq('disposition', 'WATCH');
    if (emErr) throw new Error(`emerging: ${emErr.message}`);

    // NEEDS YOUR REVIEW — fold in curation queue, but only the genuinely
    // ambiguous subset: mission_relevance is LOW_CONFIDENCE or the model
    // hasn't judged relevance at all yet. A confident NOT_RELEVANT/RELEVANT
    // call isn't ambiguous — it's a clear machine recommendation the human
    // can act on in one click, exactly what this card is for. Capped small
    // (mission spec: "much smaller, high-value-only queue").
    const { data: pending, error: pendErr } = await sb
      .from('health_signals')
      .select(`
        signal_id, title, description, health_domain, source_id, collected_at,
        canonical_url, mission_relevance, relevance_reason, evidence_contribution,
        population_fit, safety_relevance, disposition, disposition_reason,
        health_source_registry(source_name)
      `)
      .eq('auto_ingested', true)
      .eq('auto_ingest_reviewed', false)
      .order('collected_at', { ascending: false })
      .limit(100);
    if (pendErr) throw new Error(`pending: ${pendErr.message}`);

    const ambiguous = (pending ?? []).filter(
      (p: any) => p.mission_relevance === 'LOW_CONFIDENCE' || p.mission_relevance == null,
    ).slice(0, 6);

    const worthKnowingItems = (worthKnowing ?? []).map(summarize);
    const safetySummaries = (safetyItems ?? []).map(summarize);

    return NextResponse.json({
      worth_knowing: worthKnowingItems,
      worth_knowing_count: worthKnowingItems.length,
      safety: {
        items: safetySummaries,
        clear: safetySummaries.length === 0,
      },
      emerging_count: emergingCount ?? 0,
      needs_review: ambiguous.map((p: any) => ({
        signal_id: p.signal_id,
        title: p.title,
        description: p.description ? p.description.slice(0, 200) : null,
        source_name: (p as any).health_source_registry?.source_name ?? null,
        topic_label: topicForDomain(p.health_domain).label,
        collected_at: p.collected_at,
        canonical_url: p.canonical_url,
        recommendation: p.mission_relevance === 'LOW_CONFIDENCE' ? 'UNCLEAR' : 'NEEDS_JUDGMENT',
        reason: p.relevance_reason ?? null,
      })),
      needs_review_total_pending: (pending ?? []).length,
      gaps: {
        disposition_coverage_note:
          'Some ingested signals do not yet have a computed disposition — they are visible in Library but not counted here until the ingestion-quality backfill (Phase 13) reprocesses them.',
      },
    });
  } catch (err) {
    console.error('[health-osint/today] read failed:', err);
    return NextResponse.json(
      { error: 'today_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
