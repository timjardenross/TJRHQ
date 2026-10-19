import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));

import * as routeModule from './route';
import { POST } from './route';

const CAPTAIN_ID = '00000000-0000-4000-8000-00000000c0de';
const TOKEN = 'header.payload.signature-DO-NOT-LOG';
const ID1 = '11111111-1111-4111-8111-111111111111';
const URL_ = 'https://x.test/api/integrations/tjr-life/v1/captures';

let inserted: Array<{ table: string; row: Record<string, unknown> }>;
let dbError: { code: string } | null;
let uniqueOnFirst: boolean;
let serviceClientsBuilt: number;

function serviceClient() {
  return {
    from(table: string) {
      return {
        insert(row: Record<string, unknown>) {
          inserted.push({ table, row });
          if (table === 'audit_events') return Promise.resolve({ error: null });
          return {
            select: () => ({
              maybeSingle: async () => {
                if (dbError) return { data: null, error: dbError };
                if (uniqueOnFirst) return { data: null, error: { code: '23505' } };
                return { data: { id: 'hq-row-1' }, error: null };
              },
            }),
          };
        },
        select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: { id: 'hq-existing' } }) }) }),
      };
    },
  };
}

const validBody = (over: Record<string, unknown> = {}) => ({
  contract_version: 'tjr-life-capture.v1',
  device_id: 'dev-1',
  captures: [{ client_id: ID1, kind: 'task', text: 'Ring the physio', captured_at: '2026-10-19T02:00:00Z' }],
  ...over,
});

function post(body: unknown, init: { token?: string | null; raw?: string } = {}) {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (init.token !== null) headers.authorization = `Bearer ${init.token ?? TOKEN}`;
  return new Request(URL_, { method: 'POST', headers, body: init.raw ?? JSON.stringify(body) });
}

describe('POST /api/integrations/tjr-life/v1/captures', () => {
  const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
    vi.spyOn(console, m).mockImplementation(() => {}),
  );

  beforeEach(() => {
    vi.clearAllMocks();
    inserted = [];
    dbError = null;
    uniqueOnFirst = false;
    serviceClientsBuilt = 0;
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'service-role-secret';
    process.env.MOBILE_WRITE_ENABLED = 'true';
    process.env.MOBILE_WRITE_CAPTAIN_USER_ID = CAPTAIN_ID;
    getUserMock.mockResolvedValue({ data: { user: { id: CAPTAIN_ID } }, error: null });
    createClientMock.mockImplementation((_url: string, key: string) => {
      if (key === 'service-role-secret') { serviceClientsBuilt++; return serviceClient(); }
      return { auth: { getUser: getUserMock } };
    });
  });

  it('exports POST only, so every other method is refused by Next with 405', () => {
    expect(Object.keys(routeModule).filter((k) => ['GET', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].includes(k))).toEqual([]);
  });

  it('accepts a valid capture: 200, private no-store, the server-built row, one audit row', async () => {
    const res = await POST(post(validBody()));
    expect(res.status).toBe(200);
    expect(res.headers.get('Cache-Control')).toBe('private, no-store');
    expect(res.headers.get('Vary')).toBe('Authorization');
    const json = await res.json();
    expect(json.results).toEqual([{ client_id: ID1, status: 'accepted', hq_id: 'hq-row-1' }]);
    expect(typeof json.received_at).toBe('string');
    const captured = inserted.filter((i) => i.table === 'captured_items');
    expect(captured).toHaveLength(1);
    expect(captured[0].row).toMatchObject({ source_type: 'tjr_life_ios', item_type: 'task', raw_text: 'Ring the physio', idempotency_key: `tjr-life:${ID1}` });
    expect(inserted.filter((i) => i.table === 'audit_events')).toHaveLength(1);
  });

  it('accepts the request the iOS app is tested to build, and answers in the shape the app is tested to accept', async () => {
    const dir = join(__dirname, '__fixtures__/capture-v1');
    const requestRaw = readFileSync(join(dir, 'request-two-items.json'), 'utf8');
    const expectedShape = JSON.parse(readFileSync(join(dir, 'response-accepted.json'), 'utf8'));
    const request = JSON.parse(requestRaw);
    // A separate Captain id keeps this request out of the per-user rate window the other tests share.
    const other = '00000000-0000-4000-8000-00000000c0df';
    process.env.MOBILE_WRITE_CAPTAIN_USER_ID = other;
    getUserMock.mockResolvedValue({ data: { user: { id: other } }, error: null });
    const res = await POST(post(null, { raw: requestRaw }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(Object.keys(json).sort()).toEqual(Object.keys(expectedShape).sort());
    expect(Object.keys(json.results[0]).sort()).toEqual(Object.keys(expectedShape.results[0]).sort());
    expect(json.results.map((r: { client_id: string }) => r.client_id)).toEqual(request.captures.map((c: { client_id: string }) => c.client_id));
    expect(json.results.every((r: { status: string }) => r.status === 'accepted')).toBe(true);
    const rows = inserted.filter((i) => i.table === 'captured_items').map((i) => i.row);
    // `commitment` is stored as a task and flagged in summary (owner decision 2026-10-18).
    expect(rows.map((r) => r.item_type)).toEqual(['task', 'task']);
    expect(rows.map((r) => r.summary)).toEqual([null, 'Commitment (captured in TJR Life)']);
    expect(rows.map((r) => r.raw_text)).toEqual(request.captures.map((c: { text: string }) => c.text));
  });

  it('reports a retry as duplicate (200), not an error', async () => {
    uniqueOnFirst = true;
    const res = await POST(post(validBody()));
    expect(res.status).toBe(200);
    expect((await res.json()).results).toEqual([{ client_id: ID1, status: 'duplicate', hq_id: 'hq-existing' }]);
  });

  it('refuses a valid token for a non-Captain with 403 BEFORE any service-role client exists or any write', async () => {
    getUserMock.mockResolvedValue({ data: { user: { id: 'another-valid-user' } }, error: null });
    const res = await POST(post(validBody()));
    expect(res.status).toBe(403);
    expect(serviceClientsBuilt).toBe(0);
    expect(inserted).toEqual([]);
    expect(createClientMock.mock.calls.every((c) => c[1] === 'public-anon-key')).toBe(true);
  });

  it('is closed by default and when the flag is not exactly "true": 403, no writes', async () => {
    process.env.MOBILE_WRITE_ENABLED = 'TRUE';
    expect((await POST(post(validBody()))).status).toBe(403);
    delete process.env.MOBILE_WRITE_ENABLED;
    expect((await POST(post(validBody()))).status).toBe(403);
    expect(serviceClientsBuilt).toBe(0);
    expect(inserted).toEqual([]);
  });

  it('answers 401 with no token and never touches the database', async () => {
    expect((await POST(post(validBody(), { token: null }))).status).toBe(401);
    expect(serviceClientsBuilt).toBe(0);
  });

  it('refuses health and decision captures with 422 and writes nothing', async () => {
    for (const kind of ['health', 'decision']) {
      const res = await POST(post(validBody({ captures: [{ client_id: ID1, kind, text: 'x', captured_at: '2026-10-19T02:00:00Z' }] })));
      expect(res.status).toBe(422);
      expect(await res.json()).toEqual({ error: 'class_not_consented' });
    }
    expect(inserted).toEqual([]);
    expect(serviceClientsBuilt).toBe(0);
  });

  it('refuses malformed JSON and invalid bodies with 400 and writes nothing', async () => {
    expect((await POST(post(null, { raw: '{not json' }))).status).toBe(400);
    expect((await POST(post(validBody({ extra: true })))).status).toBe(400);
    expect((await POST(post(validBody({ captures: [] })))).status).toBe(400);
    expect(inserted).toEqual([]);
    expect(serviceClientsBuilt).toBe(0);
  });

  it('refuses an oversized body with 413 BEFORE JSON parsing', async () => {
    const parseSpy = vi.spyOn(JSON, 'parse');
    const huge = JSON.stringify(validBody({ captures: [{ client_id: ID1, kind: 'note', text: 'x'.repeat(200_000), captured_at: '2026-10-19T02:00:00Z' }] }));
    const res = await POST(post(null, { raw: huge }));
    expect(res.status).toBe(413);
    expect(await res.json()).toEqual({ error: 'too_large' });
    expect(parseSpy.mock.calls.some((c) => typeof c[0] === 'string' && (c[0] as string).length > 100_000)).toBe(false);
    parseSpy.mockRestore();
    expect(inserted).toEqual([]);
  });

  it('answers a database failure with a generic 503 carrying no detail', async () => {
    dbError = { code: '42501' };
    const res = await POST(post(validBody()));
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: 'unavailable' });
  });

  it('answers 503 when the service-role key is missing, without writing', async () => {
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    const res = await POST(post(validBody()));
    expect(res.status).toBe(503);
    expect(inserted).toEqual([]);
  });

  it('never echoes capture text and never logs anything', async () => {
    const res = await POST(post(validBody({ captures: [{ client_id: ID1, kind: 'note', text: 'PRIVATE-CAPTURE-TEXT', captured_at: '2026-10-19T02:00:00Z' }] })));
    expect(JSON.stringify(await res.json())).not.toContain('PRIVATE-CAPTURE-TEXT');
    dbError = { code: 'XX000' };
    const failed = await POST(post(validBody()));
    expect(JSON.stringify(await failed.json())).not.toContain('XX000');
    for (const spy of logSpies) expect(spy).not.toHaveBeenCalled();
  });
});

describe('service-role key scope', () => {
  const SRC = join(__dirname, '../../../../../../');
  function walk(dir: string, out: string[] = []): string[] {
    for (const name of readdirSync(dir)) {
      if (name === 'node_modules' || name === '__tests__' || name.endsWith('.test.ts') || name.endsWith('.test.tsx')) continue;
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p, out);
      else if (/\.(ts|tsx)$/.test(name)) out.push(p);
    }
    return out;
  }
  const files = walk(SRC);

  it('is read by the capture module and by no other TJR Life bearer file', () => {
    const tjrLifeFiles = files.filter((f) => /tjr-life|tjrLife|mobileBearer/.test(f));
    const readers = tjrLifeFiles.filter((f) => readFileSync(f, 'utf8').includes('SUPABASE_SERVICE_ROLE_KEY'));
    expect(readers.map((f) => f.slice(SRC.length))).toEqual(['lib/tjrLifeCaptures.ts']);
  });

  it('is never imported by a client component or a page', () => {
    const importers = files.filter((f) => /from ['"]@\/lib\/tjrLifeCaptures['"]/.test(readFileSync(f, 'utf8')));
    for (const f of importers) {
      const text = readFileSync(f, 'utf8');
      expect(text).not.toMatch(/^['"]use client['"]/m);
      expect(f).toMatch(/app\/api\/.*route\.ts$/);
    }
    expect(importers.map((f) => f.slice(SRC.length))).toEqual(['app/api/integrations/tjr-life/v1/captures/route.ts']);
  });
});
