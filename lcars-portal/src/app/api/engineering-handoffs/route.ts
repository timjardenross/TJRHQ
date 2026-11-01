import { NextRequest, NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';

// Proxies scripts/self_improvement/dashboard.py's /api/engineering-handoffs,
// which itself just surfaces core/coordination/engineering_handoff_reader.py's
// already-computed handoff status (title, priority, live PR URL, batch
// status) — no new logic here, just the same auth/proxy pattern every other
// self-improvement route in this directory already uses.
//
// Forwards `include_completed` (2026-09-07: the Captain wants the full
// 5-stage lifecycle visible, not just outstanding work) straight through.
export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const includeCompleted = request.nextUrl.searchParams.get('include_completed') ?? '';
  try {
    const res = await fetch(
      `${selfImprovementApiUrl()}/api/engineering-handoffs?include_completed=${encodeURIComponent(includeCompleted)}`,
      { headers: selfImprovementHeaders(), cache: 'no-store' }
    );
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    if (res.ok && Array.isArray(body?.handoffs)) {
      // Publish the queue as a controlled field at the portal boundary. Older
      // VM payloads may omit it, so the compatibility mapping uses only the
      // canonical engineering status, never free-text next_action content.
      body.handoffs = body.handoffs.map((handoff: Record<string, any>) => {
        const explicit = handoff.handoff_queue ?? handoff.metadata?.handoff_queue;
        const status = handoff.metadata?.engineering_status;
        const handoff_queue = explicit === 'review' || explicit === 'delivery' || explicit === 'blocked'
          ? explicit
          : status === 'Pending Triage' ? 'blocked'
          : status === 'Awaiting Review' ? 'review'
          : 'delivery';
        return { ...handoff, handoff_queue };
      });
    }
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
