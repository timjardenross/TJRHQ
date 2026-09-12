import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// Redirect-hop SSRF coverage: a plain `redirect: 'follow'` would let a
// page under attacker control return a Location header pointing at a
// private/internal address and have it followed without ever consulting
// the SSRF check. fetchWithValidatedRedirects (route.ts) follows redirects
// manually and re-validates every hop's Location against isSafeUrl /
// rejectPrivateTarget before following it.

const requireSessionMock = vi.fn();
vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
}));

const lookupMock = vi.fn();
vi.mock('node:dns/promises', () => ({
  default: { lookup: (...args: unknown[]) => lookupMock(...args) },
  lookup: (...args: unknown[]) => lookupMock(...args),
}));

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);

import { POST } from '../route';

function makeRequest(url: string) {
  return new NextRequest('http://localhost/api/shopping-list/preview', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

function redirectResponse(location: string) {
  return new Response(null, { status: 302, headers: { Location: location } });
}

function htmlResponse(html: string) {
  return new Response(html, { status: 200, headers: { 'Content-Type': 'text/html' } });
}

describe('POST /api/shopping-list/preview — redirect handling', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    lookupMock.mockReset();
    fetchMock.mockReset();
  });

  it('rejects when a redirect Location resolves to a private address', async () => {
    lookupMock
      .mockResolvedValueOnce([{ address: '93.184.216.34', family: 4 }]) // initial rejectPrivateTarget check on origin host
      .mockResolvedValueOnce([{ address: '169.254.169.254', family: 4 }]); // hop's validateHop check
    fetchMock.mockResolvedValueOnce(redirectResponse('http://internal.attacker.example/steal'));

    const res = await POST(makeRequest('https://example.com/product'));
    expect(res.status).toBe(502);
    const json = await res.json();
    expect(json.error).toMatch(/redirect rejected/i);
    expect(fetchMock).toHaveBeenCalledTimes(1); // never followed the malicious hop
  });

  it('follows a redirect to another safe public host', async () => {
    lookupMock
      .mockResolvedValueOnce([{ address: '93.184.216.34', family: 4 }])
      .mockResolvedValueOnce([{ address: '93.184.216.35', family: 4 }]);
    fetchMock
      .mockResolvedValueOnce(redirectResponse('https://cdn.example.com/product'))
      .mockResolvedValueOnce(htmlResponse('<title>Widget</title>'));

    const res = await POST(makeRequest('https://example.com/product'));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.draft.product_name).toBe('Widget');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('rejects a redirect chain exceeding the hop cap', async () => {
    lookupMock.mockResolvedValue([{ address: '93.184.216.34', family: 4 }]);
    fetchMock.mockImplementation((input: string) => {
      const n = Number(new URL(input).searchParams.get('n') ?? '0');
      return Promise.resolve(redirectResponse(`https://example.com/hop?n=${n + 1}`));
    });

    const res = await POST(makeRequest('https://example.com/hop?n=0'));
    expect(res.status).toBe(502);
    const json = await res.json();
    expect(json.error).toMatch(/too many redirects/i);
  });
});
