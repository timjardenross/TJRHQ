import { NextResponse } from 'next/server';
import { requireValidatedUser } from '@/lib/supabase-server';

/**
 * SEC-01 Option B: single-owner gate for self-improvement and engineering-handoff routes.
 *
 * Authorisation uses the server-validated Supabase user (getUser), never the cookie-backed
 * session. The user id must be one of the entries in SELF_IMPROVEMENT_OWNER_USER_IDS, a
 * comma-separated list of Supabase Auth UUIDs. The list is parsed strictly: anything missing,
 * empty, malformed or duplicated fails closed (403) for every user.
 * Returns null when allowed, otherwise the response to return before any upstream call.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type OwnerAllowlist =
  | { ok: true; ids: readonly string[] }
  | { ok: false; reason: 'unset' | 'empty-entry' | 'malformed' | 'duplicate' };

/** Strict parse of SELF_IMPROVEMENT_OWNER_USER_IDS. No trimming: whitespace is malformed. */
export function parseOwnerAllowlist(raw: string | undefined): OwnerAllowlist {
  if (raw === undefined) return { ok: false, reason: 'unset' };
  const parts = raw.split(',');
  if (parts.some((p) => p === '')) return { ok: false, reason: 'empty-entry' };
  if (parts.some((p) => !UUID_RE.test(p))) return { ok: false, reason: 'malformed' };
  const ids = parts.map((p) => p.toLowerCase());
  if (new Set(ids).size !== ids.length) return { ok: false, reason: 'duplicate' };
  return { ok: true, ids };
}

export async function requireSiOwner(): Promise<NextResponse | null> {
  const user = await requireValidatedUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const allow = parseOwnerAllowlist(process.env.SELF_IMPROVEMENT_OWNER_USER_IDS);
  if (!allow.ok) {
    // Log the reason only. Never log the configured value or any user id.
    console.error(`SELF_IMPROVEMENT_OWNER_USER_IDS rejected: ${allow.reason}`);
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const uid = typeof user.id === 'string' ? user.id.toLowerCase() : '';
  if (!uid || !allow.ids.includes(uid)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  return null;
}
