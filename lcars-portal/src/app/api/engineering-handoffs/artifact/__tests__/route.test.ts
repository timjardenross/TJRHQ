import { describe, it, expect, vi, beforeEach } from 'vitest';

// 2026-09-07: this proxy used to swallow a non-JSON upstream body into the
// bare string "bad upstream response" with no way to tell what actually
// failed. This endpoint is Caddy-fronted on the VM (see selfImprovementApi.ts),
// so a real Caddy 502/504 page (backend down/restarting/timed out) and every
// other failure all rendered identically — confirmed live: the Captain saw
// exactly that generic text.
const requireSessionMock = vi.fn();

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
  beforeEach(() => {
    requireSessionMock.mockReset();
    vi.restoreAllMocks();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    expect(res.status).toBe(401);
  });

  it("rejects with 400 when 'path' is missing", async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await GET(makeRequest());
    expect(res.status).toBe(400);
  });

  it('forwards a valid JSON body from the backend unchanged', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
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
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
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
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    const res = await GET(makeRequest('Missions/Engineering-Handoffs/artifacts/x.md'));
    const body = await res.json();
    expect(res.status).toBe(502);
    expect(body.error).toBe('self_improvement_unreachable');
  });
});
