// Threat Assessment API — probability × impact × confidence escalation matrix

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

// Two classes of coverage gap:
//  - STRUCTURAL: definitionally always true regardless of data volume (a
//    zero-day is invisible until it's disclosed, by definition; TLS
//    payloads can't be inspected without the keys). Always listed.
//  - DATA-DRIVEN: candidates checked against real event_type volume in the
//    window. 'Supply chain' used to be hardcoded here as a permanent gap —
//    verified against real data (2026-08-08) it had 148 events/30d, so
//    it's excluded below unless volume genuinely drops low again.
const STRUCTURAL_GAPS = [
  { area: 'Zero-day activity', risk: 'high', blind_spot: 'Invisible before public disclosure by definition — this feed only sees published CVEs/advisories.' },
  { area: 'Encrypted traffic', risk: 'medium', blind_spot: "Can't inspect TLS/HTTPS payload content without decryption keys — structural, not a coverage gap." },
];

const DATA_DRIVEN_CANDIDATES: { area: string; risk: string; event_types: string[]; blind_spot: string; lowVolumeThreshold: number }[] = [
  { area: 'Internal network security', risk: 'high', event_types: [], blind_spot: 'No internal-monitoring source registered — only external/public signals.', lowVolumeThreshold: 1 },
  { area: 'Social engineering / phishing', risk: 'medium', event_types: [], blind_spot: 'No source tracks phishing/pretexting campaigns directly.', lowVolumeThreshold: 1 },
  { area: 'Policy violations / misconfiguration', risk: 'medium', event_types: [], blind_spot: 'No source tracks internal config/policy compliance.', lowVolumeThreshold: 1 },
  { area: 'Supply chain', risk: 'medium', event_types: ['supply_chain', 'third_party_disruption'], blind_spot: 'Third-party/vendor compromise detection.', lowVolumeThreshold: 10 },
];

async function computeDataDrivenGaps(sb: any, since: string, days: number) {
  const gaps: { area: string; risk: string; blind_spot: string }[] = [];
  for (const c of DATA_DRIVEN_CANDIDATES) {
    if (c.event_types.length === 0) {
      // No event_type in the schema can possibly cover this — always a gap
      // given current sources, no query needed.
      gaps.push({ area: c.area, risk: c.risk, blind_spot: c.blind_spot });
      continue;
    }
    const { count, error } = await sb
      .from('intelligence_events')
      .select('event_id', { count: 'exact', head: true })
      .in('event_type', c.event_types)
      .gte('collected_at', since);
    if (error) throw new Error(`Failed to check coverage for ${c.area}: ${error.message}`);
    // lowVolumeThreshold is calibrated against a 30-day baseline — this
    // route's window is a caller-controlled `days` param (default 7), so
    // scale proportionally. Caught in testing: the unscaled fixed
    // threshold (10) against the real 7-day count (6, vs. ~148/30d) would
    // have flagged supply_chain as a gap under the route's own default
    // window despite genuinely healthy 30-day coverage.
    const scaledThreshold = Math.max(1, Math.round(c.lowVolumeThreshold * (days / 30)));
    if ((count ?? 0) < scaledThreshold) {
      gaps.push({ area: c.area, risk: c.risk, blind_spot: `${c.blind_spot} (only ${count ?? 0} signals in this window)` });
    }
  }
  return gaps;
}

function impactFromCriticality(score: number | null): string {
  if (score === null || score === undefined) return 'medium';
  if (score >= 0.85) return 'critical';
  if (score >= 0.60) return 'high';
  if (score >= 0.35) return 'medium';
  return 'low';
}

async function getThreatAssessment(sb: any, days: number, includeSuppressed: boolean) {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();

  let query = sb
    .from('intelligence_events')
    .select(`
      event_id,
      raw_title,
      risk_rating,
      rank_score,
      criticality_score,
      osint_confidence_level,
      intelligence_source_registry (
        reliability_tier,
        reliability_score
      )
    `)
    .gte('collected_at', since)
    // Top-N rather than an absolute rank_score cutoff: the fixed SRS
    // validation loop (previously dead — see recompute_signal_scores.py)
    // means most sources are still TIER_4 while real accuracy samples
    // accumulate, so today's realistic rank_score ceiling is well under
    // the ~90s the spec's own examples assumed. An absolute >=70 gate
    // would return zero rows right now and recreate the "empty workbench"
    // symptom this whole gap-closure effort was chasing.
    .order('rank_score', { ascending: false })
    .limit(20);

  if (!includeSuppressed) query = query.eq('suppressed', false);
  query = query.neq('signal_status', 'DUPLICATE');

  const { data: signals, error: signalsErr } = await query;
  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const threats = (signals ?? []).map((s: any) => {
    const probMap: Record<string, string> = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
    const probability = probMap[s.risk_rating as keyof typeof probMap] || 'medium';
    // criticality_score, not banking_relevance — per TECHNICAL_OSINT_WORKBENCH.md
    // section 6 ("Assign impact from criticality_score + domain relevance").
    const impact = impactFromCriticality(s.criticality_score);
    const confidence = (s.osint_confidence_level || 'UNKNOWN').toLowerCase();

    let escalation = 'monitor';
    if (confidence === 'high' && impact === 'critical') escalation = 'escalate';
    else if (confidence === 'high' || impact === 'critical') escalation = 'watch';
    else if (confidence === 'medium' && impact === 'high') escalation = 'watch';

    const recommendation =
      escalation === 'escalate' ? 'Immediate action required'
      : escalation === 'watch' ? 'Monitor for spread, coordinate response'
      : 'Research and await confirmation';

    return {
      threat: s.raw_title,
      probability,
      impact,
      confidence,
      escalation,
      recommendation,
    };
  });

  const dataDrivenGaps = await computeDataDrivenGaps(sb, since, days);

  return {
    domain: 'threat-assessment',
    threats,
    gaps: [...STRUCTURAL_GAPS, ...dataDrivenGaps],
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
    return NextResponse.json(await getThreatAssessment(sb, days, includeSuppressed));
  } catch (err) {
    console.error('[threat-assessment] read failed:', err);
    return NextResponse.json(
      { error: 'assessment_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
