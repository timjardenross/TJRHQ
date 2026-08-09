import { NextRequest, NextResponse } from 'next/server';
import { publishEventServerSide } from '@/lib/core-events';
import { requireSession } from '@/lib/supabase-server';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';

/**
 * core_events has RLS enabled with zero anon/authenticated policies
 * (migration 0055: "service_role bypasses; no public read/write"). This
 * route exists purely so the workout runner (browser, anon key) can reach
 * a server context that publishEventServerSide() can use to build a
 * service-role client — see lib/core-events.ts / lib/supabase-service-role.ts.
 */
export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let body: { sessionType?: string; metrics?: Record<string, unknown> } = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  if (!body.sessionType || !body.metrics) {
    return NextResponse.json({ error: 'sessionType and metrics required' }, { status: 400 });
  }

  const result = await publishEventServerSide({
    eventType: 'physical_readiness.workout_completed',
    domain: 'physical-readiness',
    source: 'lcars-portal/physical-readiness',
    metrics: body.metrics,
  });

  // The Captain's actual physical_readiness_checkins / physical_workout_sessions
  // writes already happened client-side before this route was ever called
  // (see the session page's handleSubmitCompletion) — this route is the
  // RLS-safe notification step. Heartbeat only fires once that notification
  // itself is confirmed written, not before, and not if it failed.
  if (result.ok) {
    await recordHeartbeatServerSide({ domainKey: 'physical_readiness', detail: `sessionType=${body.sessionType}` });
  }

  return NextResponse.json({ ok: result.ok, error: result.error });
}
