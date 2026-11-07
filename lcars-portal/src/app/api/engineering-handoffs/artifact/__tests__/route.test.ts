import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// 2026-09-07: this proxy used to swallow a non-JSON upstream body into the
// bare string "bad upstream response" with no way to tell what actually
// failed. This endpoint is Caddy-fronted on the VM (see selfImprovementApi.ts),
// so a real Caddy 502/504 page (backend down/restarting/timed out) and every
// other failure all rendered identically — confirmed live: the Captain saw
// exactly that generic text.
const requireSessionMock = vi.fn();

// Synthetic test fixture, not a real user id.
const OWNER_ID = 'test-owner-0000-0000-0000-000000000000';
const OTHER_ID = 'test-other-1111-1111-1111-111111111111';
const ownerSession = () => ({ user: { id: OWNER_ID, email: 'captain@example.com' } });

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
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
  const savedOwner = process.env.SELF_IMPROVEMENT_OWNER_USER_ID;
  beforeEach(() => {
    requireSessionMock.mockReset();
    vi.restoreAllMocks();
    process.env.SELF_IMPROVEMENT_OWNER_USER_ID = OWNER_ID;
  });
  afterEach(() => {
    if (savedOwner === undefined) delete process.env.SELF_IMPROVEMENT_OWNER_USER_ID;
    else process.env.SELF_IMPROVEMENT_OWNER_USER_ID = savedOwner;
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(401);
  });

  it("rejects with 400 when 'path' is missing", async () => {
    requireSessionMock.mockResolvedValue(ownerSession());
    const res = await GET(makeRequest());
    expect(res.status).toBe(400);
  });

  it('forwards a valid JSON body from the backend unchanged', async () => {
    requireSessionMock.mockResolvedValue(ownerSession());
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
    requireSessionMock.mockResolvedValue(ownerSession());
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
    requireSessionMock.mockResolvedValue(ownerSession());
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    const body = await res.json();
    expect(res.status).toBe(502);
    expect(body.error).toBe('self_improvement_unreachable');
  });

  it('rejects with 403 for a valid session that is not the owner, and never calls the backend', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: OTHER_ID, email: 'other@example.com' } });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('rejects with 403 (fail closed) when the owner env is unset, even for a valid owner session', async () => {
    delete process.env.SELF_IMPROVEMENT_OWNER_USER_ID;
    requireSessionMock.mockResolvedValue(ownerSession());
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
