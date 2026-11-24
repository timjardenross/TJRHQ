// Source effectiveness classification: TypeScript port of
// intelligence/source_effectiveness.py (classify_source / classify_all /
// summarise). Keep the two in lockstep: tests/fixtures/source_effectiveness_parity.json
// is classified by both languages and must give identical output.
// Evidence (quiet verifications, declared coverage gaps) comes from
// src/config/source_effectiveness.json, an identical copy of
// config/source_effectiveness.json (tests in both languages assert the copies match).

import evidenceJson from '@/config/source_effectiveness.json';

export type SourceState = 'HEALTHY' | 'QUIET' | 'UNVERIFIED' | 'DEGRADED' | 'BROKEN' | 'UNCOVERED';
export const SOURCE_STATES: SourceState[] = ['HEALTHY', 'QUIET', 'UNVERIFIED', 'DEGRADED', 'BROKEN', 'UNCOVERED'];

export interface SourceRow {
  source_name: string;
  source_type?: string | null;
  active: boolean;
  n7?: number | null;
  n30?: number | null;
  last_event?: string | null;
  checks7?: number | null;
  bad7?: number | null;
  last_check?: string | null;
  last_ok?: string | null;
}

export interface Evidence {
  priority_sources?: string[];
  quiet_verifications: { source_name: string; verified_on: string; newest_item_on_source: string }[];
  coverage_gaps: { sector: string; provider: string; reason: string; observed_on?: string }[];
}

export interface ClassifiedSource {
  source_name: string;
  state: SourceState;
  reason: string;
}

export const DEFAULT_EVIDENCE = evidenceJson as unknown as Evidence;

const DAY_MS = 86_400_000;

export function classifySource(row: SourceRow, evidence: Evidence = DEFAULT_EVIDENCE, now: Date = new Date()): [SourceState, string] {
  if (!row.active) return ['UNCOVERED', 'inactive: not collecting'];
  const checks = Number(row.checks7 || 0);
  const bad = Number(row.bad7 || 0);
  const lastCheck = row.last_check ? new Date(row.last_check) : null;
  if (checks === 0 || lastCheck === null) return ['BROKEN', 'active but not checked in the last 7 days'];
  if (bad / checks >= 0.8) return ['BROKEN', `${bad} of ${checks} checks failed in 7 days`];
  if (bad / checks >= 0.2) return ['DEGRADED', `${bad} of ${checks} checks failed in 7 days`];
  if (now.getTime() - lastCheck.getTime() > 2 * DAY_MS) {
    return ['DEGRADED', `last check ${lastCheck.toISOString().slice(0, 10)}, older than two days`];
  }
  if (Number(row.n30 || 0) > 0) {
    return ['HEALTHY', `${row.n30} items in 30 days, ${row.n7 || 0} in 7`];
  }
  const v = evidence.quiet_verifications.find((q) => q.source_name === row.source_name);
  if (v) return ['QUIET', `live feed probe on ${v.verified_on}: newest item on source ${v.newest_item_on_source}`];
  return ['UNVERIFIED', 'checks succeed but no items in 30 days and no live-feed probe on record'];
}

export function classifyAll(rows: SourceRow[], evidence: Evidence = DEFAULT_EVIDENCE, now: Date = new Date()): ClassifiedSource[] {
  const out: ClassifiedSource[] = rows.map((r) => {
    const [state, reason] = classifySource(r, evidence, now);
    return { source_name: r.source_name, state, reason };
  });
  for (const g of evidence.coverage_gaps) {
    out.push({ source_name: `${g.provider} (${g.sector})`, state: 'UNCOVERED', reason: g.reason });
  }
  return out;
}

export function summarise(classified: ClassifiedSource[]): Record<SourceState, number> {
  const counts = Object.fromEntries(SOURCE_STATES.map((s) => [s, 0])) as Record<SourceState, number>;
  for (const c of classified) counts[c.state] += 1;
  return counts;
}

export const SOURCE_COVERAGE_HREF = '/intelligence-workbench?tab=sources';
export const MATERIAL_BROKEN_DAYS = 3;

export function isPriority(sourceName: string, evidence: Evidence = DEFAULT_EVIDENCE): boolean {
  return (evidence.priority_sources ?? []).some((p) => new RegExp(`\\b${p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(sourceName));
}

function brokenPriority(rows: SourceRow[], evidence: Evidence, now: Date): SourceRow[] {
  return rows.filter((r) => isPriority(r.source_name, evidence) && classifySource(r, evidence, now)[0] === 'BROKEN');
}

export interface MaterialException {
  /** Stable dedupe key: one broken priority source = one entry. */
  key: string;
  source_name: string;
  reason: string;
  href: string;
}

/**
 * The only source-health matter raised on Home: a BROKEN priority source with
 * no successful check for 3+ days. Never QUIET/UNVERIFIED/DEGRADED/UNCOVERED.
 */
export function materialExceptions(rows: SourceRow[], evidence: Evidence = DEFAULT_EVIDENCE, now: Date = new Date()): MaterialException[] {
  const out = new Map<string, MaterialException>();
  for (const r of brokenPriority(rows, evidence, now)) {
    const lastOk = r.last_ok ? new Date(r.last_ok) : null;
    if (lastOk !== null && now.getTime() - lastOk.getTime() < MATERIAL_BROKEN_DAYS * DAY_MS) continue;
    const key = `source-coverage:broken:${r.source_name}`;
    if (!out.has(key)) out.set(key, { key, source_name: r.source_name, reason: classifySource(r, evidence, now)[1], href: SOURCE_COVERAGE_HREF });
  }
  return Array.from(out.values());
}

export interface CoverageLimitation {
  name: string;
  kind: 'uncovered' | 'broken_priority';
  reason: string;
}

/** Short list for intelligence products: declared uncovered providers plus any BROKEN priority source. */
export function coverageLimitations(rows: SourceRow[], evidence: Evidence = DEFAULT_EVIDENCE, now: Date = new Date()): CoverageLimitation[] {
  return [
    ...evidence.coverage_gaps.map((g): CoverageLimitation => ({ name: g.provider, kind: 'uncovered', reason: g.reason })),
    ...brokenPriority(rows, evidence, now).map((r): CoverageLimitation => ({ name: r.source_name, kind: 'broken_priority', reason: classifySource(r, evidence, now)[1] })),
  ];
}

export function limitationsLine(limits: CoverageLimitation[]): string {
  if (limits.length === 0) return '';
  const unc = limits.filter((l) => l.kind === 'uncovered').map((l) => l.name);
  const brk = limits.filter((l) => l.kind === 'broken_priority').map((l) => l.name);
  const parts = [
    ...(unc.length ? [`${unc.join(', ')} not covered by an authoritative feed`] : []),
    ...(brk.length ? [`${brk.join(', ')} currently failing`] : []),
  ];
  return `Coverage limitations: ${parts.join('; ')}.`;
}
