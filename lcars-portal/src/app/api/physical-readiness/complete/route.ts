import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { publishEvent } from '@/lib/core-events';

/**
 * core_events has RLS enabled with zero policies (migration 0055: "service_role
 * bypasses; no public read/write"). The browser anon client and the SSR
 * authenticated-cookie client both get denied — publishEvent() swallows that
 * silently by design, so the workout-completion event never lands if called
 * client-side. This route is server-only so it can use the service-role key.
 */
function getServiceRoleSupabase() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, key);
}

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

  const supabase = getServiceRoleSupabase();
  await publishEvent(supabase, {
    eventType: 'physical_readiness.workout_completed',
    domain: 'physical-readiness',
    source: 'lcars-portal/physical-readiness',
    metrics: body.metrics,
  });

  return NextResponse.json({ ok: true });
}
