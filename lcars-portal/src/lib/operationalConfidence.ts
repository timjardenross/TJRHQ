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
 * Policy: unknown-freshness cap on the "high" band.
 *
 * `freshSourcePct` (and therefore the numeric score) treats a source with
 * freshness 'unknown' or 'unavailable' as simply "not fresh" — the same as
 * 'stale'. That is enough to depress the score, but it is a *binary* penalty:
 * once a source is counted as not-fresh it does not matter whether we could
 * not verify it at all (unknown/unavailable) or actively know it is old
 * (stale). A dashboard reading "high confidence" is read by a human as "you
 * can trust this without digging further" — that claim is not defensible
 * when a large share of the source set was never actually checked for
 * freshness, even if the numeric 60/40 completeness/freshness blend still
 * clears the 85 threshold (e.g. 100% completeness + 75% freshness = 90,
 * "high", with a quarter of sources unverified).
 *
 * So: regardless of the numeric score, the band cannot read 'high' if more
 * than UNKNOWN_FRESHNESS_HIGH_BAND_CAP of sources have unknown/unavailable
 * freshness. 20% was chosen as the line because it is stricter than the
 * ~15% of "impurity" the 85-score high-band threshold itself already
 * tolerates (100 - 85 = 15 points of slack) — so an unknown-freshness share
 * bigger than that slack should not be able to hide behind an otherwise
 * strong completeness number. Below the cap, unknown/unavailable sources
 * still cost score the normal way; above it, "high" is downgraded to
 * 'moderate' and a reason is surfaced explaining why.
 */
const UNKNOWN_FRESHNESS_HIGH_BAND_CAP = 0.2;

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
  let band: OperationalConfidenceBand = score === null ? 'unknown' : score >= 85 ? 'high' : score >= 65 ? 'moderate' : 'low';
  const reasons: string[] = [];
  if (completeness !== null) reasons.push(`Source coverage is ${Math.round(completeness * 100)}% complete.`);
  else reasons.push('Source completeness is not reported yet.');
  reasons.push(`${freshCount} of ${sources.length} sources are fresh.`);
  const incomplete = sources.filter((source) => source.completeness !== null && source.completeness < 1).length;
  const uncertain = sources.filter((source) => source.freshness === 'unknown' || source.freshness === 'unavailable').length;
  const uncertainPct = uncertain / sources.length;
  if (incomplete > 0) reasons.push(`${incomplete} source${incomplete === 1 ? '' : 's'} have incomplete coverage.`);
  if (uncertain > 0) reasons.push(`${uncertain} source${uncertain === 1 ? '' : 's'} have unknown or unavailable freshness.`);
  if (band === 'high' && uncertainPct > UNKNOWN_FRESHNESS_HIGH_BAND_CAP) {
    band = 'moderate';
    reasons.push(`Confidence capped at moderate: ${Math.round(uncertainPct * 100)}% of sources have unknown or unavailable freshness, above the ${Math.round(UNKNOWN_FRESHNESS_HIGH_BAND_CAP * 100)}% limit for a "high" rating.`);
  }
  return { score, band, completenessPct: completeness === null ? null : Math.round(completeness * 100), freshSourcePct: Math.round(freshness * 100), assessedSources, totalSources: sources.length, reasons };
}
