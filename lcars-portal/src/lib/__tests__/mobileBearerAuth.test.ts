import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));

import {
  MOBILE_READ_RATE_LIMIT,
  failureResponse,
  parseBearerToken,
  requireCaptainRead,
} from '../mobileBearerAuth';

const CAPTAIN_ID = '00000000-0000-4000-8000-00000000c0de';
const TOKEN = 'header.payload.signature-DO-NOT-LOG';

function req(authorization?: string) {
  return new Request('https://example.test/api/integrations/tjr-life/v1/snapshot', {
    headers: authorization ? { authorization } : {},
  });
}

describe('requireCaptainRead', () => {
  const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
    vi.spyOn(console, m).mockImplementation(() => {}),
  );

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    process.env.MOBILE_BEARER_READ_ENABLED = 'true';
    process.env.MOBILE_READ_CAPTAIN_USER_ID = CAPTAIN_ID;
    createClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
    getUserMock.mockResolvedValue({ data: { user: { id: CAPTAIN_ID } }, error: null });
  });

  it('accepts the Captain and returns a user-scoped client carrying the bearer token', async () => {
    const result = await requireCaptainRead(req(`Bearer ${TOKEN}`));
    expect(result.ok).toBe(true);
    const [url, key, options] = createClientMock.mock.calls[0];
    expect(url).toBe('https://example.supabase.co');
    expect(key).toBe('public-anon-key');
    expect(options.global.headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(options.auth).toMatchObject({ persistSession: false, autoRefreshToken: false });
  });

  it('refuses a missing or malformed header with 401 before any network call', async () => {
    for (const header of [undefined, 'Bearer', 'Token abc', 'Bearer a b']) {
      const result = await requireCaptainRead(req(header));
      expect(result).toMatchObject({ ok: false, status: 401 });
    }
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('refuses a different user with 403', async () => {
    getUserMock.mockResolvedValue({ data: { user: { id: 'other' } }, error: null });
    expect(await requireCaptainRead(req(`Bearer ${TOKEN}`))).toMatchObject({ ok: false, status: 403 });
  });

  it('fails closed with 403 when the flag is not exactly "true"', async () => {
    process.env.MOBILE_BEARER_READ_ENABLED = 'yes';
    expect(await requireCaptainRead(req(`Bearer ${TOKEN}`))).toMatchObject({ ok: false, status: 403 });
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('fails closed with 403 when the Captain id is unset', async () => {
    delete process.env.MOBILE_READ_CAPTAIN_USER_ID;
    expect(await requireCaptainRead(req(`Bearer ${TOKEN}`))).toMatchObject({ ok: false, status: 403 });
  });

  it('rate limits per Captain at 30 requests a minute with Retry-After', async () => {
    // Own id so earlier tests in this file do not share the counter.
    const id = '11111111-1111-4111-8111-111111111111';
    process.env.MOBILE_READ_CAPTAIN_USER_ID = id;
    getUserMock.mockResolvedValue({ data: { user: { id } }, error: null });
    for (let i = 0; i < MOBILE_READ_RATE_LIMIT; i++) {
      expect((await requireCaptainRead(req(`Bearer ${TOKEN}`))).ok).toBe(true);
    }
    const blocked = await requireCaptainRead(req(`Bearer ${TOKEN}`));
    expect(blocked).toMatchObject({ ok: false, status: 429 });
    const response = failureResponse(blocked as Parameters<typeof failureResponse>[0]);
    expect(response.status).toBe(429);
    expect(response.headers.get('retry-after')).toBe('60');
    expect(response.headers.get('cache-control')).toBe('private, no-store');
  });

  it('does not leak the auth-server error text', async () => {
    getUserMock.mockResolvedValue({
      data: { user: null },
      error: { name: 'AuthApiError', status: 401, message: 'jwt expired: internal detail' },
    });
    const result = await requireCaptainRead(req(`Bearer ${TOKEN}`));
    expect(JSON.stringify(result)).not.toContain('internal detail');
    expect(result).toMatchObject({ ok: false, status: 401, error: 'Unauthorized' });
  });

  it('never logs the token', async () => {
    getUserMock.mockRejectedValueOnce(new Error(`failed ${TOKEN}`));
    await requireCaptainRead(req(`Bearer ${TOKEN}`));
    expect(JSON.stringify(logSpies.flatMap((s) => s.mock.calls))).not.toContain(TOKEN);
  });
});

describe('parseBearerToken', () => {
  it('accepts a well-formed header case-insensitively and rejects the rest', () => {
    expect(parseBearerToken('Bearer abc')).toBe('abc');
    expect(parseBearerToken('bearer abc')).toBe('abc');
    expect(parseBearerToken(null)).toBeNull();
    expect(parseBearerToken('Bearer')).toBeNull();
    expect(parseBearerToken('Bearer a b')).toBeNull();
  });
});

describe('requireSession is untouched', () => {
  it('has no bearer handling and does not import the bearer module', () => {
    const source = readFileSync(join(__dirname, '..', 'supabase-server.ts'), 'utf8');
    expect(source).not.toMatch(/mobileBearerAuth|authorization|bearer/i);
    expect(source).toContain('export async function requireSession()');
  });
});
