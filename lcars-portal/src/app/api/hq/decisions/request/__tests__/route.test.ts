import { NextRequest } from 'next/server';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const requireSession = vi.fn();
const proposeAction = vi.fn();
let existingRow: { id: string; status: string } | null = null;
const admin = { from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: existingRow }) }) }) }) };
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSession() }));
vi.mock('@/lib/ai-actions', () => ({ proposeAction: (...a: unknown[]) => proposeAction(...a), supabaseAdmin: () => admin }));
vi.mock('@/lib/actionHistoryServer', () => ({ logActionHistory: vi.fn(async () => {}) }));
import { POST } from '../route';

const body = { sourceId: 'tech:e1', sourceTitle: 'Outage', question: 'Switch provider?', reason: 'Vendors affected.', options: ['Switch', 'Wait'], recommendation: 'Wait', evidence: [{ label: 'Status page', detail: 'ack' }] };
const req = (b: unknown) => new NextRequest('http://localhost/api/hq/decisions/request', { method: 'POST', body: JSON.stringify(b) });
const original = process.env.HQ_WORKBENCH_ENABLED;
beforeEach(() => { vi.clearAllMocks(); process.env.HQ_WORKBENCH_ENABLED = 'true'; requireSession.mockResolvedValue({ user: {} }); existingRow = null; proposeAction.mockResolvedValue({ type: 'log_decision', success: true, detail: 'ok', id: 'row-1' }); });
afterAll(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('POST /api/hq/decisions/request', () => {
  it('404 when HQ is off; 401 without a session; 400 for an invalid request', async () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect((await POST(req(body))).status).toBe(404);
    process.env.HQ_WORKBENCH_ENABLED = 'true';
    requireSession.mockResolvedValue(null);
    expect((await POST(req(body))).status).toBe(401);
    requireSession.mockResolvedValue({ user: {} });
    expect((await POST(req({ ...body, options: ['one'] }))).status).toBe(400);
    expect(proposeAction).not.toHaveBeenCalled();
  });
  it('creates the request through the existing proposal mechanism, with a deterministic id and the full payload', async () => {
    const r = await POST(req(body));
    expect(r.status).toBe(201);
    const [type, payload, opts] = proposeAction.mock.calls[0];
    expect(type).toBe('log_decision');
    expect(payload).toMatchObject({ rationale: 'Vendors affected.', options: ['Switch', 'Wait'], recommendation: 'Wait', source: { id: 'tech:e1', title: 'Outage' } });
    expect(opts.requestId).toMatch(/^HQ-INTEL-/);
    expect(opts.source).toBe('hq-intelligence-decision-request');
  });
  it('a repeat returns the existing request and creates nothing', async () => {
    existingRow = { id: 'row-0', status: 'awaiting_review' };
    const r = await POST(req(body));
    expect(await r.json()).toMatchObject({ ok: true, existing: true, id: 'row-0' });
    expect(proposeAction).not.toHaveBeenCalled();
  });
  it('a lost race (unique violation) also returns the existing request', async () => {
    proposeAction.mockResolvedValue({ type: 'log_decision', success: false, duplicate: true, detail: 'exists' });
    const r = await POST(req(body));
    expect((await r.json()).existing).toBe(true);
  });
});
