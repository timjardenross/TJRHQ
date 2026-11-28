import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadIntelExtras, mapIncident, mapProductException } from '../intelExtras';
import type { IncidentRow } from '@/lib/incidents';

const incident: IncidentRow = { incident_key: 'inc-abc', headline: 'Telstra mobile outage', tier: 'IMMEDIATE_ALERT', restoration_status: 'partial_restoration', n_reports: 4, why: 'Alert-level and still live.', reports: [], material_exception: false, snapshot_at: '2026-11-24T05:00:00Z', last_report_at: '2026-11-24T04:50:00Z' };
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const stub = (map: Record<string, unknown>) => vi.stubGlobal('fetch', vi.fn(async (url: string) => {
  const key = Object.keys(map).find((k) => String(url).startsWith(k));
  return key ? ok(map[key]) : { ok: false, status: 404, json: async () => ({}) };
}));
afterEach(() => vi.unstubAllGlobals());

describe('HQ reads the Intelligence delivery instead of rebuilding it', () => {
  it('an incident becomes one HQ item with the programme\'s own tier and reason, and claims no evidence grade', () => {
    const i = mapIncident(incident);
    expect(i).toMatchObject({ id: 'incident:inc-abc', title: 'Telstra mobile outage', risk: 'High', needsYou: true, evidence: 'Unknown', why: 'Alert-level and still live.' });
    expect(i.legacyHref).toContain('incidents');
    expect(mapIncident({ ...incident, tier: 'SCHEDULED_BRIEF', material_exception: true }).risk).toBe('Medium');
  });
  it('a high-severity product exception needs you; others are watching', () => {
    const base = { dedupe_key: 'k1', title: 'Recurring provider', detail: 'd', severity: 'high', product_key: 'p', product_title: 'Provider product', generated_for: '2026-11-24', href: '/x' };
    expect(mapProductException(base)).toMatchObject({ id: 'product:k1', needsYou: true, watching: false, risk: 'High' });
    expect(mapProductException({ ...base, severity: 'low' })).toMatchObject({ needsYou: false, watching: true });
  });
  it('states "off" when the incident flag is off, never an empty all-clear', async () => {
    stub({ '/api/intelligence-workbench/incidents': { enabled: false, available: false, incidents: [] }, '/api/intelligence-workbench/products': { available: false }, '/api/intelligence-workbench/source-coverage': { summary: { HEALTHY: 3, QUIET: 0, UNVERIFIED: 0, DEGRADED: 0, BROKEN: 0, UNCOVERED: 0 }, sources: [], limitations_line: '' } });
    const x = await loadIntelExtras();
    expect(x.incidents.state).toBe('off');
    expect(x.products.state).toBe('unavailable');
    expect(x.coverage.state).toBe('ok');
  });
  it('passes incidents, product exceptions and non-healthy sources through when present', async () => {
    stub({
      '/api/intelligence-workbench/incidents': { enabled: true, available: true, incidents: [incident] },
      '/api/intelligence-workbench/products': { available: true, products: [{ product_key: 'p', title: 'T', summary: 's', as_of: '2026-11-24', generated_for: '2026-11-24', sections: {}, exceptions: [], body_md: '' }], exceptions: [{ dedupe_key: 'k', title: 'e', detail: 'd', severity: 'medium', product_key: 'p', product_title: 'T', generated_for: '2026-11-24', href: '/x' }] },
      '/api/intelligence-workbench/source-coverage': { summary: { HEALTHY: 5, QUIET: 1, UNVERIFIED: 0, DEGRADED: 1, BROKEN: 1, UNCOVERED: 0 }, sources: [{ source_name: 'A', state: 'BROKEN', reason: 'no check in 4 days' }, { source_name: 'B', state: 'HEALTHY', reason: '' }], limitations_line: 'Telstra not covered.' },
    });
    const x = await loadIntelExtras();
    expect(x.incidents).toMatchObject({ state: 'ok' });
    expect(x.incidents.items).toHaveLength(1);
    expect(x.products.items).toHaveLength(1);
    expect(x.coverage.notHealthy.map((s) => s.source_name)).toEqual(['A']);
    expect(x.coverage.limitationsLine).toBe('Telstra not covered.');
  });
  it('an endpoint that fails is "unavailable", not an error and not empty', async () => {
    stub({});
    const x = await loadIntelExtras();
    expect([x.incidents.state, x.products.state, x.coverage.state]).toEqual(['unavailable', 'unavailable', 'unavailable']);
  });
});
