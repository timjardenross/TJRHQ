import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const requireValidatedUserMock = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireValidatedUser: () => requireValidatedUserMock() }));
vi.mock('@/lib/actionHistoryServer', () => ({ logActionHistory: vi.fn(async () => {}) }));

import { GET as findingsGET } from './findings/route';
import { GET as oppsGET } from './opportunities/route';
import { GET as summaryGET } from './evolution-summary/route';
import { GET as missionGET } from './mission-dispatch-status/route';
import { POST as decidePOST } from './decide/route';
import { POST as oppDecidePOST } from './opportunities/decide/route';
import { GET as handoffsGET } from '../engineering-handoffs/route';
import { GET as artifactGET } from '../engineering-handoffs/artifact/route';

const OWNER = '11111111-1111-4111-8111-111111111111';   // fake fixture
const OTHER = '33333333-3333-4333-8333-333333333333';
const SECRET = 'test-secret-value-not-prod';
const reqJson = (body: unknown) => ({ json: async () => body }) as any;
const reqUrl = (u: string) => ({ url: u, nextUrl: new URL(u) }) as any;

const readRoutes: Array<[string, () => Promise<Response>]> = [
  ['findings', () => findingsGET()],
  ['opportunities', () => oppsGET(reqUrl('http://x/api/self-improvement/opportunities'))],
  ['evolution-summary', () => summaryGET()],
  ['mission-dispatch-status', () => missionGET()],
  ['engineering-handoffs', () => handoffsGET(reqUrl('http://x/api/engineering-handoffs'))],
  ['engineering-handoffs/artifact', () => artifactGET(reqUrl('http://x/api/engineering-handoffs/artifact?path=x.md'))],
];
const writeRoutes: Array<[string, () => Promise<Response>]> = [
  ['decide', () => decidePOST(reqJson({ finding_id: 'F1', decision: 'approved' }))],
  ['opportunities/decide', () => oppDecidePOST(reqJson({ opportunity_id: 'EVO-1', decision_type: 'reject' }))],
];

describe('SEC-01 Option B route gate', () => {
  const saved = { ...process.env };
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    requireValidatedUserMock.mockReset();
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = OWNER;
    process.env.SELF_IMPROVEMENT_API_SECRET = SECRET;
    fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { process.env = { ...saved }; vi.unstubAllGlobals(); });

  for (const [name, call] of [...readRoutes, ...writeRoutes]) {
    it(`${name}: no session -> 401, upstream never called`, async () => {
      requireValidatedUserMock.mockResolvedValue(null);
      const res = await call();
      expect(res.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });
    it(`${name}: non-owner session -> 403, upstream never called`, async () => {
      requireValidatedUserMock.mockResolvedValue({ id: OTHER });
      const res = await call();
      expect(res.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    });
    it(`${name}: owner -> upstream called with the secret header`, async () => {
      requireValidatedUserMock.mockResolvedValue({ id: OWNER });
      const res = await call();
      expect(res.status).toBe(200);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const init = fetchMock.mock.calls[0][1] as RequestInit;
      expect((init.headers as Record<string, string>)['X-Self-Improvement-Secret']).toBe(SECRET);
    });
  }

  it('production with secret unset -> 502, upstream never called (fail closed)', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OWNER });
    delete process.env.SELF_IMPROVEMENT_API_SECRET;
    (process.env as any).NODE_ENV = 'production';
    const res = await findingsGET();
    (process.env as any).NODE_ENV = 'test';
    expect(res.status).toBe(502);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // Both owner identities get identical access on every protected route.
  const SECOND_OWNER = '22222222-2222-4222-8222-222222222222';
  for (const [name, call] of [...readRoutes, ...writeRoutes]) {
    it(`${name}: second authorised UUID -> allowed, upstream called`, async () => {
      process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = `${OWNER},${SECOND_OWNER}`;
      requireValidatedUserMock.mockResolvedValue({ id: SECOND_OWNER });
      const res = await call();
      expect(res.status).toBe(200);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    it(`${name}: excluded third UUID with both owners configured -> 403, no upstream`, async () => {
      process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = `${OWNER},${SECOND_OWNER}`;
      requireValidatedUserMock.mockResolvedValue({ id: OTHER });
      const res = await call();
      expect(res.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }
});
