// USS-TJR-MSN-0054 follow-on (2026-09-08) — first live consumer bridge for
// core/coordination/number_one.py's get_health_adjusted_queue(), same
// pattern as api/number-one-brief: this Next.js app may run on Vercel's
// Node.js serverless runtime, which has no python3 available, so this
// fetches the context_service.py HTTP bridge (GET /queue/health-adjusted)
// rather than shelling out to a local interpreter.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const resp = await fetch(`${contextServiceUrl()}/queue/health-adjusted`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const queue = await resp.json();
    if (!resp.ok || (queue && typeof queue === 'object' && 'error' in queue)) {
      return NextResponse.json(
        { error: 'Health-adjusted queue failed', detail: String(queue?.detail ?? queue?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(queue);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Context Assembly service', detail: String(err) },
      { status: 502 },
    );
  }
}
