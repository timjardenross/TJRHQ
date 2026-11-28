import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const requireSession = vi.fn();
const upstream = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
vi.mock('@/app/api/weekly-review/route', () => ({ GET: () => upstream() }));
import { GET } from '../route';

const original = process.env.HQ_WORKBENCH_ENABLED;
beforeEach(() => {
  vi.clearAllMocks(); process.env.HQ_WORKBENCH_ENABLED = 'true'; requireSession.mockResolvedValue({ user: {} });
  upstream.mockResolvedValue({ ok: true, json: async () => ({ summary: {}, workbenches: [{ key: 'ready-room', title: 'Ready Room', signals: [{ key: 'a', label: 'a', count: 3, tone: 'warn', items: [{ id: '1', title: 'Private task' }] }] }], synthesis: { weekInReview: { narrative: 'Ready Room private text' } } }) });
});
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('/api/hq/weekly-review', () => {
  it('404 when HQ is off, without calling the existing review', async () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect((await GET()).status).toBe(404);
    expect(upstream).not.toHaveBeenCalled();
  });
  it('401 without a session', async () => {
    requireSession.mockResolvedValue(null);
    expect((await GET()).status).toBe(401);
    expect(upstream).not.toHaveBeenCalled();
  });
  it('never returns personal sections or the narrative', async () => {
    const text = JSON.stringify(await (await GET()).json());
    expect(text).not.toContain('Private task');
    expect(text).not.toContain('private text');
  });
  it('502 when the existing review fails', async () => {
    upstream.mockResolvedValue({ ok: false, json: async () => ({}) });
    expect((await GET()).status).toBe(502);
  });
});
