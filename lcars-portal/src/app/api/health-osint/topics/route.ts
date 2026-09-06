// GET /api/health-osint/topics — My Evidence: persistent per-topic evidence
// position (Phase 2 Three-Workbench Simplification mission, "My Evidence"
// section). No dedicated topic-taxonomy table exists in the schema — this
// groups the existing health_domain column via lib/healthOsintTopics.ts's
// topicForDomain() (a lightweight grouping view over the real column, not a
// new source of truth) rather than inventing one.
//
// Strength/trend are derived, not stored: there is no evidence-strength
// snapshot table (source-network/route.ts hit the same absence for source
// reliability trending). Trend compares two 90-day windows of
// confidence_level composition and reports 'unknown' rather than a
// fabricated direction when either window is thin — see computeTrend()'s
// own comment for the exact rule.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { topicForDomain, strengthFromComposition, computeTrend } from '@/lib/healthOsintTopics';

const DAYS_365 = 365 * 86_400_000;
const DAYS_90 = 90 * 86_400_000;

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - DAYS_365).toISOString();

    const { data: signals, error } = await sb
      .from('health_signals')
      .select('signal_id, health_domain, confidence_level, collected_at, disposition, safety_relevance')
      .eq('suppressed', false)
      .gte('collected_at', since);
    if (error) throw new Error(error.message);

    const now = Date.now();
    const recentSince = now - DAYS_90;
    const priorSince = now - 2 * DAYS_90;

    type Row = { confidence_level: string | null; collected_at: string; disposition: string | null; safety_relevance: boolean };
    const byTopic = new Map<string, { label: string; rows: Row[] }>();

    for (const s of signals ?? []) {
      const topic = topicForDomain(s.health_domain);
      if (!byTopic.has(topic.key)) byTopic.set(topic.key, { label: topic.label, rows: [] });
      byTopic.get(topic.key)!.rows.push({
        confidence_level: s.confidence_level,
        collected_at: s.collected_at,
        disposition: s.disposition,
        safety_relevance: !!s.safety_relevance,
      });
    }

    const topics = Array.from(byTopic.entries()).map(([key, { label, rows }]) => {
      const counts = { high: 0, medium: 0, low: 0, unknown: 0 };
      let lastChanged = rows[0]?.collected_at ?? null;
      for (const r of rows) {
        const c = (r.confidence_level || 'UNKNOWN').toUpperCase();
        if (c === 'HIGH') counts.high++;
        else if (c === 'MEDIUM') counts.medium++;
        else if (c === 'LOW') counts.low++;
        else counts.unknown++;
        if (!lastChanged || new Date(r.collected_at) > new Date(lastChanged)) lastChanged = r.collected_at;
      }
      const recent = rows.filter((r) => new Date(r.collected_at).getTime() >= recentSince);
      const prior = rows.filter((r) => {
        const t = new Date(r.collected_at).getTime();
        return t >= priorSince && t < recentSince;
      });
      const hasSafety = rows.some((r) => r.safety_relevance);
      return {
        topic_key: key,
        topic_label: label,
        strength: strengthFromComposition(counts),
        trend: computeTrend(recent, prior),
        last_changed: lastChanged,
        safety_relevant: hasSafety,
        composition: counts, // evidence-quality composition — allowed per counts rule §18
      };
    });

    // Order: safety-relevant topics first, then by most-recently-changed —
    // "what needs your attention/is fresh" beats alphabetical.
    topics.sort((a, b) => {
      if (a.safety_relevant !== b.safety_relevant) return a.safety_relevant ? -1 : 1;
      return new Date(b.last_changed ?? 0).getTime() - new Date(a.last_changed ?? 0).getTime();
    });

    return NextResponse.json({
      topics,
      gap_note:
        'No stored evidence-strength-trend field or historical snapshot table exists — trend is derived by comparing two 90-day windows of confidence-level composition, and reads "unknown" rather than a guess when a window has fewer than 3 signals.',
    });
  } catch (err) {
    console.error('[health-osint/topics] read failed:', err);
    return NextResponse.json(
      { error: 'topics_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
