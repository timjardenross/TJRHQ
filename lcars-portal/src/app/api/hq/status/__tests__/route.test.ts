import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const requireSession = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
import { GET } from '../route';

const original = process.env.HQ_WORKBENCH_ENABLED;
beforeEach(() => { requireSession.mockResolvedValue({ user: {} }); delete process.env.HQ_WORKBENCH_ENABLED; delete process.env.NOTION_TOKEN; });
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('/api/hq/status', () => {
  it('reports off by default', async () => { expect(await (await GET()).json()).toEqual({ enabled: false, notionConfigured: false }); });
  it('reports on when the flag is on', async () => { process.env.HQ_WORKBENCH_ENABLED = 'true'; expect(await (await GET()).json()).toEqual({ enabled: true, notionConfigured: false }); });
  it('reports notionConfigured as a boolean only', async () => {
    process.env.NOTION_TOKEN = 'secret_x';
    const t = JSON.stringify(await (await GET()).json());
    delete process.env.NOTION_TOKEN;
    expect(t).toContain('"notionConfigured":true');
    expect(t).not.toContain('secret_x');
  });
  it('requires a session', async () => { requireSession.mockResolvedValue(null); expect((await GET()).status).toBe(401); });
});
