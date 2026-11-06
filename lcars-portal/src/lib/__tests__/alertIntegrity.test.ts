import { describe, it, expect } from 'vitest';
import { capDetails, integrityLines } from '@/lib/alertIntegrity';
import { assessCoverage } from '@/lib/alertCoverage';
import type { EmergencyAlertSourceEntry, SourceIntegrity } from '@/app/api/emergency-alerts/sources/route';

const NOW = Date.parse('2026-11-06T12:00:00Z');
const minsAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();

const integrity = (o: Partial<SourceIntegrity> = {}): SourceIntegrity => ({
  checkedAt: minsAgo(5), status: 'ok', itemsSeen: 4, accepted: 4, excluded: {}, invalid: {}, unmapped: {}, newestItemAt: minsAgo(30), warnings: [], ...o,
});
const src = (o: Partial<EmergencyAlertSourceEntry> = {}): EmergencyAlertSourceEntry => ({
  sourceKey: 'wa_dfes', jurisdiction: 'WA', sourceName: 'WA DFES — Warnings', sourceType: 'rss', baseUrl: '', feedUrl: null, active: true,
  fetchIntervalMinutes: 15, notes: null, status: 'ok', lastRun: minsAgo(5), lastAction: null, alertCount: 0, integrity: integrity(), ...o,
});

describe('integrityLines', () => {
  it('lists only sources that dropped something or need attention', () => {
    const lines = integrityLines([
      src(),
      src({ sourceKey: 'nsw_rfs', jurisdiction: 'NSW', sourceName: 'NSW RFS — Major Incidents', integrity: integrity({ itemsSeen: 30, accepted: 13, excluded: { hazard_reduction: 15, not_applicable: 2 } }) }),
    ]);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ sourceKey: 'nsw_rfs', sourceName: 'NSW RFS', summary: 'saw 30, kept 13', attention: false });
    expect(lines[0].drops).toEqual(['excluded 17 (hazard reduction 15, not applicable 2)']);
  });

  it('puts sources that need attention first and carries the warnings', () => {
    const lines = integrityLines([
      src({ sourceKey: 'a', integrity: integrity({ excluded: { smoke_alert: 2 } }) }),
      src({ sourceKey: 'b', integrity: integrity({ warnings: ['STALE: newest item 80h old (expected under 72h)'] }) }),
    ]);
    expect(lines.map((l) => l.sourceKey)).toEqual(['b', 'a']);
    expect(lines[0].attention).toBe(true);
    expect(lines[0].warnings[0]).toMatch(/^STALE/);
  });

  it('ignores inactive sources and sources with no integrity row yet (migration not applied)', () => {
    expect(integrityLines([src({ active: false, integrity: integrity({ excluded: { x: 1 } }) }), src({ integrity: null }), src({ integrity: undefined })])).toEqual([]);
  });

  it('flags a failed run even when it carries no warning text', () => {
    const [l] = integrityLines([src({ integrity: integrity({ status: 'failed' }) })]);
    expect(l.attention).toBe(true);
    expect(l.warnings).toEqual(['run failed the integrity check']);
  });
});

describe('capDetails', () => {
  it('shows what the source gave and hides the literal SA "Unknown" severity', () => {
    expect(capDetails({ capEvent: 'Bushfire', capUrgency: 'Immediate', capCertainty: 'Observed', capSeverity: 'Unknown' })).toEqual([
      { label: 'Event', value: 'Bushfire' }, { label: 'Urgency', value: 'Immediate' }, { label: 'Certainty', value: 'Observed' },
    ]);
    expect(capDetails({ capSeverity: 'Severe' })).toEqual([{ label: 'Source severity', value: 'Severe' }]);
  });
  it('is empty for sources without CAP fields', () => {
    expect(capDetails({ capEvent: null, capUrgency: null })).toEqual([]);
  });
});

describe('stale_content coverage', () => {
  const warn = ['STALE: newest item 80h old (expected under 72h)'];

  it('a source that runs fine but whose feed went quiet degrades coverage', () => {
    const a = assessCoverage([src({ integrity: integrity({ warnings: warn }) })], NOW);
    expect(a.level).toBe('degraded');
    expect(a.gaps.map((g) => [g.sourceKey, g.issue, g.detail])).toEqual([['wa_dfes', 'stale_content', warn[0]]]);
  });

  it('an old integrity row is not evidence about now', () => {
    const a = assessCoverage([src({ integrity: integrity({ checkedAt: minsAgo(600), warnings: warn }) })], NOW);
    expect(a.level).toBe('good');
  });

  it('non-STALE warnings (field drift) do not change coverage', () => {
    const a = assessCoverage([src({ integrity: integrity({ warnings: ['FIELD DRIFT: updated missing on all 5 alerts'] }) })], NOW);
    expect(a.level).toBe('good');
  });

  it('heartbeat staleness still takes precedence', () => {
    const a = assessCoverage([src({ lastRun: minsAgo(300), integrity: integrity({ warnings: warn }) })], NOW);
    expect(a.gaps[0].issue).toBe('stale');
  });
});
