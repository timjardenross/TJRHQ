import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// WORKBENCH-REVIEW.md C3 (2026-07-18): this route used a bare anon-key
// client with no session check against a table whose own RLS was
// role=public — together a live open data leak. Locks in the 401 gate on
// both GET and POST now that requireSession() + the admin client are used.

const requireSessionMock = vi.fn();
const insertSingleMock = vi.fn().mockResolvedValue({ data: { id: 'sess-1', created_at: '2026-07-18T00:00:00Z' }, error: null });
const insertMock = vi.fn(() => ({ select: () => ({ single: insertSingleMock }) }));
// GET chains .select().order().limit() then optionally .eq() zero or more
// times before being awaited — make every link return the same thenable
// chain object so any call order/count resolves to the same result.
function makeSelectChain() {
  const chain: Record<string, unknown> = {
    order: () => chain,
    limit: () => chain,
    eq: () => chain,
    then: (resolve: (v: { data: unknown[]; error: null }) => unknown) =>
      resolve({ data: [], error: null }),
  };
  return chain;
}
const fromMock = vi.fn(() => ({
  insert: insertMock,
  select: () => makeSelectChain(),
}));

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
}));

vi.mock('@/lib/ai-actions', () => ({
  supabaseAdmin: () => ({ from: fromMock }),
}));

import { POST, GET } from '../route';

function makePostRequest(body: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/advisory-sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

function makeGetRequest(qs = '') {
  return new NextRequest(`http://localhost/api/advisory-sessions${qs}`);
}

describe('POST /api/advisory-sessions', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    insertMock.mockClear();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makePostRequest({ mode: 'consult', question: 'q', response: 'r' }));
    expect(res.status).toBe(401);
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('rejects consult mode with 400 when response is missing', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makePostRequest({ mode: 'consult', question: 'q' }));
    expect(res.status).toBe(400);
  });

  it('saves a consult message when authenticated', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makePostRequest({ mode: 'consult', question: 'q', response: 'r' }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(json.id).toBe('sess-1');
  });
});

describe('GET /api/advisory-sessions', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await GET(makeGetRequest());
    expect(res.status).toBe(401);
  });

  it('returns sessions when authenticated', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await GET(makeGetRequest('?mode=consult'));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.sessions).toEqual([]);
  });
});
