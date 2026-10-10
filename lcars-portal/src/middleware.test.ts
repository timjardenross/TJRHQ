import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

const { createServerClientMock, getUserMock } = vi.hoisted(() => ({
  createServerClientMock: vi.fn(),
  getUserMock: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({ createServerClient: createServerClientMock }));
vi.mock('@/lib/public-site', () => ({ PUBLIC_ROUTE_ALLOWLIST: new Set<string>() }));

import { middleware } from './middleware';

describe('middleware authentication boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'public-anon-key';
    getUserMock.mockResolvedValue({ data: { user: null }, error: null });
    createServerClientMock.mockReturnValue({ auth: { getUser: getUserMock } });
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
