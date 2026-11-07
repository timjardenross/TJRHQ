import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const requireSessionMock = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireSession: () => requireSessionMock() }));

import { requireSiOwner } from '@/lib/selfImprovementAuth';

const OWNER = 'test-owner-id-0000';   // fake test fixture, not a real user id
const OTHER = 'test-other-id-1111';

describe('requireSiOwner (SEC-01 Option B)', () => {
  const saved = { ...process.env };
  beforeEach(() => { requireSessionMock.mockReset(); process.env.SELF_IMPROVEMENT_OWNER_USER_ID = OWNER; });
  afterEach(() => { process.env = { ...saved }; });

  it('401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const r = await requireSiOwner();
    expect(r?.status).toBe(401);
  });
  it('403 for a valid session that is not the owner', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: OTHER } });
    const r = await requireSiOwner();
    expect(r?.status).toBe(403);
  });
  it('403 (fail closed) when owner env is unset, even for a valid session', async () => {
    delete process.env.SELF_IMPROVEMENT_OWNER_USER_ID;
    requireSessionMock.mockResolvedValue({ user: { id: OWNER } });
    const r = await requireSiOwner();
    expect(r?.status).toBe(403);
  });
  it('403 (fail closed) when owner env is empty', async () => {
    process.env.SELF_IMPROVEMENT_OWNER_USER_ID = '';
    requireSessionMock.mockResolvedValue({ user: { id: '' } });
    const r = await requireSiOwner();
    expect(r?.status).toBe(403);
  });
  it('403 when session has no user id', async () => {
    requireSessionMock.mockResolvedValue({ user: {} });
    const r = await requireSiOwner();
    expect(r?.status).toBe(403);
  });
  it('null (allowed) only for the owner id', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: OWNER } });
    expect(await requireSiOwner()).toBeNull();
  });
});
