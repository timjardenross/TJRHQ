import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: createClientMock,
}));

import { GET } from '../route';

const captainId = 'captain-user-id';

function requestWithAuthorization(value?: string): Request {
  const headers = new Headers();
  if (value !== undefined) headers.set('authorization', value);
  return new Request('https://usstjros.vercel.app/api/integrations/health-bridge/ping', { headers });
}

describe('GET /api/integrations/health-bridge/ping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID = captainId;
    getUserMock.mockResolvedValue({ data: { user: { id: captainId, email: 'captain@example.com' } }, error: null });
    createClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
  });

  it.each([
    ['missing token', undefined],
    ['malformed token', 'Basic not-a-bearer-token'],
  ])('returns 401 for %s', async (_label, authorization) => {
    const response = await GET(requestWithAuthorization(authorization));
    expect(response.status).toBe(401);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it('returns 401 for an expired or otherwise invalid token', async () => {
    getUserMock.mockResolvedValueOnce({ data: { user: null }, error: { message: 'invalid token' } });
    const response = await GET(requestWithAuthorization('Bearer expired-token'));
    expect(response.status).toBe(401);
  });

  it('returns 403 for a valid token belonging to another user', async () => {
    getUserMock.mockResolvedValueOnce({ data: { user: { id: 'other-user-id' } }, error: null });
    const response = await GET(requestWithAuthorization('Bearer valid-token'));
    expect(response.status).toBe(403);
  });

  it('fails closed when the Captain user ID is not configured', async () => {
    delete process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID;
    const response = await GET(requestWithAuthorization('Bearer valid-token'));
    expect(response.status).toBe(403);
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it('returns 200 for the authorized Captain and no personal information', async () => {
    const response = await GET(requestWithAuthorization('Bearer valid-token'));
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body).toEqual({
      ok: true,
      service: 'tjr-hq',
      server_time: expect.any(String),
    });
    expect(body).not.toHaveProperty('user_id');
    expect(body).not.toHaveProperty('email');
    expect(body).not.toHaveProperty('token');
    expect(getUserMock).toHaveBeenCalledWith('valid-token');
  });

  it('denies unexpected authentication failures without logging or exposing details', async () => {
    getUserMock.mockRejectedValueOnce(new Error('token contained secret details'));
    const response = await GET(requestWithAuthorization('Bearer failing-token'));
    const body = await response.json();
    expect(response.status).toBe(401);
    expect(JSON.stringify(body)).not.toContain('secret');
  });

  it('uses only public Supabase configuration and performs no writes', async () => {
    await GET(requestWithAuthorization('Bearer valid-token'));
    expect(createClientMock).toHaveBeenCalledWith(
      'https://example.supabase.co',
      'public-anon-key',
      expect.objectContaining({ auth: expect.objectContaining({ persistSession: false }) }),
    );
    expect(getUserMock).toHaveBeenCalledTimes(1);
  });
});
