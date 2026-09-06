// GET /api/health-osint/topics/[domain] — topic drill-down (My Evidence ->
// Topic Detail, Phase 2 mission spec). [domain] is the topic_key produced
// by lib/healthOsintTopics.ts's topicForDomain() (e.g. "epidemiology",
// "neuro_adhd", "chronic_pain") — this route re-derives the same grouping
// server-side rather than trusting a client-supplied domain list, so it
// always matches whatever /api/health-osint/topics just returned.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { topicForDomain, strengthFromComposition, computeTrend } from '@/lib/healthOsintTopics';

const DAYS_365 = 365 * 86_400_000;
const DAYS_90 = 90 * 86_400_000;

export async function GET(_req: NextRequest, { params }: { params: { domain: string } }) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const topicKey = params.domain;

  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - DAYS_365).toISOString();

    const { data: signals, error } = await sb
      .from('health_signals')
      .select(`
        signal_id, title, description, health_domain, confidence_level, rank_score,
        study_design, sample_size, published_at, collected_at, canonical_url,
        disposition, evidence_contribution, safety_relevance, population_fit,
        actionable_recommendation,
        health_source_registry ( source_name, source_url )
      `)
      .eq('suppressed', false)
      .gte('collected_at', since)
      .order('collected_at', { ascending: false });
    if (error) throw new Error(error.message);

    const matching = (signals ?? []).filter((s: any) => topicForDomain(s.health_domain).key === topicKey);
    if (matching.length === 0) {
      return NextResponse.json({ error: 'not_found', detail: 'No signals in this topic (or topic key unknown).' }, { status: 404 });
    }

    const label = topicForDomain(matching[0].health_domain).label;
    const counts = { high: 0, medium: 0, low: 0, unknown: 0 };
    for (const s of matching) {
      const c = (s.confidence_level || 'UNKNOWN').toUpperCase();
      if (c === 'HIGH') counts.high++;
      else if (c === 'MEDIUM') counts.medium++;
      else if (c === 'LOW') counts.low++;
      else counts.unknown++;
    }

    const now = Date.now();
    const recent = matching.filter((s: any) => now - new Date(s.collected_at).getTime() <= DAYS_90);
    const prior = matching.filter((s: any) => {
      const age = now - new Date(s.collected_at).getTime();
      return age > DAYS_90 && age <= 2 * DAYS_90;
    });
    const trend = computeTrend(recent, prior);
    const strength = strengthFromComposition(counts);
    const lastChanged = matching[0]?.collected_at ?? null; // already ordered desc

    const summarize = (s: any) => ({
      signal_id: s.signal_id,
      title: s.title,
      summary: s.description ? s.description.slice(0, 240) : null,
      source_url: s.canonical_url || s.health_source_registry?.source_url || null,
      source_name: s.health_source_registry?.source_name || 'Unknown',
      confidence_level: (s.confidence_level || 'UNKNOWN').toLowerCase(),
      study_design: s.study_design,
      sample_size: s.sample_size,
      published_at: s.published_at,
      collected_at: s.collected_at,
      evidence_contribution: s.evidence_contribution,
      disposition: s.disposition,
      safety_relevance: !!s.safety_relevance,
      actionable_recommendation: s.actionable_recommendation,
    });

    // "What changed recently" — contributing items tagged with a real
    // evidence_contribution value, most recent first. Sparse today (only 63
    // of 2658 live rows carry evidence_contribution at all — Phase 13
    // backfill hasn't run) so this can legitimately be empty; that's
    // reported via evidence_contribution_coverage, not papered over.
    const recentChanges = matching
      .filter((s: any) => ['CONFIRMS', 'CHALLENGES', 'EXTENDS', 'REPLICATION'].includes(s.evidence_contribution))
      .slice(0, 10)
      .map(summarize);

    const supports = matching.filter((s: any) => s.evidence_contribution === 'CONFIRMS').slice(0, 10).map(summarize);
    const challenges = matching.filter((s: any) => s.evidence_contribution === 'CHALLENGES').slice(0, 10).map(summarize);
    const safetyItems = matching.filter((s: any) => s.safety_relevance).slice(0, 10).map(summarize);
    const withContribution = matching.filter((s: any) => s.evidence_contribution != null).length;

    return NextResponse.json({
      topic_key: topicKey,
      topic_label: label,
      strength,
      trend,
      last_changed: lastChanged,
      composition: counts, // evidence-base breakdown — an appropriate count per §18
      recent_changes: recentChanges,
      supports,
      challenges,
      safety: { items: safetyItems, clear: safetyItems.length === 0 },
      what_we_dont_know_yet:
        counts.high === 0
          ? ['No high-confidence evidence yet in this topic — treat any single study here as preliminary.']
          : [],
      recent_items: matching.slice(0, 20).map(summarize),
      gaps: {
        evidence_contribution_coverage: `${withContribution} of ${matching.length} signals in this topic have a classified evidence contribution (CONFIRMS/CHALLENGES/EXTENDS/REPLICATION/etc). The rest predate the classifier and show under "Recent items" only, not "What changed recently".`,
        history_over_time: 'No historical evidence-strength snapshot is stored, so a strength-over-time chart is not shown here — only the current position and a two-window trend comparison.',
      },
    });
  } catch (err) {
    console.error('[health-osint/topics/[domain]] read failed:', err);
    return NextResponse.json(
      { error: 'topic_detail_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
