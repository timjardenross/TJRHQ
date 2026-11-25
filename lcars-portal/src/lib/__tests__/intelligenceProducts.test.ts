import { describe, test, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import {
  PRODUCT_SECTIONS,
  collectExceptions,
  fetchLatestProducts,
  isMissingTable,
  latestPerProduct,
  newestPerProduct,
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
    expect(out[0].href).toBe('/intelligence-workbench?tab=products#forward_watch');
  });

  test('dated forward-watch exceptions expire after their due_date, not on it', () => {
    const mkEx = (key: string, due?: string) => ({ dedupe_key: key, title: 't', detail: 'd', severity: 'attention', due_date: due });
    const products = [
      mk('forward_watch', '2026-11-24', [
        mkEx('fw:passed', '2026-11-26'),
        mkEx('fw:today', '2026-11-27'),
        mkEx('fw:future', '2026-11-30'),
        mkEx('fw:undated'),
      ]),
      mk('systemic_risk', '2026-11-24', [mkEx('sys:old-due', '2026-11-01')]),
    ];
    const keys = collectExceptions(products, new Date('2026-11-27T10:00:00Z')).map((e) => e.dedupe_key);
    expect(keys).toEqual(['fw:today', 'fw:future', 'fw:undated', 'sys:old-due']);
    expect(collectExceptions(products, new Date('2026-11-28T00:00:00Z')).map((e) => e.dedupe_key)).toEqual([
      'fw:future',
      'fw:undated',
      'sys:old-due',
    ]);
  });

  test('missing table (view and base) is reported as unavailable, not an error', async () => {
    const sb = fakeDb({});
    expect(isMissingTable({ code: '42P01' })).toBe(true);
    expect(await fetchLatestProducts(sb)).toEqual({ available: false, products: [] });
  });

  test('other read errors throw (base table and view)', async () => {
    await expect(fetchLatestProducts(fakeDb({ intelligence_products: { error: { code: '500', message: 'boom' } } }))).rejects.toThrow('boom');
    await expect(
      fetchLatestProducts(fakeDb({ intelligence_products_current: { error: { code: '500', message: 'viewboom' } } })),
    ).rejects.toThrow('viewboom');
  });
});

type Tbl = { rows?: any[]; error?: { code?: string; message?: string } };
/** Minimal PostgREST-like fake: chained order()s are applied as a stable multi-key sort; limit() truncates. A missing table errors 42P01. */
function fakeDb(tables: Record<string, Tbl>, calls: string[] = []) {
  return {
    from: (name: string) => {
      const t = tables[name];
      const orders: [string, boolean][] = [];
      const q: any = {
        select: () => q,
        order: (col: string, o: { ascending: boolean }) => (orders.push([col, o.ascending]), q),
        limit: async (n: number) => {
          calls.push(`${name}|${orders.map(([c, a]) => c + (a ? '+' : '-')).join(',')}`);
          if (!t) return { data: null, error: { code: '42P01', message: `relation "public.${name}" does not exist` } };
          if (t.error) return { data: null, error: t.error };
          const rows = [...(t.rows ?? [])];
          rows.sort((x, y) => {
            for (const [c, asc] of orders) {
              if (x[c] === y[c]) continue;
              return (x[c] < y[c] ? -1 : 1) * (asc ? 1 : -1);
            }
            return 0; // ties keep storage order (arbitrary, as in Postgres)
          });
          return { data: rows.slice(0, n), error: null };
        },
      };
      return q;
    },
  };
}

const gen = (key: string, day: string, hhmm: string, seq: number, title = `${key}#${seq}`, cadence = 'daily') =>
  ({ ...mk(key, day), id: seq * 100 + key.length, as_of: `${day}T${hhmm}:00Z`, title, cadence, reporting_date: day, generation_seq: seq });

describe('multi-generation days (history migration)', () => {
  // The reviewer's case: four generations on one day, stored so that the 05:02 row precedes the newest 05:03 row.
  const sameDay = [
    gen('systemic_risk', '2026-11-26', '03:37', 1),
    gen('systemic_risk', '2026-11-26', '05:02', 3),
    gen('systemic_risk', '2026-11-26', '05:03', 4),
    gen('systemic_risk', '2026-11-26', '05:01', 2),
  ];

  test('BEFORE: base table ordered by generated_for only picks an arbitrary same-day generation (reproduced)', () => {
    const legacyOrder = [...sameDay].sort((a, b) => (a.generated_for < b.generated_for ? 1 : a.generated_for > b.generated_for ? -1 : 0));
    expect(latestPerProduct(legacyOrder)[0].title).toBe('systemic_risk#1'); // not the newest (#4)
  });

  test('AFTER: view present returns the newest generation per product, whatever the row order', async () => {
    const calls: string[] = [];
    const rows = [...sameDay, gen('forward_watch', '2026-11-26', '05:03', 2), gen('forward_watch', '2026-11-26', '05:02', 1)];
    const out = await fetchLatestProducts(fakeDb({ intelligence_products_current: { rows } }, calls));
    expect(out.available).toBe(true);
    expect(Object.fromEntries(out.products.map((p) => [p.product_key, p.title]))).toEqual({
      systemic_risk: 'systemic_risk#4',
      forward_watch: 'forward_watch#2',
    });
    expect(calls).toEqual(['intelligence_products_current|as_of-']);
  });

  test('view with several cadences per product shows the newest generation, ties broken by generation_seq then id', () => {
    const rows = [
      gen('systemic_risk', '2026-11-26', '05:00', 1, 'weekly', 'weekly'),
      gen('systemic_risk', '2026-11-26', '05:03', 4, 'daily'),
      gen('forward_watch', '2026-11-26', '05:00', 1, 'a'),
      gen('forward_watch', '2026-11-26', '05:00', 2, 'b'),
    ];
    expect(newestPerProduct(rows).map((r) => r.title)).toEqual(['daily', 'b']);
    expect(newestPerProduct(rows.slice().reverse()).map((r) => r.title).sort()).toEqual(['b', 'daily']);
  });

  test('fallback: view absent uses the base table with an as_of tie-break, same-day generations resolve to the newest', async () => {
    const calls: string[] = [];
    const rows = sameDay.map(({ id, cadence, reporting_date, generation_seq, ...r }) => r);
    const out = await fetchLatestProducts(fakeDb({ intelligence_products: { rows } }, calls));
    expect(out.products.map((p) => p.title)).toEqual(['systemic_risk#4']);
    expect(calls).toEqual(['intelligence_products_current|as_of-', 'intelligence_products|generated_for-,as_of-']);
  });
});

// Optional local fixture: set INTELLIGENCE_PRODUCTS_FIXTURE to the preserved six-row JSON export to run this block.
const EVIDENCE = process.env.INTELLIGENCE_PRODUCTS_FIXTURE ?? '';
if (!EVIDENCE || !existsSync(EVIDENCE)) {
  console.info('SKIPPED: preserved-rows tests need INTELLIGENCE_PRODUCTS_FIXTURE to point at the six-row JSON export (not set or file absent).');
}
describe.skipIf(!EVIDENCE || !existsSync(EVIDENCE))('preserved six rows: identical behaviour on one-row-per-day data', () => {
  const rows: IntelligenceProduct[] = existsSync(EVIDENCE) ? JSON.parse(readFileSync(EVIDENCE, 'utf8')) : [];
  const legacy = (rs: IntelligenceProduct[]) => latestPerProduct([...rs].sort((a, b) => (a.generated_for === b.generated_for ? 0 : a.generated_for < b.generated_for ? 1 : -1)));
  const byKey = (ps: IntelligenceProduct[]) => [...ps].sort((a, b) => a.product_key.localeCompare(b.product_key));

  test('fixture is the six preserved rows', () => {
    expect(rows).toHaveLength(6);
  });

  test('base-table fallback result is identical to the previous implementation', async () => {
    const out = await fetchLatestProducts(fakeDb({ intelligence_products: { rows } }));
    expect(byKey(out.products)).toEqual(byKey(legacy(rows)));
    expect(out.products.map((p) => `${p.product_key}:${p.generated_for}`).sort()).toEqual([
      'forward_watch:2026-11-25',
      'recurring_provider:2026-11-25',
      'systemic_risk:2026-11-25',
    ]);
  });

  test('view (one generation per product) yields the same products, bodies untouched', async () => {
    const viewRows = rows.filter((r) => r.generated_for === '2026-11-25').map((r, i) => ({ ...r, id: i + 1, cadence: 'unknown', reporting_date: r.generated_for, generation_seq: 1 }));
    const out = await fetchLatestProducts(fakeDb({ intelligence_products_current: { rows: viewRows } }));
    const base = legacy(rows);
    expect(out.products.map((p) => p.body_md).sort()).toEqual(base.map((p) => p.body_md).sort());
    expect(out.products.map((p) => p.product_key).sort()).toEqual(base.map((p) => p.product_key).sort());
    expect(collectExceptions(out.products, new Date('2026-11-25T00:00:00Z')).map((e) => e.dedupe_key).sort()).toEqual(
      collectExceptions(base, new Date('2026-11-25T00:00:00Z')).map((e) => e.dedupe_key).sort(),
    );
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
      intelProductExceptions: [{ dedupe_key: 'forward-watch:x:2026-11-27', title: 't', detail: 'd', href: '/intelligence-workbench?tab=products#forward_watch' }],
    });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ id: 'intel-product-forward-watch:x:2026-11-27', kind: 'triage', href: '/intelligence-workbench?tab=products#forward_watch' });
  });
});
