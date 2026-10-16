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
const SEVERITIES_BY_RANK = ['emergency_warning', 'watch_and_act', 'unknown', 'advice'];

type Row = Record<string, unknown>;
type Result = { data: unknown[] | null; error: unknown };
let tables: Record<string, Result>;
let calls: { table: string; select: string; order: unknown[][]; limit: unknown[] }[];

// A chainable stand-in for the user-scoped client that really applies eq, neq,
// is, not, like, order and limit to the rows in tables[table]. (The expiry
// `or` filter and the is_active filter are not evaluated: test rows are all
// active and unexpired.) This makes the ranking tests exercise the real query
// bound rather than the order the test happened to hand rows in.
function stubClient(): never {
  return {
    from: (table: string) => {
      const call = { table, select: '', order: [] as unknown[][], limit: [] as unknown[] };
      calls.push(call);
      const filters: ((r: Row) => boolean)[] = [];
      let sort: { col: string; asc: boolean } | null = null;
      let max = Infinity;
      const chain: Record<string, unknown> = {};
      const add = (m: string, fn: (...a: unknown[]) => void) => {
        chain[m] = (...args: unknown[]) => { fn(...args); return chain; };
      };
      add('select', (c) => { call.select = String(c); });
      add('eq', (c, v) => { if (c !== 'is_active') filters.push((r) => r[c as string] === v); });
      add('neq', (c, v) => filters.push((r) => r[c as string] !== v));
      add('is', (c, v) => filters.push((r) => (r[c as string] ?? null) === v));
      add('not', (c, _op, v) => filters.push((r) => (r[c as string] ?? null) !== v));
      add('like', (c, pat) => { const prefix = String(pat).replace(/%$/, ''); filters.push((r) => String(r[c as string]).startsWith(prefix)); });
      add('or', () => {});
      add('order', (c, o) => { call.order.push([c, o]); sort = { col: String(c), asc: Boolean((o as { ascending?: boolean })?.ascending) }; });
      add('limit', (n) => { call.limit.push(n); max = Number(n); });
      chain.then = (resolve: (r: Result) => unknown, reject: (e: unknown) => unknown) => {
        const src: Result = tables[table] ?? { data: [], error: null };
        if (src.error || !src.data) return Promise.resolve(src).then(resolve, reject);
        let rows = (src.data as Row[]).filter((r) => filters.every((f) => f(r)));
        if (sort) {
          const { col, asc } = sort;
          rows = [...rows].sort((x, y) => (Date.parse(String(x[col])) - Date.parse(String(y[col]))) * (asc ? 1 : -1));
        }
        return Promise.resolve({ data: rows.slice(0, max), error: null }).then(resolve, reject);
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
    const alertQueries = calls.filter((c) => c.table === 'alerts');
    expect(alertQueries.length).toBe(8); // 4 severities x (dated, undated)
    for (const q of alertQueries) expect(q.select).toBe(MAIN_SELECT);
    for (const c of calls) {
      expect(c.select).not.toMatch(/\*|source_key|raw_text|latitude|longitude|canonical_url|description|location|event_key|emergency_email_sent_at|feed_url|base_url|notes/);
    }
  });

  it('embeds only source_name from alert_sources, never base_url, feed_url, notes or source_key', () => {
    const embeds = [...MAIN_SELECT.matchAll(/alert_sources\(([^)]*)\)/g)].map((m) => m[1]);
    expect(embeds).toEqual(['source_name']);
  });

  it('leaves contract_version at 1.1 and hq_status and latest_brief untouched', async () => {
    const snapshot = await buildTjrLifeSnapshot(stubClient(), FIXED);
    expect(snapshot.contract_version).toBe('1.1');
    expect(snapshot.hq_status).toEqual({ generated_at: '2026-10-15T01:59:30.000Z', summary: 'HQ is operating normally', state: 'ok', error: null });
    expect(snapshot.latest_brief).toEqual({ generated_at: null, brief_date: null, lines: [], error: null });
  });
});

describe('v1.1 alerts: caps and mappings', () => {
  it('keeps the cap at 20: every alert query is bounded to 20 rows and ordered newest first', async () => {
    await buildTjrLifeSnapshot(stubClient(), FIXED);
    const alertQueries = calls.filter((c) => c.table === 'alerts');
    for (const q of alertQueries) expect(q.limit).toEqual([20]);
    expect(alertQueries.map((q) => q.order[0][0]).sort()).toEqual(['first_seen_at', 'first_seen_at', 'first_seen_at', 'first_seen_at', 'issued_at', 'issued_at', 'issued_at', 'issued_at']);
    for (const q of alertQueries) expect(q.order[0][1]).toEqual({ ascending: false });
  });

  it('never returns more than 20 alerts', async () => {
    expect((await items(Array.from({ length: 30 }, (_, n) => alertRow(n)))).length).toBe(20);
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

describe('v1.1 alerts: ranking (severity, then newest first)', () => {
  const sev = (n: number, severity: string, extra: Row = {}) => alertRow(n, { severity, headline: `${severity} ${n}`, ...extra });

  it('keeps an older emergency_warning when 20 newer advice alerts exist', async () => {
    const old = sev(100, 'emergency_warning', { issued_at: '2026-10-01T00:00:00.000Z' });
    const out = await items([...Array.from({ length: 25 }, (_, n) => sev(n, 'advice')), old]);
    expect(out.length).toBe(20);
    expect(out[0].id).toBe(old.id);
    expect(out[0].severity).toBe('emergency_warning');
  });

  it('ranks emergency_warning, then watch_and_act, then unknown, then advice, whatever the recency', async () => {
    const out = await items([
      sev(1, 'advice', { issued_at: '2026-10-15T01:59:00.000Z' }),
      sev(2, 'unknown', { issued_at: '2026-10-15T01:58:00.000Z' }),
      sev(3, 'watch_and_act', { issued_at: '2026-10-10T00:00:00.000Z' }),
      sev(4, 'emergency_warning', { issued_at: '2026-10-05T00:00:00.000Z' }),
    ]);
    expect(out.map((i) => i.severity)).toEqual(SEVERITIES_BY_RANK);
  });

  it('puts unknown (BOM) above advice even when the advice is newer', async () => {
    const out = await items([sev(1, 'advice', { issued_at: '2026-10-15T01:59:00.000Z' }), sev(2, 'unknown', { issued_at: '2026-10-14T00:00:00.000Z' })]);
    expect(out.map((i) => i.severity)).toEqual(['unknown', 'advice']);
  });

  it('orders ties in rank newest first, with issued_at falling back to first_seen_at', async () => {
    const out = await items([
      sev(1, 'watch_and_act', { issued_at: '2026-10-15T00:10:00.000Z' }),
      sev(2, 'watch_and_act', { issued_at: '2026-10-15T01:10:00.000Z' }),
      sev(3, 'watch_and_act', { issued_at: null, first_seen_at: '2026-10-15T00:40:00.000Z' }),
      sev(4, 'watch_and_act', { issued_at: null, first_seen_at: '2026-10-15T01:40:00.000Z' }),
    ]);
    expect(out.map((i) => i.occurred_at)).toEqual(['2026-10-15T01:40:00.000Z', '2026-10-15T01:10:00.000Z', '2026-10-15T00:40:00.000Z', '2026-10-15T00:10:00.000Z']);
  });

  it('with more than 20 emergency_warnings keeps the newest 20 and no lower severity', async () => {
    const emergencies = Array.from({ length: 24 }, (_, n) => sev(n, 'emergency_warning', { issued_at: new Date(Date.UTC(2026, 9, 15, 1, 0) - n * 60000).toISOString() }));
    const out = await items([sev(99, 'watch_and_act', { issued_at: '2026-10-15T01:59:00.000Z' }), ...emergencies]);
    expect(out.length).toBe(20);
    expect(out.every((i) => i.severity === 'emergency_warning')).toBe(true);
    expect(out.map((i) => i.id)).toEqual(emergencies.slice(0, 20).map((r) => r.id));
  });

  it('keeps an undated emergency_warning that is newer than 20 dated ones by first_seen_at', async () => {
    const dated = Array.from({ length: 20 }, (_, n) => sev(n, 'emergency_warning', { issued_at: new Date(Date.UTC(2026, 9, 14, 1, 0) - n * 60000).toISOString() }));
    const undated = sev(50, 'emergency_warning', { issued_at: null, first_seen_at: '2026-10-15T01:00:00.000Z' });
    const out = await items([...dated, undated]);
    expect(out[0].id).toBe(undated.id);
    expect(out.length).toBe(20);
  });
});

describe('v1.1 alerts: last_polled_at (source heartbeat)', () => {
  const hb = (domain_key: string, checked_at: string, status = 'ok'): Row => ({ domain_key, checked_at, status });
  const polled = async (rows: Row[] | null, error: unknown = null) => {
    tables.domain_heartbeats_latest = { data: rows, error };
    return (await buildAlertsSection(stubClient(), FIXED)).last_polled_at;
  };

  it('is the newest checked_at among ok emergency_alert_ sources, read from domain_heartbeats_latest', async () => {
    expect(await polled([hb('emergency_alert_nsw_rfs', '2026-10-15T01:10:00.000Z'), hb('emergency_alert_wa', '2026-10-15T01:55:00+00:00')])).toBe('2026-10-15T01:55:00.000Z');
    const q = calls.find((c) => c.table === 'domain_heartbeats_latest');
    expect(q?.select).toBe('domain_key, checked_at');
    expect(q?.order).toEqual([['checked_at', { ascending: false }]]);
    expect(q?.limit).toEqual([50]);
    expect(calls.some((c) => c.table === 'alerts' && c.select === 'last_seen_at')).toBe(false); // alert rows no longer used
  });

  it('ignores skipped and failed sources (only status ok counts)', async () => {
    expect(await polled([hb('emergency_alert_tas', '2026-10-15T01:59:00.000Z', 'skipped'), hb('emergency_alert_nt', '2026-10-15T01:58:00.000Z', 'skipped'), hb('emergency_alert_vic', '2026-10-15T01:57:00.000Z', 'failed'), hb('emergency_alert_wa', '2026-10-15T01:20:00.000Z')])).toBe('2026-10-15T01:20:00.000Z');
  });

  it('excludes the hourly summary job and any key without the emergency_alert_ prefix', async () => {
    expect(await polled([hb('emergency_alert_hourly_summary', '2026-10-15T01:59:59.000Z'), hb('emergency-alertXnsw', '2026-10-15T01:59:00.000Z'), hb('core_events', '2026-10-15T01:58:00.000Z'), hb('emergency_alert_nsw_rfs', '2026-10-15T01:00:00.000Z')])).toBe('2026-10-15T01:00:00.000Z');
  });

  it('is null when no row qualifies, when there are no rows, and when the heartbeat query fails', async () => {
    expect(await polled([hb('emergency_alert_tas', '2026-10-15T01:59:00.000Z', 'skipped')])).toBeNull();
    expect(await polled([])).toBeNull();
    expect(await polled(null, { message: 'LEAK' })).toBeNull();
  });

  it('is null when the heartbeat query throws, and the alerts section is still served', async () => {
    const client = stubClient() as unknown as { from: (t: string) => unknown };
    const inner = client.from;
    client.from = (t: string) => { if (t === 'domain_heartbeats_latest') throw new Error('LEAK'); return inner(t); };
    tables.alerts = { data: [alertRow(1)], error: null };
    const section = await buildAlertsSection(client as never, FIXED);
    expect(section.last_polled_at).toBeNull();
    expect(section.items.length).toBe(1);
  });
});

describe('v1.1 failure and size behaviour', () => {
  it('a failure in an alerts query makes only alerts exactly {"error":"unavailable"}', async () => {
    tables.alerts = { data: null, error: { message: 'LEAK' } };
    const a = await buildTjrLifeSnapshot(stubClient(), FIXED);
    expect(a.alerts).toEqual({ error: 'unavailable' });
    expect(JSON.stringify(a)).not.toContain('LEAK');
    expect('summary' in a.hq_status && 'lines' in a.latest_brief).toBe(true);
  });

  it('a failed heartbeat query does not make alerts unavailable: last_polled_at is null', async () => {
    tables.alerts = { data: [alertRow(1)], error: null };
    tables.domain_heartbeats_latest = { data: null, error: { message: 'x' } };
    const a = (await buildTjrLifeSnapshot(stubClient(), FIXED)).alerts as { items: AlertItem[]; last_polled_at: string | null };
    expect(a.last_polled_at).toBeNull();
    expect(a.items.length).toBe(1);
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
        row(3, { headline: 'Hazard reduction burn, smoke possible', severity: 'advice', issued_at: '2026-10-14T23:00:00.000Z', jurisdiction: 'QLD', alert_type: 'hazard_reduction', status: 'new', expiry: '2026-10-15T06:00:00.000Z', updated_at_src: '2026-10-14T23:05:00.000Z', last_seen_at: '2026-10-15T01:56:00.000Z', alert_sources: { source_name: 'QFES' } }),
        row(2, { headline: 'Severe thunderstorm warning for the Illawarra', severity: 'unknown', issued_at: '2026-10-15T00:10:00.000Z', jurisdiction: 'NSW', alert_type: 'severe_weather', status: 'active', expiry: null, updated_at_src: null, last_seen_at: '2026-10-15T01:57:00.000Z', alert_sources: { source_name: 'Bureau of Meteorology warnings' } }),
        row(4, { headline: 'Watch and Act: grass fire near Geelong', severity: 'watch_and_act', issued_at: '2026-10-14T20:00:00.000Z', jurisdiction: 'VIC', alert_type: 'bushfire', status: 'active', expiry: null, updated_at_src: '2026-10-15T00:30:00.000Z', last_seen_at: '2026-10-15T01:58:00.000Z', alert_sources: { source_name: 'VIC Emergency' } }),
        row(1, { headline: 'Bushfire Emergency Warning: evacuate now', severity: 'emergency_warning', issued_at: '2026-10-15T01:40:00.000Z', jurisdiction: 'VIC', alert_type: 'bushfire', status: 'updated', expiry: '2026-10-15T09:00:00.000Z', updated_at_src: '2026-10-15T01:52:00.000Z', last_seen_at: '2026-10-15T01:58:00.000Z', alert_sources: { source_name: 'VIC Emergency' } }),
      ], error: null },
      domain_heartbeats_latest: { data: [
        { domain_key: 'emergency_alert_nsw_rfs', checked_at: '2026-10-15T01:58:30.000Z', status: 'ok' },
        { domain_key: 'emergency_alert_wa', checked_at: '2026-10-15T01:57:00.000Z', status: 'ok' },
        { domain_key: 'emergency_alert_tas', checked_at: '2026-10-15T01:59:00.000Z', status: 'skipped' },
        { domain_key: 'emergency_alert_vic', checked_at: '2026-10-15T01:59:10.000Z', status: 'failed' },
        { domain_key: 'emergency_alert_hourly_summary', checked_at: '2026-10-15T01:59:50.000Z', status: 'ok' },
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
        headline: cjk(400), severity: i % 5 === 0 ? 'unknown' : 'watch_and_act', issued_at: new Date(Date.UTC(2026, 9, 15, 1, 40) - i * 60000).toISOString(),
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
