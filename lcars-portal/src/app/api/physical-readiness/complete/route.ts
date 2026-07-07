import { NextRequest, NextResponse } from 'next/server';
import { publishEventServerSide } from '@/lib/core-events';

/**
 * core_events has RLS enabled with zero anon/authenticated policies
 * (migration 0055: "service_role bypasses; no public read/write"). This
 * route exists purely so the workout runner (browser, anon key) can reach
 * a server context that publishEventServerSide() can use to build a
 * service-role client — see lib/core-events.ts / lib/supabase-service-role.ts.
 */
export async function POST(request: NextRequest) {
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

  return NextResponse.json({ ok: result.ok, error: result.error });
}
