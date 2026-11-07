import { NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSiOwner } from '@/lib/selfImprovementAuth';

// Small, morning-compression summary (spec §15/§20/§37) — used by both the
// HQ Evolution Discover tab and Captain's Chair's one-line signal. Never
// expands into the full findings/opportunities payload; see
// scripts/self_improvement/dashboard.py's /api/evolution-summary.
export async function GET() {
  const denied = await requireSiOwner();
  if (denied) return denied;
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
