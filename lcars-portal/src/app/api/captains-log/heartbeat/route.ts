import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';

/**
 * captains_log's real write (an upsert into captains_log_entries) happens
 * directly from the browser via the anon-key Supabase client — see
 * app/(app)/captains-log/page.tsx's handleSubmit(). There is no server API
 * route for that write itself, and there doesn't need to be one; this
 * route is not it.
 *
 * domain_heartbeats' RLS only allows service_role writes (policy
 * `domain_heartbeats_service_write`), so the browser can never record its
 * own heartbeat directly — same reason /api/physical-readiness/complete
 * exists for core_events (see core-events.ts's module docstring). This
 * route is the RLS-safe side channel the client calls, and only calls,
 * after its own upsert has already succeeded.
 *
 * domain_key is intentionally hardcoded rather than taken from the request
 * body — this route exists to record exactly one domain's heartbeat, not
 * as a generic heartbeat-injection endpoint.
 */
export async function POST() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const result = await recordHeartbeatServerSide({ domainKey: 'captains_log' });
  return NextResponse.json({ ok: result.ok, error: result.error });
}
