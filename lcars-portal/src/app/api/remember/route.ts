// Mission 3 (Capture, Remember & Follow-Through) — first live consumer
// bridge for context_service.py's GET /remember (the Remember capability:
// resurfacing personal_tasks via the Personal Task Attention Adapter, plus
// unresolved captured_items, both capacity-aware). Same pattern as
// api/number-one-brief: this Next.js app may run on Vercel's Node.js
// serverless runtime, which has no python3 available, so this fetches the
// context_service.py HTTP bridge rather than shelling out to a local
// interpreter or re-deriving Remember's logic here.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const resp = await fetch(`${contextServiceUrl()}/remember`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const remember = await resp.json();
    if (!resp.ok || (remember && typeof remember === 'object' && 'error' in remember)) {
      return NextResponse.json(
        { error: 'Remember fetch failed', detail: String(remember?.detail ?? remember?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(remember);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Context Assembly service', detail: String(err) },
      { status: 502 },
    );
  }
}
