// Contract v1.1 (richer alerts). The v1.0 behaviour and fixtures are covered by
// snapshot.test.ts; this file covers only what v1.1 adds. Fixtures:
// fixtures/tjr-life-snapshot-v1_1/ (regenerate the four builder-made ones with
// UPDATE_FIXTURES=1 npx vitest run <this file>).
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { overviewMock } = vi.hoisted(() => ({ overviewMock: vi.fn() }));
vi.mock('@/lib/agentStatusOverview', () => ({ buildAgentStatusOverview: overviewMock }));

import { buildAlertsSection, buildTjrLifeSnapshot, enforceSizeCap, type AlertItem } from '@/lib/tjrLifeSnapshot';

const FIXTURE_DIR = join(__dirname, '../../../../../../../../fixtures/tjr-life-snapshot-v1_1');
const FIXED = new Date('2026-10-15T02:00:00.000Z');
const MAIN_SELECT =
  'id, headline, severity, issued_at, first_seen_at, jurisdiction, alert_type, status, expiry, updated_at_src, last_seen_at, alert_sources(source_name)';

type Row = Record<string, unknown>;
type Result = { data: unknown[] | null; error: unknown };
let tables: Record<string, Result>;
let calls: { table: string; select: string; order: unknown[][]; limit: unknown[] }[];

// A chainable stand-in for the user-scoped client. The alerts table serves two
// queries: the main page, and the one-row last_polled_at query (select
// 'last_seen_at'), which is derived from the same rows unless overridden.
function stubClient(): never {
  return {
    from: (table: string) => {
      const call = { table, select: '', order: [] as unknown[][], limit: [] as unknown[] };
      calls.push(call);
      const chain: Record<string, unknown> = {};
      for (const m of ['select', 'eq', 'or', 'order', 'limit']) {
        chain[m] = (...args: unknown[]) => {
          if (m === 'select') call.select = String(args[0]);
          if (m === 'order') call.order.push(args);
          if (m === 'limit') call.limit.push(args[0]);
          return chain;
        };
      }
      chain.then = (resolve: (r: Result) => unknown, reject: (e: unknown) => unknown) => {
        let result: Result = tables[table] ?? { data: [], error: null };
        if (table === 'alerts' && call.select === 'last_seen_at') {
          result = tables.alerts_polled ?? {
            data: result.error ? null : [...((result.data ?? []) as Row[])].sort((a, b) => String(b.last_seen_at).localeCompare(String(a.last_seen_at))).slice(0, 1),
            error: result.error,
          };
        }
        return Promise.resolve(result).then(resolve, reject);
      };
      return chain;
    },
  } as never;
}

const alertRow = (n: number, extra: Row = {}): Row => ({
  id: `6f1c0c1e-0000-4000-8000-${String(n).padStart(12, '0')}`,
  headline: `Alert ${n}`,
  severity: 'advice',
  issued_at: new Date(Date.UTC(2026, 9, 15, 1, 40) - n * 60000).toISOString(),
  first_seen_at: '2026-10-15T00:00:00.000Z',
  last_seen_at: '2026-10-15T01:50:00.000Z',
  jurisdiction: 'VIC',
  alert_type: 'flood',
  status: 'active',
  expiry: null,
  updated_at_src: '2026-10-15T01:45:00.000Z',
  alert_sources: { source_name: 'VIC Emergency' },
  ...extra,
});

async function items(rows: Row[]): Promise<AlertItem[]> {
  tables.alerts = { data: rows, error: null };
  return (await buildAlertsSection(stubClient(), FIXED)).items;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  calls = [];
  tables = { captains_daily_briefs: { data: [], error: null }, alerts: { data: [], error: null } };
  overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'NORMAL', summary: 'HQ is operating normally', last_updated: '2026-10-15T01:59:30.000Z' } });
});

describe('v1.1 alerts: allowlist', () => {
  it('sends only the allowlisted keys per item and per section, never the excluded columns', async () => {
    const leaky = alertRow(1, {
      latitude: -37.8, longitude: 144.9, canonical_url: 'https://feed.example/LEAK-URL', raw_text: 'LEAK-RAW', description: 'LEAK-DESC',
      location: 'LEAK-LOCATION', event_key: 'LEAK-EVENT', emergency_email_sent_at: '2026-10-15T00:00:00Z', source_key: 'LEAK-SOURCEKEY',
      alert_sources: { source_name: 'VIC Emergency', source_key: 'LEAK-SOURCEKEY', feed_url: 'https://feed.example/LEAK-FEED', notes: 'LEAK-NOTES' },
    });
    tables.alerts = { data: [leaky], error: null };
    const snapshot = await buildTjrLifeSnapshot(stubClient(), FIXED);
    const text = JSON.stringify(snapshot);
    expect(text).not.toMatch(/LEAK|latitude|longitude|canonical_url|raw_text|description|location|event_key|emergency_email_sent_at|source_key|feed_url|notes|silence/);
    const alerts = snapshot.alerts as { items: AlertItem[] };
    expect(Object.keys(snapshot.alerts)).toEqual(['generated_at', 'last_polled_at', 'items', 'error']);
    expect(Object.keys(alerts.items[0])).toEqual(['id', 'headline', 'severity', 'occurred_at', 'alert_type', 'status', 'expires_at', 'jurisdiction', 'updated_at', 'source_name']);
  });

  it('pins the select list: named columns plus only source_name from the embed', async () => {
    await buildTjrLifeSnapshot(stubClient(), FIXED);
    const main = calls.find((c) => c.table === 'alerts' && c.select !== 'last_seen_at');
    expect(main?.select).toBe(MAIN_SELECT);
    for (const c of calls) expect(c.select).not.toMatch(/\*|source_key|raw_text|latitude|longitude|canonical_url|description|location|event_key|emergency_email_sent_at|feed_url|notes/);
  });

  it('leaves contract_version at 1.1 and hq_status and latest_brief untouched', async () => {
    const snapshot = await buildTjrLifeSnapshot(stubClient(), FIXED);
    expect(snapshot.contract_version).toBe('1.1');
    expect(snapshot.hq_status).toEqual({ generated_at: '2026-10-15T01:59:30.000Z', summary: 'HQ is operating normally', state: 'ok', error: null });
    expect(snapshot.latest_brief).toEqual({ generated_at: null, brief_date: null, lines: [], error: null });
  });
});

describe('v1.1 alerts: caps and mappings', () => {
  it('keeps the cap at 20 and newest-first ordering (issued_at descending)', async () => {
    await buildTjrLifeSnapshot(stubClient(), FIXED);
    const main = calls.find((c) => c.table === 'alerts' && c.select === MAIN_SELECT);
    expect(main?.limit).toEqual([20]);
    expect(main?.order).toEqual([['issued_at', { ascending: false, nullsFirst: false }]]);
  });

  it('maps alert_type to the ten allowed values, anything else to other', async () => {
    const types = ['bushfire', 'flood', 'storm', 'cyclone', 'heatwave', 'hazard_reduction', 'structure_fire', 'severe_weather', 'tsunami', 'other'];
    const out = await items([...types, 'Flood', ' STORM ', 'earthquake', '', null, 7].map((t, n) => alertRow(n, { alert_type: t })));
    expect(out.map((i) => i.alert_type)).toEqual([...types, 'flood', 'storm', 'other', 'other', 'other', 'other']);
  });

  it('maps status to the seven allowed values, anything else to unknown', async () => {
    const statuses = ['new', 'active', 'updated', 'superseded', 'expired', 'inactive', 'errored'];
    const out = await items([...statuses, 'Active', 'paused', '', null].map((t, n) => alertRow(n, { status: t })));
    expect(out.map((i) => i.status)).toEqual([...statuses, 'active', 'unknown', 'unknown', 'unknown']);
  });

  it('caps jurisdiction at 8 characters and omits it when missing or blank', async () => {
    const out = await items([alertRow(1, { jurisdiction: 'NSW' }), alertRow(2, { jurisdiction: 'ABCDEFGHIJKL' }), alertRow(3, { jurisdiction: null }), alertRow(4, { jurisdiction: '  ' }), alertRow(5, { jurisdiction: '<b>VIC</b>' })]);
    expect(out[0].jurisdiction).toBe('NSW');
    expect(out[1].jurisdiction).toBe('ABCDEFG…');
    expect(out[1].jurisdiction!.length).toBe(8);
    expect('jurisdiction' in out[2]).toBe(false);
    expect('jurisdiction' in out[3]).toBe(false);
    expect(out[4].jurisdiction).toBe('VIC');
  });

  it('sends the source display name capped at 40 characters, tolerates an array embed, omits it when missing', async () => {
    const out = await items([
      alertRow(1, { alert_sources: { source_name: 'N'.repeat(60) } }),
      alertRow(2, { alert_sources: [{ source_name: 'QLD Fire &amp; Emergency' }] }),
      alertRow(3, { alert_sources: null }),
      alertRow(4, { alert_sources: { source_name: '' } }),
    ]);
    expect(out[0].source_name).toBe(`${'N'.repeat(39)}…`);
    expect(out[0].source_name!.length).toBe(40);
    expect(out[1].source_name).toBe('QLD Fire & Emergency');
    expect('source_name' in out[2]).toBe(false);
    expect('source_name' in out[3]).toBe(false);
  });

  it('sends expires_at as ISO-8601 UTC with Z, or null when absent or unparseable', async () => {
    const out = await items([
      alertRow(1, { expiry: '2026-10-16T11:00:00+11:00' }),
      alertRow(2, { expiry: null }),
      alertRow(3, { expiry: 'not a date' }),
      alertRow(4, {}), // column absent
    ]);
    expect(out[0].expires_at).toBe('2026-10-16T00:00:00.000Z');
    expect(out.slice(1).map((i) => i.expires_at)).toEqual([null, null, null]);
  });

  it('sends updated_at from updated_at_src, else last_seen_at, else omits it', async () => {
    const out = await items([
      alertRow(1, { updated_at_src: '2026-10-15T01:00:00+00:00', last_seen_at: '2026-10-15T01:59:00+00:00' }),
      alertRow(2, { updated_at_src: null, last_seen_at: '2026-10-15T01:59:00+00:00' }),
      alertRow(3, { updated_at_src: null, last_seen_at: null }),
    ]);
    expect(out[0].updated_at).toBe('2026-10-15T01:00:00.000Z');
    expect(out[1].updated_at).toBe('2026-10-15T01:59:00.000Z');
    expect('updated_at' in out[2]).toBe(false);
  });

  it('drops a repeated id and an over-long id, as in v1.0', async () => {
    const a = alertRow(1);
    const out = await items([a, { ...alertRow(2), id: a.id }, alertRow(3, { id: 'x'.repeat(65) }), alertRow(4)]);
    expect(out.map((i) => i.headline)).toEqual(['Alert 1', 'Alert 4']);
  });
});

describe('v1.1 alerts: last_polled_at', () => {
  it('is the newest last_seen_at over all active alerts, read by its own one-row query', async () => {
    tables.alerts = { data: [alertRow(1, { last_seen_at: '2026-10-15T01:10:00.000Z' }), alertRow(2, { last_seen_at: '2026-10-15T01:55:00.000Z' })], error: null };
    const section = await buildAlertsSection(stubClient(), FIXED);
    expect(section.last_polled_at).toBe('2026-10-15T01:55:00.000Z');
    const q = calls.find((c) => c.select === 'last_seen_at');
    expect(q?.limit).toEqual([1]);
    expect(q?.order).toEqual([['last_seen_at', { ascending: false }]]);
    expect(calls.every((c) => c.table === 'alerts')).toBe(true); // no source or heartbeat table is read
  });

  it('is null when there are no active alerts', async () => {
    expect((await buildAlertsSection(stubClient(), FIXED)).last_polled_at).toBeNull();
  });
});

describe('v1.1 failure and size behaviour', () => {
  it('a failure in either alerts query makes only alerts exactly {"error":"unavailable"}', async () => {
    tables.alerts = { data: null, error: { message: 'LEAK' } };
    const a = await buildTjrLifeSnapshot(stubClient(), FIXED);
    expect(a.alerts).toEqual({ error: 'unavailable' });
    expect(JSON.stringify(a)).not.toContain('LEAK');
    expect('summary' in a.hq_status && 'lines' in a.latest_brief).toBe(true);
    tables.alerts = { data: [alertRow(1)], error: null };
    tables.alerts_polled = { data: null, error: { message: 'x' } };
    expect((await buildTjrLifeSnapshot(stubClient(), FIXED)).alerts).toEqual({ error: 'unavailable' });
  });

  const cjk = (n: number) => '漢'.repeat(n);
  it('keeps the response within 64 KB with 3-byte characters in every new text field, shedding brief lines first', async () => {
    overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'DEGRADED', summary: cjk(500), last_updated: '2026-10-15T01:59:30.000Z' } });
    tables.captains_daily_briefs = { data: [{ brief_date: '2026-10-15', generated_at: '2026-10-14T21:00:00.000Z', brief_text: Array.from({ length: 70 }, (_, i) => `${cjk(700)}${i}`).join('\n') }], error: null };
    tables.alerts = { data: Array.from({ length: 20 }, (_, n) => alertRow(n, { headline: cjk(400), jurisdiction: cjk(20), alert_sources: { source_name: cjk(100) } })), error: null };
    const snapshot = await buildTjrLifeSnapshot(stubClient(), FIXED);
    expect(new TextEncoder().encode(JSON.stringify(snapshot)).length).toBeLessThanOrEqual(64 * 1024);
    const brief = snapshot.latest_brief as { lines: string[] };
    const alerts = snapshot.alerts as { items: AlertItem[] };
    expect(brief.lines.length).toBeLessThan(40); // brief shed first
    expect(alerts.items.length).toBe(20); // alerts intact while brief lines remain
  });

  it('enforceSizeCap still sheds brief lines, then alerts, then sections', () => {
    const item = (n: number): AlertItem => ({ id: `i${n}`, headline: cjk(160), severity: 'advice', occurred_at: 'x', alert_type: 'other', status: 'unknown', expires_at: null, source_name: cjk(40) });
    const base = {
      contract_version: '1.1', generated_at: 'x',
      hq_status: { generated_at: 'x', summary: 's', state: 'ok' as const, error: null },
      latest_brief: { generated_at: null, brief_date: null, lines: Array.from({ length: 40 }, () => cjk(500)), error: null },
      alerts: { generated_at: 'x', last_polled_at: null, items: Array.from({ length: 20 }, (_, n) => item(n)), error: null },
    };
    const out = enforceSizeCap(base);
    expect('lines' in out.latest_brief && out.latest_brief.lines.length).toBeLessThan(40);
    expect('items' in out.alerts && out.alerts.items.length).toBe(20);
    const noBrief = enforceSizeCap({ ...base, alerts: { ...base.alerts, items: Array.from({ length: 20 }, (_, n) => ({ ...item(n), headline: cjk(160), source_name: cjk(40) })) }, latest_brief: { ...base.latest_brief, lines: [cjk(30000)] } });
    expect('lines' in noBrief.latest_brief && noBrief.latest_brief.lines.length).toBe(0);
    expect(enforceSizeCap({ ...base, hq_status: { ...base.hq_status, summary: cjk(30000) } }).hq_status).toEqual({ error: 'unavailable' });
  });
});

// ── Fixtures ─────────────────────────────────────────────────────────────────
const NAMES = ['all-errored', 'degraded', 'full', 'malformed-section', 'oversized', 'unknown-keys', 'unknown-version'];
const pretty = (v: unknown) => `${JSON.stringify(v, null, 2)}\n`;
const fixture = (name: string) => readFileSync(join(FIXTURE_DIR, `${name}.json`), 'utf8');
const cjk = (n: number) => '漢'.repeat(n);

async function buildFor(name: 'full' | 'degraded' | 'all-errored' | 'oversized') {
  const at = (s: string) => ({ captainSummary: { hq_posture: 'NORMAL', summary: s, last_updated: '2026-10-15T01:59:30.000Z' } });
  const brief = (text: string) => ({ data: [{ brief_date: '2026-10-15', generated_at: '2026-10-14T21:00:12.000Z', brief_text: text }], error: null });
  const row = (n: number, extra: Row) => ({ id: `6f1c0c1e-0000-4000-8000-${String(n).padStart(12, '0')}`, first_seen_at: '2026-10-14T22:00:00.000Z', ...extra });
  if (name === 'full') {
    overviewMock.mockResolvedValue(at('HQ is operating normally'));
    tables = {
      captains_daily_briefs: brief('<b>MORNING BRIEF</b>\n\nQuiet night.'),
      alerts: { data: [
        row(1, { headline: 'Bushfire Emergency Warning: evacuate now', severity: 'emergency_warning', issued_at: '2026-10-15T01:40:00.000Z', jurisdiction: 'VIC', alert_type: 'bushfire', status: 'updated', expiry: '2026-10-15T09:00:00.000Z', updated_at_src: '2026-10-15T01:52:00.000Z', last_seen_at: '2026-10-15T01:58:00.000Z', alert_sources: { source_name: 'VIC Emergency' } }),
        row(2, { headline: 'Severe thunderstorm warning for the Illawarra', severity: 'unknown', issued_at: '2026-10-15T00:10:00.000Z', jurisdiction: 'NSW', alert_type: 'severe_weather', status: 'active', expiry: null, updated_at_src: null, last_seen_at: '2026-10-15T01:57:00.000Z', alert_sources: { source_name: 'Bureau of Meteorology warnings' } }),
        row(3, { headline: 'Hazard reduction burn, smoke possible', severity: 'advice', issued_at: '2026-10-14T23:00:00.000Z', jurisdiction: 'QLD', alert_type: 'hazard_reduction', status: 'new', expiry: '2026-10-15T06:00:00.000Z', updated_at_src: '2026-10-14T23:05:00.000Z', last_seen_at: '2026-10-15T01:56:00.000Z', alert_sources: { source_name: 'QFES' } }),
      ], error: null },
    };
  } else if (name === 'degraded') {
    overviewMock.mockResolvedValue(at('HQ is degraded: alert coverage may be incomplete.'));
    tables = { captains_daily_briefs: { data: [], error: null }, alerts: { data: null, error: { message: 'x' } } };
  } else if (name === 'oversized') {
    overviewMock.mockResolvedValue(at(cjk(500)));
    tables = {
      captains_daily_briefs: brief(Array.from({ length: 70 }, (_, i) => `<b>${cjk(700)}${i}</b>`).join('\n')),
      alerts: { data: Array.from({ length: 22 }, (_, i) => row(i + 1, {
        headline: cjk(400), severity: i % 5 === 0 ? 'Catastrophic' : 'watch_and_act', issued_at: new Date(Date.UTC(2026, 9, 15, 1, 40) - i * 60000).toISOString(),
        jurisdiction: cjk(20), alert_type: i % 3 === 0 ? 'Earthquake' : 'storm', status: i % 4 === 0 ? 'paused' : 'active', expiry: '2026-10-15T09:00:00.000Z',
        updated_at_src: '2026-10-15T01:00:00.000Z', last_seen_at: '2026-10-15T01:50:00.000Z', alert_sources: { source_name: cjk(100) },
      })), error: null },
    };
  } else {
    overviewMock.mockRejectedValue(new Error('x'));
    tables = { captains_daily_briefs: { data: null, error: { message: 'x' } }, alerts: { data: null, error: { message: 'x' } } };
  }
  return buildTjrLifeSnapshot(stubClient(), FIXED);
}

// A deliberately strict client: v1.x version, unknown keys ignored, a malformed
// section is unavailable (an unknown hq_status.state is malformed).
const isObj = (v: unknown): v is Row => typeof v === 'object' && v !== null && !Array.isArray(v);
function readAsClient(body: Row): { hq: boolean; brief: boolean; alerts: boolean } | 'update_the_app' {
  if (typeof body.contract_version !== 'string' || !/^1\./.test(body.contract_version)) return 'update_the_app';
  const hq = body.hq_status, brief = body.latest_brief, alerts = body.alerts;
  return {
    hq: isObj(hq) && typeof hq.summary === 'string' && ['ok', 'degraded', 'attention', 'unknown'].includes(String(hq.state)),
    brief: isObj(brief) && Array.isArray(brief.lines),
    alerts: isObj(alerts) && Array.isArray(alerts.items) && alerts.items.every((i: unknown) => isObj(i) && typeof i.id === 'string' && typeof i.headline === 'string' && typeof i.severity === 'string' && typeof i.occurred_at === 'string'),
  };
}

describe('fixtures/tjr-life-snapshot-v1_1', () => {
  for (const name of ['full', 'degraded', 'all-errored', 'oversized'] as const) {
    it(`${name}.json is byte-identical to the builder output`, async () => {
      const expected = pretty(await buildFor(name));
      if (process.env.UPDATE_FIXTURES) {
        mkdirSync(FIXTURE_DIR, { recursive: true });
        writeFileSync(join(FIXTURE_DIR, `${name}.json`), expected);
      }
      expect(fixture(name)).toBe(expected);
    });
  }

  it('SHA256SUMS lists all seven fixtures and matches the files', () => {
    const lines = readFileSync(join(FIXTURE_DIR, 'SHA256SUMS'), 'utf8').trim().split('\n');
    expect(lines.map((l) => l.split('  ')[1])).toEqual(NAMES.map((n) => `${n}.json`));
    for (const line of lines) {
      const [hash, file] = line.split('  ');
      expect(createHash('sha256').update(readFileSync(join(FIXTURE_DIR, file))).digest('hex')).toBe(hash);
    }
  });

  it('a v1.x client reads full, degraded, all-errored and oversized; the full alerts section carries BOM unknown severity', () => {
    expect(readAsClient(JSON.parse(fixture('full')))).toEqual({ hq: true, brief: true, alerts: true });
    expect(readAsClient(JSON.parse(fixture('degraded')))).toEqual({ hq: true, brief: true, alerts: false });
    expect(readAsClient(JSON.parse(fixture('all-errored')))).toEqual({ hq: false, brief: false, alerts: false });
    expect(readAsClient(JSON.parse(fixture('oversized')))).toEqual({ hq: true, brief: true, alerts: true });
    expect(JSON.parse(fixture('full')).alerts.items.some((i: Row) => i.severity === 'unknown')).toBe(true);
  });

  it('unknown-keys, malformed-section and unknown-version behave as the client rules say', () => {
    const keys = JSON.parse(fixture('unknown-keys'));
    expect(keys.contract_version).toBe('1.1');
    expect(readAsClient(keys)).toEqual({ hq: true, brief: true, alerts: true });
    expect(keys.alerts.items[0].future_field).toBeDefined();
    expect(readAsClient(JSON.parse(fixture('malformed-section')))).toEqual({ hq: false, brief: false, alerts: false });
    expect(readAsClient(JSON.parse(fixture('unknown-version')))).toBe('update_the_app');
  });

  it('oversized.json obeys the new caps and its wire form is within 64 KB', () => {
    const body = JSON.parse(fixture('oversized'));
    expect(new TextEncoder().encode(JSON.stringify(body)).length).toBeLessThanOrEqual(64 * 1024);
    for (const i of body.alerts.items) {
      expect(i.jurisdiction.length).toBeLessThanOrEqual(8);
      expect(i.source_name.length).toBeLessThanOrEqual(40);
      expect(['unknown', 'active']).toContain(i.status);
      expect(['other', 'storm']).toContain(i.alert_type);
    }
  });

  it('no fixture contains an excluded field name or a feed URL', () => {
    for (const n of NAMES) expect(fixture(n)).not.toMatch(/latitude|longitude|canonical_url|raw_text|"description"|"location"|event_key|emergency_email_sent_at|source_key|feed_url|https?:\/\//);
  });
});
