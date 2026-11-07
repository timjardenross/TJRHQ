import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

/**
 * SEC-01 Option B: single-owner gate for self-improvement and engineering-handoff routes.
 * requireSession() verifies the Supabase user server-side (getUser). The user id must
 * equal SELF_IMPROVEMENT_OWNER_USER_ID (server-only env, not NEXT_PUBLIC_).
 * Fails closed: owner unset or empty => 403 for every user.
 * Returns null when allowed, otherwise the response to return immediately.
 */
export async function requireSiOwner(): Promise<NextResponse | null> {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const owner = process.env.SELF_IMPROVEMENT_OWNER_USER_ID;
  const uid = session.user?.id;
  if (!owner || !uid || uid !== owner) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  return null;
}
