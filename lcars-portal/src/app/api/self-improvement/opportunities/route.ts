import { NextRequest, NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSiOwner } from '@/lib/selfImprovementAuth';

export async function GET(request: NextRequest) {
  const denied = await requireSiOwner();
  if (denied) return denied;
  const { searchParams } = new URL(request.url);
  const state = searchParams.get('state');
  const qs = state ? `?state=${encodeURIComponent(state)}` : '';
  try {
    const res = await fetch(`${selfImprovementApiUrl()}/api/opportunities${qs}`, {
      headers: selfImprovementHeaders(),
      cache: 'no-store',
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
