import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

const requireSession = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
import { GET } from '../route';

const origFlag = process.env.HQ_WORKBENCH_ENABLED;
const origTok = process.env.NOTION_TOKEN;
const fetchMock = vi.fn();
const req = (q = 'roadmap') => new NextRequest(`http://localhost/api/hq/notion-search?q=${encodeURIComponent(q)}`);
const page = (title: string, id = title) => ({ object: 'page', url: `https://notion.so/${id.replace(/\W/g, '')}`, last_edited_time: '2026-11-01T00:00:00Z', properties: { Name: { type: 'title', title: [{ plain_text: title }] } } });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', fetchMock);
  process.env.HQ_WORKBENCH_ENABLED = 'true';
  process.env.NOTION_TOKEN = 'secret_test_token';
  requireSession.mockResolvedValue({ user: {} });
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({ results: [page('Roadmap 2027')] }) });
});
afterAll(() => {
  vi.unstubAllGlobals();
  if (origFlag === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = origFlag;
  if (origTok === undefined) delete process.env.NOTION_TOKEN; else process.env.NOTION_TOKEN = origTok;
});

describe('/api/hq/notion-search', () => {
  it('404 when HQ is off', async () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect((await GET(req())).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('401 without a session', async () => {
    requireSession.mockResolvedValue(null);
    expect((await GET(req())).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('reports configured:false with 200 and no call when the token is unset', async () => {
    delete process.env.NOTION_TOKEN;
    const r = await GET(req());
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ configured: false, results: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('maps results to title, url, last_edited_time, object only; one read-only search call', async () => {
    const r = await GET(req('x'.repeat(500)));
    const j = await r.json();
    expect(j).toEqual({ configured: true, results: [{ title: 'Roadmap 2027', url: 'https://notion.so/Roadmap2027', last_edited_time: '2026-11-01T00:00:00Z', object: 'page' }] });
    expect(JSON.stringify(j)).not.toContain('secret_test_token');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.notion.com/v1/search');
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body);
    expect(body.page_size).toBeLessThanOrEqual(10);
    expect(body.query.length).toBe(200);
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
  it('drops personal-health, Pain Recovery Studio and TJR Life titles', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ results: [page('Pain Recovery Studio plan'), page('TJR Life notes'), page('Sleep: 5 hours log'), page('Board pack')] }) });
    const j = await (await GET(req())).json();
    expect(j.results.map((x: { title: string }) => x.title)).toEqual(['Board pack']);
  });
  it('returns a safe 502 on an upstream error', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401, json: async () => ({ message: 'secret_test_token invalid' }) });
    const r = await GET(req());
    expect(r.status).toBe(502);
    expect(JSON.stringify(await r.json())).not.toContain('secret_test_token');
  });
  it('returns a safe 502 on timeout / network failure', async () => {
    fetchMock.mockRejectedValue(Object.assign(new Error('aborted secret_test_token'), { name: 'AbortError' }));
    const r = await GET(req());
    expect(r.status).toBe(502);
    expect(await r.json()).toEqual({ configured: true, results: [], error: 'notion_unavailable' });
  });
});
