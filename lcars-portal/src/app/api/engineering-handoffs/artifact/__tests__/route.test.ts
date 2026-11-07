import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// 2026-09-07: this proxy used to swallow a non-JSON upstream body into the
// bare string "bad upstream response" with no way to tell what actually
// failed. This endpoint is Caddy-fronted on the VM (see selfImprovementApi.ts),
// so a real Caddy 502/504 page (backend down/restarting/timed out) and every
// other failure all rendered identically — confirmed live: the Captain saw
// exactly that generic text.
const requireValidatedUserMock = vi.fn();

// Synthetic test fixture, not a real user id.
const OWNER_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_ID = '33333333-3333-4333-8333-333333333333';
const ownerSession = () => ({ id: OWNER_ID });

vi.mock('@/lib/supabase-server', () => ({
  requireValidatedUser: () => requireValidatedUserMock(),
}));

vi.mock('@/lib/selfImprovementApi', () => ({
  selfImprovementApiUrl: () => 'http://self-improvement.test',
  selfImprovementHeaders: () => ({}),
}));

import { GET } from '../route';

function makeRequest(path?: string) {
  const url = path
    ? `http://localhost/api/engineering-handoffs/artifact?path=${encodeURIComponent(path)}`
    : 'http://localhost/api/engineering-handoffs/artifact';
  return { nextUrl: new URL(url) } as unknown as Parameters<typeof GET>[0];
}

describe('GET /api/engineering-handoffs/artifact', () => {
  const savedOwner = process.env.SELF_IMPROVEMENT_OWNER_USER_IDS;
  beforeEach(() => {
    requireValidatedUserMock.mockReset();
    vi.restoreAllMocks();
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = OWNER_ID;
  });
  afterEach(() => {
    if (savedOwner === undefined) delete process.env.SELF_IMPROVEMENT_OWNER_USER_IDS;
    else process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = savedOwner;
  });

  it('rejects with 401 when there is no session', async () => {
    requireValidatedUserMock.mockResolvedValue(null);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(401);
  });

  it("rejects with 400 when 'path' is missing", async () => {
    requireValidatedUserMock.mockResolvedValue(ownerSession());
    const res = await GET(makeRequest());
    expect(res.status).toBe(400);
  });

  it('forwards a valid JSON body from the backend unchanged', async () => {
    requireValidatedUserMock.mockResolvedValue(ownerSession());
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 200,
        text: async () => JSON.stringify({ path: 'x.md', content: 'diff content' }),
      }),
    );
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.content).toBe('diff content');
  });

  it('surfaces the real status and a body snippet instead of a bare "bad upstream response" when the backend body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn());
    requireValidatedUserMock.mockResolvedValue(ownerSession());
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 502,
      text: async () => '<html>502 Bad Gateway</html>',
    });
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    const body = await res.json();
    expect(res.status).toBe(502);
    expect(body.error).toContain('502');
    expect(body.detail).toContain('502 Bad Gateway');
  });

  it('reports self_improvement_unreachable when the fetch itself throws', async () => {
    requireValidatedUserMock.mockResolvedValue(ownerSession());
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    const body = await res.json();
    expect(res.status).toBe(502);
    expect(body.error).toBe('self_improvement_unreachable');
  });

  it('rejects with 403 for a valid session that is not the owner, and never calls the backend', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OTHER_ID });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('rejects with 403 (fail closed) when the owner env is unset, even for a valid owner session', async () => {
    delete process.env.SELF_IMPROVEMENT_OWNER_USER_IDS;
    requireValidatedUserMock.mockResolvedValue(ownerSession());
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
