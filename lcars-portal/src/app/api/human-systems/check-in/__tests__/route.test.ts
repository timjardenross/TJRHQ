import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// Retirement (2026-08-22): the Medical-tab manual daily check-in is retired
// in favour of the Telegram bot's capacity_checkins flow — this route now
// only ever returns 401 (no session) or 410 Gone, never writes anything.
// Locks in that it stays a pure no-write endpoint.

const requireSessionMock = vi.fn();

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
}));

import { POST } from '../route';

function makeRequest(body: Record<string, unknown> = {}) {
  return new NextRequest('http://localhost/api/human-systems/check-in', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/human-systems/check-in (retired)', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest({ log_date: '2026-08-22' }));
    expect(res.status).toBe(401);
  });

  it('returns 410 Gone when authenticated, pointing at the Telegram bot', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ log_date: '2026-08-22', energy: 'high' }));
    expect(res.status).toBe(410);
    const json = await res.json();
    expect(json.error).toMatch(/capacity/i);
  });
});
