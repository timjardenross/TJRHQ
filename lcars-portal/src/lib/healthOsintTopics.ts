// Health OSINT topic grouping — shared between /api/health-osint/{today,
// topics,library} routes and the health-osint client views.
//
// Gap this works around (Phase 2 "Three-Workbench Simplification" mission,
// My Evidence spec): there is no dedicated topic-taxonomy table. health_domain
// is a flat/granular free-text column with three live vocabularies layered
// on top of each other over time (see health-osint/page.tsx's original
// domainLabel() comment, migration 0093 + migration 0160 + the 6
// automated-fetch parsers' epi_*/safety_*/evidence_*/performance_*/factor_*/
// mental_health_* tags). Rather than inventing a new taxonomy table, this
// groups health_domain values into the same coarse "topic" buckets a person
// would recognise, reusing the exact prefix rules already established in
// page.tsx/confidence-matrix/route.ts. This IS a lightweight grouping view,
// not a new source of truth — health_domain stays the column of record.

export interface TopicDef {
  key: string;
  label: string;
}

const DOMAIN_LABEL: Record<string, string> = {
  epidemiology: 'Epidemiology',
  treatment: 'Treatment',
  supplement: 'Supplements',
  performance: 'Performance',
  mental_health: 'Mental Health',
  vaccine: 'Vaccines',
  general_biomedical: 'General Biomedical',
  chronic_pain: 'Chronic Pain',
};

const ACRONYMS: Record<string, string> = { adhd: 'ADHD', audhd: 'AuDHD', ndis: 'NDIS' };

function titleCase(seg: string): string {
  return ACRONYMS[seg] || seg.charAt(0).toUpperCase() + seg.slice(1);
}

/** Maps a raw health_domain value onto a coarse topic key + human label.
 *  Same prefix families as confidence-matrix/route.ts's categorize() and
 *  page.tsx's domainLabel(), just returning a stable grouping key alongside
 *  the label so multiple raw domain values (e.g. epi_outbreak, epidemiology)
 *  can be counted as the same topic. */
export function topicForDomain(healthDomain: string | null | undefined): TopicDef {
  const d = (healthDomain || '').trim();
  if (!d) return { key: 'unclassified', label: 'Unclassified' };

  if (d.startsWith('neuro_')) {
    const rest = d.slice('neuro_'.length);
    return { key: `neuro_${rest}`, label: rest.split('_').map(titleCase).join(' ') };
  }
  if (d.startsWith('chronic_pain')) return { key: 'chronic_pain', label: 'Chronic Pain' };
  if (d === 'epidemiology' || d.startsWith('epi_')) return { key: 'epidemiology', label: 'Epidemiology' };
  if (d.startsWith('safety_')) return { key: 'safety', label: 'Safety & Adverse Events' };
  if (d === 'performance' || d.startsWith('performance_')) return { key: 'performance', label: 'Performance' };
  if (d.startsWith('factor_')) return { key: 'factor', label: 'Lifestyle Factors' };
  if (d === 'mental_health' || d.startsWith('mental_health_')) return { key: 'mental_health', label: 'Mental Health' };
  if (d.startsWith('evidence_')) return { key: 'evidence_quality', label: 'Research Quality' };
  if (DOMAIN_LABEL[d]) return { key: d, label: DOMAIN_LABEL[d] };
  return { key: d, label: titleCase(d) };
}

export type Strength = 'STRONG' | 'MODERATE' | 'LIMITED';
export type Trend = 'up' | 'down' | 'stable' | 'mixed' | 'unknown';

const CONF_WEIGHT: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 };

/** Strength from a topic's confidence_level composition — majority-weighted,
 *  not a raw count (counts rule §18 applies to Today/My Evidence; this is a
 *  derived qualitative label, not a shown count). */
export function strengthFromComposition(counts: { high: number; medium: number; low: number; unknown: number }): Strength {
  const weighted = counts.high * CONF_WEIGHT.HIGH + counts.medium * CONF_WEIGHT.MEDIUM + counts.low * CONF_WEIGHT.LOW;
  const n = counts.high + counts.medium + counts.low + counts.unknown;
  if (n === 0) return 'LIMITED';
  const avg = weighted / Math.max(1, counts.high + counts.medium + counts.low);
  if (counts.high >= 2 && avg >= 2.3) return 'STRONG';
  if (avg >= 1.6) return 'MODERATE';
  return 'LIMITED';
}

/** Trend by comparing confidence-weighted averages between a recent window
 *  and the prior window of equal length. Returns 'unknown' rather than
 *  fabricating a direction when either window lacks enough signals
 *  (mission instruction: note the gap, don't invent a trend) — no
 *  evidence-strength-trend field or historical snapshot exists in the
 *  schema, so this is a same-shape proxy computed from collected_at +
 *  confidence_level, not a stored ground truth. */
export function computeTrend(
  recent: { confidence_level: string | null }[],
  prior: { confidence_level: string | null }[],
): Trend {
  const MIN_N = 3;
  if (recent.length < MIN_N || prior.length < MIN_N) return 'unknown';
  const avg = (rows: { confidence_level: string | null }[]) =>
    rows.reduce((sum, r) => sum + (CONF_WEIGHT[(r.confidence_level || '').toUpperCase()] ?? 0), 0) / rows.length;
  const recentAvg = avg(recent);
  const priorAvg = avg(prior);
  const delta = recentAvg - priorAvg;
  if (Math.abs(delta) < 0.15) return 'stable';
  return delta > 0 ? 'up' : 'down';
}
