import { NextRequest, NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const payload = await req.json();
    const res = await fetch(`${selfImprovementApiUrl()}/api/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...selfImprovementHeaders() },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
