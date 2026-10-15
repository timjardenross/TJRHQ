// Bearer-token read access for the TJR Life iOS app (R3 plan, S2a).
//
// The native app cannot use the browser cookie session, so it sends a
// Supabase access token as `Authorization: Bearer`. This module is the one
// place that decides whether such a token may read, and it is used twice:
// once in middleware.ts (so a bad token never reaches a route handler) and
// once inside the route via requireCaptainRead() (defence in depth: a route
// that is ever mounted at a path the middleware does not cover still
// refuses). requireSession() in supabase-server.ts is deliberately NOT
// touched; cookie-session behaviour is unchanged.
//
// Kill switch: MOBILE_BEARER_READ_ENABLED must equal the string "true".
// Anything else (unset, "TRUE", "1") fails closed with 403 from both layers.
// The Captain is identified by MOBILE_READ_CAPTAIN_USER_ID (a separate
// variable from HEALTH_BRIDGE_CAPTAIN_USER_ID so either feature can be
// turned off or re-pointed without touching the other).
//
// Nothing in here logs. The Authorization header, the token and the
// Supabase auth response are never written to any log or response body.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { checkRateLimit } from '@/lib/rateLimit';

/** The complete bearer allowlist. Exact string match on the pathname, GET
 *  only. No wildcard, prefix or regex matching, ever: add a path here only
 *  with a security review (the exact-set test pins it). */
export const MOBILE_BEARER_READ_ROUTES: ReadonlySet<string> = new Set([
  '/api/integrations/tjr-life/v1/snapshot',
]);

export const MOBILE_READ_RATE_LIMIT = 30;
export const MOBILE_READ_RATE_WINDOW_MS = 60_000;

// A Supabase access token is a ~1 KB JWT. Cap well above that so a
// multi-megabyte header cannot be pushed through to the auth server.
const MAX_TOKEN_LENGTH = 4096;

export type MobileReadFailure = {
  ok: false;
  status: 401 | 403 | 429 | 503;
  error: string;
  retryAfterSeconds?: number;
};

export type MobileReadSuccess = {
  ok: true;
  userId: string;
  /** User-scoped client: carries the bearer token, so RLS applies as the
   *  Captain. Never the service-role key. */
  supabase: SupabaseClient;
};

/** Extract the token from a well-formed `Authorization: Bearer <token>`
 *  header; null when absent or malformed. */
export function parseBearerToken(header: string | null): string | null {
  if (!header) return null;
  const match = header.match(/^Bearer\s+(\S+)$/i);
  if (!match) return null;
  return match[1].length <= MAX_TOKEN_LENGTH ? match[1] : null;
}

export function isMobileBearerReadEnabled(): boolean {
  return process.env.MOBILE_BEARER_READ_ENABLED === 'true';
}

/** Standard headers for every response from a bearer-read path. */
export function mobileReadHeaders(extra?: Record<string, string>): Record<string, string> {
  return { 'Cache-Control': 'private, no-store', Vary: 'Authorization', ...extra };
}

export function mobileReadJson(
  body: Record<string, unknown>,
  status: number,
  extraHeaders?: Record<string, string>,
): Response {
  return Response.json(body, { status, headers: mobileReadHeaders(extraHeaders) });
}

export function failureResponse(failure: MobileReadFailure): Response {
  return mobileReadJson(
    { error: failure.error },
    failure.status,
    failure.retryAfterSeconds ? { 'Retry-After': String(failure.retryAfterSeconds) } : undefined,
  );
}

/** Verify `token` belongs to the configured Captain. Does not rate limit
 *  (middleware runs in a different runtime instance from the route, so a
 *  limiter there would be a second, uncoordinated counter). */
export async function verifyCaptainBearer(
  token: string,
): Promise<MobileReadSuccess | MobileReadFailure> {
  if (!isMobileBearerReadEnabled()) {
    return { ok: false, status: 403, error: 'Forbidden' };
  }
  const captainUserId = process.env.MOBILE_READ_CAPTAIN_USER_ID;
  if (!captainUserId) {
    return { ok: false, status: 403, error: 'Forbidden' };
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey) {
    return { ok: false, status: 503, error: 'Service unavailable' };
  }

  try {
    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
        detectSessionInUrl: false,
      },
      global: { headers: { Authorization: `Bearer ${token}` } },
    });
    const { data, error } = await supabase.auth.getUser(token);

    if (error) {
      // A network/5xx failure talking to Supabase Auth is not the client's
      // fault: answer 503 so the app keeps its session and retries, instead
      // of 401 which would make it discard a perfectly good refresh token.
      const status = (error as { status?: number }).status;
      const transient =
        error.name === 'AuthRetryableFetchError' ||
        (typeof status === 'number' && status >= 500);
      return transient
        ? { ok: false, status: 503, error: 'Service unavailable' }
        : { ok: false, status: 401, error: 'Unauthorized' };
    }
    if (!data.user) {
      return { ok: false, status: 401, error: 'Unauthorized' };
    }
    if (data.user.id !== captainUserId) {
      return { ok: false, status: 403, error: 'Forbidden' };
    }
    return { ok: true, userId: data.user.id, supabase };
  } catch {
    // Deliberately no logging: the thrown value can embed request details.
    return { ok: false, status: 503, error: 'Service unavailable' };
  }
}

/**
 * Route-level guard for bearer-read routes. Verifies the token itself
 * (independently of middleware), then applies the per-Captain rate limit.
 * Async by design; callers must `await` it.
 *
 *   const auth = await requireCaptainRead(request);
 *   if (!auth.ok) return failureResponse(auth);
 *   // auth.supabase is user-scoped; RLS applies as the Captain
 */
export async function requireCaptainRead(
  request: Request,
): Promise<MobileReadSuccess | MobileReadFailure> {
  const token = parseBearerToken(request.headers.get('authorization'));
  if (!token) {
    return { ok: false, status: 401, error: 'Unauthorized' };
  }

  const verified = await verifyCaptainBearer(token);
  if (!verified.ok) return verified;

  if (
    !checkRateLimit(
      `mobile-read:${verified.userId}`,
      MOBILE_READ_RATE_LIMIT,
      MOBILE_READ_RATE_WINDOW_MS,
    )
  ) {
    return {
      ok: false,
      status: 429,
      error: 'Too many requests',
      retryAfterSeconds: MOBILE_READ_RATE_WINDOW_MS / 1000,
    };
  }
  return verified;
}
