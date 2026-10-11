import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));

vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));

import { POST } from '../route';

const captainId = 'captain-user-id';
const validPayload = {
  schema_version: '1.0',
  date: '2026-10-10',
  timezone: 'Australia/Melbourne',
  activity: { steps: 2263 },
};

function request(body?: string, authorization?: string, headers?: Record<string, string>): Request {
  const requestHeaders = new Headers({ 'content-type': 'application/json', ...headers });
  if (authorization !== undefined) requestHeaders.set('authorization', authorization);
  return new Request('https://usstjros.vercel.app/api/integrations/health-bridge/validate', {
    method: 'POST',
    headers: requestHeaders,
    body,
  });
}

describe('POST /api/integrations/health-bridge/validate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID = captainId;
    getUserMock.mockResolvedValue({ data: { user: { id: captainId } }, error: null });
    createClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
  });

  it('requires a bearer token and never calls Supabase without one', async () => {
    const response = await POST(request(JSON.stringify(validPayload)));
    expect(response.status).toBe(401);
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it('rejects an authenticated non-Captain', async () => {
    getUserMock.mockResolvedValueOnce({ data: { user: { id: 'other-user' } }, error: null });
    expect((await POST(request(JSON.stringify(validPayload), 'Bearer valid'))).status).toBe(403);
  });

  it('fails closed on an unexpected authentication failure', async () => {
    getUserMock.mockRejectedValueOnce(new Error('synthetic auth failure with token details'));
    const response = await POST(request(JSON.stringify(validPayload), 'Bearer failing'));
    const body = await response.json();
    expect(response.status).toBe(401);
    expect(body).toEqual({ error: 'Unauthorized' });
  });

  it('fails closed when Captain configuration is missing', async () => {
    delete process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID;
    expect((await POST(request(JSON.stringify(validPayload), 'Bearer valid'))).status).toBe(403);
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it('returns 400 for malformed JSON', async () => {
    expect((await POST(request('{broken', 'Bearer valid'))).status).toBe(400);
  });

  it('returns 413 before parsing an oversized declared payload', async () => {
    expect((await POST(request('', 'Bearer valid', { 'content-length': String(32 * 1024 + 1) }))).status).toBe(413);
  });

  it('returns 422 for schema violations without writing or logging a payload', async () => {
    const response = await POST(request(JSON.stringify({ ...validPayload, email: 'captain@example.com' }), 'Bearer valid'));
    const body = await response.json();
    expect(response.status).toBe(422);
    expect(JSON.stringify(body)).not.toContain('captain@example.com');
    expect(getUserMock).toHaveBeenCalledWith('valid');
  });

  it('returns a deterministic validation result with no storage operation', async () => {
    const first = await POST(request(JSON.stringify(validPayload), 'Bearer valid'));
    const second = await POST(request(JSON.stringify({ activity: { steps: 2263 }, timezone: 'Australia/Melbourne', date: '2026-10-10', schema_version: '1.0' }), 'Bearer valid'));
    const firstBody = await first.json();
    const secondBody = await second.json();
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(firstBody).toEqual({ valid: true, schema_version: '1.0', payload_hash: expect.any(String), storage: 'not_written' });
    expect(firstBody.payload_hash).toBe(secondBody.payload_hash);
    expect(createClientMock).toHaveBeenCalledTimes(2);

    const corrected = await POST(request(JSON.stringify({ ...validPayload, activity: { steps: 2264 } }), 'Bearer valid'));
    const correctedBody = await corrected.json();
    expect(corrected.status).toBe(200);
    expect(correctedBody.payload_hash).not.toBe(firstBody.payload_hash);
  });

  describe('public key configuration', () => {
    const clientKeyArg = () => createClientMock.mock.calls[0][1];

    it('works with the publishable key only', async () => {
      delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_test_key';
      const response = await POST(request(JSON.stringify(validPayload), 'Bearer valid'));
      expect(response.status).toBe(200);
      expect(clientKeyArg()).toBe('sb_publishable_test_key');
    });

    it('works with the legacy anon key only', async () => {
      const response = await POST(request(JSON.stringify(validPayload), 'Bearer valid'));
      expect(response.status).toBe(200);
      expect(clientKeyArg()).toBe('public-anon-key');
    });

    it('prefers the publishable key when both are present', async () => {
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_test_key';
      const response = await POST(request(JSON.stringify(validPayload), 'Bearer valid'));
      expect(response.status).toBe(200);
      expect(clientKeyArg()).toBe('sb_publishable_test_key');
    });

    it.each([
      ['neither key', undefined, undefined],
      ['empty keys', '', '   '],
    ])('fails closed with 503 for %s', async (_label, publishable, anon) => {
      if (publishable === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
      else process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = publishable;
      if (anon === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
      else process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = anon;
      const response = await POST(request(JSON.stringify(validPayload), 'Bearer valid'));
      expect(response.status).toBe(503);
      expect(createClientMock).not.toHaveBeenCalled();
    });
  });

  it('does not expose personal information, tokens, or service-role behavior', async () => {
    const body = await (await POST(request(JSON.stringify(validPayload), 'Bearer synthetic-token'))).json();
    const serialized = JSON.stringify(body);
    expect(serialized).not.toContain('synthetic-token');
    expect(serialized).not.toContain('captain-user-id');
    expect(serialized).not.toContain('email');
    expect(body.storage).toBe('not_written');
    expect(createClientMock).toHaveBeenCalledWith(
      'https://example.supabase.co',
      'public-anon-key',
      expect.objectContaining({ auth: expect.objectContaining({ persistSession: false }) }),
    );
  });
});
