import { describe, it, expect } from 'vitest';
import { matchAlert, statesWithoutSiteMatch, haversineKm, stateSiteSummary } from '@/lib/siteMatching';
import type { AlertSiteEntry } from '@/app/api/emergency-alerts/sites/route';

const site = (o: Partial<AlertSiteEntry> = {}): AlertSiteEntry => ({
  id: 's1', siteType: 'Branch', name: 'Test Branch', address: '1 Main St', suburb: 'Katoomba', state: 'NSW',
  postcode: '2780', priority: 'Tier 3', latitude: -33.7134, longitude: 150.3119, geocodeQuality: 'address', ...o,
});
const alert = (o: Record<string, unknown> = {}) => ({
  jurisdiction: 'NSW', severity: 'emergency_warning', headline: 'Bush fire', location: null as string | null,
  latitude: null as number | null, longitude: null as number | null, ...o,
});

describe('matchAlert', () => {
  it('matches within the radius by distance', () => {
    const m = matchAlert(alert({ latitude: -33.6134, longitude: 150.3119 }), [site()]);
    expect(m).toHaveLength(1);
    expect(m[0].method).toBe('distance');
    expect(m[0].distanceKm).toBeGreaterThan(10);
    expect(m[0].distanceKm).toBeLessThan(12);
  });

  it('does not match outside the radius', () => {
    expect(matchAlert(alert({ latitude: -33.0, longitude: 150.3119 }), [site()])).toEqual([]);
  });

  it('advice uses a smaller radius; a coarse geocode widens reach', () => {
    const a = alert({ severity: 'advice', latitude: -33.5134, longitude: 150.3119 }); // ~22 km
    expect(matchAlert(a, [site({ geocodeQuality: 'address' })])).toEqual([]);
    expect(matchAlert(a, [site({ geocodeQuality: 'postcode' })])).toHaveLength(1);
  });

  it('distance matching ignores state (border sites)', () => {
    expect(matchAlert(alert({ jurisdiction: 'QLD', latitude: -33.7, longitude: 150.31 }), [site()])).toHaveLength(1);
  });

  it('text: suburb or postcode in same state', () => {
    expect(matchAlert(alert({ location: 'Katoomba, NSW' }), [site()])[0].method).toBe('text');
    expect(matchAlert(alert({ headline: 'Fire near 2780' }), [site()])).toHaveLength(1);
  });

  it('text: other state, partial word and short suburb names do not match', () => {
    expect(matchAlert(alert({ jurisdiction: 'VIC', location: 'Katoomba' }), [site()])).toEqual([]);
    expect(matchAlert(alert({ location: 'Katoombaville' }), [site()])).toEqual([]);
    expect(matchAlert(alert({ location: 'Ayr district' }), [site({ suburb: 'Ayr', latitude: null, longitude: null, geocodeQuality: 'none' })])).toEqual([]);
  });

  it('falls back to text when the site is not geocoded', () => {
    const s = site({ latitude: null, longitude: null, geocodeQuality: 'none' });
    expect(matchAlert(alert({ latitude: -33.7, longitude: 150.3, location: 'Katoomba' }), [s])[0].method).toBe('text');
  });

  it('orders Tier 1 first, then nearest', () => {
    const a = alert({ latitude: -33.7134, longitude: 150.3119 });
    const names = matchAlert(a, [
      site({ name: 'near-t3', priority: 'Tier 3' }),
      site({ name: 'far-t1', priority: 'Tier 1', latitude: -33.6, longitude: 150.31 }),
      site({ name: 'near-t1', priority: 'Tier 1', latitude: -33.7, longitude: 150.31 }),
    ]).map((m) => m.site.name);
    expect(names).toEqual(['near-t1', 'far-t1', 'near-t3']);
  });
});

describe('statesWithoutSiteMatch', () => {
  it('counts unmatched alerts only in states where we have sites', () => {
    const out = statesWithoutSiteMatch(
      [alert({ location: 'Katoomba' }), alert({ location: 'Dubbo' }), alert({ jurisdiction: 'TAS', location: 'x' })],
      [site()],
    );
    expect(out).toEqual({ NSW: 1 });
  });
});

describe('haversineKm', () => {
  it('Sydney to Melbourne is about 713 km', () => {
    const d = haversineKm(-33.8688, 151.2093, -37.8136, 144.9631);
    expect(d).toBeGreaterThan(700);
    expect(d).toBeLessThan(725);
  });
});

describe('stateSiteSummary', () => {
  it('counts sites and Tier 1 in one state', () => {
    expect(stateSiteSummary('NSW', [site(), site({ priority: 'Tier 1' }), site({ state: 'VIC' })])).toEqual({ total: 2, tier1: 1 });
    expect(stateSiteSummary('TAS', [site()])).toEqual({ total: 0, tier1: 0 });
  });
});
