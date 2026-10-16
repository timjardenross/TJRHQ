import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock, overviewMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
  overviewMock: vi.fn(),
}));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));
vi.mock('@/lib/agentStatusOverview', () => ({ buildAgentStatusOverview: overviewMock }));

import { GET } from './route';

const CAPTAIN_ID = '00000000-0000-4000-8000-00000000c0de';
const TOKEN = 'header.payload.signature-DO-NOT-LOG';
const FIXTURE_DIR = join(__dirname, '../../../../../../../../fixtures/tjr-life-snapshot-v1');

type Result = { data: unknown[] | null; error: unknown };
let tables: Record<string, Result>;
let selects: Record<string, string>;

function builder(table: string) {
  const chain: Record<string, unknown> = {};
  for (const m of ['select', 'eq', 'or', 'order', 'limit']) {
    chain[m] = (...args: unknown[]) => {
      if (m === 'select') selects[table] ??= String(args[0]);
      return chain;
    };
  }
  chain.then = (resolve: (r: Result) => unknown, reject: (e: unknown) => unknown) =>
    Promise.resolve(tables[table] ?? { data: [], error: null }).then(resolve, reject);
  return chain;
}

const req = (init: RequestInit & { token?: string | null } = {}) => {
  const headers: Record<string, string> = {};
  if (init.token !== null) headers.authorization = `Bearer ${init.token ?? TOKEN}`;
  return new Request('https://x.test/api/integrations/tjr-life/v1/snapshot', { method: init.method ?? 'GET', headers });
};

const SUMMARY = (posture: string, summary: string) => ({
  // Everything below `captainSummary` is data the route must never forward.
  captainSummary: { hq_posture: posture, summary, last_updated: '2026-10-15T01:00:00.000Z', freshness: 'live', material_degradations: ['LEAK-DEGRADATION'] },
  attentionItems: [{ title: 'LEAK-TITLE', detail: 'LEAK-LASTACTION: HTTP 401 from internal host' }],
  sourcesSummary: { technical: { failing: 9 } },
});

const BRIEF_TEXT = [
  '<b>☀️ MORNING BRIEF</b>',
  '<i>Stardate 2026-10-15</i>',
  '',
  'Watch for &lt;NRP&gt; &amp; <b>friends</b>.',
  '',
  '',
  'Second paragraph.',
  '',
].join('\n');

const ALERT_ROWS = [
  { id: 'a-1', headline: 'Flood <b>Warning</b> &amp; evacuation', severity: 'Emergency_Warning', issued_at: '2026-10-15T00:30:00+00:00', first_seen_at: '2026-10-15T00:31:00+00:00',
    raw_text: 'LEAK-RAWTEXT', latitude: -37.8, longitude: 144.9, canonical_url: 'https://feed.example/LEAK-URL', description: 'LEAK-DESC' },
  { id: 'a-2', headline: 'Fire danger', severity: 'advice', issued_at: null, first_seen_at: '2026-10-14T20:00:00+00:00', raw_text: 'LEAK-RAWTEXT-2' },
  { id: 'a-3', headline: 'No usable date', severity: 'advice', issued_at: null, first_seen_at: null },
];

const BRIEF_ROW = [{ brief_date: '2026-10-15', generated_at: '2026-10-14T21:00:00+00:00', brief_text: BRIEF_TEXT, health_snapshot: { LEAK: 'HEALTH-SNAPSHOT' }, signals_count: 4 }];

async function call(request = req()) {
  const response = await GET(request);
  return { response, text: await response.text() };
}

function fixture(name: string) {
  return readFileSync(join(FIXTURE_DIR, `${name}.json`), 'utf8');
}

beforeEach(() => {
  vi.clearAllMocks();
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
  process.env.MOBILE_BEARER_READ_ENABLED = 'true';
  process.env.MOBILE_READ_CAPTAIN_USER_ID = CAPTAIN_ID;
  selects = {};
  tables = {
    captains_daily_briefs: { data: BRIEF_ROW, error: null },
    alerts: { data: ALERT_ROWS, error: null },
  };
  getUserMock.mockResolvedValue({ data: { user: { id: CAPTAIN_ID } }, error: null });
  createClientMock.mockReturnValue({ auth: { getUser: getUserMock }, from: builder });
  overviewMock.mockResolvedValue(SUMMARY('DEGRADED', 'HQ is degraded — Technical intelligence coverage may be delayed or incomplete.'));
});

describe('GET /api/integrations/tjr-life/v1/snapshot', () => {
  it('returns the v1 contract for the Captain with private, no-store', async () => {
    const { response, text } = await call();
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('private, no-store');
    const body = JSON.parse(text);
    expect(Object.keys(body)).toEqual(['contract_version', 'generated_at', 'hq_status', 'latest_brief', 'alerts']);
    expect(body.contract_version).toBe('1.1');
    expect(body.hq_status).toEqual({
      generated_at: '2026-10-15T01:00:00.000Z',
      summary: 'HQ is degraded — Technical intelligence coverage may be delayed or incomplete.',
      state: 'degraded',
      error: null,
    });
    expect(body.latest_brief.lines).toEqual([
      '☀️ MORNING BRIEF',
      'Stardate 2026-10-15',
      '',
      'Watch for <NRP> & friends.',
      '',
      'Second paragraph.',
    ]);
    expect(body.latest_brief.brief_date).toBe('2026-10-15');
    expect(body.alerts.items).toEqual([
      { id: 'a-1', headline: 'Flood Warning & evacuation', severity: 'emergency_warning', occurred_at: '2026-10-15T00:30:00.000Z', alert_type: 'other', status: 'unknown', expires_at: null },
      { id: 'a-2', headline: 'Fire danger', severity: 'advice', occurred_at: '2026-10-14T20:00:00.000Z', alert_type: 'other', status: 'unknown', expires_at: null },
    ]);
  });

  it('maps every interpreter posture to a contract state without collapsing attention', async () => {
    for (const [posture, state] of [['NORMAL', 'ok'], ['DEGRADED', 'degraded'], ['ATTENTION', 'attention'], ['UNKNOWN', 'unknown'], ['WEIRD', 'unknown']]) {
      overviewMock.mockResolvedValue(SUMMARY(posture, 'x'));
      expect(JSON.parse((await call()).text).hq_status.state).toBe(state);
    }
  });

  it('contains none of the excluded fields or values', async () => {
    const { text } = await call();
    for (const forbidden of [
      'LEAK', 'HEALTH-SNAPSHOT', 'health_snapshot', 'raw_text', 'latitude', 'longitude', 'canonical_url', 'feed.example',
      'created_by', 'error_message', 'lastAction', 'description', 'signals_count', 'material_degradations', 'attentionItems', 'sourcesSummary',
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it('never selects the excluded columns', async () => {
    await call();
    expect(selects.captains_daily_briefs).toBe('brief_date, generated_at, brief_text');
    expect(selects.alerts).toBe(
      'id, headline, severity, issued_at, first_seen_at, jurisdiction, alert_type, status, expiry, updated_at_src, last_seen_at, alert_sources(source_name)',
    );
    for (const select of Object.values(selects)) {
      expect(select).not.toMatch(/health_snapshot|raw_text|latitude|longitude|canonical_url|description|created_by|\*/);
    }
  });

  it('limits alerts to 20', async () => {
    const limit = vi.fn();
    createClientMock.mockReturnValue({
      auth: { getUser: getUserMock },
      from: (table: string) => {
        const b = builder(table) as Record<string, (...a: unknown[]) => unknown>;
        const original = b.limit;
        b.limit = (n: unknown) => { if (table === 'alerts') limit(n); return original(n); };
        return b;
      },
    });
    await call();
    expect(limit).toHaveBeenCalledWith(20);
  });

  it('isolates a failing section: only that section is {"error":"unavailable"}', async () => {
    overviewMock.mockRejectedValue(new Error('relation "domain_heartbeats_latest" LEAK-DB-TEXT'));
    const { response, text } = await call();
    expect(response.status).toBe(200);
    const body = JSON.parse(text);
    expect(body.hq_status).toEqual({ error: 'unavailable' });
    expect(body.latest_brief.error).toBeNull();
    expect(body.alerts.error).toBeNull();
    expect(text).not.toContain('LEAK-DB-TEXT');

    overviewMock.mockResolvedValue(SUMMARY('NORMAL', 'ok'));
    tables.alerts = { data: null, error: { message: 'permission denied for table alerts LEAK-DB-TEXT', code: '42501' } };
    const second = JSON.parse((await call()).text);
    expect(second.alerts).toEqual({ error: 'unavailable' });
    expect(second.hq_status.error).toBeNull();
    expect(second.latest_brief.error).toBeNull();
  });

  it('answers 200 with three unavailable sections when everything fails', async () => {
    overviewMock.mockRejectedValue(new Error('down'));
    tables.captains_daily_briefs = { data: null, error: { message: 'down' } };
    tables.alerts = { data: null, error: { message: 'down' } };
    const { response, text } = await call();
    expect(response.status).toBe(200);
    const body = JSON.parse(text);
    expect(body.hq_status).toEqual({ error: 'unavailable' });
    expect(body.latest_brief).toEqual({ error: 'unavailable' });
    expect(body.alerts).toEqual({ error: 'unavailable' });
  });

  it('treats a hung section as unavailable after the timeout', async () => {
    vi.useFakeTimers();
    try {
      overviewMock.mockReturnValue(new Promise(() => {}));
      const pending = call();
      await vi.advanceTimersByTimeAsync(8100);
      const body = JSON.parse((await pending).text);
      expect(body.hq_status).toEqual({ error: 'unavailable' });
      expect(body.alerts.error).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('returns an empty brief section when there is no brief yet', async () => {
    tables.captains_daily_briefs = { data: [], error: null };
    expect(JSON.parse((await call()).text).latest_brief).toEqual({ generated_at: null, brief_date: null, lines: [], error: null });
  });

  it('refuses without a valid Captain token, with no data access', async () => {
    expect((await call(req({ token: null }))).response.status).toBe(401);
    getUserMock.mockResolvedValue({ data: { user: { id: 'someone-else' } }, error: null });
    const other = await call();
    expect(other.response.status).toBe(403);
    expect(other.response.headers.get('cache-control')).toBe('private, no-store');
    expect(overviewMock).not.toHaveBeenCalled();
    expect(selects).toEqual({});
  });

  it('is off when the flag is off (kill switch)', async () => {
    process.env.MOBILE_BEARER_READ_ENABLED = 'false';
    const { response } = await call();
    expect(response.status).toBe(403);
    expect(overviewMock).not.toHaveBeenCalled();
  });

  it('exports GET only', async () => {
    const mod = await import('./route');
    expect(Object.keys(mod).filter((k) => /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/.test(k))).toEqual(['GET']);
  });

  it('never logs the token or response content', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}));
    overviewMock.mockRejectedValue(new Error(`bad ${TOKEN}`));
    await call();
    const logged = JSON.stringify(spies.flatMap((s) => s.mock.calls));
    expect(logged).not.toContain(TOKEN);
    expect(logged).toContain('hq_status');
    spies.forEach((s) => s.mockRestore());
  });
});

// ── Shared fixtures ──────────────────────────────────────────────────────────
// The PO copies fixtures/tjr-life-snapshot-v1/*.json byte-for-byte into the iOS
// repo. full, degraded and all-errored are produced by the real builder from
// the inputs below and compared byte-for-byte; regenerate with
// UPDATE_FIXTURES=1 npx vitest run <this file>. unknown-version and
// unknown-keys are hand-authored contract edge cases (checked structurally).
const FIXTURE_NAMES = ['all-errored', 'degraded', 'full', 'malformed-section', 'oversized', 'unknown-keys', 'unknown-version'];
const FIXED = new Date('2026-10-15T02:00:00.000Z');
const pretty = (value: unknown) => `${JSON.stringify(value, null, 2)}\n`;

async function buildFor(scenario: 'full' | 'degraded' | 'all-errored' | 'oversized') {
  const { buildTjrLifeSnapshot } = await import('@/lib/tjrLifeSnapshot');
  const stub = {
    from: (table: string) => builder(table),
  } as never;
  if (scenario === 'full') {
    overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'NORMAL', summary: 'HQ is operating normally', last_updated: '2026-10-15T01:59:30.000Z' } });
    tables = {
      captains_daily_briefs: { data: [{ brief_date: '2026-10-15', generated_at: '2026-10-14T21:00:12.000Z', brief_text: '<b>MORNING BRIEF</b>\n<i>Stardate 2026-10-15</i>\n\n<b>Overnight</b>\nQuiet night. 2 items watched, none escalated.\n\n<b>Today</b>\nBrief at 07:00, review at 12:30.' }], error: null },
      alerts: { data: [
        { id: '6f1c0c1e-0000-4000-8000-000000000001', headline: 'Bushfire Emergency Warning: evacuate now', severity: 'emergency_warning', issued_at: '2026-10-15T01:40:00.000Z' },
        { id: '6f1c0c1e-0000-4000-8000-000000000002', headline: 'Severe thunderstorm warning', severity: 'watch_and_act', issued_at: '2026-10-15T00:10:00.000Z' },
      ], error: null },
    };
  } else if (scenario === 'degraded') {
    overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'ATTENTION', summary: 'HQ needs your attention — Last night\'s self-improvement cycle may not have completed.', last_updated: '2026-10-15T01:59:30.000Z' } });
    tables = { captains_daily_briefs: { data: [], error: null }, alerts: { data: null, error: { message: 'x' } } };
  } else if (scenario === 'oversized') {
    const o = oversizedInputs();
    overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'DEGRADED', summary: o.summary, last_updated: '2026-10-15T01:59:30.000Z' } });
    tables = {
      captains_daily_briefs: { data: [{ brief_date: '2026-10-15', generated_at: '2026-10-14T21:00:12.000Z', brief_text: o.briefText }], error: null },
      alerts: { data: o.alerts, error: null },
    };
  } else {
    overviewMock.mockRejectedValue(new Error('x'));
    tables = { captains_daily_briefs: { data: null, error: { message: 'x' } }, alerts: { data: null, error: { message: 'x' } } };
  }
  return buildTjrLifeSnapshot(stub, FIXED);
}

// Inputs well over every cap, in 3-byte characters, so the per-field caps AND
// the 64 KB total cap both act. Deterministic: no randomness.
function oversizedInputs() {
  const cjk = (n: number) => '漢'.repeat(n);
  const lines = Array.from({ length: 70 }, (_, i) => `<b>${cjk(700)}${i}</b>`);
  const alerts = Array.from({ length: 22 }, (_, i) => ({
    id: `6f1c0c1e-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
    headline: cjk(400),
    severity: i % 5 === 0 ? 'Catastrophic' : 'watch_and_act',
    issued_at: new Date(Date.UTC(2026, 9, 15, 1, 40) - i * 60000).toISOString(),
  }));
  alerts[3].id = 'x'.repeat(80); // over the id cap: dropped
  alerts[5].id = alerts[4].id; // repeated id: dropped
  return { summary: cjk(900), briefText: lines.join('\n'), alerts };
}

describe('allowlist caps (approved by the PO)', () => {
  const ascii = (n: number) => 'a'.repeat(n);

  it('caps hq_status.summary at 400 characters', async () => {
    overviewMock.mockResolvedValue(SUMMARY('NORMAL', ascii(900)));
    const body = JSON.parse((await call()).text);
    expect(body.hq_status.summary.length).toBe(400);
    overviewMock.mockResolvedValue(SUMMARY('NORMAL', ascii(400)));
    expect(JSON.parse((await call()).text).hq_status.summary).toBe(ascii(400));
  });

  it('caps the brief at 40 lines of at most 500 characters, with no trailing paragraph break', async () => {
    tables.captains_daily_briefs = { data: [{ ...BRIEF_ROW[0], brief_text: Array.from({ length: 100 }, (_, i) => `${i}-${ascii(900)}`).join('\n') }], error: null };
    const { lines } = JSON.parse((await call()).text).latest_brief;
    expect(lines.length).toBe(40);
    for (const line of lines) expect(line.length).toBeLessThanOrEqual(500);
    // Exactly 40 and exactly 500 are allowed through unchanged.
    tables.captains_daily_briefs = { data: [{ ...BRIEF_ROW[0], brief_text: Array.from({ length: 40 }, () => ascii(500)).join('\n') }], error: null };
    const exact = JSON.parse((await call()).text).latest_brief.lines;
    expect(exact.length).toBe(40);
    expect(exact.every((l: string) => l === ascii(500))).toBe(true);
    // A paragraph break landing on line 41 must not leave a trailing "".
    tables.captains_daily_briefs = { data: [{ ...BRIEF_ROW[0], brief_text: [...Array.from({ length: 39 }, (_, i) => `l${i}`), 'last', '', 'after'].join('\n') }], error: null };
    const trimmed = JSON.parse((await call()).text).latest_brief.lines;
    expect(trimmed.length).toBe(40);
    expect(trimmed[39]).toBe('last');
  });

  it('caps alert headlines at 160 and ids at 64, and keeps ids unique', async () => {
    tables.alerts = { data: [
      { id: 'ok-1', headline: ascii(500), severity: 'advice', issued_at: '2026-10-15T00:00:00Z' },
      { id: 'i'.repeat(64), headline: 'exactly 64 is kept', severity: 'advice', issued_at: '2026-10-15T00:00:00Z' },
      { id: 'i'.repeat(65), headline: 'dropped: id too long', severity: 'advice', issued_at: '2026-10-15T00:00:00Z' },
      { id: 'ok-1', headline: 'dropped: duplicate id', severity: 'advice', issued_at: '2026-10-15T00:00:00Z' },
    ], error: null };
    const items = JSON.parse((await call()).text).alerts.items;
    expect(items.map((i: { id: string }) => i.id)).toEqual(['ok-1', 'i'.repeat(64)]);
    expect(items[0].headline.length).toBe(160);
    expect(new Set(items.map((i: { id: string }) => i.id)).size).toBe(items.length);
  });

  it('never splits a surrogate pair when truncating', async () => {
    tables.alerts = { data: [{ id: 'e', headline: '😀'.repeat(200), severity: 'advice', issued_at: '2026-10-15T00:00:00Z' }], error: null };
    const { text } = await call();
    const headline: string = JSON.parse(text).alerts.items[0].headline;
    expect(headline.length).toBeLessThanOrEqual(160);
    expect(() => encodeURIComponent(headline)).not.toThrow(); // throws on a lone surrogate
  });

  it('sends severity as exactly one of the four allowed values, else "unknown"', async () => {
    const stored = ['emergency_warning', 'Emergency_Warning', ' WATCH_AND_ACT ', 'advice', 'unknown', 'Catastrophic', 'emergency warning', '', null, 42, 'advice\nextra'];
    tables.alerts = { data: stored.map((severity, n) => ({ id: `s-${n}`, headline: 'h', severity, issued_at: '2026-10-15T00:00:00Z' })), error: null };
    const severities = JSON.parse((await call()).text).alerts.items.map((i: { severity: string }) => i.severity);
    expect(severities).toEqual(['emergency_warning', 'emergency_warning', 'watch_and_act', 'advice', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown']);
    for (const s of severities) expect(['emergency_warning', 'watch_and_act', 'advice', 'unknown']).toContain(s);
  });

  it('keeps the whole response at or under 64 KB even with 3-byte characters', async () => {
    const o = oversizedInputs();
    overviewMock.mockResolvedValue({ captainSummary: { hq_posture: 'DEGRADED', summary: o.summary, last_updated: '2026-10-15T01:59:30.000Z' } });
    tables.captains_daily_briefs = { data: [{ ...BRIEF_ROW[0], brief_text: o.briefText }], error: null };
    tables.alerts = { data: o.alerts, error: null };
    const { response, text } = await call();
    expect(response.status).toBe(200);
    expect(new TextEncoder().encode(text).length).toBeLessThanOrEqual(64 * 1024);
    const body = JSON.parse(text);
    
    // Per-field caps alone would exceed the total, so the cap really acted.
    expect(body.latest_brief.lines.length).toBeLessThan(40);
    expect(body.latest_brief.lines.length).toBeGreaterThan(0);
    expect(body.hq_status.summary.length).toBe(400);
    expect(body.alerts.items.length).toBeGreaterThan(0);
  });

  it('enforceSizeCap sheds sections in order and stays valid when nothing fits', async () => {
    const { enforceSizeCap } = await import('@/lib/tjrLifeSnapshot');
    const huge = Array.from({ length: 40 }, () => '漢'.repeat(500));
    const items = Array.from({ length: 20 }, (_, n) => ({ id: `i${n}`, headline: '漢'.repeat(160), severity: 'advice' as const, occurred_at: '2026-10-15T00:00:00.000Z', alert_type: 'other' as const, status: 'unknown' as const, expires_at: null }));
    const base = {
      contract_version: '1.0', generated_at: '2026-10-15T02:00:00.000Z',
      hq_status: { generated_at: 'x', summary: 's', state: 'ok' as const, error: null },
      latest_brief: { generated_at: null, brief_date: null, lines: huge, error: null },
      alerts: { generated_at: 'x', last_polled_at: null, items, error: null },
    };
    const out = enforceSizeCap(base);
    expect(new TextEncoder().encode(JSON.stringify(out)).length).toBeLessThanOrEqual(64 * 1024);
    expect(out.hq_status).toEqual(base.hq_status); // untouched when shedding brief lines is enough
    expect('lines' in out.latest_brief && out.latest_brief.lines.length).toBeLessThan(40);
    expect('items' in out.alerts && out.alerts.items.length).toBe(20); // alerts kept: brief shed first
    const tooBig = { ...base, hq_status: { ...base.hq_status, summary: '漢'.repeat(30000) } };
    const last = enforceSizeCap(tooBig);
    expect(last.hq_status).toEqual({ error: 'unavailable' });
    expect(new TextEncoder().encode(JSON.stringify(last)).length).toBeLessThanOrEqual(64 * 1024);
  });

  it('refuses an authenticated request with a query string with JSON 400, and 401 first when unauthenticated', async () => {
    const url = 'https://x.test/api/integrations/tjr-life/v1/snapshot?x=1';
    const authed = await GET(new Request(url, { headers: { authorization: `Bearer ${TOKEN}` } }));
    expect(authed.status).toBe(400);
    expect(await authed.text()).toBe('{"error":"invalid_request"}');
    expect(overviewMock).not.toHaveBeenCalled();
    expect((await GET(new Request(url))).status).toBe(401);
  });
});

describe('shared fixtures fixtures/tjr-life-snapshot-v1', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  // v1.0 files are frozen. The builder now emits v1.1, so the three builder
  // fixtures with no shedding are checked by projecting the v1.1 output back
  // to the v1.0 shape (drop the additive keys, version 1.0) and comparing bytes.
  // oversized.json sheds by size, which the larger v1.1 items change, so it is
  // pinned by hash only. Every file is also pinned by the hash recorded in #409.
  const FROZEN_SHA256: Record<string, string> = {
    'all-errored': '65a90f76a95030261deebabcb0b28eb9565f4be96266502f37ac958939400336',
    degraded: '40d19e25fa419a870d82a9fe582d9acf31a5c8aabffa0ada29a2a43123121e69',
    full: 'e909d9b52b419d2d1894773138ce931c9ba19d21ba64426883d49e888ae72127',
    'malformed-section': '291b54adda6756689ecd97b04dfed77aebc71603efecfebecd751ce69b897770',
    oversized: 'b099d2303997ae542f8fe962df3d9c40e3afe028567360aa9897d23a8f6aacec',
    'unknown-keys': 'a83351e2246d54525e1b603d6de3a95ff5183e4f7d6b42132514798dd59a519e',
    'unknown-version': '2823a96e9be70ce085a7db5d8ab31ad40ef2a1fe817d5417512ea0753f318aeb',
  };
  for (const [name, hash] of Object.entries(FROZEN_SHA256)) {
    it(`${name}.json is unchanged from v1.0`, () => {
      expect(createHash('sha256').update(readFileSync(join(FIXTURE_DIR, `${name}.json`))).digest('hex')).toBe(hash);
    });
  }
  for (const name of ['full', 'degraded', 'all-errored'] as const) {
    it(`${name}.json equals the v1.1 builder output projected to v1.0`, async () => {
      const built = (await buildFor(name)) as unknown as Record<string, unknown>;
      const alerts = built.alerts as Record<string, unknown>;
      const projected = {
        ...built,
        contract_version: '1.0',
        alerts: 'items' in alerts
          ? {
              generated_at: alerts.generated_at,
              items: (alerts.items as Record<string, unknown>[]).map(({ id, headline, severity, occurred_at }) => ({ id, headline, severity, occurred_at })),
              error: null,
            }
          : alerts,
      };
      expect(fixture(name)).toBe(pretty(projected));
    });
  }

  it('unknown-version.json carries a contract_version the app must refuse', () => {
    const body = JSON.parse(fixture('unknown-version'));
    expect(body.contract_version).toBe('2.0');
    expect(body.contract_version).not.toBe('1.0');
  });

  it('unknown-keys.json is a valid v1.0 payload with extra keys at every level', () => {
    const body = JSON.parse(fixture('unknown-keys'));
    expect(body.contract_version).toBe('1.0');
    expect(Object.keys(body)).toEqual(expect.arrayContaining(['future_top_level', 'hq_status', 'latest_brief', 'alerts']));
    expect(body.hq_status.future_field).toBeDefined();
    expect(body.latest_brief.future_field).toBeDefined();
    expect(body.alerts.future_field).toBeDefined();
    expect(body.alerts.items[0].future_field).toBeDefined();
  });

  it('malformed-section.json is a v1.0 payload whose sections each break the shape in a different way', () => {
    const body = JSON.parse(fixture('malformed-section'));
    expect(body.contract_version).toBe('1.0');
    // hq_status: right type, wrong state; latest_brief: lines is not an array;
    // alerts: neither a valid section nor {"error":"unavailable"}.
    expect(typeof body.hq_status).toBe('object');
    expect(['ok', 'degraded', 'attention', 'unknown']).not.toContain(body.hq_status.state);
    expect(Array.isArray(body.latest_brief.lines)).toBe(false);
    expect(Array.isArray(body.alerts)).toBe(true);
  });

  it('oversized.json obeys every cap (it is the builder output) and its wire form is within 64 KB', () => {
    const body = JSON.parse(fixture('oversized'));
    expect(new TextEncoder().encode(JSON.stringify(body)).length).toBeLessThanOrEqual(64 * 1024);
    expect(body.hq_status.summary.length).toBeLessThanOrEqual(400);
    expect(body.latest_brief.lines.length).toBeLessThanOrEqual(40);
    for (const l of body.latest_brief.lines) expect(l.length).toBeLessThanOrEqual(500);
    const ids = body.alerts.items.map((i: { id: string }) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const item of body.alerts.items) {
      expect(item.id.length).toBeLessThanOrEqual(64);
      expect(item.headline.length).toBeLessThanOrEqual(160);
      expect(['emergency_warning', 'watch_and_act', 'advice', 'unknown']).toContain(item.severity);
    }
  });

  it('SHA256SUMS lists all seven fixtures and matches the files', () => {
    const lines = readFileSync(join(FIXTURE_DIR, 'SHA256SUMS'), 'utf8').trim().split('\n');
    expect(lines.map((l) => l.split('  ')[1])).toEqual(FIXTURE_NAMES.map((n) => `${n}.json`));
    for (const line of lines) {
      const [hash, file] = line.split('  ');
      expect(createHash('sha256').update(readFileSync(join(FIXTURE_DIR, file))).digest('hex')).toBe(hash);
    }
  });

  it('no fixture contains an excluded field name', () => {
    for (const name of FIXTURE_NAMES) {
      expect(fixture(name)).not.toMatch(/health_snapshot|raw_text|latitude|longitude|canonical_url|created_by|error_message|lastAction/);
    }
  });
});
