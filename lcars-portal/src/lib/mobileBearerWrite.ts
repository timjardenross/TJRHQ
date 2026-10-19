// Bearer-token WRITE access for the TJR Life iOS app (R3 Delivery 2, slice
// D2-1: Quick Capture). Deliberately separate from the read path in
// mobileBearerAuth.ts: write is a new capability with its own kill switch,
// its own Captain-id variable, its own exact-path allowlist and its own rate
// limit. Nothing here widens the read path.
//
// Kill switch: MOBILE_WRITE_ENABLED must equal the string "true". Anything
// else (unset, "TRUE", "1") fails closed with 403 from both layers.
// The Captain is identified by MOBILE_WRITE_CAPTAIN_USER_ID, a variable of its
// own, so write can be turned off or re-pointed without touching read.
//
// Why this guard matters more than the database: live RLS on captured_items
// lets ANY signed-in user read and write every row (policies are `true`), so
// the only control that limits writes to the Captain is this module. The route
// therefore verifies the Captain id before any database call and never takes
// identity from the request body. The insert itself uses a server-side
// service-role client AFTER validation (see lib/tjrLifeCaptures.ts); this
// module never returns a client, only an identity.
//
// Nothing in here logs. The Authorization header, the token, the request body
// and the Supabase auth response are never written to any log or response body.
import { createClient } from '@supabase/supabase-js';
import { checkRateLimit } from '@/lib/rateLimit';
import {
  INVALID_REQUEST,
  hasQueryString,
  mobileReadJson,
  parseBearerToken,
  type MobileReadFailure,
} from '@/lib/mobileBearerAuth';

/** The complete bearer WRITE allowlist. Exact string match on the pathname,
 *  POST only. No wildcard, prefix or regex matching, ever: add a path here
 *  only with a security review (the exact-set test pins it). */
export const MOBILE_BEARER_WRITE_ROUTES: ReadonlySet<string> = new Set([
  '/api/integrations/tjr-life/v1/captures',
]);

export const MOBILE_WRITE_RATE_LIMIT = 10;
export const MOBILE_WRITE_RATE_WINDOW_MS = 60_000;

/** Largest request body accepted (bytes). A full batch (20 x 2,000 characters
 *  of 4-byte text) is far below the 160 KB this would need; ordinary text is a
 *  small fraction. Checked while reading, before any JSON parsing. */
export const MOBILE_WRITE_MAX_BODY_BYTES = 128 * 1024;

export type MobileWriteFailure =
  | MobileReadFailure
  | { ok: false; status: 405 | 413; error: string; allow?: string };

export type MobileWriteIdentity = { ok: true; userId: string };

export function isMobileBearerWriteEnabled(): boolean {
  return process.env.MOBILE_WRITE_ENABLED === 'true';
}

export function writeFailureResponse(failure: MobileWriteFailure): Response {
  const extra: Record<string, string> = {};
  if ('retryAfterSeconds' in failure && failure.retryAfterSeconds) {
    extra['Retry-After'] = String(failure.retryAfterSeconds);
  }
  if ('allow' in failure && failure.allow) extra.Allow = failure.allow;
  return mobileReadJson({ error: failure.error }, failure.status, extra);
}

/** Verify `token` belongs to the configured write Captain. Does not rate limit
 *  (middleware runs in a different runtime instance from the route). */
export async function verifyCaptainWriteBearer(
  token: string,
): Promise<MobileWriteIdentity | MobileReadFailure> {
  if (!isMobileBearerWriteEnabled()) {
    return { ok: false, status: 403, error: 'Forbidden' };
  }
  const captainUserId = process.env.MOBILE_WRITE_CAPTAIN_USER_ID;
  if (!captainUserId) {
    return { ok: false, status: 403, error: 'Forbidden' };
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey) {
    return { ok: false, status: 503, error: 'Service unavailable' };
  }

  try {
    // The anon key plus the caller's token is used ONLY to ask Supabase Auth
    // who the caller is. The service-role key is never used here.
    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
      global: { headers: { Authorization: `Bearer ${token}` } },
    });
    const { data, error } = await supabase.auth.getUser(token);

    if (error) {
      // A network/5xx failure talking to Supabase Auth is not the client's
      // fault: 503 so the app keeps its session and retries (its outbox is
      // idempotent), instead of 401 which would discard a good refresh token.
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
    return { ok: true, userId: data.user.id };
  } catch {
    // Deliberately no logging: the thrown value can embed request details.
    return { ok: false, status: 503, error: 'Service unavailable' };
  }
}

/**
 * Read a request body with a hard byte cap, WITHOUT buffering past the cap
 * and before any JSON parsing. Returns null when the cap is exceeded.
 */
export async function readBodyCapped(request: Request, maxBytes: number): Promise<string | null> {
  const declared = request.headers.get('content-length');
  if (declared !== null) {
    const n = Number(declared);
    if (!Number.isFinite(n) || n < 0 || n > maxBytes) return null;
  }
  if (!request.body) return '';
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      try { await reader.cancel(); } catch { /* ignore */ }
      return null;
    }
    chunks.push(value);
  }
  const all = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) { all.set(c, offset); offset += c.byteLength; }
  return new TextDecoder('utf-8', { fatal: false }).decode(all);
}

/**
 * Route-level guard for bearer-write routes. Verifies the token itself
 * (independently of middleware), the method, the query string and the content
 * type, then applies the per-Captain write rate limit. The Captain check
 * happens before anything else touches the database.
 *
 *   const auth = await requireCaptainWrite(request);
 *   if (!auth.ok) return writeFailureResponse(auth);
 */
export async function requireCaptainWrite(
  request: Request,
): Promise<MobileWriteIdentity | MobileWriteFailure> {
  const token = parseBearerToken(request.headers.get('authorization'));
  if (!token) {
    return { ok: false, status: 401, error: 'Unauthorized' };
  }

  const verified = await verifyCaptainWriteBearer(token);
  if (!verified.ok) return verified;

  // After auth: an unauthenticated caller still gets 401/403 first.
  if (request.method !== 'POST') {
    return { ok: false, status: 405, error: 'Method not allowed', allow: 'POST' };
  }
  if (hasQueryString(request.url)) return INVALID_REQUEST;
  const contentType = request.headers.get('content-type') ?? '';
  if (!/^application\/json(\s*;.*)?$/i.test(contentType)) return INVALID_REQUEST;

  if (
    !checkRateLimit(
      `mobile-write:${verified.userId}`,
      MOBILE_WRITE_RATE_LIMIT,
      MOBILE_WRITE_RATE_WINDOW_MS,
    )
  ) {
    return {
      ok: false,
      status: 429,
      error: 'Too many requests',
      retryAfterSeconds: MOBILE_WRITE_RATE_WINDOW_MS / 1000,
    };
  }
  return verified;
}
