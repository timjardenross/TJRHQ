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
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
