import { NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';

// Small, morning-compression summary (spec §15/§20/§37) — used by both the
// HQ Evolution Discover tab and Captain's Chair's one-line signal. Never
// expands into the full findings/opportunities payload; see
// scripts/self_improvement/dashboard.py's /api/evolution-summary.
export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const res = await fetch(`${selfImprovementApiUrl()}/api/evolution-summary`, {
      headers: selfImprovementHeaders(),
      cache: 'no-store',
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
