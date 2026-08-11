import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// physical_readiness_checkins / physical_workout_sessions are written
// client-side before this route is ever called (see the session page's
// handleSubmitCompletion); this route only handles the core_events
// notification and, as of the TS heartbeat port, the domain_heartbeats
// side-channel. Heartbeat must fire only when the notification write
// itself succeeds.

const requireSessionMock = vi.fn();
const publishEventServerSideMock = vi.fn();
const recordHeartbeatServerSideMock = vi.fn().mockResolvedValue({ ok: true });

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
}));

vi.mock('@/lib/core-events', () => ({
  publishEventServerSide: (...args: unknown[]) => publishEventServerSideMock(...args),
}));

vi.mock('@/lib/heartbeat', () => ({
  recordHeartbeatServerSide: (...args: unknown[]) => recordHeartbeatServerSideMock(...args),
}));

import { POST } from '../route';

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/physical-readiness/complete', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/physical-readiness/complete', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    publishEventServerSideMock.mockReset();
    recordHeartbeatServerSideMock.mockClear();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest({ sessionType: 'balanced_strength', metrics: {} }));
    expect(res.status).toBe(401);
    expect(recordHeartbeatServerSideMock).not.toHaveBeenCalled();
  });

  it('rejects with 400 when sessionType or metrics are missing', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ sessionType: 'balanced_strength' }));
    expect(res.status).toBe(400);
    expect(recordHeartbeatServerSideMock).not.toHaveBeenCalled();
  });

  it('records a heartbeat after a successful event publish', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    publishEventServerSideMock.mockResolvedValue({ ok: true });
    const res = await POST(makeRequest({ sessionType: 'balanced_strength', metrics: { duration_minutes: 30 } }));
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(recordHeartbeatServerSideMock).toHaveBeenCalledTimes(1);
    expect(recordHeartbeatServerSideMock).toHaveBeenCalledWith(
      expect.objectContaining({ domainKey: 'physical_readiness' }),
    );
  });

  it('does not record a heartbeat when the event publish fails', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    publishEventServerSideMock.mockResolvedValue({ ok: false, error: 'denied' });
    const res = await POST(makeRequest({ sessionType: 'balanced_strength', metrics: { duration_minutes: 30 } }));
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(recordHeartbeatServerSideMock).not.toHaveBeenCalled();
  });
});
