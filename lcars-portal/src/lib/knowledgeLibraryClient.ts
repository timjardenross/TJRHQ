'use client';

// The auth middleware redirects unauthenticated requests to /login (HTML,
// status 200) rather than returning a 401 — including for /api/* routes.
// A plain fetch() follows that redirect transparently, so `resp.ok` is
// true and the body is an HTML page, not JSON. Every call site needs to
// detect this and show "please sign in again" instead of either silently
// showing an empty list or crashing on `resp.json()` parsing HTML.
export class ApiAuthError extends Error {}

export async function fetchJson(input: string, init?: RequestInit): Promise<any> {
  const resp = await fetch(input, init);
  if (resp.redirected && resp.url.includes('/login')) {
    throw new ApiAuthError('Your session has expired. Please sign in again.');
  }
  let data: unknown = null;
  try {
    data = await resp.json();
  } catch {
    throw new Error(`Unexpected response from server (status ${resp.status}).`);
  }
  if (!resp.ok) {
    const body = data as { error?: string; detail?: string } | null;
    throw new Error(body?.error ?? body?.detail ?? `Request failed (status ${resp.status}).`);
  }
  return data;
}
