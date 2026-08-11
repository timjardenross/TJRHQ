import { describe, it, expect, vi, beforeEach } from 'vitest';

const requireSessionMock = vi.fn();
const recordHeartbeatServerSideMock = vi.fn().mockResolvedValue({ ok: true });

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
}));

vi.mock('@/lib/heartbeat', () => ({
  recordHeartbeatServerSide: (...args: unknown[]) => recordHeartbeatServerSideMock(...args),
}));

import { POST } from '../route';

describe('POST /api/captains-log/heartbeat', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    recordHeartbeatServerSideMock.mockClear();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST();
    expect(res.status).toBe(401);
    expect(recordHeartbeatServerSideMock).not.toHaveBeenCalled();
  });

  it('records a heartbeat for captains_log when authenticated', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST();
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(recordHeartbeatServerSideMock).toHaveBeenCalledTimes(1);
    expect(recordHeartbeatServerSideMock).toHaveBeenCalledWith(
      expect.objectContaining({ domainKey: 'captains_log' }),
    );
  });

  it('surfaces ok:false when the heartbeat write itself fails, without throwing', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    recordHeartbeatServerSideMock.mockResolvedValueOnce({ ok: false, error: 'denied' });
    const res = await POST();
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(json.error).toBe('denied');
  });
});
