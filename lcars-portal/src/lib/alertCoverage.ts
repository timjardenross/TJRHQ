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
 * ran / no heartbeat), stale (last run older than its own threshold), else ok.
 */

import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

export type SourceIssue = 'failed' | 'not_implemented' | 'no_data' | 'stale';

export interface CoverageGap {
  sourceKey: string;
  jurisdiction: string;
  sourceName: string;
  issue: SourceIssue;
  detail: string;
}

/** good: every source healthy. partial: healthy, but some source has no feed
 * yet. degraded: a source failed, is stale, or never reported. unknown: no
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
  }
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
    }
  }

  const reported = active.filter((s) => s.lastRun !== null).length;
  let level: CoverageLevel;
  if (active.length === 0 || reported === 0) level = 'unknown';
  else if (gaps.some((g) => g.issue !== 'not_implemented')) level = 'degraded';
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
