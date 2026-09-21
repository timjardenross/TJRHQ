export type ConfidenceFreshness = 'fresh' | 'stale' | 'unknown' | 'unavailable';
export type OperationalConfidenceBand = 'high' | 'moderate' | 'low' | 'unknown';

export interface ConfidenceSource {
  id: string;
  label: string;
  completeness: number | null;
  freshness: ConfidenceFreshness;
  required?: boolean;
}

export interface OperationalConfidence {
  score: number | null;
  band: OperationalConfidenceBand;
  completenessPct: number | null;
  freshSourcePct: number | null;
  assessedSources: number;
  totalSources: number;
  reasons: string[];
}

const clamp = (value: number) => Math.max(0, Math.min(1, value));

/**
 * Explainable cross-portal posture signal. Completeness carries 60% of the
 * score and freshness 40%; unknown/unavailable evidence is never promoted to
 * healthy. The function is deliberately pure so every portal can share the
 * same contract without duplicating scoring rules.
 */
export function calculateOperationalConfidence(sources: ConfidenceSource[]): OperationalConfidence {
  if (sources.length === 0) {
    return { score: null, band: 'unknown', completenessPct: null, freshSourcePct: null, assessedSources: 0, totalSources: 0, reasons: ['No operational sources are available to assess.'] };
  }

  const completenessValues = sources.map((source) => source.completeness).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  const assessedSources = sources.filter((source) => source.completeness !== null || source.freshness !== 'unknown').length;
  const completeness = completenessValues.length > 0 ? completenessValues.reduce((sum, value) => sum + clamp(value), 0) / completenessValues.length : null;
  const freshCount = sources.filter((source) => source.freshness === 'fresh').length;
  const freshness = freshCount / sources.length;
  const score = completeness === null ? null : Math.round((completeness * 0.6 + freshness * 0.4) * 100);
  const band: OperationalConfidenceBand = score === null ? 'unknown' : score >= 85 ? 'high' : score >= 65 ? 'moderate' : 'low';
  const reasons: string[] = [];
  if (completeness !== null) reasons.push(`Source coverage is ${Math.round(completeness * 100)}% complete.`);
  else reasons.push('Source completeness is not reported yet.');
  reasons.push(`${freshCount} of ${sources.length} sources are fresh.`);
  const incomplete = sources.filter((source) => source.completeness !== null && source.completeness < 1).length;
  const uncertain = sources.filter((source) => source.freshness === 'unknown' || source.freshness === 'unavailable').length;
  if (incomplete > 0) reasons.push(`${incomplete} source${incomplete === 1 ? '' : 's'} have incomplete coverage.`);
  if (uncertain > 0) reasons.push(`${uncertain} source${uncertain === 1 ? '' : 's'} have unknown or unavailable freshness.`);
  return { score, band, completenessPct: completeness === null ? null : Math.round(completeness * 100), freshSourcePct: Math.round(freshness * 100), assessedSources, totalSources: sources.length, reasons };
}
