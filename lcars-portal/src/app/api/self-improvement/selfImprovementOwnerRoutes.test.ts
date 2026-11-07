import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const requireSessionMock = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSessionMock() }));
vi.mock('@/lib/actionHistoryServer', () => ({ logActionHistory: vi.fn(async () => {}) }));

import { GET as findingsGET } from './findings/route';
import { GET as oppsGET } from './opportunities/route';
import { GET as summaryGET } from './evolution-summary/route';
import { GET as missionGET } from './mission-dispatch-status/route';
import { POST as decidePOST } from './decide/route';
import { POST as oppDecidePOST } from './opportunities/decide/route';
import { GET as handoffsGET } from '../engineering-handoffs/route';
import { GET as artifactGET } from '../engineering-handoffs/artifact/route';

const OWNER = 'test-owner-id-0000';   // fake fixture
const OTHER = 'test-other-id-1111';
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
    requireSessionMock.mockReset();
    process.env.SELF_IMPROVEMENT_OWNER_USER_ID = OWNER;
    process.env.SELF_IMPROVEMENT_API_SECRET = SECRET;
    fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { process.env = { ...saved }; vi.unstubAllGlobals(); });

  for (const [name, call] of [...readRoutes, ...writeRoutes]) {
    it(`${name}: no session -> 401, upstream never called`, async () => {
      requireSessionMock.mockResolvedValue(null);
      const res = await call();
      expect(res.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });
    it(`${name}: non-owner session -> 403, upstream never called`, async () => {
      requireSessionMock.mockResolvedValue({ user: { id: OTHER } });
      const res = await call();
      expect(res.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    });
    it(`${name}: owner -> upstream called with the secret header`, async () => {
      requireSessionMock.mockResolvedValue({ user: { id: OWNER } });
      const res = await call();
      expect(res.status).toBe(200);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const init = fetchMock.mock.calls[0][1] as RequestInit;
      expect((init.headers as Record<string, string>)['X-Self-Improvement-Secret']).toBe(SECRET);
    });
  }

  it('production with secret unset -> 502, upstream never called (fail closed)', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: OWNER } });
    delete process.env.SELF_IMPROVEMENT_API_SECRET;
    (process.env as any).NODE_ENV = 'production';
    const res = await findingsGET();
    (process.env as any).NODE_ENV = 'test';
    expect(res.status).toBe(502);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
