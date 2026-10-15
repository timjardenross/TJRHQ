import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
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
      if (m === 'select') selects[table] = String(args[0]);
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
    expect(body.contract_version).toBe('1.0');
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
      { id: 'a-1', headline: 'Flood Warning & evacuation', severity: 'emergency_warning', occurred_at: '2026-10-15T00:30:00.000Z' },
      { id: 'a-2', headline: 'Fire danger', severity: 'advice', occurred_at: '2026-10-14T20:00:00.000Z' },
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
    expect(selects.alerts).toBe('id, headline, severity, issued_at, first_seen_at');
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
const FIXED = new Date('2026-10-15T02:00:00.000Z');
const pretty = (value: unknown) => `${JSON.stringify(value, null, 2)}\n`;

async function buildFor(scenario: 'full' | 'degraded' | 'all-errored') {
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
  } else {
    overviewMock.mockRejectedValue(new Error('x'));
    tables = { captains_daily_briefs: { data: null, error: { message: 'x' } }, alerts: { data: null, error: { message: 'x' } } };
  }
  return buildTjrLifeSnapshot(stub, FIXED);
}

describe('shared fixtures fixtures/tjr-life-snapshot-v1', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  for (const name of ['full', 'degraded', 'all-errored'] as const) {
    it(`${name}.json is byte-identical to the builder output`, async () => {
      const expected = pretty(await buildFor(name));
      if (process.env.UPDATE_FIXTURES) {
        mkdirSync(FIXTURE_DIR, { recursive: true });
        writeFileSync(join(FIXTURE_DIR, `${name}.json`), expected);
      }
      expect(existsSync(join(FIXTURE_DIR, `${name}.json`))).toBe(true);
      expect(fixture(name)).toBe(expected);
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

  it('no fixture contains an excluded field name', () => {
    for (const name of ['full', 'degraded', 'all-errored', 'unknown-version', 'unknown-keys']) {
      expect(fixture(name)).not.toMatch(/health_snapshot|raw_text|latitude|longitude|canonical_url|created_by|error_message|lastAction/);
    }
  });
});
