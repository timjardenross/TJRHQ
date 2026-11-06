/**
 * How much of the official alert picture are we actually seeing?
 *
 * "No Emergency Warnings detected" is only reassuring if every source that
 * could carry one is working. This judges each source on its own heartbeat —
 * never the freshest source standing in for the rest — and names every gap,
 * so the workbench can say "none detected in monitored sources, but X is
 * not monitored" instead of a bare all-clear.
 *
 * Per source, in order: failed (last run errored), not_implemented (the
 * adapter has no feed yet — heartbeats "skipped" permanently), no_data (never
 * ran / no heartbeat), stale (last run older than its own threshold),
 * stale_content (runs fine, but the feed's newest item is older than that
 * feed's expected cadence — the ingestion's own STALE integrity warning),
 * incidents_only (healthy, but the feed carries incidents and not warning
 * levels), else ok.
 */

import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

export type SourceIssue = 'failed' | 'not_implemented' | 'no_data' | 'stale' | 'stale_content' | 'incidents_only';

/** Sources that are healthy but only carry incident data, not warning levels
 * (Advice / Watch and Act / Emergency Warning). They are real, working feeds,
 * so they never go red for this - but they cap coverage at 'partial' so "none
 * detected" is not read as covering warnings we cannot see. Keyed by
 * source_key. */
export const INCIDENTS_ONLY_SOURCES: Record<string, string> = {
  act_esa: 'ESA incident feed only - no warning levels (Advice / Watch and Act / Emergency Warning) are monitored for ACT',
};

export interface CoverageGap {
  sourceKey: string;
  jurisdiction: string;
  sourceName: string;
  issue: SourceIssue;
  detail: string;
}

/** good: every source healthy. partial: healthy, but some source has no feed
 * yet or carries incidents only. degraded: a source failed, is stale, or never reported. unknown: no
 * source has reported at all. */
export type CoverageLevel = 'good' | 'partial' | 'degraded' | 'unknown';

export interface CoverageAssessment {
  level: CoverageLevel;
  gaps: CoverageGap[];
  /** Most recent successful-or-failed check across sources (display only). */
  newestCheckedAt: string | null;
  /** Oldest check among sources that have one — the weakest link's age. */
  oldestCheckedAt: string | null;
}

const MIN_STALE_MS = 90 * 60 * 1000;

/** A source is stale after three of its own fetch intervals, never sooner
 * than 90 minutes (the backend runs every 15 min; six misses is a real
 * collection problem, not a slow tick). */
export function staleThresholdMs(fetchIntervalMinutes: number): number {
  return Math.max(MIN_STALE_MS, 3 * fetchIntervalMinutes * 60 * 1000);
}

export function issueLabel(issue: SourceIssue): string {
  switch (issue) {
    case 'failed': return 'unavailable';
    case 'not_implemented': return 'not monitored (no feed yet)';
    case 'no_data': return 'no data yet';
    case 'stale': return 'not refreshed recently';
    case 'stale_content': return 'feed has gone quiet (no new items for longer than expected)';
    case 'incidents_only': return 'incidents only (no warning levels monitored)';
  }
}

/** The ingestion's own "STALE: newest item Nh old (expected under Mh)" warning, if the
 * integrity row is itself fresh (an old row says nothing about now - the heartbeat checks
 * above already cover a run that stopped). */
function staleContentWarning(s: EmergencyAlertSourceEntry, nowMs: number): string | null {
  const row = s.integrity;
  if (!row || nowMs - new Date(row.checkedAt).getTime() > staleThresholdMs(s.fetchIntervalMinutes)) return null;
  return row.warnings.find((w) => w.startsWith('STALE')) ?? null;
}

export function assessCoverage(sources: EmergencyAlertSourceEntry[], nowMs: number = Date.now()): CoverageAssessment {
  const active = sources.filter((s) => s.active);
  const gaps: CoverageGap[] = [];
  const checked: number[] = [];

  for (const s of active) {
    const last = s.lastRun ? new Date(s.lastRun).getTime() : null;
    if (last !== null) checked.push(last);
    const base = { sourceKey: s.sourceKey, jurisdiction: s.jurisdiction, sourceName: s.sourceName };

    if (s.status === 'failed') {
      gaps.push({ ...base, issue: 'failed', detail: s.lastAction ?? 'last run failed' });
    } else if (s.status === 'skipped') {
      gaps.push({ ...base, issue: 'not_implemented', detail: s.lastAction ?? 'no feed implemented' });
    } else if (last === null) {
      gaps.push({ ...base, issue: 'no_data', detail: 'no collection recorded' });
    } else if (nowMs - last > staleThresholdMs(s.fetchIntervalMinutes)) {
      gaps.push({ ...base, issue: 'stale', detail: `last checked ${new Date(last).toISOString()}` });
    } else if (staleContentWarning(s, nowMs)) {
      gaps.push({ ...base, issue: 'stale_content', detail: staleContentWarning(s, nowMs) as string });
    } else if (s.sourceKey in INCIDENTS_ONLY_SOURCES) {
      // Healthy and recent: failed / skipped / no_data / stale all took
      // precedence above. Only the coverage ceiling is affected.
      gaps.push({ ...base, issue: 'incidents_only', detail: INCIDENTS_ONLY_SOURCES[s.sourceKey] });
    }
  }

  const reported = active.filter((s) => s.lastRun !== null).length;
  let level: CoverageLevel;
  if (active.length === 0 || reported === 0) level = 'unknown';
  else if (gaps.some((g) => g.issue !== 'not_implemented' && g.issue !== 'incidents_only')) level = 'degraded';
  else if (gaps.length > 0) level = 'partial';
  else level = 'good';

  const iso = (ms: number) => new Date(ms).toISOString();
  return {
    level,
    gaps,
    newestCheckedAt: checked.length ? iso(Math.max(...checked)) : null,
    oldestCheckedAt: checked.length ? iso(Math.min(...checked)) : null,
  };
}

/** "TAS (TasALERT), NT (Secure NT) — not monitored (no feed yet)" style
 * summary, grouped by issue so a long list stays readable. */
export function describeGaps(gaps: CoverageGap[]): string[] {
  const byIssue = new Map<SourceIssue, CoverageGap[]>();
  for (const g of gaps) byIssue.set(g.issue, [...(byIssue.get(g.issue) ?? []), g]);
  return [...byIssue.entries()].map(([issue, list]) => `${list.map((g) => `${g.jurisdiction} ${g.sourceName.split(' — ')[0]}`).join(', ')} — ${issueLabel(issue)}`);
}
