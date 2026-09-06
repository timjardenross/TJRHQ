// TODAY — the default Technical OSINT Workbench landing view (Three-Workbench
// Simplification, Phase 1). Reads and gates on the `disposition` column
// (intelligence/classification/disposition.py::technical_disposition(),
// migration 0186) LIVE rather than shadow-mode: ESCALATE -> "Needs you",
// BRIEF -> "Worth knowing". WATCH is summarised as a count only (never a raw
// dump — mission §18) with a link to the Watching tab. SUPPRESS is excluded
// entirely, per the mission's disposition-visibility mapping.
//
// Gap (see mission report): disposition is NULL on ~80% of historical rows
// — migration 0186 populates it going forward only, Phase 13 backfill has
// not run (OSINT Ingestion Quality mission, still blocked). Verified live:
// every row in the last 7 days already has it populated (backfill gap is
// confined to older history), so this route's 7-day window is unaffected —
// Library (which reaches further back) is where NULL disposition actually
// shows up, and is handled there as "Unclassified" rather than silently
// dropped.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchCorroborationCounts } from '../_lib/corroboration';

const EVENT_COLUMNS =
  'event_id, raw_title, raw_summary, canonical_url, sector, geography, risk_rating, ' +
  'operational_relevance, osint_confidence_level, disposition, disposition_reason, published_at';

function firstSentence(text: string | null | undefined, fallback: string): string {
  if (!text) return fallback;
  const trimmed = text.trim();
  const match = trimmed.match(/^[^.!?]+[.!?]/);
  return (match ? match[0] : trimmed).slice(0, 220).trim();
}

function whyYouCare(row: { sector: string | null; risk_rating: string | null; operational_relevance: number | null }): string {
  const sector = row.sector ? row.sector.replace(/_/g, ' ') : null;
  const parts: string[] = [];
  if (row.risk_rating === 'RED') parts.push('Assessed as elevated risk');
  else if (row.risk_rating === 'AMBER') parts.push('Assessed as moderate risk');
  if (sector) parts.push(`in ${sector}`);
  if ((row.operational_relevance ?? 0) >= 0.6) parts.push('with direct operational relevance');
  if (parts.length === 0) return 'Relevant to your monitored sectors.';
  return `${parts.join(' ')}.`;
}

function assessment(confidenceLevel: string, geography: string | null, corroboration: number): string {
  const confidenceText = confidenceLevel === 'high' ? 'High confidence'
    : confidenceLevel === 'medium' ? 'Medium confidence'
    : confidenceLevel === 'low' ? 'Low confidence'
    : 'Confidence not yet established';
  const geo = geography ? ` · ${geography}` : '';
  const sources = corroboration > 0 ? ` · ${corroboration} corroborating source${corroboration === 1 ? '' : 's'}` : '';
  return `${confidenceText}${geo}${sources}`;
}

async function getToday(sb: any) {
  const since = new Date(Date.now() - 7 * 86_400_000).toISOString();

  const { data: rows, error } = await sb
    .from('intelligence_events')
    .select(EVENT_COLUMNS)
    .in('disposition', ['ESCALATE', 'BRIEF'])
    .eq('suppressed', false)
    .gte('collected_at', since)
    .order('rank_score', { ascending: false })
    .limit(30);
  if (error) throw new Error(`Failed to fetch today's developments: ${error.message}`);

  const eventIds = (rows ?? []).map((r: any) => r.event_id);
  const corroboration = await fetchCorroborationCounts(sb, eventIds);

  function toDevelopment(r: any) {
    const confidenceLevel = (r.osint_confidence_level || 'unknown').toLowerCase();
    const corr = corroboration.get(r.event_id) || 0;
    return {
      event_id: r.event_id,
      title: r.raw_title,
      canonical_url: r.canonical_url,
      what_happened: firstSentence(r.raw_summary, r.raw_title),
      why_you_care: whyYouCare(r),
      assessment: assessment(confidenceLevel, r.geography, corr),
      you_need_to: r.disposition === 'ESCALATE'
        ? 'Review and decide — this crossed the threshold for needing your input.'
        : 'Nothing. HQ is watching this.',
      confidence_level: confidenceLevel,
      corroboration: corr,
      published_at: r.published_at,
    };
  }

  const needsYou = (rows ?? []).filter((r: any) => r.disposition === 'ESCALATE').map(toDevelopment).slice(0, 10);
  const worthKnowing = (rows ?? []).filter((r: any) => r.disposition === 'BRIEF').map(toDevelopment).slice(0, 15);

  // Watching: a count only (mission §18 — never a raw item dump on Today).
  const { count: watchingCount, error: watchErr } = await sb
    .from('intelligence_events')
    .select('event_id', { count: 'exact', head: true })
    .eq('disposition', 'WATCH')
    .eq('suppressed', false)
    .gte('collected_at', since);
  if (watchErr) throw new Error(`Failed to count watched developments: ${watchErr.message}`);

  return {
    needs_you: needsYou,
    worth_knowing: worthKnowing,
    watching_count: watchingCount ?? 0,
    unknowns: [
      { title: 'Internal network security', impact: 'Blind to internal compromise', need: 'SIEM integration' },
      { title: 'Supply chain threats', impact: 'Third-party compromise', need: 'Vendor monitoring' },
      { title: 'Zero-day activity', impact: 'Unpatched vulnerabilities in use', need: 'EDR, threat hunting' },
    ],
  };
}

export async function GET(_req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getToday(sb));
  } catch (err) {
    console.error('[intelligence-workbench/today] read failed:', err);
    return NextResponse.json(
      { error: 'today_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
