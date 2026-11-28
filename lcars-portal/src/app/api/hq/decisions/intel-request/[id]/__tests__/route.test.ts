import { NextRequest } from 'next/server';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const requireSession = vi.fn();
const approveAction = vi.fn();
let row: Record<string, unknown> | null;
let updateRows: { id: string }[] = [{ id: 'r1' }];
const seen: { update?: Record<string, unknown>; or?: string; eq: [string, unknown][] } = { eq: [] };
const admin = {
  from: () => ({
    select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: row, error: null }) }) }),
    update: (v: Record<string, unknown>) => {
      seen.update = v;
      const c: Record<string, unknown> = {};
      c.eq = (k: string, x: unknown) => { seen.eq.push([k, x]); return c; };
      c.or = (f: string) => { seen.or = f; return c; };
      c.select = () => Promise.resolve({ data: updateRows, error: null });
      return c;
    },
  }),
};
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
vi.mock('@/lib/ai-actions', () => ({ supabaseAdmin: () => admin }));
vi.mock('@/app/api/build-request/[id]/approve-action/route', () => ({ POST: (...a: unknown[]) => approveAction(...a) }));
import { POST } from '../route';

const call = (b: unknown) => POST(new NextRequest('http://localhost/x', { method: 'POST', body: JSON.stringify(b) }), { params: { id: 'r1' } });
const original = process.env.HQ_WORKBENCH_ENABLED;
const payload = { options: ['Switch', 'Wait'], source: { kind: 'intelligence', id: 'tech:e1', title: 'Outage' } };
beforeEach(() => {
  vi.clearAllMocks(); process.env.HQ_WORKBENCH_ENABLED = 'true'; requireSession.mockResolvedValue({ user: {} });
  row = { id: 'r1', status: 'awaiting_review', source: 'hq-intelligence-decision-request', action_type: 'log_decision', action_payload: payload };
  updateRows = [{ id: 'r1' }]; seen.update = undefined; seen.or = undefined; seen.eq = [];
  approveAction.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
});
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('approve an intelligence decision request with a chosen option', () => {
  it('gates: 404 off, 401 no session, 400 no or unknown option', async () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect((await call({ option: 'Wait' })).status).toBe(404);
    process.env.HQ_WORKBENCH_ENABLED = 'true';
    requireSession.mockResolvedValue(null);
    expect((await call({ option: 'Wait' })).status).toBe(401);
    requireSession.mockResolvedValue({ user: {} });
    expect((await call({})).status).toBe(400);
    expect((await call({ option: 'Something else' })).status).toBe(400);
    expect(approveAction).not.toHaveBeenCalled();
  });
  it('refuses any row that is not an intelligence decision request', async () => {
    row = { ...row!, source: 'lcars-ai-console-proposed' };
    expect((await call({ option: 'Wait' })).status).toBe(409);
    expect(approveAction).not.toHaveBeenCalled();
  });
  it('records the choice only while awaiting review and not while an approval is executing, then delegates to approve-action', async () => {
    const r = await call({ option: 'Wait' });
    expect(r.status).toBe(200);
    expect(seen.eq).toContainEqual(['status', 'awaiting_review']);
    expect(seen.or).toBe('action_result.is.null,action_result->>success.eq.false');
    expect(seen.update).toMatchObject({ action_payload: { chosen_option: 'Wait', decision: 'Wait (re: Outage)' } });
    expect(approveAction).toHaveBeenCalledTimes(1);
  });
  it('a request that is no longer awaiting review is 409 and nothing executes', async () => {
    updateRows = [];
    const r = await call({ option: 'Wait' });
    expect(r.status).toBe(409);
    expect(approveAction).not.toHaveBeenCalled();
  });
});
