import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

const { createServerClientMock, getUserMock, createClientMock, bearerGetUserMock } = vi.hoisted(() => ({
  createServerClientMock: vi.fn(),
  getUserMock: vi.fn(),
  createClientMock: vi.fn(),
  bearerGetUserMock: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({ createServerClient: createServerClientMock }));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));
vi.mock('@/lib/public-site', () => ({ PUBLIC_ROUTE_ALLOWLIST: new Set<string>() }));

import { middleware } from './middleware';
import { MOBILE_BEARER_READ_ROUTES } from '@/lib/mobileBearerAuth';

describe('middleware authentication boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    getUserMock.mockResolvedValue({ data: { user: null }, error: null });
    createServerClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
    createClientMock.mockReturnValue({ auth: { getUser: bearerGetUserMock } });
    bearerGetUserMock.mockResolvedValue({ data: { user: null }, error: { name: 'AuthApiError', status: 401, message: 'secret detail' } });
  });

  it('lets only the Health Bridge route reach its own bearer-auth handler', async () => {
    const response = await middleware(new NextRequest('https://usstjros.vercel.app/api/integrations/health-bridge/ping'));
    expect(response.status).toBe(200);
    expect(createServerClientMock).not.toHaveBeenCalled();
  });

  it('keeps browser redirect behavior for unrelated unauthenticated routes', async () => {
    const response = await middleware(new NextRequest('https://usstjros.vercel.app/api/wellness'));
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('https://usstjros.vercel.app/login');
    expect(createServerClientMock).toHaveBeenCalledTimes(1);
  });
});


const SNAPSHOT = 'https://usstjros.vercel.app/api/integrations/tjr-life/v1/snapshot';
const CAPTAIN_ID = '00000000-0000-4000-8000-00000000c0de';
const TOKEN = 'header.payload.signature-DO-NOT-LOG';

function bearerRequest(url: string, init: { method?: string; authorization?: string | null } = {}) {
  const headers: Record<string, string> = {};
  if (init.authorization !== null) headers.authorization = init.authorization ?? `Bearer ${TOKEN}`;
  return new NextRequest(url, { method: init.method ?? 'GET', headers });
}

describe('middleware bearer read path (TJR Life)', () => {
  const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
    vi.spyOn(console, m).mockImplementation(() => {}),
  );

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    process.env.MOBILE_BEARER_READ_ENABLED = 'true';
    process.env.MOBILE_READ_CAPTAIN_USER_ID = CAPTAIN_ID;
    getUserMock.mockResolvedValue({ data: { user: null }, error: null });
    createServerClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
    createClientMock.mockReturnValue({ auth: { getUser: bearerGetUserMock } });
    bearerGetUserMock.mockResolvedValue({ data: { user: { id: CAPTAIN_ID } }, error: null });
  });

  it('pins the bearer allowlist to exactly one path', () => {
    expect([...MOBILE_BEARER_READ_ROUTES]).toEqual(['/api/integrations/tjr-life/v1/snapshot']);
  });

  it('passes a valid Captain token through to the route', async () => {
    const response = await middleware(bearerRequest(SNAPSHOT));
    expect(response.status).toBe(200);
    expect(response.headers.get('x-middleware-next')).toBe('1');
    expect(bearerGetUserMock).toHaveBeenCalledWith(TOKEN);
    expect(createServerClientMock).not.toHaveBeenCalled();
  });

  it('uses the anon key, never a service-role key, to verify the token', async () => {
    process.env.SUPABASE_SECRET_KEY = 'service-role-secret';
    process.env.SUPABASE_KEY = 'service-role-secret';
    await middleware(bearerRequest(SNAPSHOT));
    expect(createClientMock.mock.calls[0][1]).toBe('public-anon-key');
    expect(JSON.stringify(createClientMock.mock.calls)).not.toContain('service-role-secret');
  });

  it("refuses another user's valid token with 403 JSON", async () => {
    bearerGetUserMock.mockResolvedValue({ data: { user: { id: 'someone-else' } }, error: null });
    const response = await middleware(bearerRequest(SNAPSHOT));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: 'Forbidden' });
  });

  it.each([
    ['missing header', null],
    ['wrong scheme', 'Basic dXNlcjpwYXNz'],
    ['empty token', 'Bearer '],
    ['two tokens', 'Bearer a b'],
    ['oversized token', `Bearer ${'a'.repeat(5000)}`],
  ])('answers %s with 401 JSON, not a redirect', async (_name, authorization) => {
    const response = await middleware(bearerRequest(SNAPSHOT, { authorization }));
    expect(response.status).toBe(401);
    expect(response.headers.get('location')).toBeNull();
    expect(await response.json()).toEqual({ error: 'Unauthorized' });
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('answers an invalid or expired token with 401 and no auth-server detail', async () => {
    bearerGetUserMock.mockResolvedValue({
      data: { user: null },
      error: { name: 'AuthApiError', status: 401, message: 'secret detail' },
    });
    const response = await middleware(bearerRequest(SNAPSHOT));
    expect(response.status).toBe(401);
    const text = await response.text();
    expect(text).toBe('{"error":"Unauthorized"}');
    expect(text).not.toContain('secret detail');
  });

  it('answers an auth-server outage with 503 so the app keeps its session', async () => {
    bearerGetUserMock.mockResolvedValue({
      data: { user: null },
      error: { name: 'AuthRetryableFetchError', status: 0, message: 'fetch failed' },
    });
    expect((await middleware(bearerRequest(SNAPSHOT))).status).toBe(503);
    bearerGetUserMock.mockRejectedValue(new Error('boom'));
    expect((await middleware(bearerRequest(SNAPSHOT))).status).toBe(503);
  });

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('refuses %s with a bearer token', async (method) => {
    const response = await middleware(bearerRequest(SNAPSHOT, { method }));
    expect(response.status).toBe(405);
    expect(response.headers.get('allow')).toBe('GET');
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it.each([undefined, 'false', 'TRUE', '1', ''])('is the kill switch when the flag is %j: 403', async (flag) => {
    if (flag === undefined) delete process.env.MOBILE_BEARER_READ_ENABLED;
    else process.env.MOBILE_BEARER_READ_ENABLED = flag;
    const response = await middleware(bearerRequest(SNAPSHOT));
    expect(response.status).toBe(403);
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('answers 403 when the Captain id is not configured', async () => {
    delete process.env.MOBILE_READ_CAPTAIN_USER_ID;
    const response = await middleware(bearerRequest(SNAPSHOT));
    expect(response.status).toBe(403);
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('sets private, no-store on every bearer-path response', async () => {
    for (const response of [
      await middleware(bearerRequest(SNAPSHOT, { authorization: null })),
      await middleware(bearerRequest(SNAPSHOT, { method: 'POST' })),
    ]) {
      expect(response.headers.get('cache-control')).toBe('private, no-store');
    }
  });

  it.each([
    '/api/integrations/tjr-life/v1/snapshot/',
    '/api/integrations/tjr-life/v1/snapshot/extra',
    '/api/integrations/tjr-life/v1/Snapshot',
    '/api/integrations/tjr-life/v1',
    '/api/integrations/tjr-life/v1/snapshot-other',
    '/api/integrations/tjr-life/v2/snapshot',
    '/api/wellness',
    '/api/captains-daily-brief',
    '/',
  ])('keeps today\'s redirect for a bearer request to %s', async (path) => {
    const response = await middleware(bearerRequest(`https://usstjros.vercel.app${path}`));
    expect(response.status).toBe(307);
    // The clone keeps a trailing slash from the request URL; that quirk is today's behaviour.
    expect(new URL(response.headers.get('location')!).pathname.replace(/\/$/, '')).toBe('/login');
    expect(createServerClientMock).toHaveBeenCalledTimes(1);
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('leaves cookie sessions unchanged on other paths', async () => {
    getUserMock.mockResolvedValue({ data: { user: { id: 'cookie-user' } }, error: null });
    const response = await middleware(new NextRequest('https://usstjros.vercel.app/api/wellness'));
    expect(response.status).toBe(200);
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('still lets the Health Bridge route through untouched', async () => {
    const response = await middleware(
      bearerRequest('https://usstjros.vercel.app/api/integrations/health-bridge/ping'),
    );
    expect(response.status).toBe(200);
    expect(bearerGetUserMock).not.toHaveBeenCalled();
  });

  it('never logs the token or the Authorization header', async () => {
    bearerGetUserMock.mockRejectedValueOnce(new Error(`failed for ${TOKEN}`));
    await middleware(bearerRequest(SNAPSHOT));
    await middleware(bearerRequest(SNAPSHOT, { method: 'POST' }));
    const logged = JSON.stringify(logSpies.flatMap((spy) => spy.mock.calls));
    expect(logged).not.toContain(TOKEN);
    expect(logged.toLowerCase()).not.toContain('bearer');
  });
});
