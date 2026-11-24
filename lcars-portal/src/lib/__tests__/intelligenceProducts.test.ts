import { describe, test, expect } from 'vitest';
import {
  PRODUCT_SECTIONS,
  collectExceptions,
  fetchLatestProducts,
  isMissingTable,
  latestPerProduct,
  type IntelligenceProduct,
} from '../intelligenceProducts';

const sections = { confirmed_evidence: [], analytical_inference: [], potential_exposure: [], unknowns: [] };
const mk = (key: string, day: string, exceptions: IntelligenceProduct['exceptions'] = []): IntelligenceProduct => ({
  product_key: key,
  generated_for: day,
  as_of: `${day}T06:00:00Z`,
  title: key,
  summary: 's',
  sections,
  exceptions,
  body_md: '',
});

describe('intelligence products', () => {
  test('four labelled sections are fixed', () => {
    expect(PRODUCT_SECTIONS.map((s) => s[1])).toEqual([
      'Confirmed evidence',
      'Analytical inference',
      'Potential exposure',
      'Unknowns',
    ]);
  });

  test('latestPerProduct keeps the first (newest) row per product', () => {
    const rows = [mk('a', '2026-11-24'), mk('b', '2026-11-24'), mk('a', '2026-11-17')];
    expect(latestPerProduct(rows).map((r) => `${r.product_key}:${r.generated_for}`)).toEqual([
      'a:2026-11-24',
      'b:2026-11-24',
    ]);
  });

  test('collectExceptions dedupes on the stable dedupe_key and links to the product anchor', () => {
    const e = { dedupe_key: 'forward-watch:x:2026-11-26', title: 't', detail: 'd', severity: 'attention' };
    const out = collectExceptions([mk('forward_watch', '2026-11-24', [e, e]), mk('systemic_risk', '2026-11-24', [e])]);
    expect(out).toHaveLength(1);
    expect(out[0].href).toBe('/intelligence#forward_watch');
  });

  test('missing table is reported as unavailable, not an error', async () => {
    const sb = {
      from: () => ({
        select: () => ({
          order: () => ({ limit: async () => ({ data: null, error: { code: '42P01', message: 'relation does not exist' } }) }),
        }),
      }),
    };
    expect(isMissingTable({ code: '42P01' })).toBe(true);
    expect(await fetchLatestProducts(sb)).toEqual({ available: false, products: [] });
  });

  test('other read errors throw', async () => {
    const sb = {
      from: () => ({
        select: () => ({ order: () => ({ limit: async () => ({ data: null, error: { code: '500', message: 'boom' } }) }) }),
      }),
    };
    await expect(fetchLatestProducts(sb)).rejects.toThrow('boom');
  });
});

describe('Needs You consumer', () => {
  test('product exceptions become low-priority triage items with the stable key; none when absent', async () => {
    const { buildNeedsYouItems } = await import('../commandState');
    const base: any = {
      emergency: null, briefingError: false, interruptNow: 0, contentAwaitingPublish: 0, oldestContentAwaitingPublish: null,
      wellnessRiskFlags: 0, notebookReadyCount: 0, capturePending: 0, oldestCapturePending: null, evolutionPendingCount: 0,
      evolutionHighestValueTitle: null, engineeringApprovalsCount: 0, oldestEngineeringApproval: null, hqPosture: 'NORMAL',
      hqAttentionItems: [], criticalAlerts: [],
    };
    expect(buildNeedsYouItems(base).some((i) => i.id.startsWith('intel-product-'))).toBe(false);
    const items = buildNeedsYouItems({
      ...base,
      intelProductExceptions: [{ dedupe_key: 'forward-watch:x:2026-11-27', title: 't', detail: 'd', href: '/intelligence#forward_watch' }],
    });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ id: 'intel-product-forward-watch:x:2026-11-27', kind: 'triage', href: '/intelligence#forward_watch' });
  });
});
