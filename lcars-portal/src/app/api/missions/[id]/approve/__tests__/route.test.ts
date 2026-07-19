import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// WORKBENCH-REVIEW.md H2/H3 (2026-07-18): approve/reject/submit/route all
// gate on requireSession() and bind the audit actor to session.user.email
// rather than a client-supplied field. These tests lock that contract in
// so a future edit can't silently drop the session check or the actor
// binding without a test failing.

const requireSessionMock = vi.fn();
const missionRow = { mission_id: 'MSN-0100', title: 'Test Mission', status: 'Validated' };
const maybeSingleMock = vi.fn().mockResolvedValue({ data: missionRow, error: null });
const updateEqMock = vi.fn().mockResolvedValue({ error: null });
const fromMock = vi.fn((table: string) => {
  if (table === 'missions') {
    return {
      select: (_cols: string) => ({
        eq: (_col: string, _val: string) => ({ maybeSingle: maybeSingleMock }),
      }),
      update: (_payload: Record<string, unknown>) => ({
        eq: (_col: string, _val: string) => updateEqMock(),
      }),
    };
  }
  throw new Error(`unexpected table ${table}`);
});

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
  createSupabaseServerClient: async () => ({ from: fromMock }),
}));

vi.mock('@/lib/supabase-service-role', () => ({
  createSupabaseServiceRoleClient: () => ({
    from: () => ({ insert: vi.fn().mockResolvedValue({ error: null }) }),
  }),
}));

vi.mock('@/lib/core-events', () => ({
  publishMissionEventServerSide: vi.fn().mockResolvedValue(undefined),
}));

import { POST } from '../route';

function makeRequest(body: Record<string, unknown> = {}) {
  return new NextRequest('http://localhost/api/missions/MSN-0100/approve', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/missions/[id]/approve', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    maybeSingleMock.mockClear();
    updateEqMock.mockClear();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest(), { params: { id: 'MSN-0100' } });
    expect(res.status).toBe(401);
    expect(maybeSingleMock).not.toHaveBeenCalled();
  });

  it('rejects with 401 when the session has no user email', async () => {
    requireSessionMock.mockResolvedValue({ user: {} });
    const res = await POST(makeRequest(), { params: { id: 'MSN-0100' } });
    expect(res.status).toBe(401);
  });

  it('approves and binds the audit actor to session.user.email, not the body', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(
      makeRequest({ owner: 'someone-else@example.com', source: 'UI' }),
      { params: { id: 'MSN-0100' } },
    );
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.owner).toBe('captain@example.com');
    expect(json.new_status).toBe('Approved');
    expect(updateEqMock).toHaveBeenCalled();
  });

  it('returns 404 when the mission does not exist', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    maybeSingleMock.mockResolvedValueOnce({ data: null, error: null });
    const res = await POST(makeRequest(), { params: { id: 'MSN-9999' } });
    expect(res.status).toBe(404);
  });

  it('returns 409 when the mission status is not approval-eligible', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    maybeSingleMock.mockResolvedValueOnce({ data: { ...missionRow, status: 'Approved' }, error: null });
    const res = await POST(makeRequest(), { params: { id: 'MSN-0100' } });
    expect(res.status).toBe(409);
  });
});
