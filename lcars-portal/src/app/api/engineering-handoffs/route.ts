import { NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';

// Proxies scripts/self_improvement/dashboard.py's /api/engineering-handoffs,
// which itself just surfaces core/coordination/engineering_handoff_reader.py's
// already-computed handoff status (title, priority, live PR URL, batch
// status) — no new logic here, just the same auth/proxy pattern every other
// self-improvement route in this directory already uses.
export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const res = await fetch(`${selfImprovementApiUrl()}/api/engineering-handoffs`, {
      headers: selfImprovementHeaders(),
      cache: 'no-store',
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
