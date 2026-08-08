// Health Threat Assessment API — probability × impact × confidence safety escalation matrix

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS_365 = 365 * 86_400_000;

const SEVERITY_IMPACT: Record<string, string> = {
  critical: 'critical',
  severe: 'high',
  moderate: 'medium',
  mild: 'low',
};

const EVIDENCE_GAPS = [
  { area: 'Long-term cardiovascular safety', risk: 'high', evidence_gap: 'Limited follow-up beyond 2 years' },
  { area: 'Pediatric population testing', risk: 'medium', evidence_gap: 'No RCTs in children for most signals' },
  { area: 'Drug-drug / drug-supplement interactions', risk: 'high', evidence_gap: 'Polypharmacy effects underexplored' },
];

function probabilityFromFrequency(freq: number | null): string {
  if (freq === null) return 'unknown';
  if (freq >= 100) return 'high';
  if (freq >= 10) return 'medium';
  return 'low';
}

async function getThreatAssessment(sb: any) {
  const since = new Date(Date.now() - DAYS_365).toISOString();

  const { data: signals, error: signalsErr } = await sb
    .from('health_signals')
    .select(`
      signal_id, title, signal_type, severity, fda_flagged, frequency_reported, confidence_level, rank_score,
      health_source_registry ( reliability_tier )
    `)
    .eq('suppressed', false)
    .gte('collected_at', since)
    .in('signal_type', ['adverse_event', 'safety_alert'])
    .order('rank_score', { ascending: false })
    .limit(20);

  if (signalsErr) throw new Error(`Failed to fetch signals: ${signalsErr.message}`);

  const threats = (signals ?? []).map((s: any) => {
    const impact = SEVERITY_IMPACT[s.severity as string] || 'medium';
    const probability = probabilityFromFrequency(s.frequency_reported);
    const confidence = (s.confidence_level || 'UNKNOWN').toLowerCase();

    let escalation = 'monitor';
    if (confidence === 'high' && (impact === 'critical' || impact === 'high')) escalation = 'escalate';
    else if (confidence === 'high' || impact === 'critical') escalation = 'watch';

    const recommendation =
      escalation === 'escalate' ? 'Issue safety alert immediately'
      : escalation === 'watch' ? 'Increase surveillance, prepare alert draft'
      : 'Continue routine monitoring';

    return {
      threat: s.title,
      probability,
      impact,
      confidence,
      escalation,
      fda_flagged: s.fda_flagged,
      frequency_reported: s.frequency_reported,
      recommendation,
    };
  });

  return {
    domain: 'threat-assessment',
    threats,
    gaps: EVIDENCE_GAPS,
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    return NextResponse.json(await getThreatAssessment(sb));
  } catch (err) {
    console.error('[health-osint/threat-assessment] read failed:', err);
    return NextResponse.json(
      { error: 'assessment_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
