import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// WORKBENCH-REVIEW.md C4 (2026-07-18): daily check-in moved from a direct
// browser Supabase upsert to a governed route with an explicit session
// check. Locks in the 401 gate and the log_date validation.

const requireSessionMock = vi.fn();
const upsertMock = vi.fn().mockResolvedValue({ error: null });
const fromMock = vi.fn(() => ({ upsert: upsertMock }));

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
  createSupabaseServerClient: async () => ({ from: fromMock }),
}));

import { POST } from '../route';

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/human-systems/check-in', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/human-systems/check-in', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    upsertMock.mockClear();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest({ log_date: '2026-07-18' }));
    expect(res.status).toBe(401);
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('rejects with 400 when log_date is missing', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ mood: 'good' }));
    expect(res.status).toBe(400);
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('upserts on log_date conflict and returns ok when authenticated', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ log_date: '2026-07-18', energy: 'high' }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(upsertMock).toHaveBeenCalledWith(
      { log_date: '2026-07-18', energy: 'high' },
      { onConflict: 'log_date' },
    );
  });

  // Manual capture retirement (Captain directive, 2026-08-10): the Medical
  // tab's manual mood-entry field is retired — this route strips `mood`
  // server-side even if a caller still sends it (defense in depth, mirrors
  // pulse/route.ts's identical mood/stress stripping).
  it('strips mood from the payload before upserting, regardless of caller', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ log_date: '2026-07-18', mood: 'good', energy: 'high' }));
    expect(res.status).toBe(200);
    expect(upsertMock).toHaveBeenCalledWith(
      { log_date: '2026-07-18', energy: 'high' },
      { onConflict: 'log_date' },
    );
  });

  it('returns 500 when the write fails', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    upsertMock.mockResolvedValueOnce({ error: { message: 'boom' } });
    const res = await POST(makeRequest({ log_date: '2026-07-18' }));
    expect(res.status).toBe(500);
  });
});
