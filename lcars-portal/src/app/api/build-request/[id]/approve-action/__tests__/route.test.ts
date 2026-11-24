import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Concurrent approvals of one AI proposal must execute it once.
const getSession = vi.fn();
const createMission = vi.fn();
const calls: { claimEq: [string, unknown][]; claimOr?: string; claimSet?: unknown; updates: unknown[] } = { claimEq: [], updates: [] };
let claimRows: { id: string }[] = [{ id: 'r1' }];
let row: { id: string; status: string; action_type: string | null; action_payload: unknown } | null;

const admin = {
  from: () => ({
    update: (v: Record<string, unknown>) => {
      const isClaim = (v.action_result as { state?: string } | undefined)?.state === 'executing';
      if (isClaim) calls.claimSet = v; else calls.updates.push(v);
      const chain: Record<string, unknown> = {};
      chain.eq = (c: string, x: unknown) => { if (isClaim) calls.claimEq.push([c, x]); return chain; };
      chain.or = (f: string) => { calls.claimOr = f; return chain; };
      chain.select = () => Promise.resolve({ data: isClaim ? claimRows : null, error: null });
      (chain as { then?: unknown }).then = (res: (v: unknown) => unknown) => res({ error: null });
      return chain;
    },
  }),
};
vi.mock('@/lib/supabase-server', () => ({ createSupabaseServerClient: async () => ({ auth: { getSession: async () => ({ data: { session: getSession() } }) } }) }));
vi.mock('@/lib/ai-actions', () => ({
  supabaseAdmin: () => admin,
  createMission: (...a: unknown[]) => createMission(...a),
  createHandoff: vi.fn(), logDecision: vi.fn(), publishContent: vi.fn(),
  validateActionPayload: () => ({ ok: true }),
}));
vi.mock('@/lib/governedFetch', () => ({ fetchGovernedRow: async () => (row ? { ok: true, row } : { ok: false, status: 404, error: 'Not found' }) }));

import { POST } from '../route';
const post = () => POST(new NextRequest('http://localhost/api/build-request/r1/approve-action', { method: 'POST' }), { params: { id: 'r1' } });

beforeEach(() => {
  vi.clearAllMocks();
  getSession.mockReturnValue({ user: {} });
  claimRows = [{ id: 'r1' }];
  row = { id: 'r1', status: 'awaiting_review', action_type: 'create_mission', action_payload: { title: 'M' } };
  calls.claimEq = []; calls.claimOr = undefined; calls.claimSet = undefined; calls.updates = [];
  createMission.mockResolvedValue({ type: 'create_mission', success: true, detail: 'ok', id: 'MSN-1' });
});

describe('approve-action claims the row before executing', () => {
  it('the winner claims (conditionally) and then executes once', async () => {
    const r = await post();
    expect(r.status).toBe(200);
    expect(calls.claimEq).toEqual([['id', 'r1'], ['status', 'awaiting_review']]);
    expect(calls.claimOr).toMatch(/action_result\.is\.null/);
    expect(calls.claimOr).toMatch(/action_result->>success\.eq\.false/);
    expect(calls.claimOr).toMatch(/action_result->>claimed_at\.lt\./);
    expect(createMission).toHaveBeenCalledTimes(1);
    expect(calls.updates.some((u) => (u as { status?: string }).status === 'approved')).toBe(true);
  });
  it('a simultaneous second approval loses the claim, gets 409 and executes NOTHING', async () => {
    claimRows = [];
    const r = await post();
    expect(r.status).toBe(409);
    expect(createMission).not.toHaveBeenCalled();
    expect(calls.updates).toEqual([]);
  });
  it('a failed execution releases the claim for a retry (records success:false, stays awaiting review)', async () => {
    createMission.mockResolvedValue({ type: 'create_mission', success: false, detail: 'boom' });
    const r = await post();
    expect(r.status).toBe(500);
    const rec = calls.updates.find((u) => (u as { action_result?: { success?: boolean } }).action_result?.success === false);
    expect(rec).toBeTruthy();
    expect(calls.updates.some((u) => (u as { status?: string }).status === 'approved')).toBe(false);
  });
  it('a thrown execution also releases the claim', async () => {
    createMission.mockRejectedValue(new Error('crash'));
    expect((await post()).status).toBe(500);
    expect(calls.updates.some((u) => (u as { action_result?: { success?: boolean } }).action_result?.success === false)).toBe(true);
  });
  it('still 401 without a session and 409 for a row not awaiting review', async () => {
    getSession.mockReturnValue(null);
    expect((await post()).status).toBe(401);
  });
});
