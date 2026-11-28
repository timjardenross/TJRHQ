import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Server-side guard for build-request decisions. The update must be ONE
// conditional statement so the database arbitrates between concurrent callers.
const requireSession = vi.fn();
const logActionHistory = vi.fn(async () => {});
let updateRows: { id: string }[] = [{ id: 'r1' }];
let currentRow: { status: string; action_type: string | null } | null = { status: 'approved', action_type: null };
const calls: { update?: unknown; eq: [string, unknown][]; is: [string, unknown][]; ledger?: unknown } = { eq: [], is: [] };

function updateChain() {
  const chain: Record<string, unknown> = {};
  chain.eq = (c: string, v: unknown) => { calls.eq.push([c, v]); return chain; };
  chain.is = (c: string, v: unknown) => { calls.is.push([c, v]); return chain; };
  chain.select = () => Promise.resolve({ data: updateRows, error: null });
  return chain;
}
const fromMock = vi.fn((table: string) => ({
  update: (v: unknown) => { calls.update = v; return updateChain(); },
  select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: currentRow, error: null }) }) }),
  insert: async (v: unknown) => { if (table === 'decide_ledger') calls.ledger = v; return { error: null }; },
}));
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession(), createSupabaseServerClient: async () => ({ from: fromMock }) }));
vi.mock('@/lib/actionHistoryServer', () => ({ logActionHistory: (...a: unknown[]) => logActionHistory(...(a as [])) }));

import { POST } from '../route';

const req = (body: unknown) => new NextRequest('http://localhost/api/hq/decisions/build-request/r1', { method: 'POST', body: JSON.stringify(body) });
const ctx = { params: { id: 'r1' } };
const original = process.env.HQ_WORKBENCH_ENABLED;

beforeEach(() => {
  vi.clearAllMocks();
  process.env.HQ_WORKBENCH_ENABLED = 'true';
  requireSession.mockResolvedValue({ user: { email: 'captain@example.test' } });
  updateRows = [{ id: 'r1' }];
  currentRow = { status: 'approved', action_type: null };
  calls.eq = []; calls.is = []; calls.update = undefined; calls.ledger = undefined;
});
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });
import { afterAll } from 'vitest';

describe('gates', () => {
  it('404 when HQ is disabled, before touching anything', async () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect((await POST(req({ action: 'approve', expectedStatus: 'awaiting_review' }), ctx)).status).toBe(404);
    expect(requireSession).not.toHaveBeenCalled();
    expect(fromMock).not.toHaveBeenCalled();
  });
  it('401 without a session', async () => {
    requireSession.mockResolvedValue(null);
    expect((await POST(req({ action: 'approve', expectedStatus: 'awaiting_review' }), ctx)).status).toBe(401);
    expect(fromMock).not.toHaveBeenCalled();
  });
  it('400 for an unknown action or a status that is not awaiting review', async () => {
    expect((await POST(req({ action: 'delete', expectedStatus: 'awaiting_review' }), ctx)).status).toBe(400);
    expect((await POST(req({ action: 'approve', expectedStatus: 'completed' }), ctx)).status).toBe(400);
    expect((await POST(req({ action: 'approve' }), ctx)).status).toBe(400);
    expect((await POST(req({ action: 'undo', restoreStatus: 'completed' }), ctx)).status).toBe(400);
    expect(fromMock).not.toHaveBeenCalled();
  });
});

describe('one conditional update', () => {
  it('approve changes the row only if it is still in the status the caller saw, and only for a plain build request', async () => {
    const r = await POST(req({ action: 'approve', expectedStatus: 'awaiting_review', question: 'Approve build request "X"?' }), ctx);
    expect(r.status).toBe(200);
    expect(calls.update).toEqual({ status: 'approved' });
    expect(calls.eq).toEqual([['id', 'r1'], ['status', 'awaiting_review']]);
    expect(calls.is).toEqual([['action_type', null]]);
    expect(calls.ledger).toMatchObject({ action: 'approve', source: 'engineering', item_ref: 'r1', undo_available: true, prior_status: 'awaiting_review' });
    expect(logActionHistory).toHaveBeenCalledWith(expect.objectContaining({ action: 'hq.build_request.approve', outcome: 'success', recordId: 'r1' }));
  });
  it('a second, conflicting request changes nothing and gets 409 with the current status', async () => {
    updateRows = [];
    const r = await POST(req({ action: 'approve', expectedStatus: 'awaiting_review' }), ctx);
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({ error: 'already_decided', currentStatus: 'approved' });
    expect(calls.ledger).toBeUndefined();
    expect(logActionHistory).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'cancelled' }));
  });
  it('refuses to approve an AI-proposed action by status flip (it must be executed by approve-action)', async () => {
    updateRows = [];
    currentRow = { status: 'awaiting_review', action_type: 'create_mission' };
    const r = await POST(req({ action: 'approve', expectedStatus: 'awaiting_review' }), ctx);
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({ error: 'wrong_kind' });
  });
  it('404 when the row does not exist', async () => {
    updateRows = []; currentRow = null;
    expect((await POST(req({ action: 'decline', expectedStatus: 'awaiting_review' }), ctx)).status).toBe(404);
  });
  it('decline is conditional too, and is audited without a ledger row (the ledger has no decline action)', async () => {
    const r = await POST(req({ action: 'decline', expectedStatus: 'awaiting_review' }), ctx);
    expect(r.status).toBe(200);
    expect(calls.update).toEqual({ status: 'rejected' });
    expect(calls.eq).toContainEqual(['status', 'awaiting_review']);
    expect(calls.is).toEqual([]);
    expect(calls.ledger).toBeUndefined();
  });
  it('undo only reverses an approval, back to an awaiting status', async () => {
    const r = await POST(req({ action: 'undo', restoreStatus: 'awaiting_review' }), ctx);
    expect(r.status).toBe(200);
    expect(calls.update).toEqual({ status: 'awaiting_review' });
    expect(calls.eq).toEqual([['id', 'r1'], ['status', 'approved']]);
    expect(calls.ledger).toMatchObject({ action: 'undo', undo_available: false });
  });
});
