import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock, getUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));

import {
  MOBILE_BEARER_WRITE_ROUTES,
  MOBILE_WRITE_RATE_LIMIT,
  readBodyCapped,
  requireCaptainWrite,
  verifyCaptainWriteBearer,
  writeFailureResponse,
} from '../mobileBearerWrite';

const CAPTAIN_ID = '00000000-0000-4000-8000-00000000c0de';
const TOKEN = 'header.payload.signature-DO-NOT-LOG';
const URL_ = 'https://example.test/api/integrations/tjr-life/v1/captures';

function req(init: { auth?: string | null; method?: string; url?: string; contentType?: string | null; body?: BodyInit | null } = {}) {
  const headers: Record<string, string> = {};
  if (init.auth !== null) headers.authorization = init.auth ?? `Bearer ${TOKEN}`;
  if (init.contentType !== null) headers['content-type'] = init.contentType ?? 'application/json';
  return new Request(init.url ?? URL_, { method: init.method ?? 'POST', headers, body: init.body ?? '{}' });
}

describe('write allowlist', () => {
  it('is pinned to exactly one path', () => {
    expect([...MOBILE_BEARER_WRITE_ROUTES]).toEqual(['/api/integrations/tjr-life/v1/captures']);
  });
});

describe('requireCaptainWrite', () => {
  const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
    vi.spyOn(console, m).mockImplementation(() => {}),
  );

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    process.env.MOBILE_WRITE_ENABLED = 'true';
    process.env.MOBILE_WRITE_CAPTAIN_USER_ID = CAPTAIN_ID;
    delete process.env.MOBILE_BEARER_READ_ENABLED;
    delete process.env.MOBILE_READ_CAPTAIN_USER_ID;
    createClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
    getUserMock.mockResolvedValue({ data: { user: { id: CAPTAIN_ID } }, error: null });
  });

  it('accepts the Captain and returns an identity, never a client', async () => {
    const result = await requireCaptainWrite(req());
    expect(result).toEqual({ ok: true, userId: CAPTAIN_ID });
    const [url, key] = createClientMock.mock.calls[0];
    expect(url).toBe('https://example.supabase.co');
    expect(key).toBe('public-anon-key');
  });

  it('refuses a missing or malformed header with 401 before any network call', async () => {
    for (const auth of [null, 'Bearer', 'Token abc', 'Bearer a b']) {
      expect(await requireCaptainWrite(req({ auth }))).toMatchObject({ ok: false, status: 401 });
    }
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('refuses a valid token for a different user with 403 (the live RLS lets any signed-in user write)', async () => {
    getUserMock.mockResolvedValue({ data: { user: { id: 'another-valid-user' } }, error: null });
    expect(await requireCaptainWrite(req())).toMatchObject({ ok: false, status: 403, error: 'Forbidden' });
  });

  it('fails closed with 403 unless the write flag is exactly "true"', async () => {
    for (const value of [undefined, '', 'TRUE', '1', 'yes', ' true']) {
      if (value === undefined) delete process.env.MOBILE_WRITE_ENABLED; else process.env.MOBILE_WRITE_ENABLED = value;
      expect(await requireCaptainWrite(req())).toMatchObject({ ok: false, status: 403 });
    }
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('fails closed with 403 when the write Captain id is not configured, and never falls back to the read id', async () => {
    delete process.env.MOBILE_WRITE_CAPTAIN_USER_ID;
    process.env.MOBILE_READ_CAPTAIN_USER_ID = CAPTAIN_ID;
    expect(await requireCaptainWrite(req())).toMatchObject({ ok: false, status: 403 });
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('is not enabled by the read switch, and the write switch does not enable reads', async () => {
    delete process.env.MOBILE_WRITE_ENABLED;
    process.env.MOBILE_BEARER_READ_ENABLED = 'true';
    expect(await verifyCaptainWriteBearer(TOKEN)).toMatchObject({ ok: false, status: 403 });
  });

  it('answers 401 for an invalid token and 503 for an auth outage, with no auth-server detail', async () => {
    getUserMock.mockResolvedValue({ data: { user: null }, error: { name: 'AuthApiError', status: 401, message: 'secret detail' } });
    const bad = await requireCaptainWrite(req());
    expect(bad).toMatchObject({ ok: false, status: 401, error: 'Unauthorized' });
    getUserMock.mockResolvedValue({ data: { user: null }, error: { name: 'AuthRetryableFetchError', status: 0, message: 'x' } });
    expect(await requireCaptainWrite(req())).toMatchObject({ ok: false, status: 503 });
    getUserMock.mockRejectedValue(new Error('network detail'));
    expect(await requireCaptainWrite(req())).toMatchObject({ ok: false, status: 503 });
  });

  it('refuses non-POST with 405 and Allow: POST, only after authentication', async () => {
    const r = await requireCaptainWrite(req({ method: 'PUT', body: null }));
    expect(r).toMatchObject({ ok: false, status: 405 });
    if (!r.ok) expect(writeFailureResponse(r).headers.get('Allow')).toBe('POST');
    getUserMock.mockResolvedValue({ data: { user: { id: 'other' } }, error: null });
    expect(await requireCaptainWrite(req({ method: 'PUT', body: null }))).toMatchObject({ ok: false, status: 403 });
  });

  it('refuses any query string and non-JSON content types with 400, after auth', async () => {
    expect(await requireCaptainWrite(req({ url: `${URL_}?x=1` }))).toMatchObject({ ok: false, status: 400 });
    expect(await requireCaptainWrite(req({ url: `${URL_}?` }))).toMatchObject({ ok: false, status: 400 });
    for (const contentType of ['text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data', null]) {
      expect(await requireCaptainWrite(req({ contentType }))).toMatchObject({ ok: false, status: 400 });
    }
    expect(await requireCaptainWrite(req({ contentType: 'application/json; charset=utf-8' }))).toMatchObject({ ok: true });
  });

  it('rate limits the Captain on the write limiter, separate from the read limiter', async () => {
    let last: Awaited<ReturnType<typeof requireCaptainWrite>> = { ok: true, userId: '' };
    for (let i = 0; i <= MOBILE_WRITE_RATE_LIMIT; i++) last = await requireCaptainWrite(req());
    expect(last).toMatchObject({ ok: false, status: 429, retryAfterSeconds: 60 });
  });

  it('never logs the token or the Authorization header', async () => {
    await requireCaptainWrite(req());
    getUserMock.mockRejectedValue(new Error(`Bearer ${TOKEN}`));
    await requireCaptainWrite(req());
    for (const spy of logSpies) expect(spy).not.toHaveBeenCalled();
  });
});

describe('readBodyCapped', () => {
  const stream = (chunks: string[]) =>
    new ReadableStream<Uint8Array>({
      start(c) { for (const s of chunks) c.enqueue(new TextEncoder().encode(s)); c.close(); },
    });

  it('returns the body when within the cap', async () => {
    expect(await readBodyCapped(new Request(URL_, { method: 'POST', body: '{"a":1}' }), 100)).toBe('{"a":1}');
  });

  it('refuses a declared Content-Length over the cap without reading', async () => {
    const r = new Request(URL_, { method: 'POST', body: 'x'.repeat(50), headers: { 'content-length': '999999' } });
    expect(await readBodyCapped(r, 100)).toBeNull();
  });

  it('stops reading a streamed body that exceeds the cap even with no Content-Length', async () => {
    const r = new Request(URL_, { method: 'POST', body: stream(['x'.repeat(60), 'x'.repeat(60)]), duplex: 'half' } as RequestInit);
    expect(await readBodyCapped(r, 100)).toBeNull();
  });

  it('treats an empty body as an empty string', async () => {
    expect(await readBodyCapped(new Request(URL_, { method: 'POST' }), 100)).toBe('');
  });
});
