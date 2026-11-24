import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const requireSession = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
import { GET } from '../route';

const original = process.env.HQ_WORKBENCH_ENABLED;
beforeEach(() => { requireSession.mockResolvedValue({ user: {} }); delete process.env.HQ_WORKBENCH_ENABLED; });
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('/api/hq/status', () => {
  it('reports off by default', async () => { expect(await (await GET()).json()).toEqual({ enabled: false }); });
  it('reports on when the flag is on', async () => { process.env.HQ_WORKBENCH_ENABLED = 'true'; expect(await (await GET()).json()).toEqual({ enabled: true }); });
  it('requires a session', async () => { requireSession.mockResolvedValue(null); expect((await GET()).status).toBe(401); });
});
