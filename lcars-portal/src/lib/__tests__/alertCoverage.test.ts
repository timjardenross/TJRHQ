import { describe, it, expect } from 'vitest';
import { assessCoverage, describeGaps, staleThresholdMs } from '@/lib/alertCoverage';
import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

const NOW = Date.parse('2026-11-01T12:00:00Z');
const minsAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();

const src = (o: Partial<EmergencyAlertSourceEntry> = {}): EmergencyAlertSourceEntry => ({
  sourceKey: 'nsw_rfs', jurisdiction: 'NSW', sourceName: 'NSW RFS — Major Incidents', sourceType: 'geojson',
  baseUrl: '', feedUrl: null, active: true, fetchIntervalMinutes: 15, notes: null,
  status: 'ok', lastRun: minsAgo(5), lastAction: null, alertCount: 0, ...o,
});

describe('assessCoverage', () => {
  it('good when every active source is healthy and recent', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'vic_emergency', jurisdiction: 'VIC' })], NOW);
    expect(a.level).toBe('good');
    expect(a.gaps).toEqual([]);
  });

  it('one dead source is not hidden by fresh ones (per-source staleness)', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'qld_fire', jurisdiction: 'QLD', lastRun: minsAgo(300) })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps.map((g) => [g.sourceKey, g.issue])).toEqual([['qld_fire', 'stale']]);
    expect(a.newestCheckedAt).toBe(minsAgo(5));
    expect(a.oldestCheckedAt).toBe(minsAgo(300));
  });

  it('failed sources degrade coverage', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'sa_cfs', jurisdiction: 'SA', status: 'failed', lastAction: 'HTTP 503' })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps[0]).toMatchObject({ sourceKey: 'sa_cfs', issue: 'failed', detail: 'HTTP 503' });
  });

  it('sources with no feed yet make coverage partial, not good', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'tas_fire', jurisdiction: 'TAS', status: 'skipped', lastAction: 'no feed' })], NOW);
    expect(a.level).toBe('partial');
    expect(a.gaps.map((g) => g.issue)).toEqual(['not_implemented']);
  });

  it('a real failure outranks a missing feed', () => {
    const a = assessCoverage([
      src({ status: 'failed' }),
      src({ sourceKey: 'tas_fire', jurisdiction: 'TAS', status: 'skipped' }),
    ], NOW);
    expect(a.level).toBe('degraded');
  });

  it('a source that never reported is a gap', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'act_esa', jurisdiction: 'ACT', status: 'unknown', lastRun: null })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps[0].issue).toBe('no_data');
  });

  it('unknown when nothing has reported, or there are no active sources', () => {
    expect(assessCoverage([src({ status: 'unknown', lastRun: null })], NOW).level).toBe('unknown');
    expect(assessCoverage([], NOW).level).toBe('unknown');
    expect(assessCoverage([src({ active: false })], NOW).level).toBe('unknown');
  });

  it('a healthy incidents-only source (ACT) makes coverage partial with an incidents_only gap', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'act_esa', jurisdiction: 'ACT', sourceName: 'ACT ESA — Current Incidents' })], NOW);
    expect(a.level).toBe('partial');
    expect(a.gaps).toHaveLength(1);
    expect(a.gaps[0]).toMatchObject({ sourceKey: 'act_esa', issue: 'incidents_only' });
    expect(a.gaps[0].detail).toContain('no warning levels');
  });

  it('a failed incidents-only source is degraded, reported as failed (not incidents_only)', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'act_esa', jurisdiction: 'ACT', status: 'failed', lastAction: 'HTTP 503' })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps.map((g) => [g.sourceKey, g.issue])).toEqual([['act_esa', 'failed']]);
  });

  it('a stale incidents-only source is degraded, reported as stale', () => {
    const a = assessCoverage([src(), src({ sourceKey: 'act_esa', jurisdiction: 'ACT', lastRun: minsAgo(300) })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps.map((g) => g.issue)).toEqual(['stale']);
  });

  it('a real failure elsewhere outranks incidents_only', () => {
    const a = assessCoverage([src({ status: 'failed' }), src({ sourceKey: 'act_esa', jurisdiction: 'ACT' })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps.map((g) => g.issue).sort()).toEqual(['failed', 'incidents_only']);
  });

  it('other sources are unaffected by the incidents-only map', () => {
    for (const key of ['nsw_rfs', 'vic_emergency', 'qld_fire', 'sa_cfs', 'wa_dfes', 'tas_fire']) {
      expect(assessCoverage([src({ sourceKey: key })], NOW).level).toBe('good');
    }
  });

  it('inactive sources are ignored', () => {
    expect(assessCoverage([src(), src({ sourceKey: 'x', active: false, status: 'failed' })], NOW).level).toBe('good');
  });
});

describe('staleThresholdMs', () => {
  it('is never under 90 minutes and scales with the source interval', () => {
    expect(staleThresholdMs(5)).toBe(90 * 60_000);
    expect(staleThresholdMs(15)).toBe(90 * 60_000);
    expect(staleThresholdMs(60)).toBe(180 * 60_000);
  });
});

describe('describeGaps', () => {
  it('labels incidents-only gaps', () => {
    const a = assessCoverage([src({ sourceKey: 'act_esa', jurisdiction: 'ACT', sourceName: 'ACT ESA — Current Incidents' })], NOW);
    expect(describeGaps(a.gaps)).toEqual(['ACT ACT ESA — incidents only (no warning levels monitored)']);
  });

  it('groups by issue and names the jurisdiction', () => {
    const a = assessCoverage([
      src({ sourceKey: 'tas_fire', jurisdiction: 'TAS', sourceName: 'TasALERT — Current Warnings', status: 'skipped' }),
      src({ sourceKey: 'nt_securent', jurisdiction: 'NT', sourceName: 'Secure NT — Alerts', status: 'skipped' }),
    ], NOW);
    expect(describeGaps(a.gaps)).toEqual(['TAS TasALERT, NT Secure NT — not monitored (no feed yet)']);
  });
});
