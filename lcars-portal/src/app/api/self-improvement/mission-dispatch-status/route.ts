import { NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSiOwner } from '@/lib/selfImprovementAuth';

export async function GET() {
  const denied = await requireSiOwner();
  if (denied) return denied;
  try {
    const res = await fetch(`${selfImprovementApiUrl()}/api/mission-dispatch-status`, {
      headers: selfImprovementHeaders(),
      cache: 'no-store',
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
