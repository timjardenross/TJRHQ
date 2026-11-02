import { describe, it, expect } from 'vitest';
import { matchAreas, parseAreas } from '@/lib/bomAreas';
import type { AlertSiteEntry } from '@/app/api/emergency-alerts/sites/route';

const site = (id: string, o: Partial<AlertSiteEntry> = {}): AlertSiteEntry => ({
  id, siteType: 'Branch', name: id, address: '', suburb: 'X', state: 'QLD', postcode: '4000', priority: 'Tier 1',
  latitude: null, longitude: null, geocodeQuality: 'address', ...o,
});

const D = {
  areas: {
    QLD_RC001: { product: 'flood_catchment', name: 'Barcoo River to Isisford', state: 'QLD' },
    QLD_RC002: { product: 'flood_catchment', name: 'Lower Condamine River', state: 'QLD' },
    NSW_RC001: { product: 'flood_catchment', name: 'Warrego River (NSW)', state: 'NSW' },
    NSW_FW003: { product: 'fire_weather_district', name: 'Greater Hunter', state: 'NSW' },
    QLD_PW010: { product: 'forecast_district', name: 'Wide Bay and Burnett', state: 'QLD' },
  },
  sites: { s1: ['QLD_RC002'], s2: [], s3: ['NSW_FW003'], s4: ['QLD_PW010'] } as Record<string, string[]>,
};

describe('parseAreas', () => {
  it('reads flood, fire weather and forecast district headlines', () => {
    expect(parseAreas('Minor Flood Warning for the Lower Moonie River', 'QLD')).toEqual([['flood_catchment', 'Moonie River', 'QLD']]);
    expect(parseAreas('Initial Minor Flood Warning for the Paroo River (NSW)', 'NSW')).toEqual([['flood_catchment', 'Paroo River', 'NSW']]);
    expect(parseAreas('Fire Weather Warning for the Greater Hunter fire weather district', 'NSW')[0]).toEqual(['fire_weather_district', 'Greater Hunter', 'NSW']);
    expect(parseAreas('Severe Thunderstorm Warning for Wide Bay and Burnett Forecast District.', 'QLD')[0]).toEqual(['forecast_district', 'Wide Bay and Burnett', 'QLD']);
  });

  it('ignores cancellations and headlines naming nothing we can resolve', () => {
    expect(parseAreas('Cancellation of Severe Thunderstorm Warning for X Forecast Districts.', 'VIC')).toEqual([]);
    expect(parseAreas('Tropical Cyclone Advice for Norfolk Island', 'NSW')).toEqual([]);
  });
});

describe('matchAreas', () => {
  const sites = [site('s1'), site('s2'), site('s3', { state: 'NSW' }), site('s4'), site('s5')];

  it('matched: a site inside the named catchment, and it counts sites we have no area for', () => {
    const r = matchAreas({ headline: 'Moderate Flood Warning for the Lower Condamine River', jurisdiction: 'QLD' }, sites, D);
    expect(r.kind).toBe('matched');
    expect(r.sites.map((s) => s.id)).toEqual(['s1']);
    expect(r.unknownSites).toBe(1); // s5 has no entry
  });

  it('none_inside: the area is known but none of our sites are in it', () => {
    const r = matchAreas({ headline: 'Moderate Flood Warning for the Barcoo River', jurisdiction: 'QLD' }, sites, D);
    expect(r.kind).toBe('none_inside');
    expect(r.areaNames).toEqual(['Barcoo River to Isisford']);
  });

  it('keeps a multi-word district whole and respects state', () => {
    expect(matchAreas({ headline: 'Severe Thunderstorm Warning for Wide Bay and Burnett Forecast District.', jurisdiction: 'QLD' }, sites, D).sites.map((s) => s.id)).toEqual(['s4']);
    expect(matchAreas({ headline: 'Fire Weather Warning for the Greater Hunter fire weather district', jurisdiction: 'NSW' }, sites, D).sites.map((s) => s.id)).toEqual(['s3']);
    expect(matchAreas({ headline: 'Initial Minor Flood Warning for the Warrego River (NSW)', jurisdiction: 'NSW' }, sites, D).kind).toBe('none_inside');
  });

  it('unparsed when the headline resolves to nothing', () => {
    expect(matchAreas({ headline: 'Tropical Cyclone Advice for Norfolk Island', jurisdiction: 'NSW' }, sites, D).kind).toBe('unparsed');
  });
});
